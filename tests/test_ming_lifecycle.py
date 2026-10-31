import os
import sys
from unittest.mock import Mock

import pytest

from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest, MingOptions, UserError
from pacttsclone.ming_engine import generation_arguments
from pacttsclone.ming_install import manifests, receipt_valid, safe_destination
from pacttsclone.ming_process import MingProcessEngine


def test_manifest_includes_verified_onnx_and_pins_all_urls():
    source, model = manifests()
    assert len(source["revision"]) == len(model["revision"]) == 40
    assert any(e["name"] == "campplus.onnx" for e in model["files"])
    for manifest in (source, model):
        for entry in manifest["files"]:
            assert manifest["revision"] in entry["url"]
            assert entry["algorithm"] in {"sha1", "sha256"}
            assert entry["size"] >= 0


@pytest.mark.parametrize("name", ["../voice.mp3", "/tmp/voice", "C:\\voice", "folder\\file"])
def test_install_rejects_path_escape(tmp_path, name):
    with pytest.raises(ValueError, match="Unsafe"):
        safe_destination(tmp_path, name)


def test_install_rejects_symlinked_destination(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "source").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe"):
        safe_destination(root, "source/voice.mp3")
    assert not receipt_valid(root)


@pytest.mark.parametrize(
    "task,control",
    [
        ("EMOTION", "emotion"),
        ("BASIC", "speed"),
        ("DIALECT", "dialect"),
        ("IP", "ip"),
        ("VOICE_DESIGN", "style"),
    ],
)
def test_task_contract_does_not_mix_reference_transcripts(task, control):
    req = GenerationRequest(text="Hello", ming=MingOptions(task=task, instruction="Warm voice"))
    args = generation_arguments("ref.wav", req)
    assert control in args["controls"]
    assert "prompt_text" not in args
    assert bool(args.get("use_zero_spk_emb")) == (task in {"IP", "VOICE_DESIGN"})


def test_multilingual_uses_explicit_upstream_mode():
    req = GenerationRequest(text="Bonjour", ref_text="Reference", ming=MingOptions(language="fr"))
    assert generation_arguments("ref.wav", req)["task"] == "MULTILINGUAL"


def test_isolated_bridge_reuses_real_child_and_normalizes_audio(tmp_path):
    # Actual process/pipe/audio transport with a simulated model, not CUDA inference.
    root = tmp_path / "engines" / "ming-3"
    python = root / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    script = tmp_path / "fake_ming.py"
    script.write_text("""import sys,json,wave,struct
print('@@PACTTS_MING@@'+json.dumps({'ok':True,'ready':True}),flush=True)
for line in sys.stdin:
    value=json.loads(line)
    with wave.open(value['output'],'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(struct.pack('<hh',3276,-3276))
    print('@@PACTTS_MING@@'+json.dumps({'ok':True}),flush=True)
""")
    engine = MingProcessEngine(Settings(data_dir=tmp_path, engine_id="ming-3", model="fixture"))
    engine._command = lambda python, root: [sys.executable, "-u", str(script)]
    observer = Mock()
    engine.residency_observer = observer
    req = GenerationRequest(text="Hello", ref_text="Reference", language="en")
    try:
        first = engine.synthesize(str(tmp_path / "reference.wav"), req)
        pid = engine.process.pid
        second = engine.synthesize(str(tmp_path / "reference.wav"), req)
        assert engine.process.pid == pid
        assert first.sample_rate == second.sample_rate == 24000
        assert first.samples.shape == (2,)
        assert not list(tmp_path.glob("ming-*"))
    finally:
        process = engine.process
        engine._close()
        assert process.poll() is not None


def test_invalid_voice_design_fails_before_runtime():
    req = GenerationRequest(text="Hello", ming=MingOptions(task="VOICE_DESIGN"))
    with pytest.raises(UserError, match="description"):
        generation_arguments("ref.wav", req)


