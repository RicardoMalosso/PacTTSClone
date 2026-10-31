"""Verified, resumable model downloads. Emits real byte progress for the setup UI."""

import argparse
import hashlib
import json
import re
import shutil
import time
import urllib.request
from pathlib import Path

from .model_cache import (
    import_weight,
    is_weight,
    move_verified_weights,
    scan_weights,
    validate_roots,
)

MARKER = "@@PACTTS_SETUP@@"


def emit(**values):
    print(MARKER + json.dumps(values), flush=True)


def verify_file(path, expected_size, expected_hash, algorithm, progress=lambda n: None):
    if not path.is_file() or path.stat().st_size != expected_size:
        return False
    digest = hashlib.new(algorithm)
    if algorithm == "sha1":
        digest.update(f"blob {expected_size}\0".encode())
    count = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            count += len(chunk)
            progress(count)
    return digest.hexdigest() == expected_hash


def fetch_file(entry, destination, progress=lambda n, phase: None):
    size, checksum, algorithm = entry["size"], entry["hash"], entry["algorithm"]
    if verify_file(
        destination, size, checksum, algorithm, lambda n: progress(n, "verifying cache")
    ):
        return "verified cache"
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset >= size:
        if verify_file(
            partial, size, checksum, algorithm, lambda n: progress(n, "verifying partial")
        ):
            partial.replace(destination)
            return "verified partial"
        partial.unlink()
        offset = 0
    request = urllib.request.Request(
        entry["url"], headers={"Range": f"bytes={offset}-"} if offset else {}
    )
    resumed = bool(offset)
    with urllib.request.urlopen(request, timeout=30) as response:
        if offset and response.status != 206:
            offset = 0
            resumed = False
        if offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
            raise ValueError("Invalid resume response.")
        with partial.open("ab" if offset else "wb") as output:
            progress(offset, "resuming download" if resumed else "downloading")
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                offset += len(chunk)
                if offset > size:
                    raise ValueError("Model download exceeded expected size.")
                progress(offset, "resuming download" if resumed else "downloading")
    if not verify_file(
        partial, size, checksum, algorithm, lambda n: progress(n, "verifying download")
    ):
        partial.unlink(missing_ok=True)
        raise ValueError("Model checksum verification failed; retry setup.")
    partial.replace(destination)
    return "downloaded and verified"


def make_plan(repo):
    if len(repo.split("/")) != 2 or any(not p or p in {".", ".."} for p in repo.split("/")):
        raise ValueError("Setup requires a Hugging Face owner/model ID.")
    with urllib.request.urlopen(
        f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=30
    ) as response:
        metadata = json.load(response)
    revision = metadata["sha"]
    files = []
    for item in metadata["siblings"]:
        name = item["rfilename"]
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Unsafe model filename.")
        if not name.endswith((".json", ".safetensors", ".model", ".txt", ".jinja", ".tiktoken")):
            continue
        lfs = item.get("lfs") or {}
        checksum = lfs.get("sha256") or item.get("blobId")
        if not checksum or not isinstance(item.get("size"), int):
            raise ValueError(f"No verifiable model metadata for {name}.")
        files.append(
            {
                "name": name,
                "size": item["size"],
                "hash": checksum,
                "algorithm": "sha256" if lfs else "sha1",
                "url": f"https://huggingface.co/{repo}/resolve/{revision}/{name}",
            }
        )
    if not any(f["name"].endswith(".safetensors") for f in files):
        raise ValueError("Model plan contains no safetensors weights.")
    return {"repo": repo, "revision": revision, "files": files}


