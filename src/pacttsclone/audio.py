import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import Settings
from .domain import UserError, Waveform


class AudioPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings

    def available(self) -> bool:
        return all(shutil.which(x) for x in (self.settings.ffmpeg, self.settings.ffprobe))

    def _run(self, executable: str, args: list[str]) -> str:
        try:
            result = subprocess.run(
                [executable, *args],
                capture_output=True,
                timeout=60,
                check=True,
            )
            return result.stdout.decode("utf-8", errors="replace")
        except FileNotFoundError as exc:
            raise UserError("Instale FFmpeg (ffmpeg e ffprobe) e adicione ao PATH.") from exc
        except subprocess.TimeoutExpired as exc:
            raise UserError("O processamento de áudio excedeu 60 segundos.") from exc
        except subprocess.CalledProcessError as exc:
            raise UserError(
                "Não foi possível processar o áudio. Verifique se o MP3 é válido."
            ) from exc

    def decode(self, source: Path, destination: Path) -> None:
        metadata = self._run(
            self.settings.ffprobe,
            [
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "json",
                str(source),
            ],
        )
        try:
            streams = json.loads(metadata).get("streams", [])
            valid = streams and streams[0].get("codec_name") == "mp3"
        except (ValueError, TypeError, KeyError) as exc:
            raise UserError("Não foi possível identificar o MP3.") from exc
        if not valid:
            raise UserError("A referência precisa ser um arquivo MP3 válido.")
        self._run(
            self.settings.ffmpeg,
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
                "31",
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
        )
        info = sf.info(destination)
        if not 1 <= info.duration <= 30:
            raise UserError("Use uma referência de 1 a 30 segundos; recomendado: 3 a 10 segundos.")
        samples, _ = sf.read(destination)
        if np.max(np.abs(samples)) < 0.0001:
            raise UserError("A referência está silenciosa. Escolha um trecho com fala audível.")

    def encode(self, waveform: Waveform, workspace: Path, destination: Path) -> None:
        values = np.asarray(waveform.samples, dtype=np.float32)
        if (
            values.ndim != 1
            or not values.size
            or not np.isfinite(values).all()
            or not 8000 <= waveform.sample_rate <= 192000
            or values.size > waveform.sample_rate * 600
        ):
            raise UserError("O modelo retornou áudio inválido ou maior que 10 minutos.")
        pcm = workspace / "generated.wav"
        sf.write(pcm, np.clip(values, -1, 1), waveform.sample_rate, subtype="PCM_16")
        # Encode beside the final file, then atomically publish after success.
        temporary = destination.with_suffix(".partial.mp3")
        try:
            self._run(
                self.settings.ffmpeg,
                [
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(pcm),
                    "-map_metadata",
                    "-1",
                    "-c:a",
                    "libmp3lame",
                    "-ar",
                    "48000",
                    "-b:a",
                    "192k",
                    str(temporary),
                ],
            )
            if not temporary.exists() or temporary.stat().st_size == 0:
                raise UserError("FFmpeg não produziu um MP3 válido.")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
