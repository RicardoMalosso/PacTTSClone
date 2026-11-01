# PacTTSClone v0.2 — status

## Implemented

- Spawned, reusable OmniVoice worker; bounded queues; real process-tree cancellation
  and recovery; idle model unloading; persisted CPU/CUDA/Automatic settings.
- Wall/stage timers, milestone/indeterminate progress, system CPU/RAM, worker RAM,
  optional NVIDIA data and structured per-stage hardware/time reports + JSONL logs.
- Saved voice title/original MP3/thumbnail/transcript, one-time automatic ASR,
  transcript editing, cancellation/restart recovery and persisted history.
- Per-channel read-only anonymous Twitch WSS IRC, command-to-voice mapping,
  mandatory basic slur filtering, optional profanity levels/custom phrases,
  cooldowns, text/queue limits, moderation history.
- Separate OBS/control pages; default 5-second moderation countdown; cancellation,
  replay/download, coordinator lease and remote OBS mirrors; Windows global panic.
- Homepage Cloudflare Quick Tunnel button, verified binary auto-download, independent
  admin/OBS capability links, secure cookie bootstrap, remote ACL and revocation.
- Browser-language detection + English/Brazilian Portuguese override, Canada/Brazil
  flag controls; original user content remains untranslated.

Current documents replace stale v1 exclusions; previous validation is archived in
v1-validation.md. V2 design and added scope: v2-design.md.

## Local execution evidence — 2026-10-24

Linux / Python 3.12.14. Deterministic results at the final local checkpoint:

| Check | Result |
|---|---|
| Core/API/process/FFmpeg tests | 114 passed |
| Chromium tests | 12 passed |
| Ruff check + formatting | Passed |
| JavaScript syntax (app, OBS, locale) | Passed |
| Build wheel | Passed; includes static HTML/CSS/JS |
| Actual spawned-worker cancellation/recovery | Passed with explicit test engine |
| Physical global hotkey | Native message-loop simulation passed; physical keypress pending |

### Actual OmniVoice, not a fake engine

The production process worker generated a valid MP3 using cached real weights in
CPU/offline mode. A second real preset workflow automatically transcribed the MP3,
saved the transcript and reused it for generation with no second ASR stage:

| Task | Wall seconds | Worker CPU seconds | Sampled peak worker RAM |
|---|---:|---:|---:|
| Real preset preparation / ASR | 11.83 | 28.9768 | 2,704,650,240 bytes |
| Speech using that saved transcript | 53.08 | 207.0595 | 5,102,972,928 bytes |

Hardware: AMD EPYC 9V74 host, 9 logical CPUs exposed, 4 inference threads,
10,451,439,616 bytes system RAM, no GPU. Torch/torchaudio 2.8.0+cpu,
omnivoice 0.2.1, transformers 5.20.2, reference 4.932 seconds (synthetic English
flite speech), Portuguese target “Olá, bom dia.”. CPU totals exceed elapsed time
because threads run in parallel. The speech job had decode/inference/encode stages
and no transcription stage. JSONL persisted the transcript and measurements.
These are short execution smokes, not real-time or perceptual-quality claims.

### Network integration evidence

- cloudflared 2026.10.3 was actually downloaded from the official release, its
  SHA-256 verified, and its CLI accepted the HTTP Host override flag.
- A real Quick Tunnel startup was attempted. This execution environment rejected
  outbound DNS/network to api.trycloudflare.com (“network is unreachable”). No
  public tunnel was left running. External routing therefore remains unverified.
- Actual anonymous Twitch WSS handshake was attempted; the environment timed out
  connecting through its HTTP proxy. Live Twitch connectivity remains unverified
  here. IRC parsing/framing/reconnection are covered by deterministic socket tests.
- Real browser tests emulate a public origin with forwarded Host and verify admin
  bootstrap, HttpOnly cookies, URL-fragment removal and OBS-only access restrictions.
  Those tests are separate from external network routing.

## CI and remaining validation

All GitHub Actions jobs passed for implementation commit
`2ec04019a0908d35fefb6ddea6a4470115e2b337`:
https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40068196955

- Windows Python 3.11 and 3.12: core tests, lint, wheel build and PowerShell syntax.
- Linux Python 3.11 and 3.12: core tests, lint and wheel build.
- Linux Chromium: all browser tests.

Final visual review inspected English/Portuguese studio and configuration screens.
A small follow-up makes live resource labels and hotkey status switch language
immediately instead of waiting for the next polling cycle; its locale browser
regression test passed. No production worker/model behavior changed afterward.

Still hardware/environment dependent: GTX 1660 SUPER 6 GB latency/VRAM, physical
Windows shortcut delivery, real OBS CEF behavior, external Cloudflare and live
Twitch connection on the user's PC. No GPU allocation/timing or network success
has been fabricated when unavailable. Basic lexical filters do not guarantee all
Twitch policy compliance or detect every evasion.

## Studio and general playback follow-up — 2026-10-24

- Gruvbox Dark studio with responsive recording-desk styling; transparent OBS
  styling remains separate. Desktop/mobile screenshots inspected, no horizontal
  overflow at 390px.
- Reapply interface locale across tabs; persist speech-language selection
  independently across reloads. Existing command voice dropdowns update when
  voice preparation completes, preserving command text and valid selections.
