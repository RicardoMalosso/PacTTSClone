# Verification plan

## Automated, without downloading weights

Run `python -m pip install -e '.[dev]'`, then `pytest` and `ruff check .`.
Unit tests verify validation, device selection and adapter calls using injected
modules; API tests inject a deterministic fake engine. Real FFmpeg tests create
an MP3 fixture, decode it, encode output, probe sample rate/duration and exercise
corrupt media and failure cleanup. Concurrency tests prove busy rejection and
recovery after failure. Security tests check Host, Origin, token and path routing.

Browser: install `pip install -e '.[browser]'`, `playwright install chromium`,
then `pytest tests/browser --browser chromium`. A real loopback app with an
explicitly injected fake engine tests selecting MP3, generating, downloading,
native player controls, stop, error rendering and autoplay handling. It verifies
the app pipeline and UI, not synthesized voice quality.

CI: Linux and Windows Python 3.11, FFmpeg, lint and non-model tests; browser on
Linux. Never silently skip required FFmpeg tests. Browser suite is opt-in locally
and is explicitly selected in its CI job.

## Real model smoke (separate, opt-in)

After installing matching torch/torchaudio and `.[inference]`, run:

```
pacttsclone-smoke --reference reference.mp3 --ref-text "Exact reference transcript" --text "Olá, este é um teste de geração local."
```

This command uses the production service/engine/FFmpeg and prints output path,
elapsed time and selected device. Listen for voice similarity, pronunciation,
clipping and missing words. Repeat with blank transcript for CPU Whisper and
with `--offline` after cache population. Record OS, GPU, torch/CUDA versions,
reference duration, text length, latency and observed VRAM separately.
Automated assertions cannot establish perceptual cloning quality.

## Release acceptance

All deterministic suites pass; document exact counts in docs/status.md.
Real inference and Windows/GPU validation must be marked pending until actually
executed. No throughput, real-time or 6 GB compatibility claim without measurements.
