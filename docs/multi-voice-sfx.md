# Multi-voice messages and custom sound effects

## Syntax and user interface

Twitch commands switch voices in written order:

```text
!pac something !lula somethingelse
!pac Hello, my [fart] name is Pac !lula hello ****
```

Commands must already map to saved voices in the channel. Each command starts a
section and consumes text until the next whitespace-delimited command or the end.
Commands and configured SFX triggers are case-insensitive. Unknown commands,
empty sections and excess work reject the entire message before queueing.
A section may contain only sound effects. Commands inside words remain literal.
A backslash escapes the next trigger opener: `\[fart]`, `\****`, `\!lula`.
Supported model emotion/event tags remain model input; registered SFX tokens are
removed before synthesis. Common model tags cannot be registered as SFX.

**SFX** is a separate tab immediately after **Voices**. Upload MP3, WAV, OGG,
FLAC or M4A, choose a name and aliases such as `[fart]` and `****`, and set volume,
optional duration and enabled state. No sound recordings are bundled. Previews
apply the saved volume and duration, using the same processing as generated scripts. A duration override
repeats or trims the sound. `****` inserts the configured sound at that position;
it does not discover, remove or automatically censor spoken words.

Uploads are limited to 10 MiB and 0.05–15 seconds, converted to mono 48 kHz PCM,
and stored under the chosen data directory's `sfx/` folder. Up to 100 effects and
10 aliases per effect; duplicate aliases and reserved model tags are rejected.
Files and settings survive app upgrades, rollback and restart. Existing optional
personal-data import does not yet import SFX from another installation.

Channel settings enable/disable SFX and limit voice sections (default 4, range
1–10) and effects (default 8, range 0–20). Existing message/queue limits, cooldown,
filtering and readiness remain effective. Preview saved channel commands shows
the parsed sequence without generation, cooldown consumption or playback.

Local generation supports inline SFX in the selected voice and retains per-job
overrides, requester identity and optional general-player autoqueue. Local voice
switching via channel commands and paid-event text scripts are outside this change.

## Speech continuity

Each voice section is synthesized as a complete utterance first. For example,
`Hello, my [fart] name is Pac` submits `Hello, my name is Pac` to the model once.
No unsupported model pause token or invented character-to-time ratio is used.

For internal SFX, cached Whisper runs on CPU with word timestamps. Insertion is
allowed only when the complete normalized word sequence matches and timestamps
are finite, monotonic and within the waveform. The cut must fall in a verified quiet interval of at least 20 ms between the previous
word's end and next word's start. Matching words without a quiet gap is insufficient. All speech samples are retained and the SFX
adds its full configured duration. Prefix/suffix effects need no alignment.

Word timestamps are estimates, not phoneme-accurate guarantees. If local ASR is
missing, unsupported, produces different words or ambiguous timestamps, generate
the surrounding phrases separately. The already generated whole utterance is
then discarded, so fallback incurs extra generation work. Each section's mode
and the fallback reason are recorded under `metrics.composition`. A whole-utterance
mode means the speech was generated once and split afterward, not that the model
created a timed pause. Model tags and unusual spellings can increase fallback.

Whisper reuses the verified shared model path/cache with `local_files_only=True`;
this feature never downloads weights or adds a model dependency. Word alignment
can add CPU time and RAM. OmniVoice uses a lazy cached CPU aligner in its worker;
Ming/Kitten use their existing isolated runtime protocol for alignment, without
requiring Transformers in the web application's runtime. Speech stays on the
selected engine's existing CUDA path.

## Job, playback and persistence contract

Parsing, moderation (including speech joined across voice/SFX boundaries), voice
readiness and settings validation happen before submitting work. Cooldown is
charged once for the message. The entire message occupies one queue slot.

The queued job snapshots every voice's active-engine settings, reference audio,
SFX PCM and SFX settings under its workspace before publication. Editing/deleting
assets cannot alter accepted work. The normal serialized process worker renders
all sections in order. PCM is normalized before assembly, with a single final
48 kHz/192 kbps MP3 encode. Total output is capped at 10 minutes.

One message produces one History entry, OBS FIFO item, moderation countdown and
optional Discord attachment. Combined voice labels and all voice IDs are retained;
Discord voice filters include a script if any participating voice matches.
Replay rechecks moderation against both the displayed script and joined speech.
Any failed segment fails the whole job; incomplete audio is never published.
Cancellation terminates the worker/process tree and removes workspace/partial
output. Restart cancels unfinished scripts using the existing job lifecycle.

ASR/assembly are supporting CPU operations; speech-stage metrics do not include
alignment/assembly and explicitly say so. No exact GPU/latency claim is made.

## API and access

- `GET/POST /api/sfx`: list or upload effect (multipart).
- `PUT/DELETE /api/sfx/{id}`: update settings or delete.
- `GET/POST /api/sfx/{id}/audio`: read PCM or replace upload.
- `POST /api/script/preview`: parse a message against a saved channel's settings.
- `GET /api/state` / SSE snapshots include the SFX catalogue.

These use the existing local/admin boundary and CSRF protection. Scoped OBS
players cannot list, modify or retrieve the SFX catalogue. They receive only
completed MP3s assigned to their playback queue. Filesystem paths/segment arrays
are internal job metadata and are not accepted from public generation requests.

## Validation

Deterministic tests use explicit fake speech engines with real FFmpeg. They cover
parsing, escaping, exact alignment and invalid timestamp rejection, whole-speech
insertion timing in the final decoded MP3, fallback, different voice transcripts,
settings/asset snapshots, moderation across boundaries, limits/cooldown, queued
and actual process cancellation/recovery, later-section failure, local autoqueue,
API validation, replacement, persistence and CSRF. Chromium exercises tab ordering,
upload/edit/delete/reload and the saved-command preview.

Real CUDA synthesis, real Whisper word-boundary accuracy, subjective prosody,
live Twitch/Discord and Windows installer acceptance are not established locally.

## Management and restart repair

Saved effects appear first in a searchable grid with an effect count and explicit
Edit buttons. Add opens a separate form. Saving rereads the catalogue from the
server, shows confirmation and preserves the selected upload on failure. Errors
appear beside the form; edits to other unchanged cards survive catalogue updates.
The configured preview is available at `GET /api/sfx/{id}/preview`; raw uploaded
PCM remains at `/audio`. Both remain within the existing admin boundary.

Local OBS sources refresh session tokens after app restart and retry startup
connection failures without requiring a new URL. Revoked shared capabilities
still stop. Queued clips preload during countdown; mirrors that observed a clip
queue play it from zero instead of seeking past its first word. A genuinely late
mirror joining an already playing clip still seeks for synchronization.
