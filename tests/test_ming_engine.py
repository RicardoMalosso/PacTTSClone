from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from pacttsclone.domain import GenerationRequest, UserError
from pacttsclone.ming_engine import MingEngine, check_runtime, generation_arguments


def request(**overrides):
    return GenerationRequest(
        text="Hello [Laughter]", ref_text="Reference words.", language="en", **overrides
    )


def test_ming_maps_only_supported_tts_controls():
    args = generation_arguments("reference.wav", request(guidance_scale=1.5))
    assert args["task"] == "TTS"
    assert args["cfg"] == 1.5
    assert args["prompt_wav_path"] == "reference.wav"
    assert args["text"] == "Hello [Laughter]"
    assert "num_step" not in args


@pytest.mark.parametrize("language", ["auto", "pt"])
def test_ming_rejects_unsupported_language_before_loading(language):
    engine = MingEngine(SimpleNamespace(model="unused"))
    engine._load = Mock()
    req = request().model_copy(update={"language": language})
    with pytest.raises(UserError, match="English explicitly"):
        engine.synthesize("ref.wav", req)
    engine._load.assert_not_called()


def test_ming_rejects_cpu_and_unsupported_bf16():
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(UserError, match="CUDA"):
        check_runtime(torch)
    torch.cuda.is_available = lambda: True
    torch.cuda.get_device_capability = lambda: (7, 5)
    torch.cuda.is_bf16_supported = lambda: True
    with pytest.raises(UserError, match="1660"):
        check_runtime(torch)


def test_ming_waveform_normalization_with_simulated_upstream():
    engine = MingEngine(SimpleNamespace())
    waveform = Mock()
    waveform.detach.return_value.float.return_value.cpu.return_value.numpy.return_value = np.array(
        [[0.1, -0.1]], dtype=np.float32
    )
    engine.model = SimpleNamespace(synthesize=Mock(return_value=waveform), sample_rate=24000)
    result = engine.synthesize("reference.wav", request())
    assert result.sample_rate == 24000
    assert result.samples.shape == (2,)


@pytest.mark.parametrize(
    "values",
    [
        {"duration": 2},
        {"speed": 1.2},
        {"steps": 16},
        {"denoise": False},
        {"preprocess_prompt": False},
    ],
)
def test_ming_rejects_incompatible_omnivoice_overrides(values):
    with pytest.raises(UserError, match="unsupported|does not accept"):
        generation_arguments("ref.wav", request(**values))
