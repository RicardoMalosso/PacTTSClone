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
- OBS player/control links always open a new tab; active generation monitoring follows
  local/Twitch jobs across tabs and after reload.
- Transparent OBS player, separate control page, replay/download/history, global
  Windows stop shortcut and playback mirroring for another OBS instance.
- Optional homepage sharing button: temporary Cloudflare tunnel with separate
  admin and per-channel OBS-only links. Stop sharing revokes those links.
- English / Português, browser-language detection and bottom 🇨🇦 / 🇧🇷 controls.

## Windows installer (preview)

Open [Releases](https://github.com/RicardoMalosso/PacTTSClone/releases) and choose
`PacTTSClone-Setup-0.3.0-rc.4.exe` when the preview is available. Draft releases are
visible only to repository collaborators with the appropriate access; a private
repository does not provide public downloads.

1. Run setup on Windows 10/11 x64. No existing Python, FFmpeg or Git is required.
2. Choose the installation **root**. For example, selecting `foo/PacTTSClone`
   puts application files in `foo/PacTTSClone/app` and data in
   `foo/PacTTSClone/data`. Tick **Choose a separate data location** to unlock
   another data path. Red labels show estimated disk usage. Either can be on another drive.
   Data includes voices, MP3s, settings, model/download caches and setup logs.
3. The installer downloads private Python and the base web packages. It bundles
   project-built FFmpeg from pinned official FFmpeg source; it installs **no PyTorch,
   CUDA packages or model weights**. Native setup logs: `data/logs/setup.log`.
4. Double-click **PacTTSClone.lnk** inside your selected root, or the Start Menu
   shortcut. Open **Initial Setup** in the browser and choose CPU or NVIDIA GPU.
   A compatible NVIDIA driver is required; setup never installs drivers.
5. Click **Install / verify setup**. The web interface installs the selected inference
   packages, downloads OmniVoice and Whisper Small, verifies the files and unlocks
   the other tabs. Model progress shows real file bytes, cache verification and
   resumed downloads. Package installation shows actual log activity; it has no
   reliable combined byte percentage. Cancel/retry and a downloadable setup log
   are available. Only then prepare the included voices.

The first red **STEP 1** page explains downloads, including about 3.3 GB for the
OmniVoice model during Initial Setup, and waits five seconds before enabling Next. Folder
labels budget roughly 12–32+ GB combined, or 4–12 GB for app-only with separate data storage
plus 8–20+ GB for data/models/caches, not
fixed limits or an exact download size.

The preview installer is **unsigned**. `SHA256SUMS.txt` detects file changes but is
not a trusted publisher signature. Build/validation details: [installer design](docs/installer-design.md).
No signing certificate is purchased or installed.

If dependency preparation fails, the installer must stay on its error page with
Next disabled. Use **Open setup log**, Back to retry, or Cancel to exit. Installation
failure does not require restarting Windows. An early failure may save
`setup-error.log` at the root if `data/logs/setup.log` could not be created.

Upgrade: stop the app with Ctrl+C, run the newer installer and keep the same data
folder. Existing voices, audio and settings are preserved. Previous custom/legacy data
locations remain selected; setup does not silently move or delete that data. Uninstall removes the
application/runtime and leaves the data folder intact. Open **Uninstall PacTTSClone**
from the Start Menu or application folder, or use Windows Installed Apps; delete that folder
manually only if you also want to remove your recordings and models.

Large caches use the chosen data drive; the setup executable and Windows may still
create small temporary files or installer metadata on the system drive. Setup does
not change global Python, system PATH, NVIDIA drivers or enable network sharing.
CPU mode uses smaller dependencies and slower generation. There is no real-time
generation guarantee. Keep several GB free for models and installation caches.

### Cache reuse and updates

Native setup verifies the cached uv archive by SHA-256 before reusing it. Managed
Python and package installation reuse their existing installations/caches. The web
model setup pins a model revision and checks file size and SHA-256 (or Git blob
SHA-1 for small repository files). Exact files are reused, including matching
Hugging Face snapshots; partial transfers resume when the server supports Range.
Corrupt files are replaced. After setup, inference uses verified local model paths
in offline mode. Startup performs a lightweight existence/size check; rerunning
Initial Setup performs the full hashes again. It does not promise zero HTTP
requests for package version/index checks.

An updater is **not implemented**. For now, stop the app and run a newer installer
with the same data folder. A future update feature should check a versioned release
manifest, stage and verify the new application, preserve data, stop the old process,
and offer rollback. Private release authentication and unsigned Windows binaries
must be handled before unattended updating is offered.

FFmpeg publishes source, not Windows executables. This project's tools are built
in CI from pinned [official FFmpeg source](https://github.com/FFmpeg/FFmpeg), using
MSYS2's signed compiler/LAME packages. The release's `FFmpeg-source-build.zip`
contains sources, licenses, hashes and build provenance; recipe:
[build-ffmpeg.sh](installer/build-ffmpeg.sh). No Gyan FFmpeg distribution is fetched.

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

## Included voices and first-use preparation

The app includes **Akuma Lady**, **Dilma**, **Chrétien**, and **lula** as unprepared
presets. Complete **Initial Setup**, then open **Voices** and click **Prepare for first use** for each voice you want.
The card shows preparation status and cancellation; when ready, its saved
transcript is reused and the voice appears in Generate and Twitch command lists.
Models are downloaded and verified during Initial Setup; opening the app does not load them for inference. You can edit a transcript manually
instead, or delete unwanted defaults; upgrades do not recreate deleted presets.

Samples were supplied by the project owner. Akuma Lady's source was 30.59 seconds;
the bundled reference is a 29.9-second copy to meet the 30-second limit. Other
samples are unchanged. Original uploaded files are not modified. Sample quality
(including the supplied Dilma recording) is not improved or guaranteed by packaging.

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
Enable **Queue automatically on general OBS player** beside autoplay on Generate
to send each new local generation to this queue. The checkbox defaults off and is
remembered in your browser. The choice is captured when submitting a job; the server
queues the completed MP3 even if that browser closes. Delay, filters and pause state
still apply; failed/cancelled jobs and Twitch jobs are not automatically copied.
Manual preview/autoplay remains independent; leave browser autoplay off when you
want to hear the audio only through OBS.

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

## Community hardware benchmarks

Anonymized measurements supplied by a user from local OmniVoice generation logs.
Voice labels are arbitrary; names, speech/transcript text, filenames, job IDs,
usernames, channel names, paths and timestamps are omitted. The raw log is not
published. These are observed runs on one machine, not a controlled comparison.

| Hardware | CPU | System RAM | GPU | VRAM | OS |
|---|---|---|---|---|---|
| H1 | AMD Ryzen 5 5600X (6 cores / 12 threads) | 16 GB | NVIDIA GeForce GTX 1660 SUPER | 6 GB | Windows 11 |

Settings: `k2-fsa/OmniVoice`, CUDA generation, 32 steps, speed 1.0,
4 CPU threads, keep-model-loaded enabled. Language selection is listed per run.

| Hardware | Voice | Completed generation | Output audio (seconds) | Total elapsed (seconds) | Model state | Language |
|---|---|---:|---|---:|---|---|
| H1 | Voice A | 1 | Not recorded | 199.33 | Loaded during this job | auto |
| H1 | Voice A | 2 | Not recorded | 84.94 | Already loaded | auto |
| H1 | Voice A | 3 | Not recorded | 77.56 | Already loaded | en |
| H1 | Voice A | 4 | Not recorded | 187.61 | Loaded during this job | pt |
| H1 | Voice A | 5 | Not recorded | 71.56 | Already loaded | pt |

Elapsed time includes setup, reference decoding, any model loading and MP3 encoding.
“Already loaded” means this job had no model-loading stage. The fourth completed
run loaded the model again; warm/resident settings do not guarantee it remains
loaded across cancellation, worker replacement or app restarts. Text/language varied
between runs, so differences cannot be attributed to warming alone.

Output durations are absent from this log and the generated MP3s were not supplied.
They cannot be inferred from generation time or text length; real-time factors are
therefore not reported. One cancelled generation is excluded from completed-run
numbering. No successful Voice B speech generation is present in the supplied log.

### Separate first-use voice preparation

Preparation transcribes a reference; it produces no speech MP3 and is not counted
as a generation above. Whisper transcription uses CPU; OmniVoice may also be loaded.

| Hardware | Voice | Preparation | Elapsed (seconds) | Model state |
|---|---|---|---:|---|
| H1 | Voice A | 1 | 19.03 | Already loaded |
| H1 | Voice B | 1 | 174.27 | Loaded during this job |

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

## Report a bug

Open **Report a bug** to watch the project guide. Its YouTube embed loads only after
opening the tab and waiting three seconds, then requests autoplay. Leaving the tab
stops/unloads it and cancels any pending start. Press play manually if browser
policy blocks autoplay; a direct YouTube link is also provided. This user-requested
video uses the internet and does not automatically submit reports or upload logs.
