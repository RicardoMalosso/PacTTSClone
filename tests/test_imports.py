import hashlib
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pacttsclone import model_cache, model_setup
from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.data_import import import_personal_data
from pacttsclone.domain import UserError
from pacttsclone.models import AppConfig, ChannelConfig
from tests.conftest import wait_job


def weight_entry(data, name="model.safetensors"):
    return dict(
        name=name,
        size=len(data),
        hash=hashlib.sha256(data).hexdigest(),
        algorithm="sha256",
        url="unused",
    )


def test_weight_scan_is_bounded_and_ignores_configs(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "MIN_WEIGHT_BYTES", 4)
    (tmp_path / "weights.safetensors").write_bytes(b"weights")
    (tmp_path / "config.json").write_bytes(b"not imported even if large")
    (tmp_path / "tiny.safetensors").write_bytes(b"a")
    blobs = tmp_path / "blobs"
    blobs.mkdir()
    (blobs / ("a" * 64)).write_bytes(b"blob weights")
    found = model_cache.scan_weights([str(tmp_path)])
    assert len(found["files"]) == 2
    assert all(not f["path"].endswith("config.json") for f in found["files"])
    assert model_cache.scan_weights([str(tmp_path)], max_files=0)["limited"]
    stop = threading.Event()
    stop.set()
    assert model_cache.scan_weights([str(tmp_path)], stop=stop)["status"] == "cancelled"


def test_import_only_validates_weights_and_never_downloads_configs(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "MIN_WEIGHT_BYTES", 1)
    source, destination = tmp_path / "old/data/cache", tmp_path / "new/models"
    source.mkdir(parents=True)
    weights = b"current pinned weight bytes"
    (source / "model.safetensors").write_bytes(weights)
    (source / "config.json").write_text("old incompatible config")
    entries = [
        weight_entry(weights),
        dict(
            name="config.json",
            size=2,
            hash=hashlib.sha1(b"blob 2\0{}").hexdigest(),
            algorithm="sha1",
            url="unused",
        ),
    ]
    monkeypatch.setattr(
        model_setup,
        "make_plan",
        lambda repo: dict(repo=repo, revision="a" * 40, files=[dict(e) for e in entries]),
    )
    monkeypatch.setattr(
        model_setup.urllib.request,
        "urlopen",
        lambda *a, **kw: pytest.fail("Import must not download weights or config"),
    )
    result = model_setup.download_models(
        destination,
        ["owner/model"],
        tmp_path / "empty-cache",
        [str(source)],
        move_weights=True,
        import_only=True,
    )
    imported = destination / "owner--model" / ("a" * 40)
    assert (imported / "model.safetensors").read_bytes() == weights
    assert not (imported / "config.json").exists()
    assert not (source / "model.safetensors").exists()
    assert (source / "config.json").read_text() == "old incompatible config"
    assert result["weight_import"][0]["moved"]
    assert result["files"][0]["hash"] == hashlib.sha256(weights).hexdigest()
    assert (destination / "weight-import-receipt.json").is_file()


def test_outdated_weights_are_not_reused_or_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "MIN_WEIGHT_BYTES", 1)
    source = tmp_path / "old"
    source.mkdir()
    old = source / "model.safetensors"
    old.write_bytes(b"outdated")
    monkeypatch.setattr(
        model_setup,
        "make_plan",
        lambda repo: dict(repo=repo, revision="b" * 40, files=[weight_entry(b"new data")]),
    )
    result = model_setup.download_models(
        tmp_path / "new",
        ["owner/model"],
        tmp_path / "cache",
        [str(source)],
        move_weights=True,
        import_only=True,
    )
    assert result["missing_weights"] and not result["files"]
    assert old.read_bytes() == b"outdated"
    assert not result["weight_import"]


def test_automatic_shared_cache_is_copied_not_moved(tmp_path, monkeypatch):
    monkeypatch.setattr(model_cache, "MIN_WEIGHT_BYTES", 1)
    cache = tmp_path / "shared"
    cache.mkdir()
    payload = b"weights"
    blob = cache / ("a" * 64)
    blob.write_bytes(payload)
    monkeypatch.setattr(
        model_setup,
        "make_plan",
        lambda repo: dict(repo=repo, revision="a" * 40, files=[weight_entry(payload)]),
    )
    selected = tmp_path / "old"
    selected.mkdir()
    result = model_setup.download_models(
        tmp_path / "new",
        ["owner/model"],
        cache,
        [str(selected)],
        move_weights=True,
        import_only=True,
    )
    assert result["reused_files"] == 1 and blob.exists()
    assert not result["weight_import"]


@pytest.fixture
def old_and_new(tmp_path, engine, mp3):
    old = create_app(Settings(data_dir=tmp_path / "old/data"), engine)
    new = create_app(Settings(data_dir=tmp_path / "new/data"), engine)
    studio = old.state.studio
    with mp3.open("rb") as reference:
        voice = studio.voices.create(
            reference, "Personal voice", "reference.mp3", "Exact transcript"
        )
    studio.save_channel(ChannelConfig(name="imported", commands={"!voice": voice["id"]}))
    studio.configure(AppConfig(device="cpu", max_queue=7))
    from pacttsclone.domain import GenerationRequest

    job = studio.voices.generate(voice["id"], GenerationRequest(text="Personal recording"))
    wait_job(studio.service, job["id"])
    try:
        yield old, new, voice, job
    finally:
        old.state.studio.close()
        new.state.studio.close()


