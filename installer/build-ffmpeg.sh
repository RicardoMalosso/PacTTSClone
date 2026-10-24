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
make -j2 ffmpeg.exe ffprobe.exe
cp ffmpeg.exe ffprobe.exe "$output/bin/"
cp COPYING.LGPLv2.1 LICENSE.md "$output/licenses/"
cp /mingw64/share/licenses/lame/COPYING "$output/licenses/LAME-COPYING" \
  || cp /mingw64/share/licenses/lame/LICENSE "$output/licenses/LAME-COPYING"
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
