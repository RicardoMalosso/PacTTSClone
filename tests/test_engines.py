import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pacttsclone.domain import BusyError, UserError
from pacttsclone.engines import EngineManager


def manager(tmp_path):
    service = SimpleNamespace(
        settings=SimpleNamespace(data_dir=tmp_path, engine_id="omnivoice"),
        setup_ready=lambda: True,
        setup_busy=False,
        pending=lambda: False,
        active_id=None,
        _lock=threading.RLock(),
        runner=Mock(),
    )
    root = tmp_path / "models"
    root.mkdir()
    weight = root / "weights.safetensors"
    weight.write_bytes(b"weights")
    state = {"status": "succeeded", "models": {"files": [{"path": str(weight), "size": 7}]}}
    setup = SimpleNamespace(
        service=service,
        model_ids=("k2-fsa/OmniVoice", "openai/whisper-small"),
        state=state,
        lock=threading.RLock(),
        snapshot=lambda: dict(state),
        _models_present=lambda: weight.exists(),
    )
    setup.update = lambda **kw: state.update(kw)
    return EngineManager(setup), weight


def test_uninstall_requires_deactivation_and_preserves_personal_data(tmp_path):
    engines, weight = manager(tmp_path)
    personal = tmp_path / "voice.mp3"
    personal.write_bytes(b"voice")
    with pytest.raises(UserError, match="Deactivate"):
        engines.change("omnivoice", "uninstall")
    engines.change("omnivoice", "deactivate")
    assert not engines.service.setup_ready()
    engines.change("omnivoice", "uninstall")
    assert not weight.exists()
    assert personal.read_bytes() == b"voice"


def test_unsafe_manifest_is_validated_before_any_deletion(tmp_path):
    engines, weight = manager(tmp_path)
    engines.change("omnivoice", "deactivate")
    engines.setup.state["models"]["files"].append({"path": str(tmp_path / "voice"), "size": 1})
    with pytest.raises(UserError, match="unsafe"):
        engines.change("omnivoice", "uninstall")
    assert weight.exists()


def test_busy_and_future_engines_cannot_be_changed(tmp_path):
    engines, weight = manager(tmp_path)
    engines.service.setup_busy = True
    with pytest.raises(BusyError):
        engines.change("omnivoice", "deactivate")
    with pytest.raises(UserError, match="not available"):
        engines.change("kittentts2", "install")
    assert weight.exists()


def test_engines_api_requires_session_token(tmp_path, engine):
    from fastapi.testclient import TestClient

    from pacttsclone.app import create_app
    from pacttsclone.config import Settings

    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/api/engines").status_code == 200
        assert client.post("/api/engines/omnivoice/deactivate").status_code == 403
        token = client.get("/api/session").json()["token"]
        response = client.post("/api/engines/kittentts2/install", headers={"X-PacTTS-Token": token})
        assert response.status_code == 422


def test_install_does_not_implicitly_activate(tmp_path):
    engines, weight = manager(tmp_path)
    weight.unlink()
    engines.setup.start = Mock(return_value={})
    engines.change("omnivoice", "install")
    assert engines.setup.state["engine_enabled"] is False
    engines.setup.start.assert_called_once_with("cuda")


def test_catalog_uses_pinned_plan_and_handles_null_download(tmp_path):
    import json

    engines, weight = manager(tmp_path)
    engines.setup.state["download"] = None
    plan = {"revision": "a" * 40, "files": [{"size": 123}]}
    (weight.parent / "k2-fsa--OmniVoice.json").write_text(json.dumps(plan))
    row = engines.snapshot()["engines"][0]
    assert row["download_bytes"] == 123
    assert row["models"][0]["revision"] == "a" * 40
    assert row["installed_bytes"] == 7


def test_symlink_manifest_never_deletes_external_files(tmp_path):
    engines, weight = manager(tmp_path)
    external = tmp_path / "personal.mp3"
    external.write_bytes(b"keep")
    link = weight.parent / "link"
    link.symlink_to(external)
    engines.setup.state["models"]["files"].append({"path": str(link), "size": 4})
    engines.change("omnivoice", "deactivate")
    with pytest.raises(UserError, match="unsafe"):
        engines.change("omnivoice", "uninstall")
    assert external.read_bytes() == b"keep"
    assert weight.exists()
