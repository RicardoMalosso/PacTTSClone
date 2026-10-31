"""Kitten contract tests; these do not claim real GPU inference."""

import json
import os
import sys
from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest, KittenOptions, UserError
from pacttsclone.kitten_engine import KittenProcessEngine, available_voices, generation_arguments
from pacttsclone.ming_install import manifests


def test_pinned_assets_include_lossless_weights_and_offline_decoder():
    source, model = manifests("kitten")
    assert len(source["revision"]) == len(model["revision"]) == 40
    names = {entry["name"] for entry in model["files"]}
    assert "lm/model-ternary.safetensors" in names
    assert "lm/model.safetensors" not in names
    assert "lm/model-tl2-emb4.safetensors" not in names
    assert len(available_voices()) == 115
    refs = next(entry for entry in model["files"] if entry["name"].endswith("refs/main"))
    assert refs["url"].startswith("data:")
    assert any(
        model["decoder_revision"] in name and name.endswith("s3gen_meanflow.safetensors")
        for name in names
    )
    for manifest in (source, model):
        for entry in manifest["files"]:
            assert entry["size"] > 0
            assert len(entry["hash"]) == (64 if entry["algorithm"] == "sha256" else 40)


def test_clone_and_preset_map_exclusive_inputs():
    clone = generation_arguments("ref.wav", GenerationRequest(text="Olá", ref_text="Referência"))
    assert clone["reference"] == "ref.wav"
    assert clone["reference_text"] == "Referência"
    assert "voice" not in clone
    req = GenerationRequest(
        text="[happy] Olá <laugh>",
        kitten=KittenOptions(
            mode="preset",
            voice="Bruno",
            preset="expressive",
            seed=123,
            normalize=False,
            use_reference_prompt=False,
            max_new_tokens=500,
        ),
    )
    preset = generation_arguments("unused.wav", req)
    assert preset["voice"] == "Bruno"
    assert "reference" not in preset and "reference_text" not in preset
    assert preset["advanced"] == {"seed": 123}
    assert preset["preset"] == "expressive"
    assert preset["normalize"] is preset["use_reference_prompt"] is False
    assert preset["max_new_tokens"] == 500


@pytest.mark.parametrize(
    "overrides",
    [
        dict(language="pt"),
        dict(language="en"),
        dict(speed=1.1),
        dict(duration=5),
        dict(steps=16),
        dict(denoise=False),
        dict(preprocess_prompt=False),
        dict(guidance_scale=3),
        dict(postprocess_output=False),
    ],
)
def test_reject_unsupported_overrides_before_loading(overrides):
    with pytest.raises(UserError):
        generation_arguments(
            "ref.wav", GenerationRequest(text="Hello", ref_text="Reference", **overrides)
        )


def test_missing_transcript_and_unknown_preset_are_clear_errors():
    with pytest.raises(UserError, match="transcript"):
        generation_arguments("ref.wav", GenerationRequest(text="Hello"))
    with pytest.raises(UserError, match="available"):
        generation_arguments(
            "ref.wav",
            GenerationRequest(text="Hello", kitten=KittenOptions(mode="preset", voice="missing")),
        )


def test_short_reference_rejected_before_runtime(tmp_path):
    path = tmp_path / "short.wav"
    sf.write(path, np.zeros(24000, dtype=np.float32), 24000)
    engine = KittenProcessEngine(Settings(data_dir=tmp_path))
    with pytest.raises(UserError, match="5 and 30"):
        engine.synthesize(str(path), GenerationRequest(text="Hello", ref_text="Reference"))
    assert engine.process is None


def test_real_child_transport_reuses_and_closes_process(tmp_path):
    root = tmp_path / "engines" / "kittentts2"
    python = root / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    script = tmp_path / "fake_kitten.py"
    script.write_text("""import sys,json,wave,struct
print('@@PACTTS_KITTEN@@'+json.dumps({'ok':True}),flush=True)
for line in sys.stdin:
 value=json.loads(line)
 assert value['arguments']['voice']=='Bruno'
 with wave.open(value['output'],'wb') as w:
  w.setparams((1,2,24000,0,'NONE','not compressed'))
  w.writeframes(struct.pack('<hh',3276,-3276))
 print('@@PACTTS_KITTEN@@'+json.dumps({'ok':True}),flush=True)
""")
    engine = KittenProcessEngine(
        Settings(data_dir=tmp_path, engine_id="kittentts2", model="fixture")
    )
    engine._command = lambda python, root: [sys.executable, "-u", str(script)]
    request = GenerationRequest(text="Olá", kitten=KittenOptions(mode="preset"))
    try:
        result = engine.synthesize(str(tmp_path / "reference.wav"), request)
        process = engine.process
        assert result.sample_rate == 24000 and result.samples.shape == (2,)
        engine.synthesize(str(tmp_path / "reference.wav"), request)
        assert engine.process is process
    finally:
        engine.close()
    assert process.poll() is not None


