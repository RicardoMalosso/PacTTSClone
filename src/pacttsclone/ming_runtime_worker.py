"""Standalone JSON-lines bridge executed by Ming's private Python, never the web Python."""

import argparse
import json
import sys
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
    try:
        import importlib.metadata

        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("Ming requires NVIDIA CUDA; CPU fallback is disabled.")
        if torch.cuda.get_device_capability()[0] < 8 or not torch.cuda.is_bf16_supported():
            raise RuntimeError(
                "Ming requires a CUDA GPU with native BF16 support (Ampere or newer)."
            )
        for line in Path(__file__).with_name("ming_requirements.txt").read_text().splitlines():
            if line.startswith(("#", "--")) or "==" not in line:
                continue
            package, version = line.split("==", 1)
            if importlib.metadata.version(package).split("+")[0] != version.split("+")[0]:
                raise RuntimeError(
                    f"Ming runtime needs {package}=={version}. Repair it in Engines."
                )
        sys.path.insert(0, args.source)
        from ming_tts import MingTTS

        if args.preflight:
            emit({"ok": True, "gpu": torch.cuda.get_device_name(), "bf16": True})
            return
        model = MingTTS(args.model, device="cuda:0", text_normalization=False)
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
                model.synthesize(**value["arguments"], output_path=value["output"])
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
