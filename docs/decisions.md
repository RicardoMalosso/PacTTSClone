# Decisions and source review

2026-10-24 — initial design, before implementation.

1. Use FastAPI + native browser audio rather than the previously proposed Gradio.
   Explicit HTTP contracts, predictable MP3 downloads, autoplay feedback and future
   event adapters justify this small custom UI. Python remains the single backend.
2. Use omnivoice==0.2.1. Upstream source inspected at
   `08be0b4ccbac3e13e374e86fbfead4b4cac343e2`:
   https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/omnivoice/models/omnivoice.py
   https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/pyproject.toml
   https://huggingface.co/k2-fsa/OmniVoice
   Current upstream dependency constraints include transformers>=5.3.0 and
   torch/torchaudio>=2.4. Installation guidance uses matching torch/torchaudio
   2.8.0; CUDA wheel selection is an explicit install step, not a universal wheel.
3. CUDA FP16 with SDPA; CPU FP32 fallback. No automatic retry on CPU after an OOM:
   inform user to reduce text or explicitly restart with CPU. GTX 1660 SUPER 6 GB
   remains a target to benchmark, not a certified configuration. Audio tokenizer
   and ASR memory mean 0.6B model weight size alone does not predict total VRAM.
4. Whisper is lazy and placed on CPU, model openai/whisper-small by default to
   reduce resources. Editable manual transcript avoids this extra model entirely.
5. FFmpeg handles MP3 decode/encode. Enforce 1–30 s rather than silently trimming:
   silent trimming would make a supplied full transcript incorrect.
6. No custom pause processing in v1. Punctuation is forwarded to the model;
   deterministic inserted silence belongs to a future feature with dedicated tests.
7. Dependencies and recordings stay local. Initial model download requires internet;
   offline mode sets Hugging Face offline flags before importing inference packages.
8. License distinction: upstream code Apache-2.0; pretrained model CC-BY-NC per
   model card. Future monetized streamer deployment must resolve model licensing.
   Do not apply a project-wide license to third-party weights.
9. Standard deployment is an isolated Python venv, confirmed with the user.
   No Docker/container service in v1. Engine module provides the requested code
   separation without adding a deployment layer.
10. Export at 48 kHz / 192 kbps MP3; OmniVoice's native 24 kHz is resampled only
    for encoding. A real FFmpeg test showed MPEG-2 at 24 kHz caps at 160 kbps.
    Resampling does not add source detail; it satisfies the MP3 bitrate contract.
11. Standard installer uses Python 3.12, the version used for local validation.
    Pin transformers 5.20.2 and torch/torchaudio 2.8.0 in the inference extra;
    CUDA/CPU wheel index is still explicitly selected before installing it.
    PyPI OmniVoice 0.2.1 wheel was downloaded without dependencies and its API
    inspected, confirming `asr_device`, `load_asr_model(device=...)`, and generation
    arguments rather than assuming the development branch matched the release.
12. Pin Playwright 1.56.0, which supplied a working Chromium download in this
    environment. Browser tests use a real loopback HTTP server and ignore external
    proxy variables only for their loopback readiness probe.

## Pre-implementation consistency review

Reviewed requirements, architecture, testing plan and this record together.
Updated the earlier Gradio proposal to FastAPI throughout. Kept MP3-only output,
no Twitch hooks, no pause tags, no saved voice prompts. Automatic ASR is optional
and lazy; Windows scripts must install compatible torch explicitly. Resource
estimates remain unverified; tests using fake engines cannot establish inference
quality, latency or hardware compatibility. No conflicting design decisions remain.

## Post-implementation consistency review

Re-read requirements against the implemented API, engine, UI, launchers and tests.
Updated output sample rate to 48 kHz for the tested 192 kbps MP3 contract; retained
24 kHz reference PCM. Standardized the Windows installer on tested Python 3.12 and
pinned inference/browser versions. Confirmed venv (no container), one generation,
Portuguese default, automatic ASR on CPU, no pause syntax and no Twitch code.
Verified real CPU generation separately from fake-engine application tests, then
verified cached offline and blank-transcript/Whisper generation. Hardware claims
remain limited to the measured CPU runs in status.md; GTX 1660 SUPER is untested.
The earlier Gradio proposal is superseded; no remaining design conflict found.

## V2 scope changes — 2026-10-24

The user's new request explicitly supersedes v1's no-Twitch/no-cancellation/no-voice
library exclusions, and adds optional sharing and locale controls. Read
requirements.md and v2-design.md for the current contract.

- Isolate inference with spawn rather than attempt to interrupt a Python thread or
  an in-flight CUDA kernel. Termination frees the worker's model memory; a later
  job loads a fresh worker. Normal completion can retain it for latency.
- Use SQLite for resumable configuration/history, but cancel unfinished work on
  startup rather than unexpectedly speaking stale messages into a stream.
- Do not present phase wall time as exact CPU/GPU compute time. Process CPU time
  counts all threads; per-stage RAM peaks are sampled; CUDA stream intervals
  include gaps; NVML utilization is device-wide and may include the game/OBS.
- Native Windows RegisterHotKey avoids a keyboard-hook dependency. Other platforms
  expose unavailable status and focused-browser fallback, not a fake global binding.
- Keep Twitch anonymous/read-only; public command triggers do not verify paid
  redemptions. Treat chat as untrusted text and filter before job/file allocation.
- Keep one playback coordinator with optional mirrors so local and remote OBS can
  hear the same channel without racing to advance the queue.
