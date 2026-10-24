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
9. Standard deployment is an isolated Python venv, confirmed with the user.
   No Docker/container service in v1. Engine module provides the requested code
   separation without adding a deployment layer.
10. Export at 48 kHz / 192 kbps MP3; OmniVoice's native 24 kHz is resampled only
    for encoding. A real FFmpeg test showed MPEG-2 at 24 kHz caps at 160 kbps.
    Resampling does not add source detail; it satisfies the MP3 bitrate contract.
11. Standard installer uses Python 3.12, the version used for local validation.
    Pin transformers 5.20.2 and torch/torchaudio 2.8.0 in the inference extra;
    CUDA/CPU wheel index is still explicitly selected before installing it.
    PyPI OmniVoice 0.2.1 wheel was downloaded without dependencies and its API
    inspected, confirming `asr_device`, `load_asr_model(device=...)`, and generation
    arguments rather than assuming the development branch matched the release.
12. Pin Playwright 1.56.0, which supplied a working Chromium download in this
    environment. Browser tests use a real loopback HTTP server and ignore external
    proxy variables only for their loopback readiness probe.

## Pre-implementation consistency review

Reviewed requirements, architecture, testing plan and this record together.
Updated the earlier Gradio proposal to FastAPI throughout. Kept MP3-only output,
no Twitch hooks, no pause tags, no saved voice prompts. Automatic ASR is optional
and lazy; Windows scripts must install compatible torch explicitly. Resource
estimates remain unverified; tests using fake engines cannot establish inference
quality, latency or hardware compatibility. No conflicting design decisions remain.

## Post-implementation consistency review

Re-read requirements against the implemented API, engine, UI, launchers and tests.
Updated output sample rate to 48 kHz for the tested 192 kbps MP3 contract; retained
24 kHz reference PCM. Standardized the Windows installer on tested Python 3.12 and
pinned inference/browser versions. Confirmed venv (no container), one generation,
Portuguese default, automatic ASR on CPU, no pause syntax and no Twitch code.
Verified real CPU generation separately from fake-engine application tests, then
verified cached offline and blank-transcript/Whisper generation. Hardware claims
remain limited to the measured CPU runs in status.md; GTX 1660 SUPER is untested.
The earlier Gradio proposal is superseded; no remaining design conflict found.
