# Implementation status

## Initial checkpoint — 2026-10-24

Design documents completed and reviewed before implementation. Repository was
empty. Source API and package version verified through the GitHub connector.

## Implemented

- Python/venv app with Windows install/start scripts; local FastAPI interface.
- MP3 reference validation, optional exact transcript or lazy CPU Whisper.
- Official OmniVoice 0.2.1 adapter, default k2-fsa/OmniVoice model, auto CUDA/CPU.
- One generation at a time, job status/errors, bounded upload/text and temp cleanup.
- Atomic MP3 output at 48 kHz / 192 kbps, native browser audio controls, stop,
  download and optional autoplay with blocked-playback feedback.
- Loopback Host/Origin boundary and ephemeral session token; no public listener.
- Engine protocol for later event adapters; no Twitch/IRC code in v1.
- Linux/Windows CI configuration and browser CI.

## Executed validation — Linux / Python 3.12.14

| Check | Result |
|---|---|
| `python -m pytest -q` | 66 passed; includes real FFmpeg integration, API/security/concurrency, fake engine contracts |
| `python -m pytest tests/browser --browser chromium -q` | 4 passed; actual Chromium browser with injected test engine |
| `python -m ruff check .` / format check | Passed |
| `python -m compileall -q src` | Passed |
| `python -m pip wheel --no-deps . -w dist` | Built; HTML/CSS/JS assets verified inside wheel |
| `pip check` in isolated inference environment | No broken requirements |
| Real OmniVoice CPU smoke, manual reference transcript | Passed: actual weights downloaded, model loaded, generated MP3 probed with FFprobe |

Real smoke used torch/torchaudio 2.8.0+cpu, omnivoice 0.2.1,
transformers 5.20.2, NumPy 2.5.4, librosa 1.0.0; OMP/MKL threads=2.
Downloaded model revision: `c5fdb5ccb189668d56333f77ba2629f4cd7535f4`.
Reference was a 4.932-second English synthetic speech clip from FFmpeg flite
(not a personal recording); Portuguese target: “Olá, este é um teste de geração
local.” Output: 2.400 seconds, MP3, 48 kHz, 192 kbps, 58,221 bytes.
Total first-job elapsed: 180.24 s, including approximately 84 s of model downloads.
This is an execution smoke test, not a perceptual quality benchmark or a claim
about generation speed on the user's PC. Browser tests use a fake model and are
reported separately from this actual model invocation.

## Remaining validation / next work

Offline cached smoke and blank-transcript ASR smoke are being checked separately.
Windows/GPU benchmark remains hardware-dependent. Current UI intentionally does
not provide a voice library, pause tags, cancellation or Twitch integration.

Pending hardware validation: Windows installation and GTX 1660 SUPER 6 GB
latency/VRAM. The initial execution environment had no torch; an isolated CPU
inference environment was subsequently installed for the real smoke above.
