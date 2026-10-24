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
or repository visibility change. Windows build/install evidence is pending the
new installer workflow; local Linux checks do not establish Windows install success.
