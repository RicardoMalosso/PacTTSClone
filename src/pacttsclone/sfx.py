"""Persistent, bounded audio uploads. Queued scripts copy assets before publication."""

import shutil
import tempfile
import uuid
from pathlib import Path

import soundfile as sf
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .domain import UserError
from .message_script import RESERVED


class SfxSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    title: str = Field(min_length=1, max_length=100)
    triggers: list[str] = Field(min_length=1, max_length=10)
    volume: float = Field(default=100, ge=0, le=300)
    duration: float | None = Field(default=None, ge=0.05, le=15)
    enabled: bool = True

    @field_validator("title")
    @classmethod
    def title_valid(cls, value):
        if not value.strip():
            raise ValueError("Provide a sound effect name.")
        return value.strip()

    @field_validator("triggers")
    @classmethod
    def triggers_valid(cls, values):
        import re

        result = []
        for value in values:
            value = value.strip().casefold()
            if not re.fullmatch(r"\[[a-z0-9_ -]{1,30}\]|\*{4}", value) or value in RESERVED:
                raise ValueError("Use [effect_name] or ****; model tags are reserved.")
            if value not in result:
                result.append(value)
        return result


class SoundEffects:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.root = service.settings.data_dir / "sfx"
        self.root.mkdir(exist_ok=True)

    def save(self, value, stream=None, effect_id=None):
        with self.service._lock:
            old = self.store.get("sfx", effect_id) if effect_id else None
            if effect_id and not old:
                raise UserError("Sound effect not found.")
            if not old and len(self.store.all("sfx")) >= 100:
                raise UserError("Maximum 100 sound effects.")
            used = {t for e in self.store.all("sfx") if e["id"] != effect_id for t in e["triggers"]}
            if used.intersection(value.triggers):
                raise UserError("A sound effect already uses that trigger.")
            effect_id = effect_id or uuid.uuid4().hex
            target = self.root / f"{effect_id}.wav"
            duration = old["audio_duration"] if old else None
            if stream is not None:
                with tempfile.TemporaryDirectory(dir=self.service.temporary) as tmp:
                    tmp = Path(tmp)
                    source, decoded = tmp / "upload", tmp / "effect.wav"
                    with source.open("wb") as out:
                        total = 0
                        while chunk := stream.read(1024 * 1024):
                            total += len(chunk)
                            if total > 10 * 1024 * 1024:
                                raise UserError("Sound effects must be at most 10 MiB.")
                            out.write(chunk)
                    self.service.audio._run(
                        self.service.settings.ffmpeg,
                        [
                            "-nostdin",
                            "-v",
                            "error",
                            "-y",
                            "-protocol_whitelist",
                            "file,pipe",
                            "-i",
                            str(source),
                            "-map",
                            "0:a:0",
                            "-vn",
                            "-t",
                            "15.1",
                            "-ac",
                            "1",
                            "-ar",
                            "48000",
                            "-c:a",
                            "pcm_s16le",
                            str(decoded),
                        ],
                    )
                    duration = sf.info(decoded).duration
                    if not 0.05 <= duration <= 15:
                        raise UserError("Sound effects must last 0.05–15 seconds.")
                    # A unique sibling keeps replacements atomic on the data drive.
                    pending = target.with_suffix(".new.wav")
                    try:
                        shutil.copyfile(decoded, pending)
                        pending.replace(target)
                    finally:
                        pending.unlink(missing_ok=True)
            elif not old:
                raise UserError("Upload an audio file for the sound effect.")
            return self.store.put(
                "sfx",
                effect_id,
                {
                    "id": effect_id,
                    **value.model_dump(),
                    "audio_duration": duration,
                    "audio_url": f"/api/sfx/{effect_id}/audio?v={uuid.uuid4().hex}",
                },
            )

    def delete(self, effect_id):
        with self.service._lock:
            if not self.store.get("sfx", effect_id):
                raise UserError("Sound effect not found.")
            self.store.delete("sfx", effect_id)
            (self.root / f"{effect_id}.wav").unlink(missing_ok=True)