def download_models(root, repos, hf_cache, search_roots=(), move_weights=False, import_only=False):
    root.mkdir(parents=True, exist_ok=True)
    plans = []
    for repo in repos:
        key = repo.replace("/", "--")
        plan_file = root / (key + ".json")
        if plan_file.is_file():
            plan = json.loads(plan_file.read_text())
            if plan["repo"] != repo:
                raise ValueError("Cached model plan mismatch.")
        else:
            plan = make_plan(repo)
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
        if not re.fullmatch(r"[a-f0-9]{40}", plan["revision"]):
            raise ValueError("Invalid model revision.")
        for entry in plan["files"]:
            name = entry["name"]
            if (
                not name
                or "\\" in name
                or ":" in name
                or Path(name).is_absolute()
                or ".." in Path(name).parts
            ):
                raise ValueError("Unsafe cached model filename.")
            if (
                entry["algorithm"] not in {"sha1", "sha256"}
                or not re.fullmatch(
                    r"[a-f0-9]{40}" if entry["algorithm"] == "sha1" else r"[a-f0-9]{64}",
                    entry["hash"],
                )
                or not isinstance(entry["size"], int)
                or entry["size"] < 0
            ):
                raise ValueError("Invalid model integrity metadata.")
            entry["url"] = f"https://huggingface.co/{repo}/resolve/{plan['revision']}/{name}"
        plans.append(plan)
    # Reserve space for full replacement files, including corrupt existing caches.
    # Verified reuse may need less; never discover a full disk mid-download knowingly.
    if not import_only:
        required = sum(
            entry["size"]
            for plan in plans
            for entry in plan["files"]
            if not verify_file(
                root / plan["repo"].replace("/", "--") / plan["revision"] / entry["name"],
                entry["size"],
                entry["hash"],
                entry["algorithm"],
            )
        )
        if required > shutil.disk_usage(root).free:
            raise ValueError(f"Insufficient disk space: need {required} additional model bytes.")
    total = sum(f["size"] for p in plans for f in p["files"] if not import_only or is_weight(f))
    weight_sizes = {entry["size"] for plan in plans for entry in plan["files"] if is_weight(entry)}
    roots = list(dict.fromkeys([str(hf_cache), *search_roots]))
    discovered = scan_weights(roots, sizes=weight_sizes) if weight_sizes else {"files": []}
    emit(weight_discovery={**discovered, "status": "complete"})
    done, reused = 0, 0
    manifest = []
    verified_entries = []
    missing_weights = []
    result = {}
    for plan in plans:
        key = plan["repo"].replace("/", "--")
        target = root / key / plan["revision"]
        for entry in plan["files"]:
            if import_only and not is_weight(entry):
                continue
            destination = target / entry["name"]
            last_emit = [0.0]

            def progress(
                count, phase, entry=entry, plan=plan, done=done, reused=reused, last_emit=last_emit
            ):
                now = time.monotonic()
                if now - last_emit[0] >= 0.2 or count == entry["size"]:
                    emit(
                        download={
                            "file": entry["name"],
                            "phase": phase,
                            "repo": plan["repo"],
                            "file_bytes": count,
                            "file_total": entry["size"],
                            "completed_bytes": done + count,
                            "total_bytes": total,
                            "reused_files": reused,
                        }
                    )
                    last_emit[0] = now

            # External folders supply large current weights only, never configuration.
            if (
                not destination.exists()
                or destination.stat().st_size != entry["size"]
                or (
                    import_only
                    and not verify_file(
                        destination, entry["size"], entry["hash"], entry["algorithm"]
                    )
                )
            ):
                import_weight(entry, destination, discovered["files"], progress)
            if import_only and not verify_file(
                destination, entry["size"], entry["hash"], entry["algorithm"]
            ):
                missing_weights.append({"repo": plan["repo"], "file": entry["name"]})
                continue
            state = "verified cache" if import_only else fetch_file(entry, destination, progress)
            if state.startswith("verified"):
                reused += 1
            done += entry["size"]
            verified_entries.append((entry, destination))
            manifest.append(
                {
                    "path": str(destination),
                    "size": entry["size"],
                    "hash": entry["hash"],
                    "algorithm": entry["algorithm"],
                }
            )
            emit(
                download={
                    "file": entry["name"],
                    "repo": plan["repo"],
                    "file_bytes": entry["size"],
                    "file_total": entry["size"],
                    "completed_bytes": done,
                    "total_bytes": total,
                    "reused_files": reused,
                    "cache_status": state,
                }
            )
        result[plan["repo"]] = str(target)
    transfers = (
        move_verified_weights(verified_entries, discovered["files"], search_roots, verify_file)
        if move_weights
        else []
    )
    if transfers:
        receipt = root / "weight-import-receipt.json"
        receipt.write_text(json.dumps(transfers, indent=2), encoding="utf-8")
        emit(
            weight_import={
                "files": transfers,
                "moved_bytes": sum(t["bytes"] for t in transfers if t["moved"]),
            }
        )
    return {
        "paths": result,
        "files": manifest,
        "reused_files": reused,
        "weight_import": transfers,
        "missing_weights": missing_weights,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--asr-model", required=True)
    parser.add_argument("--hf-cache", type=Path, required=True)
    parser.add_argument("--search-root", action="append", default=[])
    parser.add_argument("--move-weights", action="store_true")
    parser.add_argument("--import-only", action="store_true")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    result = download_models(
        args.root,
        [args.model, args.asr_model],
        args.hf_cache,
        validate_roots(args.search_root),
        args.move_weights,
        args.import_only,
    )
    emit(**{"imported_models" if args.import_only else "models": result})


if __name__ == "__main__":
    main()
