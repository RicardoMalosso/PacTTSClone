"""Verify that the bundled jingling-keys clip is decodable with video AND audio."""
import hashlib
import json
import subprocess

from pacttsclone.app import STATIC


def test_jingling_keys_webm_has_video_and_audio():
    media = STATIC / "jingling-keys.webm"
    assert media.is_file(), "User-supplied jingling keys clip must be bundled locally"
    # Original user upload, unmodified: guards against a placeholder/transcode.
    assert hashlib.sha256(media.read_bytes()).hexdigest() == (
        "01f5003f1ad001452249af8939afdecd6cb7470d29772af7d18d038c41d3c894"
    )

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
