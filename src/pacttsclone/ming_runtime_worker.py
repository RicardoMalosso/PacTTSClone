"""Standalone JSON-lines bridge executed by Ming's private Python, never the web Python."""

import argparse
import hashlib
import json
import logging
import sys
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

MARKER = "@@PACTTS_MING@@"


def emit(value):
    print(MARKER + json.dumps(value), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if __package__:
        from .ming_inference import diagnostic, install_safe_generation, load_patched_model
    else:
        from ming_inference import diagnostic, install_safe_generation, load_patched_model

    logger = logging.getLogger("pactts.ming.inference")
    logger.setLevel(logging.INFO)
    try:
        import importlib.metadata

        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("Ming requires NVIDIA CUDA; CPU fallback is disabled.")
        if torch.cuda.get_device_capability()[0] < 8 or not torch.cuda.is_bf16_supported():
            raise RuntimeError(
                "Ming requires a CUDA GPU with native BF16 support (Ampere or newer)."
            )
        handler = RotatingFileHandler(
            Path(args.source).parent / "inference.log", maxBytes=2 * 1024 * 1024,
            backupCount=2, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        for line in Path(__file__).with_name("ming_requirements.txt").read_text().splitlines():
            if line.startswith(("#", "--")) or "==" not in line:
                continue
            package, version = line.split("==", 1)
            if importlib.metadata.version(package).split("+")[0] != version.split("+")[0]:
                raise RuntimeError(
                    f"Ming runtime needs {package}=={version}. Repair it in Engines."
                )
        sys.path.insert(0, args.source)
        load_patched_model(args.source)
        from ming_tts import MingTTS

        if args.preflight:
            emit({"ok": True, "gpu": torch.cuda.get_device_name(), "bf16": True})
            return
        model = MingTTS(args.model, device="cuda:0", text_normalization=False)
        install_safe_generation(model)
        diagnostic(
            "runtime_ready",
            torch=torch.__version__,
            gpu=torch.cuda.get_device_name(),
            source_revision="9332fb9443325d4726ce02cefd4ec1c211df4079",
        )
        emit({"ok": True, "ready": True})
        for line in sys.stdin:
            try:
                value = json.loads(line)
                if value.get("kind") == "transcribe":
                    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

                    processor = AutoProcessor.from_pretrained(
                        value["asr_model"], local_files_only=True
                    )
                    asr_model = AutoModelForSpeechSeq2Seq.from_pretrained(
                        value["asr_model"], local_files_only=True
                    )
                    asr = pipeline(
                        "automatic-speech-recognition",
                        model=asr_model,
                        tokenizer=processor.tokenizer,
                        feature_extractor=processor.feature_extractor,
                        device=-1,
                    )
                    emit({"ok": True, "transcript": asr(value["reference"])["text"]})
                    del asr, asr_model, processor
                    continue
                try:
                    generation = value["arguments"]
                    diagnostic(
                        "request_start",
                        request_id=uuid.uuid4().hex,
                        task=generation.get("task"),
                        characters=len(generation.get("text", "")),
                        text_sha256=hashlib.sha256(
                            generation.get("text", "").encode("utf-8")
                        ).hexdigest(),
                        transcript_characters=len(generation.get("prompt_text") or ""),
                        cuda_rng_sha256=hashlib.sha256(
                            torch.cuda.get_rng_state().cpu().numpy().tobytes()
                        ).hexdigest(),
                    )
                    model.synthesize(**value["arguments"], output_path=value["output"])
                finally:
                    # Temporary reference paths differ per job. Keep conditioning for
                    # all fragments of this job, but never retain stale job tensors.
                    model._prompt_cache.clear()
                torch.cuda.synchronize()
                diagnostic("request_complete")
                emit({"ok": True})
            except Exception as exc:
                diagnostic(
                    "request_failed",
                    exception_type=type(exc).__name__,
                    traceback=traceback.format_exc(),
                )
                emit({"ok": False, "error": str(exc)[:1400] +
                      " See engines/ming-3/inference.log for diagnostics."})
                # Discard resident state after errors, including CUDA OOM.
                return
    except Exception as exc:
        diagnostic(
            "runtime_failed", exception_type=type(exc).__name__, traceback=traceback.format_exc()
        )
        emit({"ok": False, "error": str(exc)[:1500]})
        sys.exit(1)


if __name__ == "__main__":
    main()
