"""Bounded discovery of large model weights; never migrate app/configuration files."""

import hashlib
import os
import re
import threading
import time
from pathlib import Path

from .domain import UserError

MIN_WEIGHT_BYTES = 64 * 1024 * 1024


def default_roots(data_dir):
    home = Path.home()
    values = [
        data_dir,
        data_dir.parent / "PacTTSClone-data",
        data_dir.parent / "data",
        home / ".cache/huggingface/hub",
        home / ".pacttsclone",
    ]
    for key in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE", "HF_HOME", "PACTTS_PREVIOUS_HF_CACHE"):
        if os.environ.get(key):
            values.append(Path(os.environ[key]))
    if os.environ.get("LOCALAPPDATA"):
        local = Path(os.environ["LOCALAPPDATA"])
        values += [
            local / "Programs/PacTTSClone/data",
            local / "Programs/PacTTSClone-data",
            local / "Programs/PacTTS/PacTTSClone-data",
            local / "Programs/PacTTS/data",
        ]
    return list(dict.fromkeys(str(p.expanduser().resolve()) for p in values if p.is_dir()))


def validate_roots(values):
    if (
        not isinstance(values, list)
        or len(values) > 20
        or any(not isinstance(p, str) or not p.strip() or len(p) > 4096 for p in values)
    ):
        raise UserError("Use up to 20 local model/cache folder paths, one per line.")
    result = []
    for value in values:
        path = Path(value).expanduser()
        if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
            raise UserError("Use absolute local folder paths, not network shares.")
        result.append(str(path.resolve()))
    return list(dict.fromkeys(result))


def is_weight(entry):
    return (
        entry["size"] >= MIN_WEIGHT_BYTES
        and entry["name"].endswith(".safetensors")
        and entry["algorithm"] == "sha256"
    )


def scan_weights(
    roots, *, sizes=None, stop=None, report=lambda result: None, max_files=50000, max_seconds=30
):
    stop = stop or threading.Event()
    result = {"status": "running", "files": [], "checked_files": 0, "limited": False}
    started = time.monotonic()
    seen = set()
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            continue
        for directory, dirs, files in os.walk(base, followlinks=False):
            if stop.is_set():
                return {**result, "status": "cancelled"}
            if time.monotonic() - started > max_seconds:
                return {**result, "status": "complete", "limited": True}
            # Avoid scanning installations, environments, recordings or source control.
            dirs[:] = [
                d
                for d in dirs
                if d
                not in {
                    ".git",
                    ".venv",
                    "node_modules",
                    "outputs",
                    "voices",
                    "environments",
                    "runtime",
                    "logs",
                    "temporary",
                }
                and not Path(directory, d).is_symlink()
            ]
            if len(Path(directory).relative_to(base).parts) >= 10:
                dirs[:] = []
            for name in files:
                if stop.is_set():
                    return {**result, "status": "cancelled"}
                result["checked_files"] += 1
                if result["checked_files"] > max_files or time.monotonic() - started > max_seconds:
                    return {**result, "status": "complete", "limited": True}
                if not (name.endswith(".safetensors") or re.fullmatch(r"[a-f0-9]{40,64}", name)):
                    continue
                path = Path(directory) / name
                try:
                    size = path.stat().st_size
                    resolved = str(path.resolve())
                    if (
                        size < MIN_WEIGHT_BYTES
                        or (sizes is not None and size not in sizes)
                        or resolved in seen
                    ):
                        continue
                    seen.add(resolved)
                    result["files"].append({"path": resolved, "size": size})
                    result["files"].sort(key=lambda f: f["size"], reverse=True)
                    report({**result, "files": list(result["files"])})
                    if len(result["files"]) >= 200:
                        return {**result, "status": "complete", "limited": True}
                except OSError:
                    continue
    return {**result, "status": "complete"}


def import_weight(entry, destination, candidates, progress=lambda n, phase: None):
    """Copy only byte-identical weights, publishing atomically after hashing the copy."""
    if not is_weight(entry):
        return False
    for candidate in candidates:
        if candidate["size"] != entry["size"]:
            continue
        source = Path(candidate["path"])
        if source == destination:
            continue
        temporary = destination.with_name(destination.name + ".reuse")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.new(entry["algorithm"])
            count = 0
            with source.open("rb") as src, temporary.open("wb") as target:
                while chunk := src.read(1024 * 1024):
                    count += len(chunk)
                    if count > entry["size"]:
                        break
                    digest.update(chunk)
                    target.write(chunk)
                    progress(count, "copying candidate weights")
            if count == entry["size"] and digest.hexdigest() == entry["hash"]:
                temporary.replace(destination)
                return True
        except OSError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
    return False


def move_verified_weights(entries, candidates, roots, verify):
    """Remove only selected old weights after their new copies are fully verified."""
    roots = [Path(p).resolve() for p in roots]
    result = []
    handled = set()
    for entry, destination in entries:
        if not is_weight(entry):
            continue
        for candidate in candidates:
            source = Path(candidate["path"]).resolve()
            if (
                source in handled
                or source == destination.resolve()
                or candidate["size"] != entry["size"]
                or not any(source.is_relative_to(root) for root in roots)
            ):
                continue
            try:
                if not verify(source, entry["size"], entry["hash"], entry["algorithm"]):
                    continue
            except OSError:
                continue
            if not verify(destination, entry["size"], entry["hash"], entry["algorithm"]):
                raise UserError("Imported destination changed; original weights were retained.")
            record = {
                "source": str(source),
                "destination": str(destination),
                "bytes": entry["size"],
                "moved": False,
            }
            try:
                source.unlink()
                record["moved"] = True
            except OSError:
                record["warning"] = "Source could not be removed; verified copy retained."
            handled.add(source)
            result.append(record)
    return result
