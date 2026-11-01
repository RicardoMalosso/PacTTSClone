# Requirements — v0.2 streamer studio

Current scope supersedes v1 exclusions. Detailed rationale: v2-design.md.

| ID | Acceptance |
|---|---|
| R1 | MP3 reference, 1–30 s, <=20 MiB; Automatic speech-language default; text <=2000 chars; valid local 48 kHz /192 kbps MP3. |
| R2 | Live wall timer, per-stage indeterminate/completed progress and measured CPU/RAM/GPU data where available. Never invent download ETA or exact GPU compute seconds. |
| R3 | Structured generation.jsonl and downloadable per-job report: hardware, selected device, wall/worker CPU times, per-stage sampled RAM/CUDA allocation peaks, outcome. |
| R4 | Configuration: Automatic/NVIDIA CUDA/CPU, CPU threads, resident model toggle, queue bound and global playback shortcut. No restart needed for settings; generation must be idle. |
| R5 | Cancel queued/current work, terminate actual inference process tree and remove partial files. Cancel all also disconnects chat, cancels playback and releases idle worker memory; completed history/voices remain. |
| R6 | Saved voice: title, original MP3 filename, single reference MP3, optional sanitized thumbnail and editable persisted transcript. Automatic transcription runs once; cancelled/interrupted preparation can be retried. |
| R7 | Persistent per-channel commands (!lula → voice), anonymous read-only Twitch IRC, tags/PING/reconnect/deduplication, per-user cooldown, text/queue limits. No paid-redeem verification. |
| R8 | Mandatory basic PT/EN slur blocklist, optional profanity/strict level, custom words/phrases. Reject before allocating generation work. Do not claim complete Twitch ToS enforcement. |
| R9 | Per-channel FIFO, default 5 s moderation countdown before each audio; cancellation before/during playback; Windows global stop shortcut outside browser focus; unsupported-platform status. |
| R10 | /channel is transparent OBS player; /channel/control is silent dashboard. One lease coordinates queue, additional OBS instances mirror current audio without advancing it. Heartbeat failure stops audio. |
| R11 | Persistent history, MP3 download, local preview and replay without regeneration; replay rechecks current moderation and countdown. |
| R12 | Homepage start/stop sharing button, opt-in Cloudflare Quick Tunnel, independently keyed admin and per-channel OBS links. Remote player cannot inspect/change administration or other channels. |
| R13 | Browser/system language detection, English and Brazilian Portuguese, persisted override with Canadian/Brazilian flag buttons at bottom. Preserve user content verbatim. |
| R15 | Always-available /playbackMain OBS player and /playbackMain/control dashboard; explicitly queue completed Generate/History audio from any origin without changing its channel metadata. Independent delay/filter/pause policy, cancellation, panic, replay and scoped tunnel link. No Twitch connection required. |
| R14 | Deterministic unit/API/process/browser tests and Linux/Windows CI. Real model, real external network and real GPU/physical hotkey validation reported separately. |

Bind the server to 127.0.0.1. Public requests must enter through the opt-in tunnel
with a forced non-loopback origin Host, active capability cookie and CSRF boundary.
No public inference service, chat posting or telemetry. Sharing relays audio and
control requests through Cloudflare; generation/model assets remain on the host.

Data directory is configurable; keep outputs, SQLite, voices and logs there.
Models use HF_HOME/HF_HUB_CACHE. Venv/project/caches can all reside on G:. V1 MP3s
are retained but v1 had no persistent job metadata to import into the new history.

R16: A small unsigned Windows x64 bootstrap installer downloads isolated Python,
FFmpeg and selected CPU/CUDA dependencies during setup, accepts separate app/data
locations, creates shortcuts, preserves user data on upgrade/uninstall, and produces
logs/checksums. No signing enrollment or repository visibility change. See
installer-design.md for acceptance and release gates.

R17: Installer defaults to app/data sibling directories, with a checkbox to choose
custom data storage. Path pickers show small red bold capacity estimates at their
right. First interactive page uses large red storage/download/unsigned wording and
a five-second Next delay. Uninstaller is discoverable in Start Menu and app folder
and preserves data by default.

