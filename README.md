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

## Requirements

Python **3.12, 64-bit** recommended (application CI also tests Python 3.11).
FFmpeg and ffprobe must be on PATH. Use matching torch/torchaudio 2.8.0 wheels.
NVIDIA CUDA is supported; CPU is supported but slower. AMD/Intel/Apple GPU
acceleration is not implemented. GTX 1660 SUPER 6 GB still needs its own benchmark.
Reserve several GB for packages/models; automatic ASR can download additional
model formats through the upstream loader. No claim of real-time generation.

## Update an existing Windows installation on G:

Stop the running app first (Ctrl+C in its terminal), then in PowerShell:

```powershell
Set-Location G:\projects\chatgpt\PacTTSClone
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -e ".[inference]"
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 --data-dir G:\projects\chatgpt\PacTTSClone-data
```

Existing model caches are reused. If you already created
`G:\utils\Start-PacTTSClone.cmd`, that launcher continues to work after updating.
V1 MP3 files remain in outputs, but v1 did not retain metadata for history import.

## Fresh installation

You can install prerequisites outside C:

```powershell
winget install --id Python.Python.3.12 -e --scope user --architecture x64 --location "G:\utils\Python312"
winget install --id Gyan.FFmpeg -e --scope user --location "G:\utils\FFmpeg"
```

Open a fresh terminal after installation. Clone into your projects directory:

```powershell
New-Item -ItemType Directory -Force G:\projects\chatgpt | Out-Null
Set-Location G:\projects\chatgpt
git clone https://github.com/RicardoMalosso/PacTTSClone.git
Set-Location PacTTSClone
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Device cuda
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1 --data-dir G:\projects\chatgpt\PacTTSClone-data
```

Use `-Device cpu` to install CPU wheels instead. The isolated `.venv` stays inside
this project. The first generation downloads models; install scripts do not train
anything. To keep model/pip caches off C:, set these user environment variables
before installing or generating (the earlier full setup block already does this):

```powershell
[Environment]::SetEnvironmentVariable('HF_HOME', 'G:\utils\cache\huggingface', 'User')
[Environment]::SetEnvironmentVariable('HF_HUB_CACHE', 'G:\utils\cache\huggingface\hub', 'User')
[Environment]::SetEnvironmentVariable('PIP_CACHE_DIR', 'G:\utils\cache\pip', 'User')
```

Open a new terminal to pick them up. TEMP/TMP can also be set to a G: directory
for the installer session. Windows may retain small installer metadata on C:.

Linux/manual setup:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[inference]'
pacttsclone --data-dir ./local-data
```

Install FFmpeg through your system package manager. For NVIDIA replace `cpu` in
PyTorch's wheel URL with `cu128`, subject to driver compatibility.

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

Data directory (default `~/.pacttsclone`, or the G: path above):

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