def test_activation_rollback_persistence_and_safe_removal(tmp_path, monkeypatch, engine):
    monkeypatch.setattr(
        "pacttsclone.ming_lifecycle.receipt_valid", lambda root, profile="ming": True
    )
    response = {
        "returncode": 1,
        "stdout": '@@PACTTS_KITTEN@@{"ok":false,"error":"Unsupported GPU"}',
    }
    monkeypatch.setattr(
        "pacttsclone.ming_lifecycle.subprocess.run", lambda *a, **kw: type("Result", (), response)()
    )
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"X-PacTTS-Token": client.get("/api/session").json()["token"]}
        assert client.post("/api/engines/kittentts2/activate", headers=headers).status_code == 422
        assert app.state.service.settings.engine_id == "omnivoice"
        response.update(returncode=0, stdout='@@PACTTS_KITTEN@@{"ok":true,"bf16":true}')
        assert client.post("/api/engines/kittentts2/activate", headers=headers).status_code == 200
        assert client.get("/api/state").json()["active_engine"] == "kittentts2"
        assert client.post("/api/engines/kittentts2/uninstall", headers=headers).status_code == 422
    restored = create_app(Settings(data_dir=tmp_path), engine)
    assert restored.state.service.settings.engine_id == "kittentts2"
    with TestClient(restored, base_url="http://127.0.0.1") as client:
        headers = {"X-PacTTS-Token": client.get("/api/session").json()["token"]}
        assert client.post("/api/engines/kittentts2/deactivate", headers=headers).status_code == 200
        personal = tmp_path / "voices" / "keep.txt"
        personal.parent.mkdir(exist_ok=True)
        personal.write_text("keep")
        assert client.post("/api/engines/kittentts2/uninstall", headers=headers).status_code == 200
        assert personal.read_text() == "keep"


def test_engine_settings_remain_independent(tmp_path, engine):
    from pacttsclone.domain import GenerationSettings
    from pacttsclone.service import GenerationService
    from pacttsclone.voices import Voices

    service = GenerationService(Settings(data_dir=tmp_path), engine)
    voices = Voices(service)
    try:
        service.store.put("voice", "v", {"id": "v", "generation_settings": {"speed": 1.2}})
        service.settings = replace(service.settings, engine_id="kittentts2")
        voices.set_generation_settings(
            "v", GenerationSettings(kitten=KittenOptions(mode="preset", voice="Bruno"))
        )
        saved = service.store.get("voice", "v")
        assert saved["generation_settings"]["speed"] == 1.2
        assert saved["engine_generation_settings"]["kittentts2"]["kitten"]["mode"] == "preset"
        assert json.loads(json.dumps(saved)) == saved
    finally:
        service.close()


def test_unsupported_host_python_fails_before_installing(tmp_path, monkeypatch):
    from pacttsclone import ming_install

    monkeypatch.setattr(ming_install.sys, "version_info", (3, 11))
    with pytest.raises(ValueError, match="Python 3.12"):
        ming_install.install(tmp_path / "kitten", profile="kitten")
    assert not (tmp_path / "kitten").exists()


def test_unprepared_profile_preset_generates_without_asr(tmp_path, mp3, engine):
    import shutil

    from pacttsclone.domain import GenerationSettings
    from pacttsclone.service import GenerationService
    from pacttsclone.voices import Voices
    from tests.conftest import wait_job

    service = GenerationService(Settings(data_dir=tmp_path), engine)
    service.settings = service.runner.settings = replace(service.settings, engine_id="kittentts2")
    voices = Voices(service)
    root = voices.root / "profile"
    root.mkdir()
    shutil.copyfile(mp3, root / "reference.mp3")
    service.store.put(
        "voice",
        "profile",
        {
            "id": "profile",
            "status": "unprepared",
            "transcript": "",
            "title": "Preset profile",
            "original_filename": "reference.mp3",
        },
    )
    voices.set_generation_settings(
        "profile", GenerationSettings(kitten=KittenOptions(mode="preset"))
    )

    def no_asr(reference):
        raise AssertionError("Preset speech must not call ASR")

    engine.transcribe = no_asr
    try:
        job = voices.generate("profile", GenerationRequest(text="Olá"))
        result = wait_job(service, job["id"])
        assert result["status"] == "succeeded", result.get("error")
        assert engine.calls[0][1].ref_text == ""
        assert engine.calls[0][1].kitten.mode == "preset"
        assert service.store.get("voice", "profile")["status"] == "unprepared"
        with pytest.raises(UserError, match="not ready"):
            voices.generate(
                "profile", GenerationRequest(text="Olá", kitten=KittenOptions(mode="clone"))
            )
    finally:
        service.close()


