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

Generate, Voices, Twitch & OBS, History and Configuration tabs share server state.
/channel/control selects its channel; /channel loads the transparent audio page.
Locale module detects preferred browser language, supports en-CA/pt-BR and persists
manual override. Static UI and explicit dynamic labels translate; user content and
machine-readable diagnostic keys do not. Canadian/Brazilian flags are inline SVG.

### Studio preferences and command drafts

Reapply the selected interface locale when activating a tab. Load generation speech language from each saved voice; Local overrides apply only
to the submitted job. Interface translation must not change speech language. Refresh existing command voice dropdowns
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

## RC4 remote access and observability

Remote admins unlock voices/history using host readiness from session/state,
without polling owner-only setup/tunnel endpoints. Shared OBS links include a
channel capability and work in a separate browser context. A lost cookie gets one
bootstrap retry; revoked/unauthorized links stop polling and ask for a fresh link.
Successful high-frequency HTTP polls are omitted from the CLI access log; errors
remain visible and TTS request lifecycle records remain in requests.jsonl.

Generate requires a browser-persisted requester name and random UUID. Server-derived
local/cloudflare/Twitch origin and installation-scoped origin IDs are recorded on
jobs; labels are for debugging, not proof of identity. History includes pending,
completed, failed/cancelled generation, sample preparation and moderation-rejected
TTS commands. Existing records have explicit legacy fallbacks. No IP addresses or
capability keys are added to the request log. All voices share one worker-reported
base-model resident state; changing voice repeats reference conditioning rather
than training a new model. OOM/reset/death clears residency. Fixed top status spans
all tabs, and language flags are beside the application title. Detailed contract:
[remote observability design](remote-observability-design.md).

Local validation: 138 backend tests, 25 Chromium tests and ruff passed. Remote tests
use a local tunnel simulation with independent browser contexts, not a live public
Cloudflare tunnel. Physical GPU behavior remains untested here.

