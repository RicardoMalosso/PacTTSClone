# KittenTTS2 integration

Task 3 adds KittenML's KittenTTS2 1.7B native PyTorch backend, using lossless packed
weights and the default flow decoder. It does not use the older CPU ONNX KittenTTS.

## Requirements and controls

| Item | Requirement / behavior |
|---|---|
| GPU | NVIDIA CUDA with native BF16 (Ampere or newer); CPU speech fallback disabled |
| VRAM | Upstream recommends about 8 GB **free** VRAM; estimate, not an app measurement |
| Assets | 2,114,438,061 bytes of pinned source/model/decoder/voice assets |
| Installation space | Assets plus a conservative 16 GiB budget for private CUDA environment and package cache; actual usage varies |
| System RAM | Minimum not measured; packed weights expand while loading |
| Languages | 20 upstream languages including Portuguese; automatically detected from text |
| Voice cloning | Saved 5–30 second reference plus exact transcript |
| Built-in voices | 115 voices, selected per saved voice's engine settings |
| Expression | Leading `[emotion]`, inline `<event>`, `(((emphasis)))` (beta) |
| Controls | Stable/expressive preset, per-chunk token budget, normalization, reference conditioning, seed, output volume |
| Unsupported app controls | Forced language, OmniVoice speed/duration/steps/CFG/processing controls |
| Output | Existing local MP3/OBS/Discord pipeline; no streaming API exposed |
| License | Apache-2.0 code, Stellon Labs Community License model, MIT ResembleAI decoder; consult upstream licenses |

The Engines table exposes disk/VRAM/features and Install/Cancel/Activate/Deactivate/
Uninstall. Installation does not activate the model. CUDA/BF16 activation preflight
runs before replacing the previous selection. No driver is installed. The engine's
Python packages are isolated from OmniVoice and Ming. Inference uses verified local
files with Hub offline mode; it never downloads Whisper large automatically.
Blank reference transcripts use the app's separately installed shared CPU Whisper,
or can be entered manually. Preset mode ignores the saved reference audio; selecting
a saved voice still selects its stored Kitten settings.

Code revision: `b9517e3050adced306219f8bea5f117d87ecfaa7` (kittenml 0.9.7).
Model: `KittenML/kitten-tts-2@c93cb7c271baa51d9ae8204d5277988906f235a2`.
Decoder: `ResembleAI/chatterbox-turbo@749d1c1a46eb10492095d68fbcf55691ccf137cd`.
Each file is size/hash verified. The decoder's offline cache ref points at the pinned
snapshot; full/emb4/GGUF/student weights are excluded.

Official sources:
- https://github.com/KittenML/KittenTTS/tree/b9517e3050adced306219f8bea5f117d87ecfaa7
- https://huggingface.co/KittenML/kitten-tts-2/tree/c93cb7c271baa51d9ae8204d5277988906f235a2
- https://huggingface.co/ResembleAI/chatterbox-turbo/tree/749d1c1a46eb10492095d68fbcf55691ccf137cd

## Validation status

Implementation is in progress. Focused contract/API/process tests passed (45 tests,
including Ming and Engines regression tests). These use simulated inference.
Real dependency installation, full regression/Chromium and Windows installer gates
are pending. No physical CUDA synthesis, measured quality/latency/VRAM or minimum
system RAM has been established. Do not treat an import or simulated audio test as
real GPU generation. A separate release follows successful acceptance.