R18: Seed user-provided Akuma Lady, Dilma, Chrétien and lula references once, without
inference on startup. Explicit first-use preparation with progress/cancel/retry and
persisted transcript; only ready voices selectable for generation/chat. Preserve
edits/deletions across upgrades. Parent-folder shortcut starts installed app.

R19: Report a bug tab embeds the supplied video only after explicit activation and
a three-second delay, requests autoplay, cancels/unloads on exit, and provides a
manual-play/direct-link fallback. No initial YouTube embed/network request.

R20: Optional browser-persisted local autoqueue checkbox, separate from autoplay.
Snapshot per submitted upload/preset job; backend queues successful local speech
once to playbackMain, even after browser closure. Honor filters/delay/pause, report
queue rejection, and exclude failed/cancelled jobs and Twitch-channel duplicates.


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

## Per-voice OmniVoice tuning — 2026-10-27

Each saved voice persists the seven native generation settings, including
duration, which overrides speed. IRC/EventSub requests use stored presets.
The Local Studio can override them without mutating the voice profile.
Presets can be restored to OmniVoice defaults. Legacy voices load defaults
without a database migration. Reject invalid parameters server-side and
preserve the effective settings in every queued generation's request record.

## RC9 maintenance controls — 2026-10-27

Configuration must provide a manual, repeatable button that opens the original
jingling-keys dialog, with 2-second loading animation, audible looping clip and
close-to-stop; no setup state changes. The direct YouTube link in Report a bug
becomes visible only two seconds after the ready-gated tab opens, resets upon
navigation, and does not delay the 200 ms autoplay request. RC9 packaging must
produce a separate **draft** after green full tests and actual Windows acceptance,
not overwrite RC8 or auto-publish unvalidated assets.


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

## Local Discord integration — 2026-10-28

The owner explicitly requested local bot-token configuration and Discord
integration. This adds opt-in Discord MP3 posting to the earlier no-chat-posting
scope; Twitch stays read-only. Host-only settings persist one bot token with
Windows DPAPI/0600 protection, enabled state, one permitted server, optional
channel IDs, default ready voice, filters, text limit and cooldown. `/tts` and
`/voices` use Gateway slash commands without privileged intents or a public
endpoint. Generation stays isolated in the existing worker and inherits saved
voice settings. Disconnect/remove/cancel-all/shutdown close the connection and
cancel undelivered generation. See [Discord contract](discord.md).


## KittenTTS2 engine

Engines supports a separately installed KittenTTS2 1.7B packed native CUDA runtime,
with explicit activation, cancellation, uninstall safety and independent voice
settings. Expose 115 built-in voices and reference cloning (5–30 seconds plus
transcript), automatic language detection including Portuguese, stable/expressive
presets, token budget, normalization, reference conditioning, seed and output volume.
Hide and reject unsupported OmniVoice controls. Target compatible NVIDIA native
BF16 GPUs generally; the owner's hardware is not a requirement. Label upstream
VRAM guidance as an estimate and unmeasured minima explicitly. See
[requirements and validation record](kitten-integration.md).

## Updater channels and versions

Managed installations include RC releases by default and sort compatible releases
by publication date. Local owners can pin a previous version or resume Latest.
Persistent updater controls survive application rollback. See [update contract](auto-updates.md).

## Dashboard notifications — 2026-11-01

Replace frequent local dashboard polling with SSE while preserving REST API
compatibility and persistent state. Coalesce redundant progress, bound memory for
slow consumers, reconnect/resynchronize after interruption and retain slower REST
fallback. Keep admin/player and host-only permission boundaries. Browsers must
never own generation, Twitch, Discord or playback completion. Preserve OBS polling,
leases and acknowledgements in this migration. LAN hosting is a separately planned
feature; Quick Tunnel testing support must not constrain direct local SSE.

## Frontend organization — 2026-11-01

Keep vanilla JavaScript and split dashboard transport, shared state, voices,
Twitch, engines, monitoring and configuration into feature modules. Preserve
existing UI behavior, drafts, localization, SSE recovery, updater bridge and OBS
controls. No React/Angular, bundler or new frontend installation step is required.
