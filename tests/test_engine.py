import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest, UserError
from pacttsclone.engine import OmniVoiceEngine, choose_device


@pytest.fixture
def modules(monkeypatch):
    torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: True, empty_cache=Mock()),
        float16="fp16",
        float32="fp32",
        inference_mode=nullcontext,
    )
    model = Mock()
    model.sampling_rate = 24000
    model.generate.return_value = [np.ones(24000) * 0.1]
    factory = Mock(return_value=model)
    config = Mock(side_effect=lambda **kwargs: kwargs)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(
        sys.modules,
        "omnivoice",
        SimpleNamespace(
            OmniVoice=SimpleNamespace(from_pretrained=factory),
            OmniVoiceGenerationConfig=config,
        ),
    )
    return torch, model, factory


def test_real_adapter_contract_and_lazy_cache(modules):
    _, model, factory = modules
    engine = OmniVoiceEngine(Settings())
    assert factory.call_count == 0
    request = GenerationRequest(text="Olá", ref_text="Referência", speed=1.1, steps=16)
    for _ in range(2):
        waveform = engine.synthesize("reference.wav", request)
        assert waveform.sample_rate == 24000
    factory.assert_called_once_with(
        "k2-fsa/OmniVoice",
        device_map="cuda",
        dtype="fp16",
        attn_implementation="sdpa",
        load_asr=False,
        asr_model_name="openai/whisper-small",
        asr_device="cpu",
    )
    model.load_asr_model.assert_not_called()
    model.generate.assert_called_with(
        text="Olá",
        language="pt",
        ref_audio="reference.wav",
        ref_text="Referência",
        speed=1.1,
        generation_config={"num_step": 16},
    )


def test_blank_transcript_loads_asr_once_on_cpu(modules):
    _, model, _ = modules
    engine = OmniVoiceEngine(Settings())
    request = GenerationRequest(text="Olá", language="auto")
    engine.synthesize("reference.wav", request)
    engine.synthesize("reference.wav", request)
    model.load_asr_model.assert_called_once_with(model_name="openai/whisper-small", device="cpu")
    assert model.generate.call_args.kwargs["language"] is None
    assert model.generate.call_args.kwargs["ref_text"] is None


def test_cpu_uses_float32(modules):
    torch, _, factory = modules
    torch.cuda.is_available = lambda: False
    engine = OmniVoiceEngine(Settings())
    engine.synthesize("reference.wav", GenerationRequest(text="Olá", ref_text="Ref"))
    assert factory.call_args.kwargs["device_map"] == "cpu"
    assert factory.call_args.kwargs["dtype"] == "fp32"


def test_explicit_unavailable_cuda_fails(modules):
    torch, _, _ = modules
    torch.cuda.is_available = lambda: False
    with pytest.raises(UserError, match="CUDA indisponível"):
        choose_device(torch, "cuda")


def test_oom_drops_cache_and_allows_retry(modules):
    torch, model, factory = modules
    engine = OmniVoiceEngine(Settings())
    model.generate.side_effect = RuntimeError("CUDA out of memory")
    with pytest.raises(UserError, match="Memória insuficiente"):
        engine.synthesize("reference.wav", GenerationRequest(text="Olá", ref_text="Ref"))
    assert engine.model is None
    torch.cuda.empty_cache.assert_called_once()
    model.generate.side_effect = None
    engine.synthesize("reference.wav", GenerationRequest(text="Olá", ref_text="Ref"))
    assert factory.call_count == 2


def test_load_failure_explained_without_leaking_paths(modules):
    _, _, factory = modules
    factory.side_effect = OSError("/secret/cache/model not found")
    with pytest.raises(UserError, match="cache no modo offline") as result:
        OmniVoiceEngine(Settings()).synthesize("ref.wav", GenerationRequest(text="Olá"))
    assert "/secret" not in str(result.value)


def test_missing_dependencies_actionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "omnivoice", None)
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(UserError, match="Dependências de inferência"):
        OmniVoiceEngine(Settings()).synthesize("ref.wav", GenerationRequest(text="Olá"))


def test_offline_sets_flags_before_loading(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)
    import os

    engine = OmniVoiceEngine(Settings(offline=True))
    assert engine.model is None
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    # Restore environment to avoid influencing other tests in this process.
    monkeypatch.delenv("HF_HUB_OFFLINE")
    monkeypatch.delenv("TRANSFORMERS_OFFLINE")


def test_residency_is_shared_across_voice_changes_and_cleared_on_oom(modules):
    _, model, factory = modules
    engine = OmniVoiceEngine(Settings())
    events = []
    engine.residency_observer = lambda loaded, device: events.append((loaded, device))
    request = GenerationRequest(text="Test", ref_text="Known reference")
    engine.synthesize("voice-a.wav", request)
    engine.synthesize("voice-b.wav", request)
    assert factory.call_count == 1
    assert events == [(True, "cuda")]
    model.generate.side_effect = RuntimeError("out of memory")
    with pytest.raises(UserError, match="Memória"):
        engine.synthesize("voice-a.wav", request)
    assert events[-1] == (False, "cuda")
