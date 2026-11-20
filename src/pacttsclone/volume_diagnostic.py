"""Local, deterministic checks for a saved voice's MP3 output gain."""

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .domain import UserError, Waveform


def _measure(path: Path) -> dict:
    samples, rate = sf.read(path, dtype="float32")
    if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all():
        raise UserError("The local volume test produced invalid MP3 audio.")
    return {
        "sample_rate_hz": rate,
        "duration_seconds": round(len(samples) / rate, 4),
        "rms": float(np.sqrt(np.mean(np.square(samples, dtype=np.float64)))),
        "peak": float(np.max(np.abs(samples))),
        "file_bytes": path.stat().st_size,
    }


def run_volume_diagnostic(service, studio, voice_id: str) -> dict:
    """Encode and measure a small synthetic signal at 100% and the saved voice gain."""
    voice, volume = studio.voices.volume_setting(voice_id)
    if not service.audio.available():
        raise UserError("FFmpeg and ffprobe are required for the local volume test.")

    rate = 48000
    duration = 0.5
    frequency = 440
    amplitude = 0.08
    times = np.arange(round(rate * duration), dtype=np.float32) / rate
    samples = (amplitude * np.sin(2 * np.pi * frequency * times)).astype(np.float32)
    input_rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))

    with tempfile.TemporaryDirectory(dir=service.temporary, prefix="volume-test-") as folder:
        workspace = Path(folder)
        baseline_path = workspace / "baseline.mp3"
        configured_path = workspace / "configured.mp3"
        waveform = Waveform(samples, rate)
        service.audio.encode(waveform, workspace, baseline_path, volume=100)
        service.audio.encode(waveform, workspace, configured_path, volume=volume)
        baseline = _measure(baseline_path)
        configured = _measure(configured_path)

    expected_ratio = volume / 100
    measured_ratio = configured["rms"] / baseline["rms"] if baseline["rms"] else 0.0
    expected_rms = input_rms * expected_ratio
    if volume == 0:
        gain_matches = configured["rms"] <= max(0.0002, baseline["rms"] * 0.02)
        error_percent = None
    else:
        error_percent = abs(measured_ratio - expected_ratio) / expected_ratio * 100
        gain_matches = error_percent <= 10

    baseline = {key: round(value, 7) if isinstance(value, float) else value
                for key, value in baseline.items()}
    configured = {key: round(value, 7) if isinstance(value, float) else value
                  for key, value in configured.items()}
    report = {
        "schema_version": 1,
        "diagnostic": "local-volume-test",
        "engine": service.settings.engine_id,
        "voice_title": voice["title"],
        "saved_volume_percent": volume,
        "signal": {
            "type": "synthetic_sine_tone",
            "frequency_hz": frequency,
            "duration_seconds": duration,
            "sample_rate_hz": rate,
            "input_rms": round(input_rms, 7),
        },
        "baseline_100_percent": baseline,
        "configured_volume_output": configured,
        "expected_gain_ratio": round(expected_ratio, 5),
        "measured_gain_ratio": round(measured_ratio, 5),
        "expected_rms": round(expected_rms, 7),
        "gain_error_percent": round(error_percent, 2) if error_percent is not None else None,
        "checks": {
            "gain_matches_saved_setting": gain_matches,
            "output_clipped": configured["peak"] >= 0.999,
            "temporary_files_removed": True,
        },
        "result": "pass" if gain_matches and configured["peak"] < 0.999 else "fail",
        "scope": (
            "Runs locally without model inference, reference audio, or network requests. "
            "Measures the saved voice gain through the production MP3 encoder. It cannot "
            "inspect OBS mixer levels, filters, or physical speaker output."
        ),
    }
    return report
