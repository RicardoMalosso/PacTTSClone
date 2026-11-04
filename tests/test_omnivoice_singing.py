"""Regression tests for the optional OmniVoice Singing model variant."""

import json
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pacttsclone.config import Settings
from pacttsclone.domain import BusyError, UserError
from pacttsclone.engines import EngineManager
from pacttsclone.ming_lifecycle import MingLifecycle
from pacttsclone.omnivoice_singing_install import MODEL_KEY, MODEL_REPO, install


@pytest.fixture(autouse=True)
def mock_shared_inference_runtime(monkeypatch):
    """Unit tests must not require the heavy CUDA/OmniVoice packages."""
    monkeypatch.setattr(
        "pacttsclone.omnivoice_singing_lifecycle.dependencies_available", lambda: True
    )
    monkeypatch.setattr("pacttsclone.engines.dependencies_available", lambda: True)


def make_manager(tmp_path):
    original = tmp_path / "models" / "original"
    original.mkdir(parents=True)
    original_weights = original / "weights.safetensors"
    original_weights.write_bytes(b"original weights")
    settings = Settings(data_dir=tmp_path, model=str(original))
    runner = Mock()
    runner.pid = None
    service = SimpleNamespace(
        settings=settings,
        setup_ready=lambda: True,
        setup_busy=False,
        pending=lambda: False,
        active_id=None,
        _lock=threading.RLock(),
        runner=runner,
        logs=tmp_path,
    )
    state = {
        "status": "succeeded",
        "active_engine": "omnivoice",
        "engine_enabled": True,
        "models": {
            "files": [{"path": str(original_weights), "size": original_weights.stat().st_size}],
        },
    }
    setup = SimpleNamespace(
        service=service,
        model_ids=("k2-fsa/OmniVoice", "openai/whisper-small"),
        state=state,
        lock=threading.RLock(),
        snapshot=lambda: dict(state),
        _models_present=lambda: original_weights.is_file(),
        update=lambda **kw: state.update(kw),
    )

    def restore_original():
        settings = replace(
            service.settings,
            engine_id="omnivoice",
            model=str(original),
            offline=True,
        )
        service.settings = service.runner.settings = settings

    setup._apply_models = Mock(side_effect=restore_original)
    return EngineManager(setup), original_weights


def write_singing_receipt(root, *, revision="a" * 40):
    model = root / "model"
    model.mkdir(parents=True)
    (model / "config.json").write_text("{}", encoding="utf-8")
    (model / "model.safetensors").write_bytes(b"singing weights")
    files = [
        {"name": "config.json", "size": 2},
        {"name": "model.safetensors", "size": 15},
    ]
    (root / "installation.json").write_text(
        json.dumps({
            "repo": MODEL_REPO,
            "revision": revision,
            "files": files,
            "installed_bytes": sum(file["size"] for file in files),
        }),
        encoding="utf-8",
    )


def test_singing_is_separate_and_original_engine_remains_unchanged(tmp_path):
    manager, original = make_manager(tmp_path)
    write_singing_receipt(manager.singing.root)
    singing = manager.singing
    assert singing.installed()
    manager.change("omnivoice-singing", "activate")
    assert manager.service.settings.engine_id == "omnivoice-singing"
    assert manager.service.settings.model == str(singing.root / "model")
    assert manager.service.settings.offline
    assert manager.snapshot()["engines"][3]["active"]
    assert not manager.snapshot()["engines"][0]["active"]

    manager.change("omnivoice", "activate")
    assert manager.service.settings.engine_id == "omnivoice"
    assert manager.service.settings.model == str(original.parent)
    assert original.read_bytes() == b"original weights"
    assert singing.installed()
    assert manager.snapshot()["engines"][0]["active"]


def test_singing_survives_restart_without_auto_activation(tmp_path):
    manager, _ = make_manager(tmp_path)
    write_singing_receipt(manager.singing.root)
    assert manager.singing.installed()
    restarted = EngineManager(manager.setup)
    assert restarted.service.settings.engine_id == "omnivoice"
    assert restarted.singing.installed()
    restarted.change("omnivoice-singing", "activate")
    restarted_again = EngineManager(restarted.setup)
    assert restarted_again.service.settings.engine_id == "omnivoice-singing"
    assert restarted_again.service.settings.model == str(manager.singing.root / "model")


def test_missing_or_tampered_singing_receipt_does_not_become_installed(tmp_path):
    manager, _ = make_manager(tmp_path)
    root = manager.singing.root
    write_singing_receipt(root)
    assert manager.singing.installed()
    (root / "model" / "model.safetensors").write_bytes(b"bad")
    assert not manager.singing.installed()
    with pytest.raises(UserError, match="Install and verify"):
        manager.change("omnivoice-singing", "activate")
    assert manager.service.settings.engine_id == "omnivoice"


