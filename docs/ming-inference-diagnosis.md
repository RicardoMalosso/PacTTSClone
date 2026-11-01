# Ming dense inference diagnosis — 2.2.3

Inspected the actual pinned `modeling_bailingmm.py`, `ming_tts.py`,
`prompt_contract.py`, VAE encoder/decoder and audio Aggregator at upstream revision
`9332fb9443325d4726ce02cefd4ec1c211df4079` before implementing the repair.

## Confirmed defects

`generate()` concatenates `sampled_tokens_list` without checking it. `sample()`
iterates `min(max_decode_steps, (512 - input_positions) // patch_size)` times.
If this is zero or negative, nothing is yielded and the concatenation fails.
Short target text does not imply short input: the trained prompt contains system
and user wrappers, speaker slots, the full reference transcript, target text,
optional instruction and one position per aggregated reference-latent patch.

The budget also mixes units. `Aggregator.forward()` returns `x[:, :1, :]`;
each audio patch becomes **one** LLM embedding. The decode loop increments its
dense position ID by one, not `patch_size`. Dividing remaining LLM positions by
audio patch size needlessly reduces available generation. Previously, reaching
either limit without a stop signal still returned decoded, potentially truncated
audio as a success. The repair retains the conservative 512-position ceiling and
counts one position per decode iteration; it does not extend the trained context.

## What does not explain intermittency

The learned stop head is checked after sampling a latent. Even when it signals
completion, that latent is yielded and appended. The `step > 3` condition permits
stopping only at the fifth step or later. Early stopping cannot, by itself,
produce an empty latent list in this pinned implementation.

The VAE samples its reference posterior, and Flow Matching consumes random noise.
Identical requests can therefore sound different or stop differently. Reference
posterior sampling changes latent values, not the number of positions for the same
recording. Prompt caching also changes RNG consumption; per-job temporary reference
paths previously accumulated cached conditioning. Cache entries now live for one
complete synthesis job and are released afterward, while weights remain resident.

The reported intermittent short-text failure has **not** been reproduced on a real
GPU here. A traceback is needed to distinguish this concatenation from a failure
inside another dependency, a different installed source, or changed conditioning.
These confirmed defects must not be presented as proof of every reported failure.

## Repair and diagnostics

The application verifies the original source's Git blob SHA and applies three
narrow in-memory substitutions before importing Ming. Installed source files,
checkpoint manifests and model weights are unchanged; no model download or
dependency reinstall is needed. Unknown source revisions fail explicitly.

The chunk planner calls the same trained `prompt_contract.build_input_ids()` with
the actual tokenizer, instruction, transcript, speakers and acoustic-prompt length.
It reserves 64 decode positions and bisects long normalized fragments at word or
sentence boundaries, falling back to Unicode character boundaries while keeping
inline vocal tags intact. Every cloned fragment reuses the original transcript,
speaker embeddings and the once-encoded reference latents. No generated fragment
replaces a clone's reference. If fixed conditioning alone consumes the budget,
the user gets an actionable shorter-clip/matching-transcript error; neither side
of the reference pair is silently cropped or removed.

Budget exhaustion is distinct from learned stopping and triggers bounded splitting
and regeneration of just that fragment. Empty/non-finite decoder output is an
explicit error. Repeated missing-stop failures are capped at eight attempts per
upstream fragment. No synthetic silence is substituted for missing speech.

`data/engines/ming-3/inference.log` is local and rotates at 2 MiB with two backups.
It records request IDs, text hash/length, CUDA RNG-state hash, runtime/GPU details,
reference latent shape, transcript and acoustic-position counts, input positions,
decode budget/steps, final and maximum stop probability, termination reason,
split/retry activity and full failure tracebacks. Nothing is uploaded. Error
messages point to this log. Compare failing/successful request records before
attributing remaining intermittency to context overflow.

## Validation

The regression suite executes the pinned upstream `sample()` and `generate()`
methods with simulated NumPy-backed tensors, plus the real upstream token-contract
builder with a simulated tokenizer. It reproduces zero-budget concatenation,
the patch-size budget error, silent truncation, minimum-step stopping, missing stop
signals, source-drift refusal, tag-safe long-text splitting and unchanged clone
conditioning. These are deterministic control-flow tests, **not** CUDA inference
or perceptual voice-quality validation. Real NVIDIA/BF16 acceptance remains needed.