Windows RC4 build compiled project-built FFmpeg and Inno; the actual wizard's
five-second delay/default folders/failure page passed, including disabled Next/
Finish, log availability and no requested restart. Minimal app install and root
shortcut HTTP launch passed. Web CPU setup exposed uv's constraint-path handling
with spaces (upstream issue astral-sh/uv#12639); commands now use a relative
constraint filename in an explicit setup working directory. Full CPU/model setup,
repeat installation and uninstall await the next Windows acceptance run.

Shared clients also receive the latest completed MP3 in Generate without needing
to submit it in that browser. Controls show its source/requester; foreign results
never trigger local autoplay or duplicate queueing, and active manual playback is
not interrupted. Remote status gets only sanitized host setup activity (no owner
logs or install controls). Browser requester IDs/names are site-origin scoped;
a new Quick Tunnel hostname naturally has separate browser storage.



## RC6 authorized Twitch events — 2026-10-25

The requested per-channel IRC/OAuth choice supersedes earlier IRC-only/no-paid-event
scope exclusions. Existing channels default to IRC. OAuth uses a public-client
Device Code grant and EventSub WebSockets, without a client secret or public
server. Rules cover message commands, points, Bits/Power-ups, subs/gifts/resub
messages, subscription endings, follows, raids and stream lifecycle.

Host-only credential/reward endpoints, Windows DPAPI (0600 files on other systems),
rotating refresh tokens, hourly validation, durable deduplication, moderation,
OBS-acknowledged reward fulfillment, failure refunds and reconnect recovery are
specified in [Twitch EventSub design and setup](twitch-eventsub.md).
External consent/paid-event validation remains separate from deterministic tests.
RC5 release assets are preserved; this source change is versioned RC6.


## RC6 optional imports and pre-setup Configuration

Configuration is available before Initial Setup completes. Imports are optional
and independent: verified large model weights (explicit copy/move), and additive
configuration/voices/completed output migration preserving the source. Generation
and voice/chat/history tabs remain gated by verified setup readiness. See
[optional import contract](optional-imports.md) for compatibility checks, backups,
conflict handling, host-only endpoints, cancellation and validation. This supersedes
earlier wording that locked every tab except Initial Setup.


Twitch connectivity: IRC remains the chat receiver for every active channel. An
optional independent EventSub receiver handles authorized events only. Channel
on/off controls both receivers; authorization changes restart only EventSub.

## Per-voice generation settings — 2026-10-27

A saved voice contains one validated `GenerationSettings` document with speed,
optional duration, inference steps, denoise, CFG and two processing toggles.
`Voices.generate` merges saved settings with only the request fields explicitly
provided by the caller, snapshots the effective values into the job, and queues
generation. Twitch events and IRC automatically inherit saved defaults. The
Local Studio loads saved values on voice selection and sends per-job overrides.
Duration supersedes speed in the OmniVoice adapter. Queued jobs do not change
when the voice defaults are edited; no model reload or training is required.

## RC9 manual clip and deferred YouTube link — 2026-10-27

The saved jingling-keys WebM remains served from the packaged static directory.
Configuration launches the exact same countermeasure dialog and two-second
loading sequence as Initial Setup. This route does not call the backend one-time
offer endpoint or alter setup state. The modal video loops with audio until closed;
closing pauses it and rewinds. The Report a bug pane only appears once YouTube's
iframe reports readiness and schedules video playback 200 ms later. The direct
YouTube link stays hidden until the bug pane has been visible for 2000 ms; leaving
the pane clears its timer, and reentering restarts it. Both timeout and autoplay
behavior remain subject to browser policy.

Release preparation: a merged, same-repo PR labeled `prepare-release`
runs the complete test and Windows installer acceptance workflow, then creates
a uniquely tagged RC9 **draft** on main. No automatic publication; prior RC8
assets remain immutable. The installer is unsigned.


## RC10 speech language defaults — 2026-10-28

Speech language belongs to the saved voice generation settings: Automatic (`auto`),
Português (`pt`) or English (`en`). Automatic is the default for new voices, legacy
voices with missing settings/language, JSON requests and legacy multipart uploads.
IRC and EventSub inherit the selected voice language. Local loads that same default
and allows a one-job override, without changing the voice. Old browser-only language
preferences no longer override saved defaults. Restore defaults selects Automatic.
Interface locale remains independent. Automatic passes `language=None` to OmniVoice.
Existing queued jobs keep their request snapshots; no voice re-preparation is needed.

RC10 publication is explicitly authorized by the owner. The publish-release merge
label runs the complete suite and Windows installer acceptance, creates a separate
RC10 draft, verifies its target and uploaded asset sizes/SHA-256 digests, then
publishes it as a prerelease. Previous release assets are never replaced.

## Discord adapter — 2026-10-28

Studio owns DiscordIntegration, with its own bounded-lifecycle asyncio/Gateway
thread using discord.py. DiscordBot registers guild-only `/tts` and `/voices`,
defers generation interactions and polls the existing GenerationService for a
terminal result before uploading its MP3. It receives only the Guilds intent;
message-content/member/presence intents are unnecessary. Saved voice defaults,
request auditing and cancellation remain shared with Local/Twitch. Discord jobs
carry an explicit origin, never a Twitch playback destination. Credentials stay
outside SQLite; host-only APIs and tunnel ACLs prevent shared administration from
reading or altering them. Settings are available before model setup; connection
waits for readiness. No hosted service/public route is added. See [discord.md](discord.md).

Discord lifecycle follow-up (2026-10-29): shield asynchronous queue submission
so cancellation retains the allocated job ID and cancels unfinished generation.
Client close drains command tasks before closing the Gateway. A resumed session
restores connected status through `on_resumed`, without depending on `on_ready`.

## Per-voice output volume

GenerationSettings includes `volume` (0–300 percent, default 100). Saved voice
presets inherit it for local and integration requests; local jobs may override it.
The worker applies linear amplitude gain after synthesis and before MP3 encoding,
using the same output path for every consumer. The reference and model input are
unchanged. Samples are clipped to the existing PCM range; extreme boosts may
distort peaks. Previously generated MP3s are not reprocessed.


## KittenTTS2 runtime

KittenProcessEngine shares the persistent isolated subprocess protocol with Ming,
using its own worker, marker, engine directory and validated request mapping.
KittenLifecycle shares serialized install/cancel/preflight/switch/removal behavior
with Ming while selecting a separate source/model/dependency manifest. The private
Python 3.12 runtime uses Torch CUDA, packed language-model weights and the default
S3 decoder. The decoder's Hub cache contains a pinned snapshot/ref and inference
runs offline. Cloning supplies an exact transcript to avoid upstream automatic
Whisper-large downloads; blank saved references use the existing shared CPU ASR.
Preset mode uses packaged reference artifacts. Per-engine defaults persist under
engine_generation_settings and are snapshotted into queued jobs. External runtime
CPU/RAM is excluded from bridge-only metrics; no fabricated private allocator
measurements are reported. Details: [integration](kitten-integration.md).

Kitten's upstream reference caches use file paths as keys. Since app references
are unique per-job temporary paths, the bridge clears both reference-conditioning
caches after each completed generation while keeping the base model resident.
This prevents unbounded retention across repeated requests.

## Updater channels and versions

Managed installations include RC releases by default and sort compatible releases
by publication date. Local owners can pin a previous version or resume Latest.
Persistent updater controls survive application rollback. See [update contract](auto-updates.md).

## Dashboard SSE migration — 2026-11-01

The local dashboard now receives shared SSE notifications from `/api/events`.
Committed Store changes invalidate document kinds; one application-level sampler
combines state/progress updates and samples resources/in-memory statuses for all
subscribed browsers. Latest values per topic and cumulative section versions bound
buffering and let existing components update without a frontend rewrite. REST
remains the baseline on reconnect and a five-second fallback. OBS ticks/leases,
inference isolation, SQLite persistence and integration lifecycles are unchanged.
See [protocol, deployment limits and measurements](realtime-communication.md).
LAN hosting remains planned; the testing Quick Tunnel path retains REST fallback.

## Frontend modules — 2026-11-01

The dashboard entrypoint now uses native ES module imports. Feature modules own
their rendering and event handlers; state.js holds shared values and snapshot
subscriptions, and api.js owns REST/CSRF handling. Explicit feature initialization
precedes asynchronous startup. REST and SSE snapshots use the same subscription
path; existing updater bridge events and OBS contracts remain intact. No framework,
bundler or npm runtime dependency is introduced. See [module guide](frontend.md).