- Cloudflare Quick Tunnel is a user-click action, never automatic startup. Distinct
  admin/player capabilities, forced origin Host and cookie ACLs prevent sharing an
  OBS link from granting full machine administration. Automatic binary installation
  requires the official asset digest; never silently execute an unverified download.
- Browser language first, then persisted choice. Translate interface strings only;
  preserve presets, transcripts, messages and technical log data.

Reviewed current requirements, architecture, tests, UI and upgrade instructions for
consistency. Replaced v1 scope statements in current docs; historical v1 evidence is
preserved separately in v1-validation.md. Exact GPU timing, physical global-hotkey
operation and external routing remain separate from deterministic fake-engine tests.

## Studio follow-up — 2026-10-24

Use Gruvbox Dark for the studio, retaining transparent OBS backgrounds. UI locale
and generation language are independent browser preferences. Tab activation
reapplies locale; speech language survives reloads. Existing command rows refresh
ready voice options on polling instead of requiring users to recreate the row or
reload the page. Preserve command drafts and valid selected voice IDs.
Automatic device selection is only CUDA availability selection, not an additional
model. Blank reference transcripts trigger CPU Whisper; saved transcripts avoid
repeating ASR. Automatic speech language passes `language=None` to OmniVoice and
does not explicitly load another language-detection model in our adapter.

General playback uses an internal persisted destination rather than a fake Twitch
connection. Reuse the proven playback state machine; allow explicit destination
override only on the admin queue endpoint, retaining original job provenance.
The general player capability authorizes only jobs actually queued to that bus.

## Unsigned installer preview — 2026-10-24

User explicitly chose setup-time dependency downloads and unsigned distribution.
Use Inno Setup plus pinned uv managed Python, not unsupported pip modification of
Python's embeddable distribution. Bundle the tiny app wheel to avoid authenticated
GitHub asset downloads during installation of a private repository. Python, FFmpeg,
PyTorch and other dependencies are downloaded, and models remain first-use assets.
Version 0.3.0rc1 / release v0.3.0-rc.1 is a draft preview, not a stable declaration.
Official uv 0.9.5 and Gyan FFmpeg 8.0.1 SHA-256 values were retrieved from their
GitHub release metadata. No certificate enrollment, signing claim or public access
change. No blanket project license is invented for the repository or model weights.

## RC2 installer UX — 2026-10-24

Use sibling folders by default rather than unrelated app/data defaults. Explicit
custom data paths remain supported via checkbox and /DATADIR. Existing custom
upgrade paths are preserved. Budget labels are estimates, not limits; model files
are approximately 3.3 GB per official repository listing, while total app/data
usage depends on CPU/CUDA, ASR and growing caches/recordings. The requested red
five-second notice applies to interactive setup only. Reuse Inno's existing
uninstaller, add visible shortcuts, and keep user data outside deletion rules.

The user explicitly supplied four references for distribution as defaults. This
supersedes the blanket no-recordings-in-git rule only for assets/voices: no model
weights or arbitrary user recordings are committed. Preserve source filenames and
user-requested titles, trim only Akuma Lady's overlong source to a documented
29.9-second copy, and never guess transcripts. Hash/copy samples once, then require
manual Prepare or a manually supplied exact transcript. Preserve deleted presets
and edits across upgrades. Reuse the existing isolated transcription pipeline.

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

## Per-voice OmniVoice parameter scope — 2026-10-27

The official OmniVoice demo exposes speed, fixed duration, num_step, denoise,
CFG, preprocess_prompt and postprocess_output. PacTTSClone already had speed
and step-count inputs; extend the request model/adapter to pass all seven
natively. A single OmniVoice model is shared by all saved voices, so persist
parameter defaults on the saved voice records, not separate per-voice model
weights. IRC/EventSub inherit the saved defaults; Studio submits overrides
per job. Do not restart a warm model or re-prepare a voice on parameter changes.

## RC9 release preparation — 2026-10-27

Keep the bundled original jingling-keys WebM and its single shared modal:
Configuration gains an explicit manual control, independent of Initial Setup's
one-time countermeasure offer. Keep autoplay readiness gating for the bug guide,
but defer its optional YouTube link until 2 s after the pane opens.
Version increment is RC9, not an overwrite of RC8. Change the merge-time
release gate to `prepare-release` with draft-only output. Do not publish
automatically, and do not bypass full Windows installer acceptance.


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

## Discord local ownership — 2026-10-28

The user authorized an installation-specific bot token stored locally. Each
installation uses its own dedicated Discord application; no developer bot token
is distributed. Reuse existing DPAPI protection and a separate 0600 credential
file, and expose only a saved/not-saved flag to the browser. A dedicated
discord.py Gateway client handles heartbeat/reconnect/protocol details; no new
handwritten Discord transport, tunnel or public interaction endpoint. Start with
guild-only slash commands returning MP3 attachments, sharing the existing local
queue and saved voice defaults. Voice-channel audio and automatic output
forwarding are excluded from this first increment. This explicit request permits
Discord posting while preserving Twitch's no-chat-posting behavior.

## SSE for dashboard notifications — 2026-11-01

Use one native EventSource per local dashboard and existing REST for commands.
A process-local dispatcher holds the latest topic values, and a shared sampler
combines committed changes/progress. Reconnection uses an authoritative baseline
instead of a durable event replay log; SQLite remains the source of truth. Retain
slower fallback for unsupported or stale streams and the testing Quick Tunnel.
Keep OBS polling/leases: WebSockets need a separate reconnect/ownership/watchdog
protocol and a playback latency benchmark. No new framework, broker, database
migration or integration dependency. LAN hosting remains separately planned.
