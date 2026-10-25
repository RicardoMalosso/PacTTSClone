"""Optional additive migration of irreplaceable user data; source remains untouched."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from .domain import UserError
from .models import AppConfig, ChannelConfig


def source_folder(value):
    if not isinstance(value, str) or not value.strip():
        raise UserError("Choose the previous installation data folder.")
    path = Path(value).expanduser()
    if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
        raise UserError("Choose an absolute local data folder path.")
    path = path.resolve()
    if (
        not (path / "pacttsclone.sqlite3").is_file()
        and (path / "data/pacttsclone.sqlite3").is_file()
    ):
        path = path / "data"
    if not (path / "pacttsclone.sqlite3").is_file():
        raise UserError("No PacTTSClone database found. Choose its data folder, not only cache.")
    return path


def safe_file(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise UserError("An imported asset points outside the selected data folder.")
    return path


def copy_verified(source, target, stop, progress):
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as src, target.open("wb") as dst:
        while chunk := src.read(1024 * 1024):
            if stop.is_set():
                raise InterruptedError("Import cancelled; source data was retained.")
            digest.update(chunk)
            dst.write(chunk)
            progress(len(chunk))
        dst.flush()
        os.fsync(dst.fileno())
    check = hashlib.sha256()
    with target.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check.update(chunk)
    if check.digest() != digest.digest():
        raise UserError("Imported asset verification failed; no data was activated.")


def import_personal_data(studio, folder, sections, replace_config, stop, report):
    if (
        not isinstance(sections, list)
        or not sections
        or any(not isinstance(s, str) or s not in {"config", "voices", "outputs"} for s in sections)
        or not isinstance(replace_config, bool)
    ):
        raise UserError("Select configuration, voices and/or outputs to import.")
    source = source_folder(folder)
    service, store = studio.service, studio.store
    if source == service.settings.data_dir.resolve():
        raise UserError("The selected source is the current data folder.")
    stage = Path(tempfile.mkdtemp(prefix="import-", dir=service.temporary))
    installed = []
    result = {"voices": 0, "outputs": 0, "channels": 0, "bytes": 0, "warnings": []}
    try:
        # SQLite backup takes a consistent committed snapshot including WAL contents.
        old = sqlite3.connect((source / "pacttsclone.sqlite3").as_uri() + "?mode=ro", uri=True)
        snapshot = sqlite3.connect(stage / "source.sqlite3")
        try:
            old.backup(snapshot)
            rows = snapshot.execute("SELECT kind,id,data FROM records LIMIT 100001").fetchall()
        except sqlite3.DatabaseError as exc:
            raise UserError("The old database is unreadable or incompatible.") from exc
        finally:
            old.close()
            snapshot.close()
        if len(rows) > 100000:
            raise UserError("The old database exceeds the supported import size.")
        records = {}
        for kind, key, raw in rows:
            if kind not in {"voice", "job", "channel", "config", "identity"}:
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise UserError("Invalid record in the old database.")
            records[(kind, key)] = value
        identity = records.get(("identity", "installation"), {}).get("id", str(source))
        namespace = uuid.UUID(service.installation_id)

        def mapped(kind, key):
            return uuid.uuid5(namespace, f"import:{identity}:{kind}:{key}").hex

        def progress(count):
            result["bytes"] += count
            report(dict(result))

        voice_ids = {}
        pending = []
        assets = []
        for (kind, old_id), value in records.items():
            if kind != "voice" or not re.fullmatch("[a-f0-9]{32}", old_id):
                continue
            new_id = mapped("voice", old_id)
            if "voices" not in sections:
                if store.get("voice", old_id):
                    voice_ids[old_id] = old_id
                continue
            voice_ids[old_id] = new_id
            if store.get("voice", new_id):
                continue
            reference = safe_file(source, Path("voices") / old_id / "reference.mp3")
            if not reference.is_file():
                result["warnings"].append(f"Missing voice reference: {value.get('title', old_id)}")
                voice_ids.pop(old_id)
                continue
            folder_stage = stage / "voices" / new_id
            copy_verified(reference, folder_stage / "reference.mp3", stop, progress)
            thumb = safe_file(source, Path("voices") / old_id / "thumbnail.jpg")
            if thumb.is_file():
                copy_verified(thumb, folder_stage / "thumbnail.jpg", stop, progress)
            imported = {
                **value,
                "id": new_id,
                "preparation_job_id": None,
                "status": "ready" if value.get("transcript") else "unprepared",
                "thumbnail_url": f"/api/voices/{new_id}/thumbnail" if thumb.is_file() else None,
                "error": None,
                "import_source_id": old_id,
            }
            pending.append(("voice", new_id, imported, False))
            assets.append((folder_stage, studio.voices.root / new_id))
            result["voices"] += 1
        if "outputs" in sections:
            outputs = source / "outputs"
            if outputs.is_dir():
                for audio in outputs.iterdir():
                    if (
                        not audio.is_file()
                        or audio.suffix.lower() != ".mp3"
                        or audio.name.endswith(".partial.mp3")
                    ):
                        continue
                    audio = safe_file(source, Path("outputs") / audio.name)
                    old_id = audio.stem
                    new_id = mapped("job", old_id)
                    if store.get("job", new_id):
                        continue
                    copy_verified(audio, stage / "outputs" / f"{new_id}.mp3", stop, progress)
                    original = records.get(("job", old_id), {})
                    imported = {
                        **original,
                        "id": new_id,
                        "kind": "speech",
                        "status": "succeeded",
                        "stage": "Imported audio",
                        "workspace": "",
                        "output_url": f"/api/jobs/{new_id}/audio",
                        "created_at": original.get("created_at", time.time()),
                        "finished_at": original.get("finished_at") or time.time(),
                        "elapsed_seconds": original.get("elapsed_seconds", 0),
                        "request": original.get("request", {"text": "Imported audio"}),
                        "voice_id": voice_ids.get(original.get("voice_id")),
                        "error": None,
                        "original_filename": original.get("original_filename") or audio.name,
                        "metrics": original.get("metrics", {}),
                        "resources": {},
                        "general_playback_item_id": None,
                        "import_source_id": old_id,
                    }
                    if not isinstance(imported["request"], dict) or not isinstance(
                        imported["request"].get("text"), str
                    ):
                        raise UserError("Invalid audio history record in the old database.")
                    pending.append(("job", new_id, imported, False))
                    assets.append(
                        (stage / "outputs" / f"{new_id}.mp3", service.output_path(new_id))
                    )
                    result["outputs"] += 1
        imported_config = None
        if "config" in sections:
            if replace_config and ("config", "main") in records:
                imported_config = AppConfig.model_validate(records[("config", "main")])
                pending.append(("config", "main", imported_config.model_dump(), True))
            for (kind, key), value in records.items():
                if kind != "channel":
                    continue
                if store.get("channel", key):
                    result["warnings"].append(f"Existing channel settings retained: {key}")
                    continue
                value = {k: v for k, v in value.items() if k in ChannelConfig.model_fields}
                value["commands"] = {
                    cmd: voice_ids[v]
                    for cmd, v in value.get("commands", {}).items()
                    if v in voice_ids
                }
                value["event_rules"] = [
                    {**r, "voice_id": voice_ids[r["voice_id"]]}
                    for r in value.get("event_rules", [])
                    if r.get("voice_id") in voice_ids
                ]
                value.update(enabled=False, paused=True)
                channel = ChannelConfig.model_validate(value)
                pending.append(("channel", channel.name, channel.model_dump(), False))
                result["channels"] += 1
        if stop.is_set():
            raise InterruptedError("Import cancelled; source data was retained.")
        # Back up current metadata before the one transaction. Never overwrite existing assets.
        backups = service.settings.data_dir / "import-backups"
        backups.mkdir(exist_ok=True)
        backup_path = backups / (
            time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8] + ".sqlite3"
        )
        with service._lock, store.lock:
            backup = sqlite3.connect(backup_path)
            try:
                store.db.backup(backup)
            finally:
                backup.close()
            try:
                for temporary, destination in assets:
                    if destination.exists():
                        raise UserError(
                            "An import destination already exists; current data was retained."
                        )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    temporary.replace(destination)
                    installed.append(destination)
                with store.db:
                    for kind, key, value, replace in pending:
                        verb = "REPLACE" if replace else "IGNORE"
                        store.db.execute(
                            f"INSERT OR {verb} INTO records VALUES (?,?,?,?)",
                            (kind, key, json.dumps(value, ensure_ascii=False), time.time()),
                        )
            except Exception:
                for path in installed:
                    if path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        path.unlink(missing_ok=True)
                raise
            if imported_config:
                service.runner.reset()
                service.config = imported_config
                studio.hotkey.configure(imported_config.hotkey)
        result["backup"] = str(backup_path)
        report(dict(result))
        return result
    finally:
        shutil.rmtree(stage, ignore_errors=True)