- `/playbackMain` and `/playbackMain/control` provide a general OBS queue without
  Twitch. Generate/History manually queue any successful generated MP3. Original
  channel metadata remains unchanged. Independent delay/filter/pause settings,
  cancellation, panic and general-player tunnel capability reuse existing logic.
- Validation: 116 backend/API/process tests and 15 Chromium tests passed. New
  coverage includes local/channel audio reuse, general FIFO countdown/acks/cancel,
  filter validation, player audio ACL, Generate-to-OBS browser playback and
  separate control routing; language persistence and live dropdown refresh.
- No new real-model/GPU/network performance claim is made by these fake-engine
  regression tests. Prior real CPU evidence remains above.

## Ctrl+C shutdown follow-up — 2026-10-24

The user's Windows console broadcast SIGINT to the idle spawned worker, which
printed KeyboardInterrupt at commands.get() although the server shut down.
The worker now ignores SIGINT immediately; server-controlled sentinel/hard-stop
shutdown remains authoritative. Actual spawned regression verifies child SIGINT
handling, same-PID subsequent generation and exit code zero on graceful reset.
All 117 backend tests, Ruff checks/formatting and diff checks passed locally.
Physical Windows Ctrl+C delivery remains a Windows acceptance check; the regression
checks the installed signal handler inside a real child on both CI platforms.

## Windows bootstrap preview — implementation checkpoint

Version 0.3.0rc1: Inno Setup source, isolated uv-managed Python, verified uv/FFmpeg
archives, CPU/CUDA dependencies downloaded at setup time, selectable separate data
folder, shortcuts, reusable caches and data-preserving uninstall. README now uses
general installation paths and documents source/installer distinctions. No signing
or repository visibility change. Windows installer workflow passed on commit
`0d83cf513b732ae8f64f72fefd63933532c12cd5`:
https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40110383432

- Inno Setup 6.7.1 compiled a 2,171,921-byte unsigned setup executable.
- Windows PowerShell 5.1 download/path/cache helper tests passed.
- Actual CPU installation downloaded managed Python 3.12.12, FFmpeg and real
  inference dependencies into paths containing spaces.
- Runtime imports, audio tools and installed-launcher HTTP health check passed.
- Repeated setup and uninstall retained the separate user-data marker.
- Draft prerelease v0.3.0-rc.1 contains setup, application wheel and SHA256SUMS.txt.
- Downloaded the CI artifact independently; both file hashes matched SHA256SUMS,
  and the executable's empty certificate directory confirmed it is unsigned.
- Local backend suite: 117 passed; Ruff and formatting passed. Core application
  CI passed Windows/Linux Python 3.11/3.12; browser CI is tracked separately.

The first setup smoke exposed default payload path initialization; the next exposed
managed-runtime path discovery. Explicit payload and pinned private Python paths
resolved these. The final complete install smoke passed, not only compilation.

Remaining acceptance: interactive wizard on a physical Windows PC, GPU dependency
installation and generation on that installed build. CI uses a Windows runner,
not a pristine consumer Windows VM. No model inference or CUDA performance claim
is inferred from the CPU installation/import/HTTP smoke.

## RC2 installer UX — implementation checkpoint

Added first-page large red storage/model/unsigned notice with a five-second
interactive Next gate. Default data is a sibling PacTTSClone-data directory;
checkbox unlocks a custom data path. Small red bold estimates sit beside both
pickers. Existing native uninstaller gains explicit Start Menu/app-folder links.
Windows validation passed in run 40112512322 on commit
`91823bf7121fd6ba93acdd9668d440c29ab42af1`:
https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40112512322

- Actual wizard automation verified disabled Next/countdown, both space labels,
  sibling data default, checkbox unlock/relock and default restoration.
- Screenshots visually reviewed: large red notice and small red bold estimates
  appear without overlap; disabled data picker and checkbox are visible.
- Real CPU installation used default sibling data layout under PacTTS, checked
  uninstaller links and launched the parent PacTTSClone.lnk to serve HTTP.
- Reinstall and uninstall preserved user data and removed the parent shortcut.
- RC2 draft setup: 3,608,636 bytes, below the 10 MiB gate and still unsigned.
- Setup/wheel checksums independently verified from the downloaded CI artifact.

## Default voices and parent launcher — implementation checkpoint

Bundled the four explicitly authorized user references in the wheel with hashes;
Akuma Lady is a 29.9-second copy of the 30.59-second original, other samples byte
unchanged. Defaults seed once without jobs/model downloads, require Prepare, and
retain edits/deletions across restarts. Preparation is idempotent with stored ASR
text, UI progress/cancel/retry and readiness gating. Added parent launcher shortcut.
All samples passed real FFmpeg reference decoding. Validation completed: 119 backend tests and 16 Chromium tests passed locally,
and all five Windows/Linux application CI jobs passed in run 40112512318:
https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40112512318

New tests cover lazy/default seeding, real FFmpeg decoding of all four references,
readiness gating, preparation/transcript reuse, persisted edits/deletion markers,
and first-use UI progress/cancel controls. The default voice generation path was
also exercised with an explicit test engine. All four references were verified
inside the release wheel against their catalog hashes. No real ASR accuracy or
new GPU performance claim is inferred from these application tests.

## RC3 bug guide — implementation checkpoint

