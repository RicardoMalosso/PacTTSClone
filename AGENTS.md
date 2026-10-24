# PacTTSClone — implementation guide

Read README.md, docs/requirements.md, docs/architecture.md, docs/decisions.md,
docs/testing.md and docs/status.md before changing behavior. Update affected docs
and status in the same change. Record actual test results and limitations; never
describe a mocked model test as a real inference test.

V1 is local MP3 reference + text → local MP3, with optional browser playback.
Twitch integrations are future work. Keep inference behind the Engine protocol.
Do not add remote inference, public hosting, telemetry, or credentials to v1.
Run `pytest` and `ruff check .`. Browser tests: `pytest tests/browser --browser chromium`.
Real model smoke: see docs/testing.md. No model weights, recordings, outputs or
machine-specific paths belong in git. Never silently substitute synthetic audio.
