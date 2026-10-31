# PacTTSClone 2.2.0-rc.1 — Ming 3.0 preview

Adds Ming 3.0 0.5B dense as a separately installed engine. Source and model assets
are pinned and verified, including its ONNX speaker encoder. Torch 2.6/CUDA 12.4 and
Transformers 4.46.3 live in a private environment alongside OmniVoice.

Engines supports install/cancel/resume, compatibility preflight, activate/deactivate
and uninstall. Model selection persists. Per-voice Ming task settings are separate
from OmniVoice defaults and inherited by Local and Twitch; output still uses the
normal MP3/OBS/Discord pipeline. Supported tasks include cloning/vocal tags,
emotion, attributes, dialect, freeform, voice design and built-in voices.

Requires an NVIDIA CUDA GPU with native BF16 support (Ampere or newer). Target
languages: English, Chinese, German, Spanish, French, Korean and Japanese.
Portuguese is unsupported. Minimum VRAM/RAM and actual GPU quality/performance
remain unverified. This preview does not claim a real GPU synthesis test.

Real Linux source/model download, integrity verification, isolated dependency
installation, pip check and upstream imports succeeded. Reinstallation with asset
network disabled reused the cache successfully. Actual CPU-only preflight correctly
rejected unsupported hardware. Process transport, shutdown/cancellation, task mapping,
settings, activation rollback and browser flows have deterministic regression coverage.
Windows runtime/import and installer acceptance results are recorded by Actions.
See docs/ming-integration.md for measurement scope and limitations.
