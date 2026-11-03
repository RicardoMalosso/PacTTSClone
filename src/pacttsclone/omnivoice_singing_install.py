"""Install the optional OmniVoice Singing checkpoint without touching original OmniVoice.

This module intentionally reuses the existing verified/resumable model downloader.
It does not install or replace inference packages and never writes to the base
OmniVoice setup manifest.
"""

import argparse
import json
import shutil
from pathlib import Path

from .model_setup import download_models

MODEL_REPO = "ModelsLab/omnivoice-singing"
MODEL_KEY = MODEL_REPO.replace("/", "--")
MARKER = "@@PACTTS_SINGING@@"


def emit(**values):
    print(MARKER + json.dumps(values), flush=True)


def install(root: Path, hf_cache: Path):
    # Reject redirects into the original OmniVoice installation or shared caches.
    # The lifecycle always supplies a dedicated data/engines/omnivoice-singing root.
    if root.name != "omnivoice-singing" or root.parent.name != "engines":
        raise ValueError("Singing requires its dedicated engines/omnivoice-singing folder.")
    if any(path.is_symlink() for path in [root, *root.parents]):
        raise ValueError("Unsafe Singing installation directory.")
    root.mkdir(parents=True, exist_ok=True)
    # Keep partial downloads for cancellation/retry, separate from base OmniVoice.
    staging = root / "download"
    if staging.is_symlink():
        raise ValueError("Unsafe Singing download directory.")
    model = root / "model"
    previous = root / "previous-model"
    if previous.is_symlink():
        raise ValueError("Unsafe previous-model directory.")
    if previous.exists() and not model.exists():
        # Repair interrupted replacement without losing the last installed weights.
        previous.rename(model)
    result = download_models(staging, [MODEL_REPO], hf_cache)
    plan = json.loads((staging / f"{MODEL_KEY}.json").read_text(encoding="utf-8"))
    source = Path(result["paths"][MODEL_REPO])
    if not source.is_dir() or not source.resolve().is_relative_to(staging.resolve()):
        raise ValueError("Invalid Singing model download location.")
    if not (source / "config.json").is_file():
        raise ValueError("Singing checkpoint is missing config.json.")
    if not any((source / f["name"]).is_file() for f in plan["files"]
               if f["name"].endswith(".safetensors")):
        raise ValueError("Singing checkpoint is missing model weights.")

    receipt = {
        "repo": MODEL_REPO,
        "revision": plan["revision"],
        "files": [{"name": item["name"], "size": item["size"]} for item in plan["files"]],
        "installed_bytes": sum(item["size"] for item in plan["files"]),
    }
    if previous.exists() or previous.is_symlink():
        raise ValueError("Unexpected previous-model directory. Remove it manually before repair.")
    if model.is_symlink() or any(p.is_symlink() for p in [root, *root.parents]):
        raise ValueError("Unsafe Singing installation directory.")
    # Rename on the same filesystem, restoring an older checkpoint if the final
    # receipt cannot be written. The download staging directory is retained.
    had_previous = model.exists()
    if had_previous:
        model.rename(previous)
    try:
        source.rename(model)
        pending = root / "installation.json.partial"
        pending.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        pending.replace(root / "installation.json")
    except Exception:
        if model.exists():
            shutil.rmtree(model)
        if had_previous:
            previous.rename(model)
        raise
    if had_previous:
        shutil.rmtree(previous)
    emit(status="succeeded", stage="installed", revision=plan["revision"],
         installed_bytes=receipt["installed_bytes"])
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--hf-cache", type=Path, required=True)
    args = parser.parse_args()
    install(args.root, args.hf_cache)


if __name__ == "__main__":
    main()