Added localized Report a bug tab for the user-supplied b2eEl2oKXLA video. The embed
is absent initially, starts after a three-second user-triggered delay, requests
autoplay and unloads on tab exit/panic. Cancellation and manual-play/direct-link
fallback are explicit. No automatic report/log submission. Browser lifecycle tests
use a stubbed external frame; real YouTube playback is not asserted by those tests.

## Local autoqueue — implementation checkpoint

Added opt-in remembered checkbox beside autoplay. Upload and preset submissions
persist autoqueue_general; backend completion queues successful local speech once
to playbackMain and saves the item ID. Browser closure does not prevent queueing.
Channel jobs are not copied; rejection is surfaced through saved playback_error
and a separate queue-status label. Validation results recorded after test completion.

## Anonymized community benchmark documentation

README now records five successful CUDA generation timings and two separate
reference-preparation timings from a user-supplied local JSONL log. Only hardware,
non-content settings, aggregate wall time and model-loading state are published.
Voice labels A/B replace identifiers; raw logs, texts, transcripts, names, filenames,
paths, channels and timestamps are excluded. Output duration is explicitly missing
from the source, so no audio length or real-time factor is invented. Voice B has
preparation only; no successful speech run was fabricated. Table values and
anonymization were checked against the private input during documentation update.

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

RC4 local validation: ruff passed; 129 backend tests and 21 Chromium tests passed.
Browser checks include actual OBS/control new-tab navigation, stable links across
polls, first-run gate/progress/cancel/unlock, and Twitch active-job monitoring with
two queued requests, reload, cross-tab status and cancellation. Downloader checks
cover hash failure, exact cache reuse (including existing HF snapshots), HTTP Range
resume and servers ignoring Range. These use tiny fixtures/fake inference, not a
real model-generation benchmark. Live HF metadata plans resolved successfully for
OmniVoice (8 files, 3,267,443,402 bytes) and Whisper Small (11 files, 971,367,937 bytes).
Windows build/real dependency/model download validation remains pending CI. The
first source build failed because the isolated MSYS2 environment lacked git; git
and Python were added explicitly. A pre-existing browser timer test was made
deterministic by pausing its test clock; the application retains the three-second
delay. Obsolete preview builds are cancelled when a newer commit supersedes them.

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

Expanded RC4 local checks: 132 backend tests and 23 Chromium tests passed, plus
ruff/JavaScript syntax checks. Added actual long-reference crop/retained duration,
thumbnail replacement/invalid upload preservation/default migration tests, and
channel connect/disconnect/delete/history retention tests. Browser tests now import
references through Voices, then select a saved voice for generation. No new real
OmniVoice inference measurement is claimed. Windows acceptance remains pending.

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

Windows acceptance at commit 77252c5 completed every assertion: minimal install,
root shortcut HTTP launch, actual CPU PyTorch/OmniVoice imports, download and hash
verification of 4,238,811,339 model bytes through the web setup API, repeat install
reusing Python/download caches, and uninstall preserving data. The workflow then
reported exit 1 because the test script inherited a best-effort cleanup command's
LASTEXITCODE; the script now explicitly exits 0 only after all checked assertions
pass. This does not skip any failed assertion. The next build packages that fix
and the validated cross-browser result controls. No real-model synthesis/GPU
performance is asserted by this installation/import/download test.

## RC4 verified installer snapshot

Snapshot: aa06a85720d459e07ae15f749c64e2e518a0ee54. Windows installer workflow
40130667963 succeeded; test workflow 40130667999 succeeded (Windows/Linux,
Python 3.11/3.12 plus Chromium). Local/application totals: 138 backend tests and
25 browser tests. Actual Windows acceptance passed native wizard error/delay/path
checks, minimal install without PyTorch, root shortcut HTTP launch, web CPU runtime
installation and verified model download, repeat install and data-preserving
uninstall. Real inference quality and physical CUDA remain separate checks.

Draft preview: https://github.com/RicardoMalosso/PacTTSClone/releases/tag/untagged-6b421e5dab1ef8ce46d5
Installer: PacTTSClone-Setup-0.3.0-rc.4.exe, 4,331,203 bytes, unsigned.
SHA-256: 3a986c5ee329c221d6a90ade29e3eae4128bd0ed691c416868d6e0f009e9ed60.
Downloaded the workflow ZIP and independently verified every SHA256SUMS entry;
installer/wheel/FFmpeg archive hashes also match GitHub release asset digests.
No unfinished feature or auto-updater was added to this snapshot. Future feature
work must preserve these RC4 artifacts and use a new version for another installer.


## Reference transcription regression — 2026-10-24

The packaged minimal FFmpeg omitted the f32le muxer and pcm_f32le encoder used
by Transformers ffmpeg_read. Enable both and execute that exact pipe protocol
against the newly compiled Windows binary in the installer build. ASR receives
already decoded float32 PCM through OmniVoice's tuple API, avoiding a second
FFmpeg decode. A regression uses real MP3/WAV decoding, verifies every PCM sample
and rate, blocks subprocess creation during transcription, and checks lazy ASR
reuse; the model is mocked, not real inference.

