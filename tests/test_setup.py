import hashlib
import io
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pacttsclone import model_setup
from pacttsclone.app import create_app
from pacttsclone.config import Settings


def test_verified_cache_does_not_download(tmp_path, monkeypatch):
    path = tmp_path / "model"
    path.write_bytes(b"complete weights")
    entry = dict(
        size=path.stat().st_size,
        hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        algorithm="sha256",
        url="https://unused",
    )
    monkeypatch.setattr(
        model_setup.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("Cached file was downloaded again"),
    )
    phases = []
    assert (
        model_setup.fetch_file(entry, path, lambda n, phase: phases.append(phase))
        == "verified cache"
    )
    assert phases == ["verifying cache"]


@pytest.mark.parametrize("range_supported", [True, False])
def test_partial_download_resumes_or_restarts_safely(tmp_path, monkeypatch, range_supported):
    data = b"0123456789"
    path = tmp_path / "model"
    path.with_name("model.partial").write_bytes(data[:4])
    requests = []

    class Response(io.BytesIO):
        status = 206 if range_supported else 200
        headers = {"Content-Range": "bytes 4-9/10"} if range_supported else {}

    def open_url(request, timeout):
        requests.append(request.get_header("Range"))
        return Response(data[4:] if range_supported else data)

    monkeypatch.setattr(model_setup.urllib.request, "urlopen", open_url)
    entry = dict(
        size=len(data),
        hash=hashlib.sha256(data).hexdigest(),
        algorithm="sha256",
        url="https://example.test/model",
    )
    assert model_setup.fetch_file(entry, path) == "downloaded and verified"
    assert requests == ["bytes=4-"]
    assert path.read_bytes() == data
    assert not path.with_name("model.partial").exists()


