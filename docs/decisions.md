# Decisions and source review

2026-10-24 — initial design, before implementation.

1. Use FastAPI + native browser audio rather than the previously proposed Gradio.
   Explicit HTTP contracts, predictable MP3 downloads, autoplay feedback and future
   event adapters justify this small custom UI. Python remains the single backend.
2. Use omnivoice==0.2.1. Upstream source inspected at
   `08be0b4ccbac3e13e374e86fbfead4b4cac343e2`:
   https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/omnivoice/models/omnivoice.py
   https://github.com/k2-fsa/OmniVoice/blob/08be0b4ccbac3e13e374e86fbfead4b4cac343e2/pyproject.toml
   https://huggingface.co/k2-fsa/OmniVoice
   Current upstream dependency constraints include transformers>=5.3.0 and
   torch/torchaudio>=2.4. Installation guidance uses matching torch/torchaudio
   2.8.0; CUDA wheel selection is an explicit install step, not a universal wheel.
3. CUDA FP16 with SDPA; CPU FP32 fallback. No automatic retry on CPU after an OOM:
   inform user to reduce text or explicitly restart with CPU. GTX 1660 SUPER 6 GB
   remains a target to benchmark, not a certified configuration. Audio tokenizer
   and ASR memory mean 0.6B model weight size alone does not predict total VRAM.
4. Whisper is lazy and placed on CPU, model openai/whisper-small by default to
   reduce resources. Editable manual transcript avoids this extra model entirely.
5. FFmpeg handles MP3 decode/encode. Enforce 1–30 s rather than silently trimming:
   silent trimming would make a supplied full transcript incorrect.
6. No custom pause processing in v1. Punctuation is forwarded to the model;
   deterministic inserted silence belongs to a future feature with dedicated tests.
7. Dependencies and recordings stay local. Initial model download requires internet;
   offline mode sets Hugging Face offline flags before importing inference packages.
8. License distinction: upstream code Apache-2.0; pretrained model CC-BY-NC per
   model card. Future monetized streamer deployment must resolve model licensing.
   Do not apply a project-wide license to third-party weights.

## Pre-implementation consistency review

Reviewed requirements, architecture, testing plan and this record together.
Updated the earlier Gradio proposal to FastAPI throughout. Kept MP3-only output,
no Twitch hooks, no pause tags, no saved voice prompts. Automatic ASR is optional
and lazy; Windows scripts must install compatible torch explicitly. Resource
estimates remain unverified; tests using fake engines cannot establish inference
quality, latency or hardware compatibility. No conflicting design decisions remain.