Local checks: 136 backend tests passed (tests/test_default_voices.py excluded
because binary preset assets are unavailable in this connector checkout); all
22 focused engine/audio tests passed; ruff and bash syntax checks passed. The new
regression fails when the old path-based model call is restored. Initial broad
run failed because the partial checkout lacked static files; after retrieving
those files and installing local metadata the above backend run passed.
Windows compiled-binary smoke awaits GitHub Actions. No real Whisper/OmniVoice
weights or physical GPU inference were executed locally; these results do not
establish speech quality or end-to-end model inference.


## RC5 Work-session reconciliation — 2026-10-24

Reviewed PR #4 at `3be5ecad11523ee9b25d348e537e0f8651e0b128`, its recent
commits and project documentation. Run 40139655898 passed fast checks, Windows
FFmpeg and all four Windows/Linux Python 3.11/3.12 core jobs. Chromium had 25
passing tests and one failure: the countermeasures test dismissed the video
before waiting for its clock to advance. The test now checks playback before
closing and observes two complete loop transitions plus decoded, unmuted audio.

The old bundled file was a 9,308-byte 128x72 derivative. Restored the exact
136,654-byte 640x360 original supplied by the user; digest and installed HTTP/
FFmpeg acceptance protect that identity. Current-tree search found no Tenor or
GIF dependency to remove. Local core suite: 142 passed; Ruff, Python compilation,
JavaScript syntax, actual video/audio FFmpeg decode and wheel hash verification
passed. All 26 local Chromium tests passed (69.20 seconds), including two observed
full loops and audio decoding. Final GitHub/installer results remain pending; no model inference or physical audio-device claim is implied.



## Overnight known-issue and release review — 2026-10-25

Current review: [known issues](known-issues.md). Rechecked original pending items
against main e71b39bf8caaf7d4c01466c69da5df3ecf481551, source/tests, all seven
post-merge CI jobs and the successful Windows installer acceptance job logs.
The earlier RC5 pending-results note is superseded: those runs passed.

Fresh local Linux/Python 3.12 rerun: 142 core tests passed (18.11 s), 26 Chromium
tests passed (70.45 s); Ruff, Python compilation and all three JavaScript syntax
checks passed. One upstream Starlette TestClient/httpx deprecation warning was
reported; no failed tests. These checks use deterministic inference substitutes
and real FFmpeg/browser playback, not new real-model or physical CUDA inference.

Confirmed draft RC5 already contains the validated installer, wheel, FFmpeg
provenance and SHA256SUMS. Re-downloaded the accepted Actions ZIP, verified its
archive hash, every packaged checksum and original WebM identity in the wheel;
installer/wheel/provenance hashes match draft release asset digests. Corrected
README's stale RC4 download recommendation to RC5 (59.73 MB). Existing binaries
were preserved; no redundant installer build or release publication was needed.

No critical regression reproduced. Punctuation/prosody, automatic updates and
Bits/Channel Points remain unimplemented features, explicitly listed separately
from resolved bugs. Public routing, live Twitch, OBS CEF, physical hotkey/audio
and user GPU validation still need the relevant environment. The discarded
temporary demonstration was not preserved.

## RC6 Twitch events and optional imports — 2026-10-25

Implemented per-channel anonymous IRC or authorized EventSub, public-client Device
OAuth, host-only credential/reward endpoints, Windows DPAPI, refresh/validation,
configurable event-to-voice rules, individual subscription diagnostics, durable
deduplication, managed reward settlement after OBS playback, refunds and bounded
reconnect recovery. See twitch-eventsub.md for exact scopes and limitations.

Configuration is available before Initial Setup completes. Optional imports are
independent: verified large model weights with explicit copy/move; and additive
configuration/voice/completed-audio migration preserving the source and backing up
current metadata. Models never import old configs. Personal data remaps IDs, keeps
existing assets/channels, supports explicit application-settings replacement and
never replays old pending queues. See optional-imports.md.

Local Linux/Python 3.12 validation: 177 core tests passed (27.11 s), 29 Chromium
tests passed (78.81 s), Ruff/Python compilation/JavaScript syntax passed. Final wheel
built and includes the new modules. Desktop/mobile Twitch and pre-setup Configuration
screens inspected; no horizontal overflow at 390px. One upstream Starlette
TestClient/httpx deprecation warning, no failed tests. The model-import fixtures
lower the 64 MiB threshold; real files still require exact pinned size/SHA-256.
Tests cover source preservation, incompatible weights, shared-cache copies,
explicit moves, migration mapping/idempotency, backup/rollback/cancellation,
pre-setup Config access and generation gating. Twitch tests use simulated service
responses and explicit fake inference, not real paid transactions or new synthesis.

Cross-platform CI results will be checked before merging this source change.
No registered public Twitch Client ID is bundled: broadcaster authorization and
live paid-event acceptance require one and remain unverified here. RC5 release
assets are preserved; source, installer version metadata and future draft recipe
advance to RC6 without overwriting RC5. The user subsequently authorized RC6
publication after passing tests and installer acceptance; the explicit merged-PR
publication workflow enforces that gate. Final results will be reported from Actions.


## RC6 release gate caught initialization race

PR #5 passed all seven checks and merged as 96bd04378b7e7d02fa97abec4b89486cb86fcc49
with an identical tested tree. Release run 40162639296 correctly blocked the
installer/publication when Chromium reproduced a late initialization response
resetting an unsaved OAuth mode back to the persisted IRC setting. Initialization
now honors the user's selected tab and channel draft. A deterministic browser
regression holds the initial resources response, edits the mode, releases the
response and verifies OAuth remains visible after the next poll.
Publication remains blocked until validation of this corrected source completes.

