# KittenTTS2 integration

Task 3 adds KittenML's KittenTTS2 1.7B native PyTorch backend, using lossless packed
weights and the default flow decoder. It does not use the older CPU ONNX KittenTTS.

## Requirements and controls

| Item | Requirement / behavior |
|---|---|
| Python | 3.12 (included by the Windows installer); source installations must use 3.12 |
| GPU | NVIDIA CUDA with native BF16 (Ampere or newer); CPU speech fallback disabled |
| VRAM | Upstream recommends about 8 GB **free** VRAM; estimate, not an app measurement |
| Assets | 2,114,438,061 bytes of pinned source/model/decoder/voice assets |
| Installation space | Assets plus a conservative 20 GiB budget for private CUDA environment and package cache; actual usage varies |
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
Removing an inactive OmniVoice installation preserves the selected private engine
and its shared Whisper files/path, including after restart. Missing private assets
clear an invalid selection so another engine can be installed.

Blank reference transcripts use the app's separately installed shared CPU Whisper,
or can be entered manually. Preset mode ignores the saved reference audio and
requires no Whisper or reference preparation. Save preset mode in a voice profile, then select that profile in Local
or Twitch; the profile selects its stored Kitten settings.

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

Implementation is complete. The final local suite passed **294 backend tests and
41 Chromium tests**, including preset generation from an unprepared profile with
no ASR, independent engine settings, language switching and mobile layout. Ruff,
JavaScript syntax, compilation, wheel contents and desktop/mobile visual checks passed.

Actual private CUDA dependency installation, pip check, upstream imports and repeated
source/runtime cache reuse passed on Windows and Linux (Actions runs 41252188987
and 41252608236). Direct dependency versions are pinned identically on both
platforms. Full local source/model/decoder download and integrity checks passed.
Repeated installation with asset downloads and pip indexes disabled passed, including
reuse without reinstalling dependencies. Offline structural checks passed for the
tokenizer, model config, packed/speaker/decoder tensor files and all 115 voices'
reference files, artifacts and transcripts. Actual CPU-only activation preflight
correctly rejected unsupported hardware.

The initial Linux installation reported about 14.97 GB including runtime/cache.
Repeated validation retained temporary/resumable files and reached about 19.45 GB;
the 20 GiB runtime/cache budget is conservative guidance, not a fixed size or minimum.
The UI reports each installation's actual receipt size. Final CI/Windows installer
acceptance and v2.3.0-rc.1 publication run through the release workflow.

No physical CUDA synthesis, measured quality/latency/VRAM or minimum system RAM has
been established. Do not treat an import or simulated audio test as real GPU
generation. This remains a preview release.
