"""Standalone JSON-lines bridge executed by KittenTTS2's private Python, never the web Python."""

import argparse
import json
import sys
from pathlib import Path

MARKER = "@@PACTTS_KITTEN@@"


def emit(value):
    print(MARKER + json.dumps(value), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    try:
        import importlib.metadata

        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("KittenTTS2 requires NVIDIA CUDA; CPU fallback is disabled.")
        if torch.cuda.get_device_capability()[0] < 8 or not torch.cuda.is_bf16_supported():
            raise RuntimeError(
                "KittenTTS2 requires a CUDA GPU with native BF16 support (Ampere or newer)."
            )
        for line in Path(__file__).with_name("kitten_requirements.txt").read_text().splitlines():
            if line.startswith(("#", "--")) or "==" not in line:
                continue
            package, version = line.split("==", 1)
            if importlib.metadata.version(package).split("+")[0] != version.split("+")[0]:
                raise RuntimeError(
                    f"KittenTTS2 runtime needs {package}=={version}. Repair it in Engines."
                )
        sys.path.insert(0, args.source)
        import soundfile as sf
        from kittenml import KittenTTS2

        if args.preflight:
            emit({"ok": True, "gpu": torch.cuda.get_device_name(), "bf16": True})
            return
        config = json.loads((Path(args.model) / "config.json").read_text())
        if config.get("type") != "KITTEN2":
            raise RuntimeError("This is not the pinned KittenTTS2 checkpoint.")
        model = KittenTTS2(
            args.model,
            config,
            device="cuda",
            backend="torch",
            weights="packed",
            decoder="default",
            cache_dir=str(Path(args.model) / ".hf-cache"),
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
                with torch.inference_mode():
                    samples = model.generate(**value["arguments"])
                sf.write(value["output"], samples, 24000)
                torch.cuda.synchronize()
                emit({"ok": True})
            except Exception as exc:
                emit({"ok": False, "error": str(exc)[:1500]})
                # Discard resident state after errors, including CUDA OOM.
                return
    except Exception as exc:
        emit({"ok": False, "error": str(exc)[:1500]})
        sys.exit(1)


if __name__ == "__main__":
    main()