def test_receipt_path_traversal_does_not_escape_engine_directory(tmp_path):
    manager, original = make_manager(tmp_path)
    root = manager.singing.root
    write_singing_receipt(root)
    receipt_path = root / "installation.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["files"][1]["name"] = "../../../models/original/weights.safetensors"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    assert not manager.singing.installed()
    assert original.read_bytes() == b"original weights"


def test_singing_install_is_weights_only_and_uses_existing_runtime(tmp_path, monkeypatch):
    manager, original = make_manager(tmp_path)
    monkeypatch.setattr(
        "pacttsclone.omnivoice_singing_lifecycle.dependencies_available", lambda: True
    )
    installed = Mock()
    monkeypatch.setattr(MingLifecycle, "start", lambda self: installed())
    assert manager.singing.start() == installed.return_value
    assert installed.call_count == 1
    write_singing_receipt(manager.singing.root)
    installed.reset_mock()
    manager.singing.start()
    installed.assert_not_called()
    assert original.read_bytes() == b"original weights"


def test_installer_moves_only_singing_weights_and_retains_original(tmp_path, monkeypatch):
    manager, original = make_manager(tmp_path)
    root = manager.singing.root

    def fake_download(staging, repos, hf_cache):
        assert repos == [MODEL_REPO]
        staging.mkdir(parents=True)
        plan = {
            "revision": "b" * 40,
            "files": [
                {"name": "config.json", "size": 2},
                {"name": "model.safetensors", "size": 15},
            ],
        }
        (staging / f"{MODEL_KEY}.json").write_text(json.dumps(plan), encoding="utf-8")
        model = staging / MODEL_KEY / plan["revision"]
        model.mkdir(parents=True)
        (model / "config.json").write_text("{}", encoding="utf-8")
        (model / "model.safetensors").write_bytes(b"singing weights")
        return {"paths": {MODEL_REPO: str(model)}}

    monkeypatch.setattr("pacttsclone.omnivoice_singing_install.download_models", fake_download)
    receipt = install(root, tmp_path / "hf-cache")
    assert receipt["repo"] == MODEL_REPO
    assert (root / "model" / "model.safetensors").read_bytes() == b"singing weights"
    assert manager.singing.installed()
    assert original.read_bytes() == b"original weights"
    assert not (tmp_path / "models" / "ModelsLab--omnivoice-singing").exists()


def test_uninstall_singing_does_not_touch_original_or_saved_voices(tmp_path):
    manager, original = make_manager(tmp_path)
    write_singing_receipt(manager.singing.root)
    voice = tmp_path / "voices" / "sample.mp3"
    voice.parent.mkdir()
    voice.write_bytes(b"reference audio")
    manager.change("omnivoice-singing", "uninstall")
    assert not manager.singing.root.exists()
    assert original.read_bytes() == b"original weights"
    assert voice.read_bytes() == b"reference audio"


def test_original_installation_does_not_get_singing_model(tmp_path):
    manager, original = make_manager(tmp_path)
    assert manager.snapshot()["engines"][0]["name"] == "OmniVoice"
    assert manager.snapshot()["engines"][3]["id"] == "omnivoice-singing"
    assert manager.snapshot()["engines"][3]["installed"] is False
    assert original.read_bytes() == b"original weights"


def test_original_configuration_and_setup_manifest_are_untouched(tmp_path):
    manager, original = make_manager(tmp_path)
    baseline_model = manager.service.settings.model
    baseline_asr = manager.service.settings.asr_model
    baseline_manifest = json.dumps(manager.setup.state["models"], sort_keys=True)
    baseline_bytes = original.read_bytes()
    baseline_ready = manager.service.setup_ready()
    assert baseline_ready

    # Discovering, installing, and listing the optional variant must not activate it.
    write_singing_receipt(manager.singing.root)
    rows = manager.snapshot()["engines"]
    assert rows[0]["active"]
    assert rows[3]["installed"]
    assert not rows[3]["active"]
    assert manager.service.settings.engine_id == "omnivoice"
    assert manager.service.settings.model == baseline_model
    assert manager.service.settings.asr_model == baseline_asr
    assert manager.service.setup_ready() == baseline_ready
    assert json.dumps(manager.setup.state["models"], sort_keys=True) == baseline_manifest
    assert original.read_bytes() == baseline_bytes
    manager.service.runner.reset.assert_not_called()


def test_switching_back_restores_base_model_and_asr_without_reinstall(tmp_path):
    manager, original = make_manager(tmp_path)
    original_model = manager.service.settings.model
    original_asr = manager.service.settings.asr_model
    original_manifest = json.dumps(manager.setup.state["models"], sort_keys=True)
    write_singing_receipt(manager.singing.root)
    manager.setup.start = Mock(side_effect=AssertionError("Unexpected setup/reinstall"))
    manager.change("omnivoice-singing", "activate")
    assert manager.service.setup_ready()
    assert manager.service.settings.model != original_model
    assert manager.service.settings.asr_model == original_asr
    manager.change("omnivoice", "activate")
    assert manager.service.setup_ready()
    assert manager.service.settings.model == original_model
    assert manager.service.settings.asr_model == original_asr
    assert manager.service.settings.engine_id == "omnivoice"
    assert json.dumps(manager.setup.state["models"], sort_keys=True) == original_manifest
    assert original.read_bytes() == b"original weights"
    assert manager.service.runner.reset.call_count == 2
    manager.setup.start.assert_not_called()


