# PacTTSClone 2.2.3 — Ming inference repair and diagnostics

- Prevent Ming's empty-latent concatenation crash with explicit context diagnostics.
- Correct audio-patch versus LLM-position budget accounting within the existing
  512-position ceiling; distinguish learned stopping from truncated generation.
- Split long text using the actual tokenized conditioning budget and retry
  non-stopping fragments with bounded splitting. Cloned chunks retain the same
  original reference latents, transcript and speaker embedding.
- Add rotating local inference diagnostics and full failure tracebacks; release
  per-job reference caches while keeping Ming weights resident.

Use Configuration's updater in Latest mode, or install the wheel/installer normally.
Existing models, private inference packages, voices and settings are retained;
no model re-download or Ming reinstall is required. Version pins remain respected.

Deterministic regression tests exercise the actual pinned upstream sampler with
simulated tensors. Real GPU reproduction of the reported intermittent short-text
failure and perceptual voice quality remain unverified. See
[diagnosis](ming-inference-diagnosis.md) for confirmed defects and remaining uncertainty.
