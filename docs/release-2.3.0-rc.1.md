# PacTTSClone 2.3.0-rc.1 — KittenTTS2 preview

Adds KittenTTS2 1.7B packed as the third separately installed engine. The native
PyTorch CUDA backend uses lossless packed language-model weights and the default
flow decoder. Verified source, model, decoder and all 115 preset voices are pinned.
Dependencies live in their own environment alongside OmniVoice and Ming.

Engines exposes disk/VRAM/features, install/cancel/resume, activate/deactivate and
uninstall. Activation checks CUDA/native BF16 before changing the selected engine.
Local and Voices offer reference cloning, 115 preset voices, stable/expressive
presets, token budget, text normalization, reference conditioning, seed and output
volume. Settings persist separately per engine and apply to Twitch/Discord jobs.
Language is automatic, including Portuguese. Generated audio uses the existing
local MP3/OBS/Discord output pipeline.

Requires Python 3.12 and an NVIDIA GPU with native BF16 (Ampere or newer).
Upstream recommends roughly 8 GB **free** VRAM; this is an estimate, not a measured
minimum. Model/source assets total about 2.11 GB; dependency/cache installation is
additional. No driver installation or CPU speech fallback. Cloning requires a
5–30 second reference and exact transcript; preset mode ignores saved reference
audio. Unsupported OmniVoice controls and forced language selection are hidden.

Code is Apache-2.0; model weights use the separate Stellon Labs Community License;
the ResembleAI decoder is MIT. See upstream terms linked in the integration guide.

Real private CUDA dependency installation, upstream imports, pip check and repeated
source/runtime cache reuse passed on Windows and Linux. Deterministic tests cover
request mapping, process transport, settings, rollback, persistence and safe removal.
No physical GPU synthesis, audio quality, latency or VRAM measurement is claimed.
See [requirements and current validation](kitten-integration.md) for remaining gates.
