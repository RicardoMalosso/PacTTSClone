#!/usr/bin/env bash
set -euo pipefail
# Official upstream FFmpeg source, pinned rather than a mutable branch/tag.
commit=8ae0b34901ba60a802f183ee75a250a9fc3e09a5
source_dir="$GITHUB_WORKSPACE/build-sources/ffmpeg"
output="$GITHUB_WORKSPACE/installer/ffmpeg"
mkdir -p "$output/bin" "$output/licenses"
cd "$source_dir"
test "$(git rev-parse HEAD)" = "$commit"
# The compiler and LAME development library come from signature-verified MSYS2
# packages. We do NOT download any precompiled FFmpeg distribution.
./configure --disable-everything --disable-autodetect --disable-network \
  --disable-doc --disable-debug --disable-shared --enable-static --disable-ffplay \
  --enable-ffmpeg --enable-ffprobe --enable-small \
  --enable-protocol=file,pipe --enable-demuxer=mp3,wav --enable-muxer=mp3,wav \
  --enable-decoder=mp3float,pcm_s16le,pcm_f32le,pcm_s24le,pcm_s32le \
  --enable-encoder=libmp3lame,pcm_s16le --enable-parser=mpegaudio \
  --enable-filter=aresample,aformat,anull --enable-libmp3lame \
  --pkg-config-flags=--static --extra-ldflags=-static
make -j"$(nproc)" ffmpeg.exe ffprobe.exe
cp ffmpeg.exe ffprobe.exe "$output/bin/"
cp COPYING.LGPLv2.1 LICENSE.md "$output/licenses/"
# The signed LAME package does not install a COPYING file. Include its exact
# upstream source/license and MSYS2 patch recipe instead of guessing a file path.
case "$(pacman -Q mingw-w64-x86_64-lame)" in
  "mingw-w64-x86_64-lame 3.100-3") ;;
  *) echo "Update source/license manifest for the installed LAME version." >&2; exit 1 ;;
esac
pushd "$output" >/dev/null
python - <<'PYLAME'
import hashlib
import pathlib
import tarfile
import urllib.request

name = "lame-3.100.tar.gz"
with urllib.request.urlopen("https://downloads.sourceforge.net/project/lame/lame/3.100/" + name, timeout=60) as response:
    data = response.read()
assert hashlib.sha256(data).hexdigest() == "ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e", "LAME source integrity failure"
pathlib.Path(name).write_bytes(data)
with tarfile.open(name) as archive:
    for filename in ["COPYING", "README"]:
        pathlib.Path("licenses", "LAME-" + filename).write_bytes(archive.extractfile("lame-3.100/" + filename).read())
base = "https://raw.githubusercontent.com/msys2/MINGW-packages/c9e5b84b9bd7ac93517ffc177522606b9762c1e5/mingw-w64-lame/"
recipe = pathlib.Path("lame-build-recipe")
recipe.mkdir(exist_ok=True)
files = ["PKGBUILD", "0002-07-field-width-fix.all.patch", "0005-no-gtk.all.patch", "0006-dont-use-outdated-symbol-list.patch", "0007-revert-posix-code.patch", "0008-skip-termcap.patch", "0009-lame-add-pkgconfig.patch"]
for filename in files:
    with urllib.request.urlopen(base + filename, timeout=30) as response:
        (recipe / filename).write_bytes(response.read())
PYLAME
popd >/dev/null

{
 echo "FFmpeg official source: https://github.com/FFmpeg/FFmpeg"
 echo "Commit: $commit"
 echo "Recipe: installer/build-ffmpeg.sh"
 echo "Toolchain/package versions (MSYS2 packages verified by pacman signatures):"
 pacman -Q
 echo "Executable SHA-256:"
 sha256sum "$output"/bin/*.exe
 echo "Compiler:"
 gcc --version
} > "$output/BUILD-PROVENANCE.txt"
git archive --format=tar.gz --output="$output/ffmpeg-source.tar.gz" HEAD
# Basic real MP3 round-trip; CI later exercises the installed application too.
python -c 'import wave; w=wave.open("smoke.wav","wb"); w.setparams((1,2,24000,0,"NONE","NONE")); w.writeframes(bytes(48000)); w.close()'
./ffmpeg.exe -v error -y -i smoke.wav -ar 48000 -b:a 192k "$output/test.mp3"
./ffprobe.exe -v error -show_entries format=duration "$output/test.mp3"
rm -f "$output/test.mp3" smoke.wav
