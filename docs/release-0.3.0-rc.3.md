PacTTSClone 0.3.0-rc.3 introduces a small, unsigned Windows x64 bootstrap installer.

Download `PacTTSClone-Setup-0.3.0-rc.3.exe`. No existing Python, FFmpeg or Git is
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

RC2 installer changes: red Step 1 download/storage notice with a five-second Next
lock; default app/data sibling folders with a checkbox for separate data storage;
small red bold space estimates beside both path pickers; explicit uninstaller
shortcuts in the Start Menu and application directory. User data remains retained.
Size figures are planning estimates; recordings/caches can grow without a fixed cap.

A parent-folder PacTTSClone.lnk launches the app directly. Defaults live under
PacTTS/PacTTSClone and PacTTS/PacTTSClone-data. Includes user-supplied Akuma Lady,
Dilma, Chrétien and lula references, initially unprepared; explicit preparation
saves transcripts once and exposes progress/cancel/retry. Akuma Lady is shortened
to 29.9 seconds to fit the reference limit; other samples remain unchanged.

RC3 adds a Report a bug tab with the project owner's video guide. The YouTube
iframe is created only three seconds after explicitly opening the tab; leaving
cancels the timer and removes the player. Autoplay is requested with a manual-play
fallback if the browser blocks it. Labels support English/Portuguese. This is a
video guide, not an automatic report submission or log upload.

Adds an independent, remembered autoqueue checkbox on Generate. Opted-in local
uploads and saved-voice generations are queued server-side to playbackMain once
complete, using existing moderation/delay/pause rules. Browser autoplay is separate.
