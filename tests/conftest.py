import subprocess
import time

import numpy as np
import pytest
import soundfile as sf

from pacttsclone.domain import Waveform


class FakeEngine:
    def __init__(self):
        self.calls = []

    def synthesize(self, reference, request):
        self.calls.append((reference, request))
        # Deliberately synthetic audio for application tests only.
        samples = 0.1 * np.sin(2 * np.pi * 440 * np.arange(24000) / 24000)
        return Waveform(samples, 24000)


@pytest.fixture
def engine():
    return FakeEngine()


@pytest.fixture
def mp3(tmp_path):
    wav = tmp_path / "source.wav"
    samples = 0.1 * np.sin(2 * np.pi * 220 * np.arange(72000) / 24000)
    sf.write(wav, samples, 24000)
    path = tmp_path / "reference.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(wav),
            "-c:a",
            "libmp3lame",
            str(path),
        ],
        check=True,
    )
    return path


def wait_job(service, job_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Job failed to reach terminal state")
