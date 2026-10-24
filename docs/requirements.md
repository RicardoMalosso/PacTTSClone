# Requirements — v1

## Scope and workflow

Local browser application for Windows first; portable Python implementation.
Choose a local MP3 reference, type Portuguese text, optionally type the exact
reference transcript, generate a local MP3, play/pause/seek/change volume and
download it. Optional autoplay is off by default and browser permission dependent.
First inference downloads public model assets; cached use can be offline.

## Acceptance criteria

| ID | Behavior |
|---|---|
| R1 | Accept MP3 reference up to 20 MiB; decode and validate 1–30 s of mono audio; recommend 3–10 s. Invalid audio produces an actionable error. |
| R2 | Require nonempty target text, maximum 2,000 characters. Default language Portuguese (`pt`); also offer English and automatic. |
| R3 | Optional transcript: blank invokes local Whisper on CPU; supplied transcript avoids loading Whisper. |
| R4 | Produce a valid MP3 at 192 kbps in the configured local outputs directory. Output names are generated identifiers; failed jobs leave no partial result. |
| R5 | Show processing state and failure reason without blocking the HTTP server. Only one job is accepted at a time; busy requests fail explicitly. |
| R6 | Playback uses native audio controls plus stop/restart; optional autoplay reports when the browser blocks it. Download works independently of autoplay. |
| R7 | Bind to 127.0.0.1 only; validate Host/Origin; require a per-process session token for mutation. No remote inference or uploading recordings to third parties. |
| R8 | Auto-select CUDA when available, otherwise CPU. Explicit device override supported. Inference remains lazy; opening UI does not load weights. |
| R9 | Errors identify missing FFmpeg, missing inference dependencies, model download/load failures and insufficient memory. A failure releases the worker for subsequent attempts. |
| R10 | Unit, API, real FFmpeg integration and browser tests; optional real OmniVoice smoke recorded separately. |

## Excluded from v1

Twitch/IRC/EventSub, Bits/channel-point validation, queueing remote requests,
OBS integration, voice library, training, explicit pause syntax, packaging as an
EXE, multi-user access and LAN exposure. Future channel point redemptions require
investigating Twitch event APIs; do not assume IRC supplies all redemption events.

## Resource and retention policy

Use short references and bounded text to limit resource use. Each job's reference
and temporary PCM files are removed on success/failure. Final MP3s persist until
the user deletes them in the outputs directory. Browser refresh does not delete
MP3s. Job state is process-local and bounded; UI need not restore it after restart.
Do not promise specific memory or latency on untested hardware.