def test_shared_asr_path_survives_omni_removal_and_restart(tmp_path, engine, monkeypatch):
    # Fake model files verify lifecycle metadata only, never real inference.
    monkeypatch.setattr(
        "pacttsclone.ming_lifecycle.receipt_valid", lambda root, profile="ming": profile == "kitten"
    )
    app = create_app(Settings(data_dir=tmp_path), engine)
    tts = tmp_path / "models" / "tts" / "weights.bin"
    asr = tmp_path / "models" / "asr" / "weights.bin"
    for path in [tts, asr]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    app.state.runtime_setup.update(
        status="succeeded",
        device="cuda",
        models={
            "paths": {"tts": str(tts.parent), "asr": str(asr.parent)},
            "files": [{"path": str(p), "size": 7} for p in [tts, asr]],
        },
        active_engine="kittentts2",
        engine_enabled=True,
    )
    app.state.runtime_setup._apply_models()
    service = app.state.service
    service.settings = service.runner.settings = replace(service.settings, engine_id="kittentts2")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"X-PacTTS-Token": client.get("/api/session").json()["token"]}
        assert client.post("/api/engines/omnivoice/uninstall", headers=headers).status_code == 200
        assert not tts.exists() and asr.exists()
        assert service.settings.engine_id == "kittentts2"
        assert app.state.runtime_setup.state["engine_enabled"] is True
    restored = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(restored, base_url="http://127.0.0.1") as client:
        assert restored.state.service.settings.engine_id == "kittentts2"
        assert restored.state.service.settings.asr_model == str(asr.parent)
        assert client.get("/api/setup").json()["ready"]


def test_standalone_worker_reuses_model_without_retaining_job_reference_caches(
    tmp_path, monkeypatch, capsys
):
    # Exercise the actual bridge loop with explicit simulated CUDA/model objects.
    # This verifies residency/cache lifecycle, never GPU audio quality.
    import contextlib
    import importlib.metadata
    import io
    from pathlib import Path
    from types import SimpleNamespace

    from pacttsclone import kitten_runtime_worker

    model_path = tmp_path / "model"
    model_path.mkdir()
    (model_path / "config.json").write_text('{"type":"KITTEN2"}')
    instances = []

    class SimulatedModel:
        def __init__(self, *args, **kwargs):
            assert kwargs["device"] == "cuda" and kwargs["backend"] == "torch"
            assert kwargs["weights"] == "packed" and kwargs["decoder"] == "default"
            self._reference_cache = {}
            self.codec = SimpleNamespace(_ref_cache={})
            self.calls = 0
            instances.append(self)

        def generate(self, **kwargs):
            assert not self._reference_cache and not self.codec._ref_cache
            self.calls += 1
            self._reference_cache["job-reference"] = object()
            self.codec._ref_cache["job-reference"] = object()
            return np.zeros(24, dtype=np.float32)

    cuda = SimpleNamespace(
        is_available=lambda: True,
        get_device_capability=lambda: (8, 0),
        is_bf16_supported=lambda: True,
        synchronize=lambda: None,
    )
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(cuda=cuda, inference_mode=contextlib.nullcontext)
    )
    monkeypatch.setitem(sys.modules, "kittenml", SimpleNamespace(KittenTTS2=SimulatedModel))
    requirements = Path(kitten_runtime_worker.__file__).with_name("kitten_requirements.txt")
    versions = dict(
        line.split("==") for line in requirements.read_text().splitlines() if "==" in line
    )
    monkeypatch.setattr(importlib.metadata, "version", lambda package: versions[package])
    monkeypatch.setattr(sys, "path", sys.path[:])
    monkeypatch.setattr(
        sys, "argv", ["worker", "--source", str(tmp_path), "--model", str(model_path)]
    )
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                json.dumps(
                    {"arguments": {"text": str(i)}, "output": str(tmp_path / f"output-{i}.wav")}
                )
                for i in range(2)
            )
            + "\n"
        ),
    )
    kitten_runtime_worker.main()
    assert len(instances) == 1 and instances[0].calls == 2
    assert not instances[0]._reference_cache and not instances[0].codec._ref_cache
    messages = [
        json.loads(line.split("@@PACTTS_KITTEN@@")[1])
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("@@PACTTS_KITTEN@@")
    ]
    assert len(messages) == 3 and all(message["ok"] for message in messages)
