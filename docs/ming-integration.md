# Ming 3.0 integration checkpoint

Status: adapter implementation started; not exposed for installation/activation yet.
This branch depends on the Engines manager in PR 21. No release has been made.

## Upstream baseline

- Source: https://github.com/inclusionAI/Ming-3.0-tts
- Inspected source revision: 9332fb9443325d4726ce02cefd4ec1c211df4079
- Checkpoint: inclusionAI/Ming-3.0-tts-0.5b (dense; not the larger Tiny MoE)
- API: ming_tts.MingTTS(model_path, device='cuda:0', text_normalization=False)
- Runtime pins: torch/torchaudio 2.6.0, transformers 4.46.3, accelerate 1.3.0,
  x-transformers 2.9.2, diffusers 0.33.0. Full lock remains to be built.
- Upstream constructor explicitly loads BF16. Current adapter requires native
  BF16 CUDA support, so GTX 1660 SUPER is rejected. FP16 compatibility must be
  established separately with actual inference before it can be advertised.
- Upstream languages: Chinese/English plus German, Spanish, French, Korean and
  Japanese in a separate multilingual task; Sichuanese/Cantonese dialect tasks.
  Portuguese is not documented. Initial adapter supports explicit English TTS.
- Model layout includes campplus.onnx; the OmniVoice-only downloader suffix list
  must not be reused unchanged. Required tokenizer/head/encoder assets must all
  appear in a verified per-engine manifest before install controls are enabled.

## Implemented

An inference-only MingEngine maps cloning requests to upstream TTS, reference audio
and transcript, English language, CFG and trim_silence. It validates unsupported
OmniVoice overrides before model loading, reports CUDA/BF16/package incompatibility,
normalizes upstream mono tensors to the existing Waveform contract and rejects
empty/nonfinite audio. It never generates on CPU. ASR remains a separate dependency:
this initial adapter requires a saved exact transcript. Text normalization is off
because optional pynini is problematic on Windows. Other task modes are not exposed.

The adapter is deliberately not wired to the existing OmniVoice runtime: replacing
its transformers 5.x with Ming's 4.46.3 would break dependency isolation.

## Remaining implementation

1. Create isolated managed Ming environment with a complete dependency lock and
   pinned verified upstream source installation; never mutate OmniVoice packages.
2. Add explicit per-engine download plans including ONNX and all checkpoint assets,
   exact disk accounting, cancellation/resume/import and verification.
3. Implement isolated runtime worker transport, worker process-tree cancellation,
   persisted selection/rollback, and engine/revision history/report metadata.
4. Add engine-specific voice defaults/language/task controls and validation across
   Local/Twitch. Add preparation using independent ASR; retain original references.
5. Expose installation/activation only after runtime preflight succeeds. Document
   unavailable BF16 hardware in the table. Evaluate FP16 on GTX hardware separately.
6. Test real CUDA generation and audio quality/memory/latency on supported hardware,
   Windows installer acceptance and all regression suites; version and release Ming
   separately after gates pass. Mock tests are not actual inference evidence.

Validation: 10 new deterministic adapter tests passed; Ruff passed. No model weights,
Ming runtime, real CUDA inference, Windows compatibility or quality have been tested.
