"""Validated request mapping for the isolated Ming 3.0 dense runtime."""

from .domain import MingOptions, UserError


def generation_arguments(reference, request):
    if request.language == "pt":
        raise UserError("Portuguese is not supported by Ming. Choose a supported Ming language.")
    options = MingOptions.model_validate(request.ming)
    if request.duration is not None or request.speed != 1.0:
        raise UserError("Ming does not accept OmniVoice duration or speed controls.")
    if request.steps != 32 or not request.denoise or not request.preprocess_prompt:
        raise UserError("OmniVoice steps/denoise/preprocessing overrides are unsupported by Ming.")
    args = {
        "task": options.task,
        "text": request.text,
        "cfg": request.guidance_scale,
        "trim_silence": request.postprocess_output,
    }
    if options.task == "TTS":
        if not request.ref_text:
            raise UserError("Ming cloning requires the exact saved reference transcript.")
        args.update(
            language_id=options.language,
            prompt_wav_path=reference,
            prompt_text=request.ref_text,
            use_spk_emb=True,
        )
        if options.language not in {"en", "zh"}:
            args["task"] = "MULTILINGUAL"
    elif options.task in {"EMOTION", "BASIC", "DIALECT"}:
        args.update(prompt_wav_path=reference, use_spk_emb=True)
        if options.task == "EMOTION":
            emotions = dict(
                zip(
                    ["happy", "sad", "angry", "afraid", "disgusted", "surprised", "neutral"],
                    ["高兴", "悲伤", "愤怒", "恐惧", "厌恶", "惊讶", "中性"],
                    strict=True,
                )
            )
            args["controls"] = {"emotion": emotions[options.emotion]}
        elif options.task == "BASIC":
            levels = {"low": "低", "normal": "中", "high": "高"}
            args["controls"] = {
                "speed": {"slow": "慢速", "normal": "中速", "fast": "快速"}[options.speed],
                "pitch": levels[options.pitch],
                "volume": levels[options.loudness],
            }
        else:
            args["controls"] = {"dialect": options.dialect}
    else:
        args["use_zero_spk_emb"] = True
        if options.task == "IP":
            args["controls"] = {"ip": options.voice}
        elif not options.instruction.strip():
            raise UserError("Enter a Ming delivery instruction or voice description.")
        elif options.task == "FREEFORM":
            args["instruction"] = options.instruction
        else:
            args["controls"] = {"style": options.instruction}
    return args
