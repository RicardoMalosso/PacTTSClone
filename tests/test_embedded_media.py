"""Verify that the bundled jingling-keys clip is decodable with video AND audio."""
import json
import subprocess

from pacttsclone.app import STATIC


def test_jingling_keys_webm_has_video_and_audio():
    media = STATIC / "jingling-keys.webm"
    assert media.is_file(), "User-supplied jingling keys clip must be bundled locally"
    assert media.stat().st_size > 1000

    inspection = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_name,codec_type:format=duration", "-of", "json", str(media)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    info = json.loads(inspection.stdout)
    streams = {(stream["codec_type"], stream["codec_name"]) for stream in info["streams"]}
    assert ("video", "vp9") in streams
    assert ("audio", "opus") in streams
    assert 4.0 <= float(info["format"]["duration"]) <= 6.0

    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(media),
         "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True, check=True, timeout=30,
    )
