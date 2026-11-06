# PacTTSClone 2.3.0-rc.5 — SFX management and OBS restart repair

- Saved SFX appear first as searchable cards with explicit Edit buttons; Add opens a separate form.
- Saves reread the server catalogue and show confirmation/errors beside the form. Failed uploads stay selected; editing one sound preserves drafts on other cards.
- Sound previews now apply saved volume and duration rather than playing the unmodified upload.
- Mid-sentence sound insertion requires a verified quiet gap as well as matching word timestamps. Otherwise use the recorded phrase-generation fallback. Reports include insertion positions and source sample counts.
- Local OBS sources recover from session-token rotation after reopening the app and retry when OBS starts before the server. Genuine revoked shared links still stop.
- Clips preload during countdown. Mirrors that saw a clip queue play from zero; genuine late joins retain timestamp synchronization.

Existing managed installations with experimental updates enabled can update normally. After updating, refresh an already-open OBS browser source once so it loads the repaired player script; the URL stays the same. Models, voices, SFX and settings are preserved.

Real TTS/Whisper accuracy still needs hardware validation. Assembly tests verify samples are retained, but cannot establish whether a model omitted words before assembly. Unknown real-world save failures need the displayed error and affected upload to diagnose.