def test_personal_import_preserves_assets_maps_ids_and_is_idempotent(old_and_new):
    old, new, voice, job = old_and_new
    target = new.state.studio
    source = old.state.service.settings.data_dir
    before = old.state.service.output_path(job["id"]).read_bytes()
    result = import_personal_data(
        target,
        str(source.parent),
        ["voices", "outputs", "config"],
        False,
        threading.Event(),
        lambda _: None,
    )
    assert result["voices"] == result["outputs"] == result["channels"] == 1
    assert Path(result["backup"]).is_file()
    imported_voice = target.store.all("voice")[0]
    assert imported_voice["id"] != voice["id"]
    assert imported_voice["transcript"] == "Exact transcript"
    imported_job = target.service.history()[0]
    assert target.service.output_path(imported_job["id"]).read_bytes() == before
    assert old.state.service.output_path(job["id"]).read_bytes() == before
    assert imported_job["output_url"] == f"/api/jobs/{imported_job['id']}/audio"
    assert imported_job["workspace"] == ""
    channel = target.store.get("channel", "imported")
    assert not channel["enabled"] and channel["paused"]
    assert channel["commands"]["!voice"] == imported_voice["id"]
    assert not target.store.all("playback")
    assert target.service.config.max_queue == 30  # Replacement was not requested.
    second = import_personal_data(
        target,
        str(source),
        ["voices", "outputs", "config"],
        False,
        threading.Event(),
        lambda _: None,
    )
    assert second["voices"] == second["outputs"] == second["channels"] == 0
    assert len(target.service.history()) == 1
    assert len(target.store.all("voice")) == 1


def test_config_replacement_is_explicit_and_existing_channel_retained(old_and_new):
    old, new, _, _ = old_and_new
    target = new.state.studio
    target.save_channel(ChannelConfig(name="imported", delay_seconds=9))
    result = import_personal_data(
        target,
        str(old.state.service.settings.data_dir),
        ["config"],
        True,
        threading.Event(),
        lambda _: None,
    )
    assert target.service.config.max_queue == 7
    assert target.store.get("channel", "imported")["delay_seconds"] == 9
    assert result["warnings"]
    assert not target.store.all("voice") and not target.service.history()


def test_cancelled_personal_import_keeps_source_and_destination_unchanged(old_and_new):
    old, new, _, job = old_and_new
    stop = threading.Event()
    stop.set()
    with pytest.raises(InterruptedError):
        import_personal_data(
            new.state.studio,
            str(old.state.service.settings.data_dir),
            ["voices", "outputs"],
            False,
            stop,
            lambda _: None,
        )
    assert not new.state.service.history()
    assert not new.state.service.store.all("voice")
    assert old.state.service.output_path(job["id"]).is_file()


def test_import_routes_require_local_owner_and_idle_queue(old_and_new):
    old, new, _, _ = old_and_new
    studio = new.state.studio
    with TestClient(new, base_url="http://127.0.0.1:7860") as client:
        token = client.get("/api/session").json()["token"]
        assert client.post("/api/import/start", json={"category": "personal"}).status_code == 403
        response = client.post(
            "/api/import/start",
            headers={"X-PacTTS-Token": token},
            json={
                "category": "personal",
                "source": str(old.state.service.settings.data_dir),
                "sections": ["voices"],
                "replace_config": False,
            },
        )
        assert response.status_code == 200
        new.state.runtime_setup.import_thread.join(5)
        assert new.state.runtime_setup.import_status["status"] == "succeeded"
        assert len(studio.store.all("voice")) == 1
        tunnel = new.state.tunnel
        assert not tunnel.permitted(("admin", None), "/api/import/start", "POST")
        assert not tunnel.permitted(("admin", None), "/api/setup/weights/scan", "POST")


def test_local_path_validation_rejects_network_and_relative_folders():
    for value in ["relative", "//server/share", "\\\\server\\share"]:
        with pytest.raises(UserError):
            model_cache.validate_roots([value])


def test_personal_import_rolls_back_staged_assets_on_destination_conflict(old_and_new):
    import uuid

    old, new, _, job = old_and_new
    studio = new.state.studio
    old_identity = old.state.service.installation_id
    namespace = uuid.UUID(new.state.service.installation_id)
    new_job = uuid.uuid5(namespace, f"import:{old_identity}:job:{job['id']}").hex
    conflict = new.state.service.output_path(new_job)
    conflict.write_bytes(b"current audio must survive")
    with pytest.raises(UserError, match="already exists"):
        import_personal_data(
            studio,
            str(old.state.service.settings.data_dir),
            ["voices", "outputs"],
            False,
            threading.Event(),
            lambda _: None,
        )
    assert conflict.read_bytes() == b"current audio must survive"
    assert not studio.store.all("voice")
    assert not list(studio.voices.root.iterdir())
    assert not studio.service.history()
    assert old.state.service.output_path(job["id"]).is_file()