The RC6 follow-up also drains notifications from the old EventSub socket while the
replacement opens/waits for its welcome, rather than leaving them unread in the
old socket's buffer. Its regression delivers a notification during a deliberately
blocked new welcome and verifies delivery before old-socket closure. The focused
26 Twitch core tests pass, and all 30 Chromium tests pass locally after the UI fix.

## RC6 published and independently verified

RC6 was published as a prerelease after run 40163520519 passed the full reusable
suite, actual Windows installer acceptance and target-checked publication. Final
source 5293b9ab7b6c242b2d6dd4611479eadcaa900172 has the tested tree. Final local
counts: 178 core and 30 Chromium tests passed; final PR and post-merge CI passed
Windows/Linux Python 3.11/3.12 and Chromium. Real Windows CPU setup imported the
runtime and verified 4,238,811,339 model bytes; launcher/reinstall/data-preserving
uninstall passed. A separate 64 MiB fixture exercised the production import threshold.

Downloaded accepted artifact 12587508059; ZIP SHA-256
28d754145d1083e32d93e64ee1c8321d231aa88ef475c2cb31e254b119ab190c matched.
All SHA256SUMS entries and all four published asset digests/sizes matched.
The wheel's 42 application files match source after Windows text EOL normalization;
all binaries, including the original WebM, match exactly. Installer is 59,754,609
bytes; SHA-256 cfb975b5b21bd23344a9c829268e996d2039702596b8b6230021967819dc3aa1.
No earlier release was overwritten. Source credential/local-data ignores and this
completion documentation do not change the accepted runtime or require a rebuild.

Full evidence and limitations: [RC6 completion report](rc6-completion-report.md).
Live broadcaster consent/paid-event acceptance still needs a public Twitch Client ID
and matching account authorization; no such success or physical GPU/OBS result is
inferred from simulated-event tests or installer acceptance.


## Twitch connection UI simplification

New UI-created channels start IRC automatically. Removed the monitoring checkbox
and transport dropdown. Channel on/off controls now live in the right-hand list;
edits preserve Off. An explicit enable-events button opens broadcaster authorization,
reward creation and event rules. IRC and EventSub run alongside each other, with
EventSub chat subscriptions omitted to avoid duplicate command speech. Disabling
events preserves IRC and existing rules; channel off/delete/shutdown closes both.
Added PT-BR labels, save confirmation and event-specific template defaults. External
donations are explicitly unavailable; user selected Twitch-only scope for now.

Local validation: 178 core tests and 31 Chromium tests passed; Ruff, Python
compilation and JavaScript syntax checks passed. Desktop sidebar placement and
390px overflow are covered. Tests use fake IRC, Twitch
responses and inference, not real broadcaster consent or paid transactions.


## CUDA-only and Local UI follow-up
Speech inference now requires CUDA, including legacy CPU selections. CPU remains
for transcription/audio processing. Initialization no longer claims CPU inference.
CUDA/OOM failures preserve actionable errors in request history and generation logs.
The status shows unchecked, model loaded, active stage, or latest CUDA failure; it
is not a continuous independent CUDA probe. Windows driver-reset recovery and the
reported gaming stall still need real hardware evidence. No VRAM preallocation.

Setup hides after success; Configuration owns settings. Re-selecting an existing
CUDA setup does not install/hash again. Existing verified manifests reuse model
files by presence/size; CPU-only installations require the one-time CUDA setup.
Local generation and local OBS controls share the final Local tab. Native reward
cooldown and per-stream/per-user limits support creation and editing manageable
rewards; other rewards remain editable in Twitch.

Per-job logs/generation-vram.jsonl records start, half-second worker samples and end
(including failures/cancellation): total/used/free device VRAM plus separate PyTorch
allocated/reserved bytes. Missing readings stay unavailable, not zero. A configurable
512 MiB advisory warning logs pressure/recovery transitions; it reserves no memory.

Validation: final full core 184 passed and Chromium 31 passed with logging/status
changes; Ruff and syntax checks passed. Windows installer acceptance now expects
its CPU dependency-only smoke to leave CUDA generation locked; this updated
acceptance script has not been run locally. Restart persistence verified
for channel config and blocked/queued/running/failed/cancelled requests. Interrupted
jobs become cancelled without replay. Tests use simulated inference/CUDA; no real
GPU gaming benchmark or new Windows installer acceptance is claimed.


## Channel cards, setup visibility and reinstall reuse
All saved Twitch channel cards expose playback pause/resume, OBS player link and
a collapsible pending queue without first selecting the channel editor. Queue
refreshes preserve expanded state; channel configuration remains persisted.
Healthy setup remains hidden unless the Configuration checkbox is enabled; this
visibility preference is browser-local and survives refresh. Unhealthy setup stays
available.
The Windows bootstrap reuses an existing compatible application environment only
inside this installation's environments directory, preserving downloaded inference
packages across app version upgrades. Existing managed Python is reused; uv/pip
caches and checksum-verified downloader reuse remain active. Models retain their
verified manifest reuse or existing-file checksum validation after fresh setup.
Missing/incompatible/corrupt files may still need downloading. Different installation
roots require optional data/model imports; no arbitrary disk scanning is implied.
Windows acceptance now asserts repeat setup retains the Python environment and
inference imports. Local native Windows execution remains unavailable.