def test_failed_activation_preserves_previous_engine(tmp_path, monkeypatch, engine):
    from fastapi.testclient import TestClient

    from pacttsclone.app import create_app

    app = create_app(Settings(data_dir=tmp_path), engine)
    monkeypatch.setattr("pacttsclone.ming_lifecycle.receipt_valid", lambda root: True)
    monkeypatch.setattr(
        "pacttsclone.ming_lifecycle.subprocess.run",
        lambda *a, **kw: type(
            "Result",
            (),
            {"returncode": 1, "stdout": '@@PACTTS_MING@@{"ok":false,"error":"Unsupported GPU"}'},
        )(),
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        result = client.post("/api/engines/ming-3/activate", headers={"X-PacTTS-Token": token})
        assert result.status_code == 422
        assert app.state.service.settings.engine_id == "omnivoice"
        assert app.state.runtime_setup.state.get("active_engine", "omnivoice") == "omnivoice"


def test_ming_settings_do_not_overwrite_omnivoice_defaults(tmp_path, mp3, engine):
    from dataclasses import replace

    from pacttsclone.domain import GenerationSettings
    from pacttsclone.service import GenerationService
    from pacttsclone.voices import Voices

    service = GenerationService(Settings(data_dir=tmp_path), engine)
    voices = Voices(service)
    try:
        voice = {"id": "test-voice", "generation_settings": {}}
        service.store.put("voice", voice["id"], voice)
        voices.set_generation_settings(voice["id"], GenerationSettings(speed=1.2))
        service.settings = replace(service.settings, engine_id="ming-3")
        voices.set_generation_settings(
            voice["id"], GenerationSettings(ming=MingOptions(task="EMOTION", emotion="happy"))
        )
        saved = service.store.get("voice", voice["id"])
        assert saved["generation_settings"]["speed"] == 1.2
        assert saved["engine_generation_settings"]["ming-3"]["ming"]["emotion"] == "happy"
    finally:
        service.close()


def test_worker_reset_terminates_resident_ming_child(tmp_path, mp3):
    import shutil
    import threading
    import time

    import psutil

    from pacttsclone.models import AppConfig
    from pacttsclone.worker import ProcessRunner
    from tests.ming_fake import factory

    python = (
        tmp_path
        / "engines"
        / "ming-3"
        / "runtime"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    python.parent.mkdir(parents=True)
    python.touch()
    script = tmp_path / "fake_ming.py"
    script.write_text("""import sys,json,wave,struct
print('@@PACTTS_MING@@'+json.dumps({'ok':True,'ready':True}),flush=True)
for line in sys.stdin:
    value=json.loads(line)
    with wave.open(value['output'],'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(struct.pack('<'+'h'*24000,*([3276,-3276]*12000)))
    print('@@PACTTS_MING@@'+json.dumps({'ok':True}),flush=True)
""")
    workspace = tmp_path / "job"
    workspace.mkdir()
    shutil.copyfile(mp3, workspace / "reference.mp3")
    runner = ProcessRunner(
        Settings(data_dir=tmp_path, engine_id="ming-3", model="fixture"), factory
    )
    try:
        result = runner.execute(
            {
                "workspace": str(workspace),
                "output": str(tmp_path / "output.mp3"),
                "request": GenerationRequest(
                    text="Hello", ref_text="Reference", language="en"
                ).model_dump(),
            },
            AppConfig().model_dump(),
            lambda event: None,
            threading.Event(),
        )
        assert result["ok"]
        pid = runner.model_state["runtime_pid"]

        def alive(pid):
            if os.name == "nt":
                return psutil.pid_exists(pid)
            try:
                os.kill(pid, 0)
                return True
            except ProcessLookupError:
                return False

        assert alive(pid)
        runner.reset()
        deadline = time.monotonic() + 5
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not alive(pid)
    finally:
        runner.reset(hard=True)


def test_successful_activation_is_persisted_and_restored(tmp_path, monkeypatch, engine):
    from fastapi.testclient import TestClient

    from pacttsclone.app import create_app

    monkeypatch.setattr("pacttsclone.ming_lifecycle.receipt_valid", lambda root: True)
    monkeypatch.setattr(
        "pacttsclone.ming_lifecycle.subprocess.run",
        lambda *a, **kw: type(
            "Result", (), {"returncode": 0, "stdout": '@@PACTTS_MING@@{"ok":true,"bf16":true}'}
        )(),
    )
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        result = client.post("/api/engines/ming-3/activate", headers={"X-PacTTS-Token": token})
        assert result.status_code == 200
        assert app.state.service.settings.engine_id == "ming-3"
        assert client.get("/api/state").json()["active_engine"] == "ming-3"
    restarted = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(restarted, base_url="http://127.0.0.1") as client:
        assert client.get("/api/state").json()["active_engine"] == "ming-3"
        assert client.get("/api/setup").json()["ready"]


def test_ming_uninstall_keeps_personal_files_and_rejects_busy_queue(tmp_path, engine):
    from pacttsclone.app import create_app
    from pacttsclone.domain import BusyError
    from pacttsclone.ming_lifecycle import MingLifecycle

    app = create_app(Settings(data_dir=tmp_path), engine)
    manager = MingLifecycle(app.state.runtime_setup)
    manager.root.mkdir(parents=True)
    (manager.root / "model.bin").write_bytes(b"owned")
    reference = tmp_path / "voices" / "personal.mp3"
    reference.write_bytes(b"keep")
    app.state.service.setup_busy = True
    with pytest.raises(BusyError):
        manager.uninstall()
    app.state.service.setup_busy = False
    manager.uninstall()
    assert not manager.root.exists()
    assert reference.read_bytes() == b"keep"
    app.state.service.close()


@pytest.mark.parametrize(
    "available,capability,message", [(False, (8, 0), "CUDA"), (True, (7, 5), "BF16")]
)
def test_standalone_preflight_reports_hardware_failure(
    monkeypatch, capsys, available, capability, message
):
    from types import SimpleNamespace

    from pacttsclone import ming_runtime_worker

    cuda = SimpleNamespace(
        is_available=lambda: available,
        get_device_capability=lambda: capability,
        is_bf16_supported=lambda: True,
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda))
    monkeypatch.setattr(
        sys, "argv", ["worker", "--source", "/unused", "--model", "/unused", "--preflight"]
    )
    with pytest.raises(SystemExit):
        ming_runtime_worker.main()
    assert message in capsys.readouterr().out
