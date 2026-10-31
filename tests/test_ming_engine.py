import pytest

from pacttsclone.domain import GenerationRequest, UserError
from pacttsclone.ming_engine import generation_arguments


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


def test_ming_rejects_portuguese_before_loading():
    with pytest.raises(UserError, match="Portuguese"):
        generation_arguments("ref.wav", request().model_copy(update={"language": "pt"}))


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
