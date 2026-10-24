import hashlib
import io
import json
import shutil
import tempfile
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .config import MAX_UPLOAD_BYTES
from .domain import GenerationRequest, UserError

BUILTIN_CATALOG = Path(__file__).parent / "assets" / "voices" / "catalog.json"


class Voices:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.root = service.settings.data_dir / "voices"
        self.root.mkdir(exist_ok=True)
        for voice in self.store.all("voice"):
            if voice["status"] == "pending":
                job = self.store.get("job", voice.get("preparation_job_id", ""))
                if not job or job["status"] in {"cancelled", "failed"}:
                    self.store.patch(
                        "voice",
                        voice["id"],
                        status="cancelled",
                        error="Reference preparation was interrupted. Retry transcription.",
                    )

    def seed_defaults(self):
        if BUILTIN_CATALOG is None:
            return  # Explicit test isolation; production always uses the packaged catalog.
        catalog = json.loads(BUILTIN_CATALOG.read_text(encoding="utf-8"))
        for entry in catalog:
            key = entry["key"]
            if self.store.get("builtin_voice", key):
                continue
            voice_id = uuid.uuid5(uuid.NAMESPACE_URL, "pacttsclone-default:" + key).hex
            if not self.store.get("voice", voice_id):
                source = BUILTIN_CATALOG.parent / entry["filename"]
                if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                    raise UserError("A bundled voice reference failed its integrity check.")
                folder = self.root / voice_id
                folder.mkdir(exist_ok=True)
                shutil.copyfile(source, folder / "reference.mp3")
                self.store.put(
                    "voice",
                    voice_id,
                    {
                        "id": voice_id,
                        "title": entry["title"],
                        "original_filename": entry["original_filename"],
                        "transcript": "",
                        "status": "unprepared",
                        "thumbnail_url": None,
                        "error": None,
                        "builtin_key": key,
                    },
                )
            # Keep this marker after deletion so upgrades never resurrect user-deleted presets.
            self.store.put("builtin_voice", key, {"initialized": True, "voice_id": voice_id})

    def create(self, stream, title, filename, transcript="", thumbnail=None):
        title, transcript = title.strip(), transcript.strip()
        if not title or len(title) > 100 or len(transcript) > 4000:
            raise UserError(
                "Use a title of 1–100 characters and a transcript up to 4000 characters."
            )
        if not filename.lower().endswith(".mp3"):
            raise UserError("Choose an MP3 reference.")
        voice_id = uuid.uuid4().hex
        folder = self.root / voice_id
        folder.mkdir()
        try:
            path = folder / "reference.mp3"
            total = 0
            with path.open("wb") as target:
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise UserError("MP3 exceeds 20 MiB.")
                    target.write(chunk)
            with tempfile.TemporaryDirectory(dir=self.service.temporary) as tmp:
                self.service.audio.decode(path, Path(tmp) / "reference.wav")
            thumb_url = None
            if thumbnail:
                if len(thumbnail) > 2 * 1024 * 1024:
                    raise UserError("Thumbnail exceeds 2 MiB.")
                try:
                    with Image.open(io.BytesIO(thumbnail)) as image:
                        if image.width * image.height > 16_000_000:
                            raise UserError("Thumbnail dimensions are too large.")
                        image.thumbnail((320, 320))
                        image.convert("RGB").save(folder / "thumbnail.jpg", "JPEG", quality=85)
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                    raise UserError("Choose a valid PNG, JPEG or WebP thumbnail.") from exc
                thumb_url = f"/api/voices/{voice_id}/thumbnail"
            voice = {
                "id": voice_id,
                "title": title,
                "original_filename": filename.replace("\\", "/").rsplit("/", 1)[-1][:255],
                "transcript": transcript,
                "status": "ready" if transcript else "pending",
                "thumbnail_url": thumb_url,
                "error": None,
            }
            self.store.put("voice", voice_id, voice)
            if not transcript:
                self.prepare(voice_id)
            return self.store.get("voice", voice_id)
        except Exception:
            self.store.delete("voice", voice_id)
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def prepare(self, voice_id):
        voice = self.store.get("voice", voice_id)
        if not voice:
            raise UserError("Voice not found.")
        with self.service._lock:
            voice = self.store.get("voice", voice_id)
            if voice["status"] == "ready" and voice.get("transcript"):
                return voice
            if voice["status"] == "pending":
                current = self.store.get("job", voice.get("preparation_job_id", ""))
                if current and current["status"] in {"queued", "running"}:
                    return voice
                if current and current["status"] == "succeeded":
                    self.completed(current)
                    return self.store.get("voice", voice_id)
            with (self.root / voice_id / "reference.mp3").open("rb") as ref:
                job = self.service.submit(
                    ref,
                    GenerationRequest(text="Reference preparation"),
                    allow_queue=True,
                    voice_id=voice_id,
                    kind="transcribe",
                )
            return self.store.patch(
                "voice", voice_id, preparation_job_id=job["id"], status="pending", error=None
            )

    def completed(self, job):
        if job.get("voice_id") and job["kind"] == "transcribe":
            voice = self.store.get("voice", job["voice_id"])
            if (
                voice
                and voice["status"] == "pending"
                and voice.get("preparation_job_id") == job["id"]
            ):
                self.store.patch(
                    "voice",
                    job["voice_id"],
                    status="ready" if job["status"] == "succeeded" else job["status"],
                    transcript=job.get("transcript", ""),
                    error=job.get("error"),
                )

    def generate(self, voice_id, request, channel=None, username=None):
        voice = self.store.get("voice", voice_id)
        if not voice or voice["status"] != "ready":
            raise UserError("This voice is not ready. Finish or retry its transcription first.")
        request = request.model_copy(update={"ref_text": voice["transcript"]})
        with self.service._lock:
            with (self.root / voice_id / "reference.mp3").open("rb") as reference:
                result = self.service.submit(
                    reference,
                    request,
                    allow_queue=True,
                    voice_id=voice_id,
                    channel=channel,
                    username=username,
                    original_filename=voice["original_filename"],
                )
            self.store.patch("job", result["id"], voice_title=voice["title"])
            return self.service.get(result["id"])

    def update(self, voice_id, title, transcript):
        voice = self.store.get("voice", voice_id)
        if not voice:
            return None
        if any(j.get("voice_id") == voice_id for j in self.service.pending()):
            raise UserError("Wait for this voice to finish or cancel its jobs before editing.")
        if (
            not title.strip()
            or len(title) > 100
            or not transcript.strip()
            or len(transcript) > 4000
        ):
            raise UserError("Provide a title and an exact nonempty reference transcript.")
        return self.store.patch(
            "voice",
            voice_id,
            title=title.strip(),
            transcript=transcript.strip(),
            status="ready",
            error=None,
        )

    def delete(self, voice_id):
        if any(j.get("voice_id") == voice_id for j in self.service.pending()):
            raise UserError("Cancel or finish this voice's jobs before deleting it.")
        self.store.delete("voice", voice_id)
        shutil.rmtree(self.root / voice_id, ignore_errors=True)
