# Architecture — v0.2

## State and processes

FastAPI serves local HTML/CSS/JS and a bounded multipart/JSON API. Store is a locked
SQLite WAL document store with indexes for pending jobs and channel playback.
GenerationService serializes queued jobs. ProcessRunner uses multiprocessing spawn
and keeps one OmniVoice engine warm; device/thread changes or cancellation replace
that worker. POSIX process groups / Windows child-process termination cover FFmpeg
children. Normal idle shutdown is graceful before bounded termination fallback.
InlineRunner is only explicit test injection, never normal application fallback.

Worker stages: configure, decode, load model, optional CPU ASR, inference, encode.
Reporter samples at 500 ms and phase boundaries, emits progress events over IPC,
and records wall and process CPU seconds, RAM peaks, CUDA allocation and stream
elapsed time when available. Loading is indeterminate. No false GPU-busy counter.
The manager commits final state+metrics atomically before exposing completion and
appends generation.jsonl. Cancelled partial metrics are marked partial.

Voices manages validated MP3s, safe thumbnails and transcripts. A preparation job
transcribes a blank sample once and saves its text; later jobs reuse it. SQLite
retains voices, settings, channels, job reports, recent moderation and playback.
After restart interrupted work is cancelled, never silently replayed. Voice
preparation interrupted on restart becomes retryable.

## Twitch and playback

Studio connects configured channels through anonymous WSS IRC on Twitch port 443,
reads only, handles frames/PING/RECONNECT/tags and deduplicates IDs. Commands select
voice presets. Moderation and cooldown run before submission. No PRIVMSG is sent.

Playback has independent per-channel FIFO items. Delay starts when the next item
reaches the head and a player polls. One renewable lease coordinates readiness,
start/end/error acknowledgments. Mirrors may receive current playing audio with
its start timestamp but cannot advance the FIFO. Hotkey/panic cancels playing and
countdown items and pauses channels; cancel-all also disconnects chat and cancels
all queued/generating work. Replay reuses MP3 and applies current filter/countdown.

The OBS page polls every 250 ms; a local watchdog stops audio after 2.5 s without a
successful server response. Lease loss interrupts and pauses rather than replaying.
The dashboard is silent except explicit preview / manual autoplay.

## Access and sharing

LocalBoundary validates Host/Origin, limits bodies before multipart parsing, and
checks per-process CSRF token on all mutations. Default bind remains loopback.
Tunnel is opt-in; cloudflared is verified against official release SHA-256 before
first installation into data-dir/tools, or reused from PATH. Its HTTP Host override
is pacttsclone-tunnel.internal, ensuring tunneled requests never inherit local
owner privileges. Only the active generated hostname is accepted as remote Origin.

Shared admin and per-channel player keys are independent. URL fragments bootstrap
Secure, HttpOnly, SameSite cookies; secrets do not appear in server request paths.
Remote player ACL allows only session token, its own player tick/ack and its own
channel's successful audio. Remote admin can administer the app but cannot start,
stop or inspect tunnel capabilities. Stopping sharing revokes cookies server-side
by discarding keys. Quick Tunnel URLs are temporary and have no uptime guarantee.

## UI and locale

Generate, Voices, Twitch & OBS, History and Configuration tabs share polling state.
/channel/control selects its channel; /channel loads the transparent audio page.
Locale module detects preferred browser language, supports en-CA/pt-BR and persists
manual override. Static UI and explicit dynamic labels translate; user content and
machine-readable diagnostic keys do not. Canadian/Brazilian flags are inline SVG.

### Studio preferences and command drafts

Reapply the selected interface locale when activating a tab. Persist generation
speech language separately in `pactts-speech-language`; interface translation must
not change the requested speech language. Refresh existing command voice dropdowns
when ready voice IDs/titles or locale change, preserving valid selections and
command text. Pending voices become selectable only after preparation succeeds.
The studio uses a Gruvbox Dark palette with responsive recording-desk panels.

### General playback destination

A persisted internal playback configuration named `playbackMain` shares the FIFO,
lease, countdown, filtering, cancellation and panic implementation. It is excluded
from Twitch channel listings/connections. Queueing a completed job explicitly to
this destination does not alter its original channel, regenerate it, or duplicate
its MP3. Generate and History expose manual queue actions; no implicit double
playback is enabled. `/playbackMain/control` selects general controls; the player
is `/playbackMain`. Optional tunnel sharing includes this destination. Its player
capability can retrieve only successful audio explicitly assigned to that FIFO,
not every completed job in the studio.

### Console shutdown

The spawned inference worker ignores SIGINT before initializing the engine. On
Windows console Ctrl+C reaches both server and child; only the server owns the
shutdown lifecycle. Idle workers exit via the existing command sentinel, while
active jobs are cancelled through bounded process-tree termination. This avoids
an idle `commands.get()` KeyboardInterrupt traceback without changing cancellation.

## Installer distribution

See installer-design.md. Inno Setup embeds only app wheel/scripts/manifest. uv
manages private CPython and version/device venvs. Bootstrap validates imports/tools
before changing active.json. Installed launcher sets process-local caches and
PATH. Application data is separate and never part of uninstaller deletion rules.
Source scripts remain available; no git checkout is required by installed builds.