Local follow-up checks: 184 core tests passed. Chromium: 31 passed in the
full run, with one ambiguous test locator after adding the second OBS link;
that locator was scoped to the existing channel control and rechecked separately.
The new saved-card/Setup-toggle browser regression passed. Windows bootstrap
execution and the updated reinstall assertions remain pending Windows CI.


## RC8 public Twitch identity and ready-gated bug video
Bundled owner-supplied public Client ID 93mkh0su05k4ouzlkdk9jtu55f9ak2; the normal UI no longer asks for keys or registration. Backend defaults to the bundled ID while retaining developer environment overrides and existing account IDs. Twitch's real device endpoint accepted this ID (200), and secret-free token polling returned authorization_pending. No broadcaster account was authorized.
Bug-video player uses the official YouTube IFrame API readiness event, opens its tab only when ready, and requests playback 200 ms later. Navigation/panic cancels it; a 20-second loading timeout offers a direct video link.
Local core 184 passed; browser/release checks tracked in Actions. Actual consent and browser autoplay restrictions remain separate acceptance items.

## Voice generation tuning — implementation checkpoint 2026-10-27

Implemented saved per-voice generation defaults and API for OmniVoice speed,
optional duration, inference steps, denoise, CFG, reference preprocessing and
output postprocessing. Voices exposes editable defaults and restore-to-defaults;
Local Studio provides per-job overrides. Twitch requests inherit each voice's
presets. Effective parameters persist in generation request history.
Automated adapter/backend/Chromium regression coverage added. GPU quality
and latency, actual inference, Windows installer acceptance and release
verification remain **unverified for this change** pending CI and host tests.

## RC9 configuration and bug-guide polish — 2026-10-27

Manual Configure → Deploy countermeasures launches the exact looping
jingling-keys clip with its existing two-second loading UI and close behavior;
it does not mutate initial setup state. Bug-guide direct YouTube link is delayed
two seconds from the ready-gated tab becoming visible and cancelled on exit.
Added Chromium regressions for manual clip behavior and YouTube link timing.
Prepared `0.3.0rc9` draft-only release pipeline and notes; previous RC8 remains
untouched. Release remains contingent on all Python/Chromium checks and actual
Windows installer acceptance; no claim of local GPU-inference quality validation.


## RC10 Automatic speech language — 2026-10-28

Language is now a validated saved voice setting (Automatic/PT/EN), inherited by
IRC commands and EventSub rules. New and legacy voices without a saved language,
and legacy multipart requests, default to Automatic. Local loads each voice's
language and permits a one-job override; obsolete browser-only language preferences
are ignored. Restore defaults selects Automatic. Versions advance to 0.3.0rc10,
including the previously stale runtime __version__.

Local validation: 203 core tests and 35 Chromium tests passed; Ruff, Python
compilation, JavaScript syntax and workflow YAML parsing passed. Expanded the
Chromium preset regression to cover restoring Automatic; its focused recheck is
recorded with the PR. Tests use fake inference, not a physical NVIDIA quality or
performance measurement. Cross-platform CI and actual Windows installer acceptance
must pass before owner-authorized RC10 publication. Uploaded release asset sizes,
SHA-256 digests and target commit are checked before the draft becomes public.

## Local Discord integration — 2026-10-28

Added opt-in Configuration controls for a locally saved bot token, one server,
optional channel restrictions, default voice, filters, text limits and cooldowns.
Windows uses existing user-bound DPAPI; other systems use a 0600 credential file.
Host-only APIs never return the token; shared admins cannot read/change settings.
The installer dependency list includes discord.py and its runtime import check.

A dedicated Gateway client registers `/tts` and `/voices` without privileged
intents or a public endpoint. Speech shares the existing local worker and saved
voice language/settings, with Discord-origin audit records and no implicit OBS
queueing. First login produces an invite link; guild join syncs commands.
Disconnect/reconfigure/remove/cancel-all/shutdown cancel undelivered work;
interaction timeouts cancel generation and upload failures retain local MP3s.

Validation: 238 core tests passed; Ruff, Python compilation, JavaScript syntax,
diff checks and wheel build passed. The built wheel contains the Discord modules
and dependency metadata. Credential/API/Gateway tests use simulated Discord and
fake inference with real FFmpeg MP3 output; DPAPI dispatch is simulated locally.
Actual Discord authorization/delivery, Windows DPAPI, a new Windows installer
and GPU performance remain unverified for this change. Existing published RC10
assets are unchanged; this source change is not a release.

Chromium: all 36 tests passed in the final full run. Desktop and 390 px mobile
Discord settings were visually inspected. One earlier existing requester-name
initialization test timed out, then passed both a focused recheck and the full
rerun. New coverage includes token clearing/removal, settings persistence,
connection controls, PT-BR labels, draft preservation and hidden remote controls.

## Discord continuation — 2026-10-29

Recovered the existing implementation on current RC10 main and reviewed its
lifecycle. Fixed Gateway resume leaving the UI at reconnecting, and cancelled
command delivery leaving generation orphaned when threaded submission completes
after cancellation. Shutdown drains command cleanup before closing the client;
failed uploads still retain completed audio in local History.

