# Ming 3.0 dense integration

The Ming engine targets supported NVIDIA GPUs generally. No particular user's
hardware is an implementation target or acceptance requirement.

## Engine and runtime

Ming 3.0 **0.5B dense** uses official source revision
`9332fb9443325d4726ce02cefd4ec1c211df4079` and checkpoint revision
`7247f4c94a5b2e987404ed28a5cfec41b1a4ca61` from
https://github.com/inclusionAI/Ming-3.0-tts and
https://huggingface.co/inclusionAI/Ming-3.0-tts-0.5b.
This is not the larger Tiny MoE variant.

The upstream implementation loads BF16. Activation requires an NVIDIA CUDA GPU
with native BF16 (Ampere or newer); it checks the actual runtime/GPU before changing
active selection. No CPU speech fallback is permitted. Minimum/recommended VRAM,
system RAM, generation latency and audio quality remain unverified. The Engines
table does not invent numeric requirements.

Torch/torchaudio 2.6.0+cu124 and Transformers 4.46.3 are installed in a private
Python environment under data/engines/ming-3/runtime. They never replace OmniVoice's
packages. Direct dependency pins are in ming_requirements.txt. Platform-specific
transitive resolution is checked with pip check. Exact source files and checkpoint
assets (including campplus.onnx) are in bundled manifests with per-file sizes and
hashes. Source uses Git blob SHA-1; large weights use SHA-256. Model/source downloads
total 3,003,464,609 bytes. An additional 12 GiB conservative installation budget
covers the private runtime, CUDA wheels and pip cache; it is not a measured minimum.
Installed storage includes the private runtime/cache once installation succeeds.

## User workflow

Open Engines, choose Ming Install, and wait for verified assets and dependencies.
Installation does not activate Ming. Progress shows real asset bytes; dependency
installation is indeterminate. The Installation log link exposes the host-local log.
Cancel terminates the installation process tree. Retry reuses verified files and
resumes partial transfers. Interrupted installation never becomes activatable.

Activate runs isolated CUDA/BF16/dependency preflight before switching. A failure
keeps the previous engine selected. Changes require an idle generation queue.
Active selection persists across restart; weights load lazily on first inference.
Deactivate before Uninstall. Private Ming assets/runtime/cache are removed while
saved references, generated audio, voice settings and history are preserved.
All engine-management and log endpoints require local host access.

Local and saved-voice generation defaults expose separate Ming task controls:

- TTS: reference cloning, transcript and target language; supports the 14 inline
  upstream vocal tags. Languages: English, Chinese, German, Spanish, French,
  Korean and Japanese. Portuguese is not supported. The added languages use the
  upstream multilingual task automatically.
- Emotion: reference voice with one of the seven upstream emotions.
- Attributes: reference voice with categorical speed, pitch and loudness.
- Dialect: reference voice with Cantonese or Sichuanese.
- Freeform: a delivery instruction; no reference conditioning.
- Voice design: a voice description; no reference conditioning.
- Built-in voice: US_Emma, UK_George or UK_Charlotte.

These are separate task modes, not arbitrary combinations of controls. A saved
voice is still selected as the settings preset in the existing workflow even for
modes that do not condition on its recording. OmniVoice-only controls are hidden
and their saved values retained. Output gain and MP3 delivery work as before.
Ming defaults are stored separately per voice, inherited by Twitch and overridable
for one Local request. Submitted jobs record engine/model and effective settings.
OBS and Discord receive the same completed MP3 pipeline output.

Cloning needs an exact transcript. Existing prepared voices reuse theirs. Preparing
new voices can use the independently verified local Whisper model on CPU inside
Ming's runtime. If shared Whisper is not installed, enter the transcript manually
or install shared setup first. Optional pynini normalization is disabled for portable
installation; this is explicit rather than silently installing system tools.

## Process behavior and measurements

A persistent private-runtime subprocess owns Ming weights. The existing serialized
worker communicates through bounded JSON commands and temporary WAV files, and
validates output before MP3 encoding. Normal worker reset closes the resident child;
hard cancellation terminates its process group/tree. CUDA failures discard residency
and report errors without a CPU retry.

Reports distinguish active selection from GPU residency. For Ming, wrapper CPU/RAM
measurements exclude the isolated runtime and CUDA allocator counters are unavailable;
the report labels this scope. Device-wide NVML measurements remain available.
No wrapper measurement is presented as Ming's complete memory/compute consumption.

## Validation status

Deterministic checks cover task contracts, unsupported controls/languages, manifest
ONNX inclusion, immutable URLs, path traversal/symlinks, activation rollback,
engine-specific voice defaults, empty repository files, real child-process/pipe/WAV
transport with simulated synthesis, and resident-child termination on worker reset.
Browser checks cover catalogue controls and saved Ming task settings/reload.
These do not prove model quality or actual GPU inference. Real Linux model/dependency installation succeeded, including source imports and pip check.
A complete repeat install succeeded with asset network access disabled. Observed
storage was approximately 15.3 GB including the private runtime and caches; this
is one Linux measurement, not a universal requirement. The actual runtime preflight
correctly refused CPU-only hardware. The core suite passed 269 tests and Chromium
passed 40 tests before the final metadata checks; focused follow-up tests passed.
Windows and Linux private-runtime install/import and repeated cache reuse both passed
in Actions run 41232561493. Windows installer acceptance is in progress.
Final core suite: 271 passed; full Chromium: 40 passed; targeted Ming/Engines UI: 3 passed.
Desktop/mobile layout was visually inspected, with no horizontal overflow at 390 px. Release remains gated by the
recorded results and Windows installer acceptance; no release is claimed here.
