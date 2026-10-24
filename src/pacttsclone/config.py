from dataclasses import dataclass, field
from pathlib import Path

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + 2 * 1024 * 1024 + 128 * 1024


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path.home() / ".pacttsclone")
    device: str = "auto"
    model: str = "k2-fsa/OmniVoice"
    asr_model: str = "openai/whisper-small"
    offline: bool = False
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
