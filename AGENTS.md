# PacTTSClone — implementation guide

## Read only what the task needs

Start with the affected code and tests. Use README.md for setup/usage and the map
below for relevant documentation; do not load every document before making a change.

| Task | Read as needed |
| --- | --- |
| System boundaries or product constraints | Relevant sections of docs/architecture.md and docs/requirements.md |
| Frontend or live updates | docs/frontend.md; docs/realtime-communication.md |
| Twitch, Discord or imports | docs/twitch-eventsub.md; docs/discord.md; docs/optional-imports.md |
| Engines or audio composition | docs/ming-integration.md; docs/kitten-integration.md; docs/multi-voice-sfx.md |
| Updater or releases | docs/auto-updates.md; [release procedure](docs/release-procedure.md) |
| Test setup or real-model acceptance | Relevant sections of docs/testing.md |

docs/status.md, release notes, completed docs/tasks plans, old handoffs and v1/v2
designs are historical evidence, not current task instructions. Consult
docs/decisions.md only for relevant rationale. Some broad docs mix old and new
requirements: check dated claims against current feature docs and implementation;
record conflicts rather than silently restoring obsolete behavior.

## Preserve these boundaries

- Keep inference local and isolated in cancellable workers. Speech generation uses
  CUDA without silent CPU fallback; CPU ASR is allowed. Never substitute synthetic
  audio for failed inference.
- Preserve host-only controls, same-origin/CSRF checks and separate admin/player
  capabilities. Public sharing is opt-in and authenticated; no remote inference
  service or telemetry.
- Twitch supports IRC and authorized OAuth/EventSub actions. Discord uses opt-in,
  output-only webhooks. Preserve their existing authorization boundaries.
- Keep vanilla JavaScript modules. Do not commit credentials, model weights,
  recordings, generated outputs or machine-specific paths.

## Validate and maintain

Run relevant tests for behavior changes and `ruff check .` for Python changes.
Core suite: `pytest`. Browser suite: `pytest tests/browser --browser chromium`
for affected UI flows. Follow the release procedure for required release gates.
For documentation-only edits, check accuracy and referenced paths.

Record actual checks and limitations in the PR; distinguish mocked tests from
real inference, GPU, OBS and live-service acceptance. Update the affected current
documentation with behavior changes. Preserve historical release notes; avoid
duplicating changelog prose across documents or requiring full-history reading.
