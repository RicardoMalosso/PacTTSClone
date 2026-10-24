# PacTTSClone 0.3.0 RC5 — setup feedback and first-run improvements

This release candidate updates the initial setup interface and dependency installer.

- Real live elapsed timer during setup (including while no generation is active).
- Live, scrolling installation output over SSE, including timestamps for each command and log line.
- Actual per-package download percentages, byte totals, speed, and ETA when pip provides totals. CPU/GPU installation and package installation without size totals remain indeterminate.
- Model download progress preserved; model verification cannot reverse the global download indicator.
- One-time 30-second **Setup taking too long?** prompt with Yes / No / close. Yes triggers 2 seconds of **Deploying countermeasures** followed by the bundled looping jingling-keys WebM video with sound. The prompt is claimed persistently before display, so refresh, cancellation, or other browser sessions cannot show it again.
- Keep downloaded logs and status continuity after restart; retain Download setup log.
- Bundle the supplied local jingling-keys WebM in the wheel; no external media download. The video loops, preserves audio, and stops when the modal closes.

## Validation and limitations

The feature branch has backend and Chromium regression tests for timestamps, real progress parsing, streaming, prompt behavior, and WebM playback and looping. A release is valid only after CI passes. Dependency downloads now use pip raw progress rather than uv's noninteractive operation: expect slightly different install performance. Live bandwidth and ETA are observations, not guarantees. No real model speech-quality or physical CUDA performance testing is implied.