def test_corrupt_download_is_never_activated(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        status, headers = 200, {}

    monkeypatch.setattr(model_setup.urllib.request, "urlopen", lambda *a, **k: Response(b"bad"))
    path = tmp_path / "model"
    entry = dict(
        size=3,
        hash=hashlib.sha256(b"yes").hexdigest(),
        algorithm="sha256",
        url="https://example.test/model",
    )
    with pytest.raises(ValueError, match="checksum"):
        model_setup.fetch_file(entry, path)
    assert not path.exists()
    assert not path.with_name("model.partial").exists()


def test_git_blob_hash_verification(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(b"{}")
    checksum = hashlib.sha1(b"blob 2\0{}").hexdigest()
    assert model_setup.verify_file(path, 2, checksum, "sha1")
    assert not model_setup.verify_file(path, 2, "0" * 40, "sha1")


def test_cached_plan_rejects_path_escape(tmp_path):
    (tmp_path / "owner--model.json").write_text(
        json.dumps(
            dict(
                repo="owner/model",
                revision="a" * 40,
                files=[dict(name="../escape", algorithm="sha256", hash="a" * 64, size=1)],
            )
        )
    )
    with pytest.raises(ValueError, match="Unsafe"):
        model_setup.download_models(tmp_path, ["owner/model"], tmp_path / "cache")


def test_first_setup_blocks_generation_and_survives_interrupt(tmp_path, monkeypatch):
    monkeypatch.setattr("pacttsclone.setup_runtime.dependencies_available", lambda: False)
    app = create_app(Settings(data_dir=tmp_path / "data"))
    setup = app.state.runtime_setup
    monkeypatch.setattr(
        setup,
        "_commands",
        lambda device: [
            (
                "pytorch",
                [
                    sys.executable,
                    "-c",
                    'import time; print("installing", flush=True); time.sleep(30)',
                ],
            )
        ],
    )
    with TestClient(app, base_url="http://127.0.0.1:7860") as client:
        headers = {"X-PacTTS-Token": client.get("/api/session").json()["token"]}
        assert not client.get("/api/setup").json()["ready"]
        response = client.post(
            "/api/jobs",
            files={"reference": ("x.mp3", b"not audio", "audio/mpeg")},
            data={"text": "Hello", "ref_text": "Hi"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "first-run" in response.json()["detail"]
        assert app.state.service.store.all("job") == []
        assert (
            client.post("/api/setup/start", json={"device": "bad"}, headers=headers).status_code
            == 422
        )
        assert client.post("/api/setup/start", json={"device": "cpu"}).status_code == 403
        assert (
            client.post("/api/setup/start", json={"device": "cpu"}, headers=headers).status_code
            == 200
        )
        deadline = time.monotonic() + 5
        while not setup.snapshot()["lines"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert any("installing" in line for line in setup.snapshot()["lines"])
        assert (
            client.post("/api/setup/start", json={"device": "cpu"}, headers=headers).status_code
            == 409
        )
        client.post("/api/setup/cancel", headers=headers)
        setup.thread.join(5)
        assert not setup.thread.is_alive()
        assert setup.snapshot()["status"] == "cancelled"
        assert not setup.snapshot()["ready"]
        assert not app.state.service.setup_busy
        assert "installing" in client.get("/api/setup/log").text
        # Logs carry per-line timestamps and survive a Python process restart.
        original_lines = setup.snapshot()["lines"]
        assert any(line.startswith("[20") and "installing" in line for line in original_lines)
        from pacttsclone.setup_runtime import RuntimeSetup

        restored = RuntimeSetup(app.state.service)
        assert any("installing" in line for line in restored.snapshot()["lines"])
        monkeypatch.setattr(
            setup,
            "_commands",
            lambda device: [("verify", [sys.executable, "-c", "raise SystemExit(3)"])],
        )
        client.post("/api/setup/start", json={"device": "cpu"}, headers=headers)
        setup.thread.join(5)
        assert setup.snapshot()["status"] == "failed"
        assert "exit 3" in setup.snapshot()["error"]
        assert not setup.snapshot()["ready"]


def test_verified_model_paths_are_used_offline_after_restart(tmp_path, engine):
    data = tmp_path / "data"
    app = create_app(Settings(data_dir=data), engine)
    setup = app.state.runtime_setup
    paths = [data / "models" / "voice", data / "models" / "asr"]
    files = []
    for directory in paths:
        directory.mkdir(parents=True)
        file = directory / "model.safetensors"
        file.write_bytes(b"verified by download child")
        files.append(dict(path=str(file), size=file.stat().st_size))
    setup.update(
        status="succeeded",
        models=dict(
            paths=dict(zip(["owner/voice", "owner/asr"], map(str, paths), strict=True)), files=files
        ),
    )
    app.state.studio.close()
    second = create_app(Settings(data_dir=data), engine)
    try:
        assert second.state.service.settings.offline
        assert second.state.service.settings.model == str(paths[0])
        assert second.state.service.settings.asr_model == str(paths[1])
        assert second.state.service.runner.settings == second.state.service.settings
        Path(files[0]["path"]).unlink()
        assert not second.state.runtime_setup._models_present()
    finally:
        second.state.studio.close()


def test_model_setup_reuses_existing_hf_snapshot_and_reports_real_bytes(tmp_path, monkeypatch):
    root, cache = tmp_path / "models", tmp_path / "hf"
    revision, payload = "a" * 40, b"verified weights"
    entry = dict(
        name="model.safetensors",
        size=len(payload),
        hash=hashlib.sha256(payload).hexdigest(),
        algorithm="sha256",
        url="unused",
    )
    snapshot = cache / "models--owner--voice" / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (snapshot / entry["name"]).write_bytes(payload)
    monkeypatch.setattr(
        model_setup,
        "make_plan",
        lambda repo: dict(repo=repo, revision=revision, files=[entry.copy()]),
    )
    monkeypatch.setattr(
        model_setup.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("Existing exact HF snapshot was downloaded again"),
    )
    progress = []
    monkeypatch.setattr(model_setup, "emit", lambda **values: progress.append(values))
    result = model_setup.download_models(root, ["owner/voice"], cache)
    assert result["reused_files"] == 1
    assert Path(result["files"][0]["path"]).read_bytes() == payload
    assert progress[-1]["download"]["completed_bytes"] == len(payload)
    assert progress[-1]["download"]["total_bytes"] == len(payload)
    assert progress[-1]["download"]["cache_status"] == "verified cache"
    # A retry must use the persisted revision plan and reverify without metadata HTTP.
    monkeypatch.setattr(
        model_setup, "make_plan", lambda repo: pytest.fail("Revision resolved again")
    )
    assert model_setup.download_models(root, ["owner/voice"], cache)["reused_files"] == 1


def test_dependency_constraints_use_relative_path_in_directory_with_spaces(
    tmp_path, engine, monkeypatch
):
    app = create_app(Settings(data_dir=tmp_path / "folder with spaces"), engine)
    setup = app.state.runtime_setup
    try:
        commands = setup._commands("cpu")
        for _stage, command in commands[:2]:
            assert command[command.index("--constraint") + 1] == "base-constraints.txt"
        assert (setup.root / "base-constraints.txt").is_file()
    finally:
        app.state.studio.close()
