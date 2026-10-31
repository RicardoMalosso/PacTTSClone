"""Validated KittenTTS2 requests and isolated native CUDA subprocess transport."""

import json
from pathlib import Path

import soundfile as sf

from .domain import KittenOptions, UserError
from .ming_process import MingProcessEngine


def available_voices():
    return json.loads(Path(__file__).with_name("kitten_voices.json").read_text(encoding="utf-8"))


def generation_arguments(reference, request):
    options = KittenOptions.model_validate(request.kitten)
    if request.language != "auto":
        raise UserError("KittenTTS2 detects speech language automatically; choose Automatic.")
    if (
        request.speed != 1
        or request.duration is not None
        or request.steps != 32
        or not request.denoise
        or not request.preprocess_prompt
        or request.guidance_scale != 2
        or not request.postprocess_output
    ):
        raise UserError("OmniVoice generation controls are unsupported by KittenTTS2.")
    result = dict(
        text=request.text,
        preset=options.preset,
        max_new_tokens=options.max_new_tokens,
        normalize=options.normalize,
        use_reference_prompt=options.use_reference_prompt,
        advanced={"seed": options.seed},
    )
    if options.mode == "preset":
        if options.voice not in available_voices():
            raise UserError("Choose an available KittenTTS2 preset voice.")
        result["voice"] = options.voice
    else:
        if not request.ref_text:
            raise UserError("KittenTTS2 cloning requires the exact saved reference transcript.")
        result.update(reference=reference, reference_text=request.ref_text)
    return result


class KittenProcessEngine(MingProcessEngine):
    engine_id = "kittentts2"
    worker_file = "kitten_runtime_worker.py"
    marker = "@@PACTTS_KITTEN@@"
    label = "KittenTTS2"

    def arguments(self, reference, request):
        arguments = generation_arguments(reference, request)
        if request.kitten.mode == "clone":
            info = sf.info(reference)
            if not 5 <= info.duration <= 30.05:
                raise UserError("KittenTTS2 cloning requires a reference between 5 and 30 seconds.")
        return arguments