def test_failed_or_busy_singing_activation_preserves_original(tmp_path, monkeypatch):
    manager, original = make_manager(tmp_path)
    write_singing_receipt(manager.singing.root)
    manager.service.setup_busy = True
    with pytest.raises(BusyError):
        manager.change("omnivoice-singing", "activate")
    manager.service.setup_busy = False
    monkeypatch.setattr(
        "pacttsclone.omnivoice_singing_lifecycle.dependencies_available", lambda: False
    )
    with pytest.raises(UserError, match="runtime is unavailable"):
        manager.change("omnivoice-singing", "activate")
    assert manager.service.settings.engine_id == "omnivoice"
    assert manager.setup.state["active_engine"] == "omnivoice"
    assert manager.setup.state["engine_enabled"] is True
    assert original.read_bytes() == b"original weights"
    manager.service.runner.reset.assert_not_called()


def test_original_uninstall_retains_shared_whisper_and_singing_weights(tmp_path):
    manager, original = make_manager(tmp_path)
    write_singing_receipt(manager.singing.root)
    whisper = tmp_path / "models" / "whisper-small" / "weights.bin"
    whisper.parent.mkdir()
    whisper.write_bytes(b"shared ASR")
    manager.service.settings = replace(
        manager.service.settings, asr_model=str(whisper.parent)
    )
    manager.setup.state["models"]["files"].append(
        {"path": str(whisper), "size": whisper.stat().st_size}
    )
    manager.change("omnivoice", "deactivate")
    manager.change("omnivoice", "uninstall")
    assert not original.exists()
    assert whisper.read_bytes() == b"shared ASR"
    assert manager.singing.installed()
    assert manager.setup.state["shared_asr"]["files"]


def test_singing_uninstall_requires_deactivation_and_preserves_base(tmp_path):
    manager, original = make_manager(tmp_path)
    write_singing_receipt(manager.singing.root)
    manager.change("omnivoice-singing", "activate")
    with pytest.raises(UserError, match="Deactivate"):
        manager.change("omnivoice-singing", "uninstall")
    assert manager.singing.installed()
    assert original.read_bytes() == b"original weights"
    manager.change("omnivoice-singing", "deactivate")
    assert manager.service.settings.engine_id == "omnivoice"
    manager.change("omnivoice-singing", "uninstall")
    assert not manager.singing.root.exists()
    assert original.read_bytes() == b"original weights"


def test_missing_singing_model_on_restart_disables_only_selection(tmp_path):
    manager, original = make_manager(tmp_path)
    manager.setup.state.update(
        active_engine="omnivoice-singing", engine_enabled=True
    )
    new_manager = EngineManager(manager.setup)
    assert new_manager.setup.state["active_engine"] == "omnivoice"
    assert new_manager.setup.state["engine_enabled"] is False
    assert original.read_bytes() == b"original weights"
    assert new_manager.service.settings.model == str(original.parent)


def test_installer_refuses_path_alias_to_original_models(tmp_path, monkeypatch):
    manager, original = make_manager(tmp_path)
    monkeypatch.setattr(
        "pacttsclone.omnivoice_singing_install.download_models",
        Mock(side_effect=AssertionError("Must reject path before download")),
    )
    with pytest.raises(ValueError, match="dedicated"):
        install(tmp_path / "models", tmp_path / "hf-cache")
    assert original.read_bytes() == b"original weights"


def test_installer_rejects_symlink_to_original_before_download(tmp_path, monkeypatch):
    manager, original = make_manager(tmp_path)
    parent = tmp_path / "engines"
    parent.mkdir()
    disguised = parent / "omnivoice-singing"
    try:
        disguised.symlink_to(original.parent, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks are unavailable on this platform.")
    monkeypatch.setattr(
        "pacttsclone.omnivoice_singing_install.download_models",
        Mock(side_effect=AssertionError("Must reject symlink before download")),
    )
    with pytest.raises(ValueError, match="Unsafe"):
        install(disguised, tmp_path / "hf-cache")
    assert original.read_bytes() == b"original weights"


def test_installer_rejects_download_symlink_before_writing(tmp_path, monkeypatch):
    manager, original = make_manager(tmp_path)
    staging = manager.singing.root / "download"
    staging.mkdir(parents=True)
    try:
        (staging / MODEL_KEY).symlink_to(original.parent, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Directory symlinks are unavailable on this platform.")
    monkeypatch.setattr(
        "pacttsclone.omnivoice_singing_install.download_models",
        Mock(side_effect=AssertionError("Must reject symlink before download")),
    )
    with pytest.raises(ValueError, match="Unsafe"):
        install(manager.singing.root, tmp_path / "hf-cache")
    assert original.read_bytes() == b"original weights"
