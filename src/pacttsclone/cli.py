import argparse
import logging
import os
import time
import webbrowser
from pathlib import Path
from threading import Timer

from .config import Settings


class PollingAccessFilter(logging.Filter):
    def filter(self, record):
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            path, status = str(args[2]).split("?", 1)[0], str(args[4])
            poll = path in {
                "/api/state",
                "/api/resources",
                "/api/tunnel",
                "/api/setup",
                "/api/session",
            } or path.endswith("/player/tick")
            if status == "200" and poll:
                return False
        return True


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="PacTTSClone — geração local com OmniVoice")
    result.add_argument("--data-dir", type=Path, default=Path.home() / ".pacttsclone")
    result.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    result.add_argument(
        "--model", default="k2-fsa/OmniVoice", help="Hugging Face ID ou pasta local"
    )
    result.add_argument("--asr-model", default="openai/whisper-small")
    result.add_argument("--offline", action="store_true")
    return result


def settings_from(args) -> Settings:
    # Set before importing inference/Hugging Face libraries.
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return Settings(
        data_dir=args.data_dir.expanduser().resolve(),
        device=args.device,
        model=args.model,
        asr_model=args.asr_model,
        offline=args.offline,
    )


def main():
    arguments = parser()
    arguments.add_argument("--port", type=int, default=7860)
    arguments.add_argument("--no-browser", action="store_true")
    args = arguments.parse_args()
    if not 1 <= args.port <= 65535:
        arguments.error("porta deve estar entre 1 e 65535")
    settings = settings_from(args)
    import uvicorn

    from .app import create_app

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("uvicorn.access").addFilter(PollingAccessFilter())
    if not args.no_browser:
        timer = Timer(1.5, webbrowser.open, args=[f"http://127.0.0.1:{args.port}"])
        timer.daemon = True
        timer.start()
    print(f"MP3s serão salvos em: {settings.data_dir / 'outputs'}")
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port)


def smoke():
    arguments = parser()
    arguments.add_argument("--reference", required=True, type=Path)
    arguments.add_argument("--text", required=True)
    arguments.add_argument("--ref-text", default="")
    args = arguments.parse_args()
    settings = settings_from(args)
    from .domain import GenerationRequest
    from .service import GenerationService

    logging.basicConfig(level=logging.INFO)
    service = GenerationService(settings)
    try:
        with args.reference.open("rb") as reference:
            job = service.submit(
                reference, GenerationRequest(text=args.text, ref_text=args.ref_text)
            )
        while job["status"] in {"queued", "running"}:
            time.sleep(0.2)
            job = service.get(job["id"])
        if job["status"] != "succeeded":
            raise SystemExit(job["error"])
        print(f"Device: {job.get('device')}; elapsed: {job['elapsed_seconds']} s")
        print(service.output_path(job["id"]))
    finally:
        service.close()


if __name__ == "__main__":
    main()
