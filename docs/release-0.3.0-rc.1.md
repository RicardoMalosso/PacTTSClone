PacTTSClone 0.3.0-rc.1 introduces a small, unsigned Windows x64 bootstrap installer.

Download `PacTTSClone-Setup-0.3.0-rc.1.exe`. No existing Python, FFmpeg or Git is
required. Setup downloads an isolated runtime and CPU/NVIDIA dependencies into
your selected folders. Models download separately on first use. Total downloaded
and installed content can still occupy several GB; the setup executable is small.

- Choose independent application/data locations, including another drive.
- Automatic/NVIDIA/CPU dependency selection; Start Menu and optional desktop icon.
- Verified uv/FFmpeg downloads, setup log, reusable download caches.
- Data (voices, recordings, settings, models) retained through updates/uninstall.
- Includes Gruvbox Dark, persistent locale choices, refreshed voice dropdowns,
  general OBS playback at `/playbackMain`, Twitch queues and Ctrl+C worker fix.

The installer is unsigned. SHA256SUMS.txt provides integrity checks, not trusted
publisher identity or a guarantee against Windows reputation prompts.

Preview limitations: GPU setup on physical hardware and interactive wizard behavior
require separate acceptance testing. Automated Windows smoke installs real CPU
dependencies, imports the runtime, starts the HTTP app, repeats setup and uninstalls;
it does not download model weights or establish real voice quality/latency.

This is a draft prerelease, not a stable deployment recommendation. A private
repository keeps release downloads private; no visibility change is performed.
