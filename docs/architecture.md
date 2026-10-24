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

## Bundled reference presets

The four user-authorized samples live in assets/voices with a hash manifest. Studio
copies each once into the selected data directory with status unprepared. No FFmpeg
or inference/model download runs during seeding. Stable IDs and initialization
markers prevent duplicate presets, overwriting edited transcripts/titles, or
resurrecting deleted defaults after restart/upgrade. Explicit Prepare submits the
existing isolated transcription job; pending actions are idempotent, completion
saves the transcript, and only ready voices can generate/be assigned to commands.
UI distinguishes not prepared, preparing, ready and retryable failure/cancellation,
with per-card progress/cancel and a Generate-to-Voices preparation link.

## Bug reporting video

The Report a bug pane lazily creates a youtube-nocookie iframe for b2eEl2oKXLA
three seconds after explicit tab activation. No embed exists at initial load.
A single tracked timer is cancelled on tab exit; removing the iframe stops media.
Panic also unloads it. Repeated activation of an already-open tab does not create
duplicate players. Autoplay is delegated/requested, with manual play/direct-link
fallback for browser policy. UI locale changes update labels without reloading
an already-playing video. There is no report submission or background log upload.

## Local autoqueue

GenerationRequest carries an optional autoqueue_general boolean (default false),
accepted for MP3 uploads and saved-voice generation. The UI persists its independent
checkbox and snapshots it at submission. Studio's completion callback enqueues
successful local speech to playbackMain, under the playback lock, and persists the
item ID to prevent duplicate callback delivery. No browser completion request is
needed. Existing moderation/countdown/paused-state rules apply; rejection is saved
as playback_error and shown separately from browser autoplay feedback. Channel jobs
retain their original destination and are not duplicated to the general bus.

## RC4 contained-root layout and failure navigation

The selected destination is now a container: private app/runtime/launcher/config
files live in root/app, default recordings/models/caches live in root/data, and
launch/uninstall shortcuts live at root. The bootstrap still enforces non-overlap
between the private app directory and data. Existing custom data paths are retained;
no silent relocation/deletion of old data or legacy installation files.

Removed the unsafe global Next button reset from CurPageChanged. Only the intro
countdown may control its button. Preparation failure explicitly clears NeedsRestart,
blocks advancing the error page, offers Open setup log and saves a fallback log
for errors before PowerShell transcript initialization. Inno restart requests are
disabled and the finish-page restart choice is set to No/disabled. Failure tests use
/NORESTART as additional test-runner protection; no real reboot is attempted.

Windows tests cover the new contained data path, explicit failure before downloads,
disabled Next/Finish and log availability, plus real installation, root shortcut
startup and uninstall preserving data. Validation is pending the RC4 workflow.


## RC4 mandatory browser setup

Current design supersedes earlier installer dependency/model-on-first-use notes:
native setup contains no CUDA/PyTorch. Initial Setup is the first required web tab;
it installs CPU/NVIDIA inference packages and verified OmniVoice/Whisper files,
shows download/cache/resume activity and unlocks generation only on success.
Worker uses local offline model directories afterward. Package activity has no
fabricated byte total. Owner-only API supports cancel/retry/logs. See
[web setup design](web-setup-design.md) and [installer design](installer-design.md).
Validation pending RC4 Windows workflow; backend/browser results recorded below
when completed. An automatic updater is not implemented.

OBS player/control links open in a new tab with noopener/noreferrer. Channel link
nodes remain stable during polling so a refresh between mousedown/mouseup cannot
swallow the click. Browser acceptance covers actual popup URLs for both channel
and general playback/control links.

Generation monitoring follows the server's active job, independently of local form
submission. A compact source/stage/timer/cancel strip remains visible across tabs;
the full Generate monitor follows Twitch, preparation and queued local requests,
including after reload. It prioritizes the running job over later queued work.
Cancel targets the displayed job. Monitoring remote requests never autoplays them
in the admin browser; OBS retains playback responsibility.

## RC4 studio organization and voice media

Tunnel controls live in Configuration. Generate accepts a saved ready voice and
text; MP3 imports live only in Voices (the legacy upload API remains compatible).
Twitch & OBS includes a per-channel live dashboard with connect/disconnect/edit/
delete. Disconnect preserves config and stops chat monitoring. Delete stops the
client, cancels that channel's pending jobs/playback, drops its config/player
capability and retains output/history. Local OBS Sources renames General playback
without changing its URLs or identifiers.

Voice imports decode at most 31 seconds, then retain exactly the first 30 seconds
when longer, validate audible content, re-encode the saved reference and persist
a crop notice. Too-short/corrupt/silent/oversized inputs remain errors. Existing
voices accept bounded thumbnail replacement with atomic JPEG writes. Default
user-provided thumbnails are downsampled to <=128 px, integrity-checked, and seeded
to existing presets only when no custom thumbnail is present; tombstones remain.
No transcription, title or custom image is replaced by thumbnail migration.
