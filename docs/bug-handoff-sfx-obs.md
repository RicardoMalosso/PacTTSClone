# PacTTSClone: SFX and OBS bug handoff

## Repository and release state

Repository: https://github.com/RicardoMalosso/PacTTSClone

The affected published version is **v2.3.0-rc.4**, main commit
`4e06da107d9e5c843967ecef81926616df82646e` (PR #31).
Proposed repairs are on **fix/sfx-catalogue-audio-boundaries**. These changes are
unfinished and unmerged. A prepared `2.3.0rc5` version bump/release note is included,
but **rc.5 has NOT been released**. Do not assume preparation means validation.
The user requested this handoff rather than continued speculative fixes.

## User reports

1. SFX should save and edit multiple entries like Voices, but saved effects are not
   visible/editable; the user suspects they are not saving at all.
2. Inline effects occur in wrong mid-sentence positions, and multiple requests
   appear to lose their beginning. Required syntax: `!pac something !lula somethingelse`.
3. Reopening the app breaks the existing OBS source, displaying:
   `Shared link expired or unauthorized. Open the latest complete OBS link from Configuration.`
   Local OBS URLs must survive app restarts.

## Confirmed findings versus unresolved causes

### Saving and SFX UI

- Saving works in controlled production API/browser tests, including three distinct
  SFX records/audio files surviving application recreation. This does **not** reproduce
  or disprove the user's actual failing upload. No backend data-loss defect has been found.
- The old upload form filled the screen and pushed saved cards below it. Generic
  upload errors appeared in a global banner above the user's scroll position.
- Old previews played the original audio, ignoring saved volume/duration. This could
  look like edits were not saved, but is not proven to explain the user's report.
- Validation can reject files over 10 MiB or 15 seconds, duplicate triggers, reserved
  model tags, invalid audio and settings. Need the actual upload and response/error.

Proposed changes: saved-first searchable card grid, explicit Edit/Add controls,
server catalogue readback, visible save confirmations and inline failures, upload
retention on failure, unchanged card reuse to preserve unrelated drafts. New
`GET /api/sfx/{id}/preview` applies saved volume/duration using the same PCM helper
as composition. Raw uploads remain available at `/audio`.

Relevant files: `sfx.py`, `audio.py`, `app.py`, `static/sfx.js`, `static/index.html`,
`static/style.css`, `static/i18n.js`. Data: SQLite documents with kind `sfx`, and
`<data-dir>/sfx/<id>.wav`.

### Mid-sentence insertion and missing beginnings

- `composition.py` generates each voice section as one utterance without SFX text,
  aligns with cached CPU Whisper word timestamps, then inserts normalized PCM.
  Missing/mismatched timestamps trigger separate phrase generation.
- Old code accepted exact recognized words and finite/monotonic timestamps, then
  cut at the midpoint between adjacent word timestamps. That does NOT establish
  a safe acoustic boundary. It can cut a syllable despite matching words.
- Proposed change additionally requires a quiet PCM interval of at least 20 ms
  inside that estimated gap. Otherwise use the existing phrase fallback. This is
  conservative mitigation, **not real-world validation of correct word placement**.
  Speech sample counts and SFX source/output positions are added to reports.
- Synthetic real-FFmpeg checks preserve initial PCM for multiple effects and voices.
  These checks cannot establish whether a real TTS model omitted initial words
  before assembly, or whether short fallback phrases cause omission/prosody problems.
- OBS mirrors previously always sought to `server_time - started_at` when starting.
  An existing mirror can therefore skip the first word. Proposed changes preload
  during countdown and start at zero for a clip the mirror observed queueing;
  genuinely late joins still seek. This may trade exact mirror synchronization for
  intact beginnings and requires review. It does not explain a clipped downloaded MP3.

Relevant files: `message_script.py`, `studio.py`, `voices.py`, `worker.py`,
`composition.py`, `audio.py`, `static/obs.js`, `playback.py`.

### OBS restart authorization

- **Confirmed code defect:** app startup rotates the CSRF token. `obs.js` treated
  any tick 403 without a shared-key retry as permanent expiration and set
  `halted=true`. A local source with a stale token therefore stopped forever.
- Startup connection failure also showed a reload message without starting retries.
- Proposed changes refresh `/api/session` after stale-token 403 and retry unavailable
  startup. Fresh invalid shared capabilities still halt. Existing scoped capability
  handling and fragment removal are retained; access controls are not disabled.
- New Chromium tests pass for stale-token refresh and server-offline startup using
  the production player script. These simulate protocol failures; an actual full
  installed app/OBS restart should still be tested.
- Already-open old OBS pages need a one-time source refresh to load a repaired JS
  script. No URL replacement should be required for local sources.

## Validation actually performed

- Full backend suite: **367 passed** (before the final shared preview helper/API
  extraction; most subsequent focused checks passed, see next item).
- Later focused SFX suite: **23 passed, 1 timed out** waiting 10 seconds for the
  multi-voice onset job while another suite was running. Do not call it a proven
  harmless flake; rerun in isolation and inspect if it persists.
- Focused Chromium SFX/OBS suite: **7 passed**. Covers inline error/retry, many saved
  cards, preserved drafts, stale CSRF/startup retry, queued mirror start and late join.
- A full Chromium run was still in progress when this handoff was prepared.
  Do not claim a complete full-browser pass for this repair.
- Ruff, JS syntax and Python compilation passed at recent intermediate states.
- No real GPU synthesis, real Whisper boundary validation, user's actual failing
  MP3/upload, Windows acceptance or release validation for these repairs.

Tests: `tests/test_message_script.py`, `tests/browser/test_sfx_ui.py`,
`tests/browser/test_obs_reconnect_ui.py`. Existing scoped revocation behavior is
covered by `tests/browser/test_studio_ui.py` and `tests/test_tunnel.py`.

## Next model's focused tasks

1. Reproduce saving using the user's actual file/trigger/settings. Capture the
   `POST /api/sfx` status/body and server log; inspect matching SQLite/audio records
   before/after restart. Distinguish rejection, saving elsewhere and rendering failure.
2. Obtain exact input, active engine/settings, generated/downloaded MP3 and job
   report (`metrics.composition`). Compare downloaded audio versus OBS output to
   distinguish model omission, PCM assembly, estimated cuts and playback seeking.
3. Review the conservative quiet-gap and mirror offset changes rather than assuming
   they solve the reports. Prefer whole-utterance speech; phrase fallback is allowed
   only when reliable insertion is unavailable. Never invent timestamps by text ratio.
4. Test actual installed app restart with the same OBS source URL. Preserve revoked
   shared-link behavior and existing moderation/cancellation/queue semantics.
5. Run final suites sequentially if resource contention obscures failures. Do not
   repeatedly rerun all CI jobs after tiny commits. No model redownloads. Release
   only after the actual repair and existing acceptance gates are validated.
