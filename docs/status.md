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
| Real OmniVoice offline CPU smoke | Passed: new process with `--offline`, cached weights, manual transcript, MP3 generated |
| Real OmniVoice CPU smoke with blank transcript | Passed: Whisper-small loaded/transcribed locally on CPU and MP3 generated |

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

Offline smoke used target “Olá.” and the same 4.932 s reference: 79.01 s including
loading in a fresh process. Peak child RSS measured by `resource.getrusage` was
3,251,668 KiB (about 3.10 GiB). This single short, no-ASR CPU run does not establish
an upper bound for RAM or any GPU's VRAM requirements. Persistent server reuses
loaded models; these CLI results are not warm-server benchmarks.

Blank-transcript smoke used target “Olá, mundo.” and downloaded Whisper-small
revision `973afd24965f72e36ca33b3055d56a652f456b4d`; total 151.98 s including its
initial download. Result: 1.200 s, 48 kHz / 192 kbps MP3, 29,421 bytes. The default
upstream ASR loader snapshots the model repository, including other framework
formats, so the first ASR download can use substantially more disk than the single
PyTorch weight file. Manual reference transcripts bypass that download entirely.

GitHub Actions run for implementation commit `e578d34`:
https://github.com/RicardoMalosso/PacTTSClone/actions/runs/40061589697
Linux Python 3.11/3.12 and Chromium jobs passed. Windows jobs are still running at
this checkpoint; their final results will be recorded before closing validation.

## Remaining validation / next work

Windows/GPU benchmark remains hardware-dependent. Current UI intentionally does
not provide a voice library, pause tags, cancellation or Twitch integration.

Pending hardware validation: Windows installation and GTX 1660 SUPER 6 GB
latency/VRAM. The initial execution environment had no torch; an isolated CPU
inference environment was subsequently installed for the real smoke above.