Validation: 242 backend tests and all 36 Chromium tests passed. The 39 Discord
tests include controlled cancellation races, resume status and failed-upload
retention. Ruff, Python compilation, JavaScript syntax, diff checks and wheel
build passed; wheel modules and discord.py dependency metadata were verified.
Discord/API and inference remain simulated, with real FFmpeg output. Live bot
delivery, physical GPU behavior and a new Windows installer remain unverified.
This is source implementation work, not a new release or replacement RC10 asset.

## RC11 release preparation — 2026-10-29

Owner requested the Discord release. Versioned application/runtime/installer as
RC11 and updated the existing gated publication workflow and release notes.
Publication requires full cross-platform checks, Windows installer acceptance
and asset digest verification; previous RC10 assets remain unchanged.

## RC11 accepted installer publication recovery — 2026-10-29

Release run 40971665005 passed every Windows/Linux Python 3.11/3.12 and Chromium
job, plus actual Windows wizard, CPU/model setup, launcher, reinstall and uninstall
acceptance. It built/uploaded four RC11 files and created draft 428493183 at
24196cbe86a730e1c036e456b77eee298e51ee23. Publication alone failed because the
release-by-tag API returned 404 for the draft. Resolve drafts through the releases
collection and publish by numeric ID. A scoped recovery verifies the original
acceptance steps, artifact checksums, release target and all asset digests before
publishing that same draft. No inference/GPU or live Discord quality claim is added.

## Application auto-updates — 2026-10-30

RC12 adds automatic public GitHub release checks at startup/every six hours,
verified application-wheel downloads, isolated import/dependency preflight and
atomic next-launch activation. Configuration exposes host-only status/manual
checks and PT-BR help. Models, CUDA and personal data are preserved. Source
installs use Git. Release workflow derives package/tag/installer identity instead
of hardcoding RC11; published assets remain immutable.

Validation: 256 core tests, all 36 existing Chromium tests and the new update UI
Chromium test passed. Ruff, JavaScript syntax, Python compilation, wheel build
and diff checks passed. Downloads/release metadata and activation are simulated
in deterministic tests; no actual Windows update lifecycle or new installer
acceptance has been run locally. Dependency migrations require setup repair;
rollback and first-install requirements are documented in auto-updates.md.
## Voice output volume and control explanations — 2026-10-30

Added saved per-voice output volume, 0–300 percent (100 unchanged, 0 mute),
inherited by integration jobs and overridable per local generation. The worker
applies gain before MP3 encoding so playback and uploaded files share the level.
Existing audio/reference files remain unchanged. Excessive boost clips peaks.
Every voice/local generation setting now has explanatory EN/PT-BR help.

Validation: 245 core tests passed, plus all 30 focused audio/preset tests after
adding four real FFmpeg volume checks (mute/attenuate/unity/boost). Preset tests
cover persistence, inheritance, override and invalid values. Ruff, Python
compilation, JavaScript syntax and diff checks passed. Browser validation is
recorded with the PR. Real GPU generation and Windows acceptance are not claimed.

Voice control explanations now appear as mouseover hints on labels and inputs,
with accessible descriptions and locale updates for EN/PT-BR.

## v2.0.0 release preparation — 2026-10-30

Combined updater and voice-volume/mouseover PRs. Replaced the old Discord bot
with an output-only webhook, source/channel/voice filtering, a test button,
step-by-step EN/PT-BR help, a bounded delivery queue and visible sanitized errors.
Legacy bot credentials/config and SDK are removed; no incoming Discord commands.
Versioned package/runtime/installer as 2.0.0, tag v2.0.0. Stable publication uses
release notes and latest-release designation. Existing AppId/data paths stay intact.

Local validation: 235 core tests passed, plus a focused 14-test updater recheck
after correcting interpreter-specific activation paths. Real installed-wheel
activation, next-interpreter version selection and rollback passed with a local
release fixture; no network download or Windows execution is claimed for that
check. Windows installer acceptance now executes the same lifecycle check.
Ruff, JavaScript syntax, compilation, workflow YAML, wheel build and diff checks
passed. Browser and actual Windows acceptance results are tracked in the release PR.
Live Discord/GPU validation remains separate from controlled transport/inference tests.

## Engines manager implementation — 2026-10-31

Initial Task 1 implementation adds host-only catalogue and install/cancel controls
using the existing runtime setup, persistent active/deactivated selection, and
manifest-scoped uninstall after deactivation while queues are idle. Existing model
files are recognized. Ming 3.0 and KittenTTS2 remain planned without install buttons.
The table distinguishes unknown VRAM/disk estimates from measured installed bytes.
Model downloads check free space before transfer. New lifecycle/API/Chromium tests
cover deletion boundaries, busy state, unsupported engines and token enforcement.

Validation so far: 238 core tests passed before the additional API test; 16 focused
engine/setup checks passed. Ruff, JS syntax and compilation passed. The new Chromium catalogue/localization test passed; full Chromium
is in progress. Real CUDA and Windows installer acceptance are not claimed.
Task 1 remains in progress: complete sourced hardware/features metadata, installation
peak/runtime accounting, full EN/PT dynamic text and release validation before
publishing. No release yet. Tasks 2/3 have not begun.

