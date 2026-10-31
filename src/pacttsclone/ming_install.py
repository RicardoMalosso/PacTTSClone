"""Verified engine assets and isolated dependency installation. Run in a cancellable child."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import venv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .model_setup import fetch_file, verify_file

MARKER = "@@PACTTS_MING_INSTALL@@"
EMIT_LOCK = threading.Lock()
RUNTIME_RESERVE = 12 * 1024**3  # Conservative budget for CUDA packages, venv and pip cache.


def emit(**value):
    with EMIT_LOCK:
        print(MARKER + json.dumps(value), flush=True)


def manifests(profile="ming"):
    return [
        json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))
        for name in (f"{profile}_source.json", f"{profile}_model.json")
    ]


def safe_destination(root, name):
    relative = Path(name)
    destination = root / relative
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or "\\" in name
        or ":" in name
        or any(p.is_symlink() for p in [destination, *destination.parents])
        or not destination.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError("Unsafe engine installation path.")
    return destination


def python_path(root):
    return root / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def receipt_valid(root, profile="ming"):
    try:
        receipt = json.loads((root / "installation.json").read_text())
        if not python_path(root).is_file():
            return False
        source, model = manifests(profile)
        if (
            receipt["source_revision"] != source["revision"]
            or receipt["model_revision"] != model["revision"]
        ):
            return False
        for folder, manifest in (("source", source), ("model", model)):
            for entry in manifest["files"]:
                path = safe_destination(root / folder, entry["name"])
                if not path.is_file() or path.stat().st_size != entry["size"]:
                    return False
        return (
            receipt["requirements_hash"]
            == hashlib.sha256(
                Path(__file__).with_name(f"{profile}_requirements.txt").read_bytes()
            ).hexdigest()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def install(root, runtime_only=False, profile="ming"):
    if profile == "kitten" and sys.version_info[:2] != (3, 12):
        raise ValueError(
            "KittenTTS2 requires Python 3.12. Use the Windows installer "
            "or launch the source app with Python 3.12."
        )
    root.mkdir(parents=True, exist_ok=True)
    safe_destination(root.parent, root.name)
    source, model = manifests(profile)
    requirements = Path(__file__).with_name(f"{profile}_requirements.txt")
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    runtime_marker = root / "runtime-packages.json"
    try:
        reused = json.loads(runtime_marker.read_text())["requirements_hash"] == digest
    except (OSError, ValueError, KeyError):
        reused = False
    python = python_path(root)
    reserve = (
        0
        if reused and python.is_file()
        else (20 * 1024**3 if profile == "kitten" else RUNTIME_RESERVE)
    )
    selected = (("source", source),) if runtime_only else (("source", source), ("model", model))
    entries = [
        (root / folder, entry) for folder, manifest in selected for entry in manifest["files"]
    ]
    missing = sum(
        entry["size"]
        for folder, entry in entries
        if not verify_file(
            safe_destination(folder, entry["name"]),
            entry["size"],
            entry["hash"],
            entry["algorithm"],
        )
    )
    if shutil.disk_usage(root).free < missing + reserve:
        raise ValueError(
            f"Insufficient disk space: reserve {missing + reserve} bytes "
            "for missing assets, private CUDA runtime and installation cache."
        )
    total = sum(entry["size"] for _, entry in entries)
    counts = {}
    progress_lock = threading.Lock()
    last_progress = [0.0]

    def transfer(pair):
        folder, entry = pair
        key = str(folder / entry["name"])

        def progress(count, phase):
            with progress_lock:
                counts[key] = max(counts.get(key, 0), count)
                now = time.monotonic()
                if now - last_progress[0] < 0.2 and count != entry["size"]:
                    return
                last_progress[0] = now
                emit(
                    stage="assets",
                    file=entry["name"],
                    phase=phase,
                    completed_bytes=sum(counts.values()),
                    total_bytes=total,
                )

        fetch_file(entry, safe_destination(folder, entry["name"]), progress)
        progress(entry["size"], "verified")

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(transfer, entries))
    if not reused or not python.is_file():
        emit(stage="dependencies", message=f"Preparing private {profile} Python/CUDA environment")
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(root / "runtime")
        cache = root / "pip-cache"
        temporary = root / "temporary"
        temporary.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "PYTHONNOUSERSITE": "1",
            "PIP_CACHE_DIR": str(cache),
            "TMPDIR": str(temporary),
            "TEMP": str(temporary),
            "TMP": str(temporary),
        }
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(requirements),
            ],
            env=env,
            check=True,
        )
        if profile == "kitten":
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-build-isolation",
                    str(root / "source"),
                ],
                env=env,
                check=True,
            )
        subprocess.run([str(python), "-m", "pip", "check"], env=env, check=True)
        runtime_marker.write_text(json.dumps({"requirements_hash": digest}))
    # CPU-only import check; GPU compatibility is checked explicitly at activation.
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONPATH": str(root / "source")}
    env.pop("PYTHONHOME", None)
    subprocess.run(
        [
            str(python),
            "-c",
            (
                "import torch, torchaudio, transformers; from ming_tts import MingTTS"
                if profile == "ming"
                else "from kittenml import KittenTTS2"
            ),
        ],
        env=env,
        check=True,
    )
    if runtime_only:
        emit(stage="runtime-verified", status="succeeded")
        return
    installed_bytes = sum(
        path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink()
    )
    receipt = {
        "installed_bytes": installed_bytes,
        "source_revision": source["revision"],
        "model_revision": model["revision"],
        "requirements_hash": digest,
    }
    temporary_receipt = root / "installation.tmp"
    temporary_receipt.write_text(json.dumps(receipt))
    temporary_receipt.replace(root / "installation.json")
    emit(stage="installed", status="succeeded", **receipt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--profile", choices=["ming", "kitten"], default="ming")
    args = parser.parse_args()
    try:
        install(args.root.absolute(), runtime_only=args.runtime_only, profile=args.profile)
    except Exception as exc:
        emit(status="failed", error=str(exc)[:1500])
        sys.exit(1)


if __name__ == "__main__":
    main()
