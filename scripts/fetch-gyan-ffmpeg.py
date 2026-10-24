"""Fetch and verify the upstream gyan.dev Windows FFmpeg Essentials release.

No Chocolatey, 7-Zip, system FFmpeg, MSYS2 or Git is required.
This runs on GitHub Actions; the installer embeds only ffmpeg.exe and ffprobe.exe.
"""
import hashlib
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

BASE = "https://www.gyan.dev/ffmpeg/builds/"
NAME = "ffmpeg-release-essentials.zip"
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "installer" / "ffmpeg"


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PacTTSClone-build/0.3.0rc5"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def main() -> None:
    expected_text = get(BASE + NAME + ".sha256").decode("utf-8").strip()
    match = re.search(r"(?i)\\b([a-f0-9]{64})\\b", expected_text)
    if not match:
        raise ValueError("No SHA256 in gyan.dev checksum response")
    expected = match.group(1).lower()
    archive = get(BASE + NAME)
    actual = hashlib.sha256(archive).hexdigest()
    if actual != expected:
        raise ValueError(f"FFmpeg archive SHA256 mismatch: {actual} != {expected}")
    OUTPUT.joinpath("bin").mkdir(parents=True, exist_ok=True)
    OUTPUT.joinpath("licenses").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        folder = pathlib.Path(tmp)
        zip_path = folder / NAME
        zip_path.write_bytes(archive)
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            for tool in ("ffmpeg.exe", "ffprobe.exe"):
                matches = [n for n in names if n.lower().endswith("/bin/" + tool)]
                if len(matches) != 1:
                    raise ValueError(f"Expected one {tool} in archive, found {len(matches)}")
                with z.open(matches[0]) as source, (OUTPUT / "bin" / tool).open("wb") as target:
                    shutil.copyfileobj(source, target)
            for filename in ("LICENSE", "README.txt"):
                matches = [n for n in names if n.lower().endswith("/" + filename.lower())]
                if matches:
                    with z.open(matches[0]) as source:
                        (OUTPUT / "licenses" / filename).write_bytes(source.read())
    ffmpeg = OUTPUT / "bin" / "ffmpeg.exe"
    ffprobe = OUTPUT / "bin" / "ffprobe.exe"
    subprocess.run([str(ffmpeg), "-version"], check=True, capture_output=True)
    subprocess.run([str(ffprobe), "-version"], check=True, capture_output=True)
    # Regression for Transformers ffmpeg_read's exact raw float32 output.
    with tempfile.TemporaryDirectory() as tmp:
        wav = pathlib.Path(tmp) / "input.wav"
        subprocess.run(
            [str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
             "-t", "1", "-acodec", "pcm_s16le", "-y", str(wav)],
            check=True, capture_output=True,
        )
        result = subprocess.run(
            [str(ffmpeg), "-i", "pipe:0", "-ac", "1", "-ar", "16000",
             "-f", "f32le", "-hide_banner", "-loglevel", "quiet", "pipe:1"],
            input=wav.read_bytes(), capture_output=True, check=True,
        )
        if len(result.stdout) != 16000 * 4:
            raise AssertionError(f"Expected 64000 bytes of float32 PCM, got {len(result.stdout)}")
    (OUTPUT / "BUILD-PROVENANCE.txt").write_text(
        "FFmpeg distributor: Gyan Doshi, gyan.dev\\n"
        f"URL: {BASE}{NAME}\\nSHA256: {actual}\\n"
        "Variant: Windows 64-bit release essentials (static, GPLv3)\\n"
        "Verification: SHA256 and ffmpeg_read f32le PCM smoke test\\n",
        encoding="utf-8",
    )
    print(f"Verified gyan.dev FFmpeg: {actual}")


if __name__ == "__main__":
    main()
