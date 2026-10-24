# PacTTSClone

Local **MP3 reference + text → MP3 voice cloning** using the official
[k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice), the same model as the
[original Space](https://huggingface.co/spaces/k2-fsa/OmniVoice). No Space API calls.

## v0.2 features

- Pipeline progress, wall timer, live system/worker RAM/CPU and NVIDIA VRAM data
  where available; saved per-stage hardware/time reports and JSONL logs.
- Automatic/NVIDIA GPU/CPU settings, CPU thread count, resident-model option.
- Actual process cancellation and bounded queues; no synthetic speech fallback.
- Saved voices with title, original MP3 name, optional thumbnail and editable saved
  transcript. Blank samples are transcribed once locally and reused.
- Per-channel Twitch commands, basic always-on slur filter, optional profanity
  levels, custom phrases, cooldowns and moderation countdown (default 5 seconds).
- Transparent OBS player, separate control page, replay/download/history, global
  Windows stop shortcut and playback mirroring for another OBS instance.
- Optional homepage sharing button: temporary Cloudflare tunnel with separate
  admin and per-channel OBS-only links. Stop sharing revokes those links.
- English / Português, browser-language detection and bottom 🇨🇦 / 🇧🇷 controls.

## Windows installer (preview)

Open [Releases](https://github.com/RicardoMalosso/PacTTSClone/releases) and choose
`PacTTSClone-Setup-0.3.0-rc.1.exe` when the preview is available. Draft releases are
visible only to repository collaborators with the appropriate access; a private
repository does not provide public downloads.

1. Run setup on Windows 10/11 x64. No existing Python, FFmpeg or Git is required.
2. Choose separate application and data folders. Either can be on another drive.
   Data includes voices, MP3s, settings, model/download caches and setup logs.
3. Choose Automatic, CPU or NVIDIA CUDA. Automatic detects NVIDIA; a compatible
   NVIDIA driver is still required. AMD/Intel/Apple GPU acceleration is unsupported.
4. Follow download progress in the setup console. The executable is small; runtime
   downloads and installed files can occupy several GB. Closing the console cancels
   setup; rerun it to retry using cached downloads. Errors: `data-folder/logs/setup.log`.
5. Start **PacTTSClone** from the Start Menu or optional desktop shortcut. Models
   download on first generation; a blank reference transcript also downloads ASR.

The preview installer is **unsigned**. `SHA256SUMS.txt` detects file changes but is
not a trusted publisher signature. Build/validation details: [installer design](docs/installer-design.md).
No signing certificate is purchased or installed.

Upgrade: stop the app with Ctrl+C, run the newer installer and keep the same data
folder. Existing voices, audio and settings are preserved. Uninstall removes the
application/runtime and leaves the separate data folder intact; delete that folder
manually only if you also want to remove your recordings and models.

Large caches use the chosen data drive; the setup executable and Windows may still
create small temporary files or installer metadata on the system drive. Setup does
not change global Python, system PATH, NVIDIA drivers or enable network sharing.
CPU mode uses smaller dependencies and slower generation. There is no real-time
generation guarantee. Keep several GB free for models and installation caches.

## Run or update from source

For existing source installations, stop the app, open PowerShell **in your project
folder**, then run:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -e ".[inference]"
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 --data-dir "YOUR_DATA_FOLDER"
```

Replace `YOUR_DATA_FOLDER` with the same data directory you already use. Keep your
existing cache environment variables and launcher if configured. No particular
drive, parent directory or external launcher is required. Installer installations
and source checkouts are independent; stop one before starting the other on port 7860.

Fresh source installation requires Python 3.12 x64, FFmpeg/ffprobe on PATH and Git.
Clone this repository into any chosen directory, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Device cuda
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 --data-dir "YOUR_DATA_FOLDER"
```

Use `-Device cpu` for CPU wheels. The venv is stored in the project. Set `HF_HOME`,
`HF_HUB_CACHE`, `PIP_CACHE_DIR` and session `TEMP`/`TMP` to your chosen storage
locations **before** installing/generating if space on the system drive is limited.
The source scripts reuse existing Python/FFmpeg; use the installer for automatic
prerequisite installation. V1 MP3s remain but have no metadata for history import.

Linux/manual setup (install FFmpeg through your package manager):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[inference]'
pacttsclone --data-dir ./local-data
```

For compatible NVIDIA drivers, replace `cpu` in the wheel URL with `cu128`.

## Studio workflow

1. Open **http://127.0.0.1:7860**. In **Voices**, add an MP3 (1–30 s, recommended
   3–10 s, <=20 MiB), title and optionally thumbnail and exact transcript. A blank
   transcript creates a preparation job; wait until the voice is ready.
2. **Generate** with a saved voice or a one-off MP3. Progress bars show milestones
   and indeterminate work, not an invented ETA. Cancel kills the actual worker.
3. **Configuration** chooses Automatic, NVIDIA GPU or CPU. Whisper stays on CPU.
   An idle queue is required for hardware changes. Keeping a model resident is
   faster but continues occupying RAM/VRAM between messages.
4. In **Twitch & OBS**, save a channel login (without URL), map commands like
   `!lula` / `!dilma` to ready voices, choose filters/delay and enable connection.
   `viewer: !lula oi bom dia` queues local generation. This is read-only IRC; it
   does not post chat or validate Bits/channel-point purchases.
5. Add **http://127.0.0.1:7860/channelname** as an OBS Browser Source. The separate
   control page is **http://127.0.0.1:7860/channelname/control**. Only the OBS page
   automatically plays channel audio. Route its audio through OBS as desired.
6. During the countdown, cancel the audio in controls. **Panic** (default global
   shortcut **Ctrl+Alt+F9** on Windows) stops current/countdown audio and pauses
   channels. Resume in controls. If the shortcut is unavailable/in use, its status
   says so. **Cancel all work** additionally disconnects chat and cancels queued
   generation; saved voices/completed files are retained.
7. **History** previews/downloads audio or queues the same MP3 for OBS replay,
   without rendering again. Replay applies the current filter and delay.

The basic PT/EN word filter cannot enforce every Twitch policy or detect all
obfuscation/context. Custom blocked phrases are checked before generation. Each
channel has its own settings; the mandatory basic slur list cannot be disabled.

## General OBS player / testing

Use **http://127.0.0.1:7860/playbackMain** as an OBS Browser Source without Twitch.
Its dashboard is **http://127.0.0.1:7860/playbackMain/control**, also available in
**General playback**. Generate an MP3, then click **Queue on general player**, or
use the same button in History for any completed local or channel generation.
This reuses the MP3; it does not generate again or change the original channel.
Configure delay (default 5 seconds), filters and custom blocked phrases in the
general controls. Pause/resume, cancel, panic and playback mirrors work as with
channel players. Sharing includes a separate `playbackMain` OBS-only link.
Manual preview/autoplay on Generate remains independent; use the OBS player alone
when you want a single playback destination.

## Share with a friend

Click **Start secure tunnel** on the homepage. No Cloudflare account is required.
The app reuses cloudflared from PATH or downloads its official binary into
`data-dir/tools`, verifies SHA-256 and starts a temporary Quick Tunnel.

- **Admin panel link** grants control of this app. Share only with a trusted admin.
- **OBS-only link** can play only its specified channel. It cannot view/change
  settings, voice references, logs or other channels. Keep the complete link,
  including its `#play=...` fragment, in the friend's OBS Browser Source.
- Local and remote OBS can mirror the same channel; only one player coordinates
  the queue. A lost coordinator pauses playback rather than replaying stale audio.
- **Stop sharing** terminates the tunnel and revokes every link. The next tunnel
  gets fresh keys and typically a different address. Tunnel lifecycle remains
  local-only, including when a remote administrator is connected.

The app still binds only to loopback. Shared traffic/audio goes through Cloudflare;
voice generation remains on this PC. Quick Tunnels have no uptime guarantee and
require outbound access to Cloudflare. If downloading is blocked, install
cloudflared manually and add it to PATH; the UI displays startup/download failures.

## Logs, storage and measurement

Data directory (chosen in setup, passed with `--data-dir`, or source default `~/.pacttsclone`):

| Path | Contents |
|---|---|
| `outputs/` | Final MP3s, retained until manually removed |
| `voices/` | Preset references and sanitized thumbnails |
| `pacttsclone.sqlite3` | Settings, voices, history, moderation, playback |
| `logs/generation.jsonl` | One report per completed/failed/cancelled job |
| `temporary/` | Temporary per-job files, removed after completion/cancellation |
| `tools/` | Verified cloudflared binary, if automatically installed |

Reports distinguish elapsed wall seconds, worker CPU seconds across all threads,
per-stage sampled RAM/CUDA allocation peaks and optional CUDA stream elapsed time.
CPU seconds can exceed wall time. External FFmpeg CPU time is excluded; its stage
wall time is included. GPU stage/stream time includes CPU coordination and is not
an exact GPU-busy counter. Device-wide NVIDIA utilization/VRAM includes other apps
such as games and OBS; unavailable metrics appear as N/A. See the saved report for
hardware names, model IDs and timings. Startup cancels unfinished jobs and does not
replay old queue entries. An abrupt OS/power failure may leave temporary files.

Locale is detected from the browser/system preference, then overridden by bottom
flag controls. User voice names, filenames, transcripts and chat text are never
translated. Machine-readable report field names stay stable.

## Tests

```bash
python -m pip install -e '.[dev,browser]'
python -m pytest
python -m ruff check .
python -m playwright install chromium
python -m pytest tests/browser --browser chromium
```

Deterministic tests use explicit fake engines, real FFmpeg and a real spawned
worker lifecycle; browser tests exercise real Chromium. Those do not establish
cloning quality, live Twitch connectivity or real GPU performance. Actual CPU
model smoke/results are documented separately in [status](docs/status.md).

```bash
pacttsclone-smoke --reference reference.mp3 --ref-text "Exact reference transcript." --text "Olá, bom dia."
```

`--offline` requires cached model assets. A manual transcript avoids the initial
Whisper download. API/OBS use polling, compatible with Quick Tunnels' lack of SSE.

[Requirements](docs/requirements.md) · [Architecture](docs/architecture.md) ·
[Design](docs/v2-design.md) · [Decisions](docs/decisions.md) · [Tests](docs/testing.md)

Upstream code: Apache-2.0. OmniVoice pretrained weights: CC-BY-NC per its model
card; commercial deployment requires resolving that separate model license.
