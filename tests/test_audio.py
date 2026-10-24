import json
import subprocess

import numpy as np
import pytest
import soundfile as sf

from pacttsclone.audio import AudioPipeline
from pacttsclone.config import Settings
from pacttsclone.domain import UserError, Waveform


def test_real_decode_encode_round_trip(mp3, tmp_path):
    pipeline = AudioPipeline(Settings(data_dir=tmp_path))
    assert pipeline.available()
    reference = tmp_path / "decoded.wav"
    pipeline.decode(mp3, reference)
    samples, rate = sf.read(reference)
    assert rate == 24000
    assert samples.ndim == 1
    assert 2.9 < len(samples) / rate < 3.1
    output = tmp_path / "output.mp3"
    pipeline.encode(Waveform(samples, rate), tmp_path, output)
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    stream = json.loads(result.stdout)["streams"][0]
    assert stream["codec_name"] == "mp3"
    assert int(stream["sample_rate"]) == 48000
    assert int(stream["bit_rate"]) == 192000
    assert not output.with_suffix(".partial.mp3").exists()


def test_rejects_corrupt(mp3, tmp_path):
    mp3.write_bytes(b"this is not an MP3")
    with pytest.raises(UserError, match="MP3"):
        AudioPipeline(Settings()).decode(mp3, tmp_path / "decoded.wav")


def test_rejects_wav_disguised_as_mp3(tmp_path):
    source = tmp_path / "source.wav"
    sf.write(source, np.ones(24000) * 0.1, 24000)
    disguised = tmp_path / "reference.mp3"
    source.rename(disguised)
    with pytest.raises(UserError, match="MP3 válido"):
        AudioPipeline(Settings()).decode(disguised, tmp_path / "decoded.wav")


@pytest.mark.parametrize("duration,silent", [(0.4, False), (30.5, False), (3, True)])
def test_rejects_duration_or_silence(duration, silent, tmp_path):
    source = tmp_path / "source.wav"
    samples = np.zeros(int(duration * 24000)) if silent else np.ones(int(duration * 24000)) * 0.1
    sf.write(source, samples, 24000)
    mp3 = tmp_path / "source.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-i",
            str(source),
            str(mp3),
        ],
        check=True,
    )
    with pytest.raises(UserError, match="silenciosa" if silent else "1 a 30"):
        AudioPipeline(Settings()).decode(mp3, tmp_path / "decoded.wav")


@pytest.mark.parametrize(
    "samples,rate",
    [
        ([], 24000),
        ([float("nan")], 24000),
        ([[0.1, 0.2]], 24000),
        ([0.1], 1),
    ],
)
def test_rejects_invalid_model_output(samples, rate, tmp_path):
    with pytest.raises(UserError, match="inválido"):
        AudioPipeline(Settings()).encode(
            Waveform(np.array(samples), rate), tmp_path, tmp_path / "out.mp3"
        )


def test_missing_ffmpeg_is_actionable(tmp_path):
    pipeline = AudioPipeline(Settings(ffprobe="pactts-nonexistent-command"))
    assert not pipeline.available()
    with pytest.raises(UserError, match="Instale FFmpeg"):
        pipeline.decode(tmp_path / "ref.mp3", tmp_path / "out.wav")


def test_encode_failure_cleans_partial(monkeypatch, tmp_path):
    pipeline = AudioPipeline(Settings())
    output = tmp_path / "out.mp3"

    def fail(*args):
        output.with_suffix(".partial.mp3").write_bytes(b"partial")
        raise UserError("encoder failed")

    monkeypatch.setattr(pipeline, "_run", fail)
    with pytest.raises(UserError, match="encoder failed"):
        pipeline.encode(Waveform(np.ones(24000), 24000), tmp_path, output)
    assert not output.exists()
    assert not output.with_suffix(".partial.mp3").exists()
