# PacTTSClone — implementation guide

Read README.md, docs/requirements.md, docs/architecture.md, docs/decisions.md,
docs/testing.md and docs/status.md before changing behavior. Update affected docs
and status in the same change. Record actual test results and limitations; never
describe a mocked model test as a real inference test.

Read docs/v2-design.md for the current scope: local TTS, saved voices, hardware
settings, cancellable process worker, read-only Twitch IRC and OBS playback.
Keep inference isolated. Public access is only through the explicitly requested
opt-in authenticated tunnel with separate admin/player capabilities. No remote
inference service, chat posting or telemetry.
Run `pytest` and `ruff check .`. Browser tests: `pytest tests/browser --browser chromium`.
Real model smoke: see docs/testing.md. No model weights, recordings, outputs or
machine-specific paths belong in git. Never silently substitute synthetic audio.