### Engines follow-up — 2026-10-31

Added pinned model/revision and download-plan totals, upstream documentation links,
license/runtime/language and per-feature details. Unverified requirements remain
explicitly unknown. Added dynamic PT translations, active versus resident status,
and remote engine ACL exclusion. Fixed new installs activating implicitly: Engines
installation now requires a separate Activate action. Initial Setup remains compatible.
Added null-progress/pinned-plan, symlink containment and explicit-activation regressions.
Full core suite: 242 passed. Focused engine/setup: 20 passed. Ruff and JS syntax passed.
Previous full Chromium: 38 passed; new uninstall/retained-personal-file regression
is being checked. Windows installer acceptance and a release remain pending.

## Ming adapter started — 2026-10-31

User requested beginning Ming before the Task 1 release completes. Added an
inference-only dense 0.5b adapter and upstream source/runtime inspection record
in ming-integration.md. It is not wired to production or advertised as installable.
Ten deterministic tests passed for request mapping, unsupported language/settings,
CUDA/BF16 rejection and waveform normalization. Ruff passed. Upstream BF16 excludes
GTX 1660 SUPER in this implementation; FP16 needs separate real validation.
Runtime isolation, verified installs/UI, task controls and real inference remain.

## Ming integration implementation — 2026-10-31

Implemented host-only lifecycle and verified source/model manifests, private CUDA
runtime, persistent JSON/WAV inference bridge, preflight/selection persistence,
separate voice task defaults, Local controls and normal Twitch/MP3/OBS/Discord
routing. Supports dense 0.5B cloning/tags, multilingual, emotion, attributes,
dialect, freeform/design and selected preset voices. Does not expose Tiny MoE.
Native BF16 NVIDIA GPU required; no personal hardware constraints and no CPU speech.

Fixed the shared downloader's zero-byte repository-file bug and graceful worker
shutdown leaving a resident external inference process. Added real child transport
and shutdown tests, activation rollback/restart, task/default separation and browser
coverage. Core 269 and Chromium 40 passed before final metadata checks; focused
follow-ups passed. Ruff, JS syntax, Python compilation and application wheel passed.

Actual Linux installation downloaded/verified 3,003,464,609 model/source bytes,
installed the private Torch/CUDA/Transformers stack, passed pip check and imported
upstream Ming. A repeat with asset HTTP disabled reused verified assets/packages.
Observed total runtime/cache/assets approximately 15.3 GB; not a universal minimum.
Actual CPU-only preflight returned the required CUDA error, without fallback.
No physical GPU synthesis, audio quality, minimum VRAM or latency result is claimed.
Windows private-runtime/import and installer acceptance will run in Actions.
Task 1 PR21 merged after all seven versioned CI jobs passed; its separate 2.1.0
publication workflow is running. Ming is prepared as separate 2.2.0rc1 preview.

### Ming cross-platform runtime validation

Actions run 41232561493 passed real private CUDA dependency installation, verified
source imports and repeated runtime/cache reuse on both Windows and Linux.
Run 41232561209 passed all seven Windows/Linux core/Chromium/tooling jobs; its
Windows installer acceptance is in progress. Final local core: 271 passed; full
Chromium: 40 passed; final targeted Engines/Ming UI: 3 passed. Visual inspection
confirmed desktop/mobile layout with no overflow at 390px. A final UI correction
keeps Ming controls inside the collapsible settings panel and makes health/help
text describe the active engine. No runtime/dependency contract changed.

Task 1 release v2.1.0 is published with installer, application wheel, provenance and
checksums after run 41232408239 passed actual Windows install/reinstall/uninstall
and uploaded-asset validation. Ming remains a separate release.
Final Ming packaging correction derives Inno's numeric version from the package
version, avoiding RC suffixes in VersionInfoVersion. Added a regression for that
contract and a cached-runtime low-disk regression; cache reuse no longer reserves
another full runtime budget. Asset progress is rate limited while retaining real bytes.

## KittenTTS2 — v2.3.0-rc.1 preview

Native CUDA adapter, verified asset manifests, isolated installer/lifecycle and engine-specific Local/Voices controls are implemented. See [validation status](kitten-integration.md). All 295 local backend and 41 Chromium tests passed; actual isolated runtime install/import/cache acceptance passed on Windows/Linux. The separate [v2.3.0-rc.1 release](https://github.com/RicardoMalosso/PacTTSClone/releases/tag/v2.3.0-rc.1) is published only after final CI/Windows acceptance; no physical GPU synthesis claim.

## 2.2.1 updater channels and versions

Restored implementation after transient workspace reset. Adds default-on experimental
updates, publication-date ordering, persistent previous-version pins and rollback
controls. Preserves the separately released 2.1.1 webhook fix. All 302 local backend
and 42 Chromium tests passed. Actual installed-interpreter activation, rollback to
the public 2.1.1 wheel, persistent pin and forward staging from that older app
passed. Ruff, compilation, JS syntax, bridge RECORD/import validation and visual
inspection passed. Native Windows acceptance and publication are tracked in PR #25;
no physical GPU inference claim is added.

Windows acceptance caught a preflight cleanup error: its temporary application
kept SQLite open during directory deletion. The probe and historical acceptance
now close the studio/service before cleanup; child stderr is retained on failure.
Publication remains gated on a successful native rerun.
