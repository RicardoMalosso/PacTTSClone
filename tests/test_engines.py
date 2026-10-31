import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pacttsclone.domain import BusyError, UserError
from pacttsclone.engines import EngineManager


def manager(tmp_path):
    service = SimpleNamespace(
        settings=SimpleNamespace(data_dir=tmp_path),
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
        engines.change("ming-3", "install")
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
        response = client.post("/api/engines/ming-3/install", headers={"X-PacTTS-Token": token})
        assert response.status_code == 422
