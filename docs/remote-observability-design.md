# RC4 remote access, request identity and residency

Remote admins may view voices/history and request generation, but cannot install
software or manage tunnel lifecycle. Session/state report host setup readiness;
remote UI must unlock its allowed tabs without polling forbidden setup/tunnel APIs.
Share scoped player links suitable for a separate OBS cookie jar, not bare paths.
An OBS page may bootstrap its original capability once after losing its cookie;
a repeated 403/revoked key stops polling and asks for the latest complete link.
Never bypass channel ACL, expose admin keys in logs or turn auth failures into
unbounded retries. A normal lost-server error uses bounded exponential backoff.

Generate requires a requester display name, saved locally in that browser. Persist
a random browser UUID separately. These are debugging labels, not authentication.
The server derives local/cloudflare origin from the trusted boundary, gives each
installation a persisted random namespace, and derives an origin ID without storing
IP addresses or capability tokens. Twitch uses channel and username-derived IDs.
Accepted generation/preparation jobs and moderation-rejected TTS commands enter
history immediately, with identity, source, timestamp, status and eventual metrics.
Append request lifecycle events to requests.jsonl, while generation.jsonl retains
final hardware records. Legacy callers/jobs remain readable with explicit defaults.

A fixed top status bar reports idle/setup/download/preparation/generation, source,
requester, voice, elapsed time and progress. Indeterminate operations stay so.
Move language buttons next to the title; preserve browser detection and override.

Resident state comes from the inference worker after the model is loaded, and is
cleared on OOM, worker death, cancellation, unloading or hardware reconfiguration.
All ready voices share that base-model warm/cold state. Preparation remains a
separate per-voice state; reference conditioning is not claimed to be cached.
Display model ID/device and a voice availability list with that distinction.

Tests: remote browser tab navigation, shared voice/media/history access, scoped
OBS playback in an independent context, revoked-link backoff, local/remote/Twitch
identity and history, mandatory saved name, fixed status and worker residency.
Existing installer/download/crop/channel changes remain in scope and must pass.
