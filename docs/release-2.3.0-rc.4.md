# PacTTSClone 2.3.0-rc.4 — Multi-voice messages and custom SFX

- Switch configured voices in one Twitch message: `!pac something !lula somethingelse`.
- New **SFX** tab beside **Voices**: upload sounds, assign `[fart]` / `****` aliases,
  preview, adjust volume/duration, enable/disable, replace or delete.
- Whole voice utterances are generated first; cached CPU Whisper word timestamps
  locate inline sound insertion points. Missing or mismatched alignment falls back
  to separate phrases, recorded in the job report. Prefix/suffix sounds need no ASR.
- One combined MP3, OBS item and optional Discord attachment per message. Queued
  jobs preserve voice/sound snapshots and support cancellation, moderation and limits.
- Local generation supports inline SFX; Twitch includes a sequence preview.

## Updating

Compatible managed installations with experimental releases enabled (the default)
select this newer publication automatically. Close and reopen the app to activate.
Explicit version pins stay pinned. The application update preserves models, voices,
SFX and settings; no model downloads are introduced. New users can use the Windows
installer attached below.

## Validation and limits

PR #31 passed GitHub's cross-platform test workflow. Local coverage includes 363
backend tests, Chromium checks, real FFmpeg assembly and spawned-worker cancellation.
Real CUDA voice quality and Whisper word-cut accuracy have not been measured here.
Word timestamps are estimates; alignment may add CPU time/RAM and segmented fallback
can require extra generation. Sounds must be uploaded/configured; `****` inserts a
sound and does not automatically discover or censor spoken words.

Publication is gated by the full test suite, actual Windows installer/updater
acceptance and uploaded asset size/digest verification. See docs/multi-voice-sfx.md
for syntax, limits and behavior.
