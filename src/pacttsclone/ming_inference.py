"""Runtime-only repairs for the pinned Ming dense implementation.

Never edit the verified source/model cache. Refuse unknown source revisions rather
than applying a plausible but unsafe patch to a different inference implementation.
"""

import hashlib
import importlib.util
import json
import logging
import re
from pathlib import Path

LOGGER = logging.getLogger("pactts.ming.inference")
SOURCE_BLOB = "3c7607c36aa7304999ca8152a81aab134afeca48"
CONTEXT = 512
DECODE_RESERVE = 64


class MingInferenceError(RuntimeError):
    pass


class DecodeLimit(MingInferenceError):
    """The sampler exhausted its budget without a learned stop signal."""


def diagnostic(event, **values):
    LOGGER.info(json.dumps({"event": event, **values}, sort_keys=True))


def patched_source(source):
    data = source.encode("utf-8")
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if digest != SOURCE_BLOB:
        raise MingInferenceError(
            "Unsupported Ming inference source revision; repair source in Engines."
        )
    changes = {
        "decode_budget = (MAX_CACHE_LEN - inputs_embeds.shape[1]) // self.patch_size":
        """# Aggregator emits ONE LLM embedding per audio patch, not patch_size.
        decode_budget = MAX_CACHE_LEN - inputs_embeds.shape[1]
        self._pactts_decode = dict(input_positions=int(inputs_embeds.shape[1]),
            patch_size=int(self.patch_size), budget=int(decode_budget), steps=0,
            stop_reason=('context_limit' if decode_budget <= max_decode_steps
                         else 'max_decode_steps'),
            max_stop_probability=0.0)
        diagnostic('decode_start', **self._pactts_decode)
        if min(max_decode_steps, decode_budget) < 5:
            raise DecodeLimit('Ming has fewer than five decode steps: ' +
                              str(self._pactts_decode))""",
        "if self.stop_head(z_diff)[0][0].softmax(dim=-1)[1] > 0.5 and step > 3:":
        """stop_probability = float(self.stop_head(z_diff)[0][0].softmax(dim=-1)[1])
            self._pactts_decode.update(steps=step + 1,
                last_stop_probability=stop_probability,
                max_stop_probability=max(self._pactts_decode['max_stop_probability'],
                                         stop_probability))
            if stop_probability > 0.5 and step > 3:
                self._pactts_decode['stop_reason'] = 'stop_head'""",
        "sampled_tokens = torch.cat(sampled_tokens_list, dim=1)":
        """diagnostic('decode_end', **self._pactts_decode)
            if not sampled_tokens_list:
                raise MingInferenceError('Ming sampler yielded no audio latents: ' +
                                         str(self._pactts_decode))
            if self._pactts_decode['stop_reason'] != 'stop_head':
                raise DecodeLimit('Ming reached its decode limit without a stop signal: ' +
                                  str(self._pactts_decode))
            sampled_tokens = torch.cat(sampled_tokens_list, dim=1)""",
    }
    for old, new in changes.items():
        if source.count(old) != 1:
            raise MingInferenceError("Ming inference patch anchor mismatch.")
        source = source.replace(old, new)
    return source


def load_patched_model(source_directory):
    """Import the verified model with narrow, auditable in-memory repairs."""
    import sys

    path = Path(source_directory) / "modeling_bailingmm.py"
    source = patched_source(path.read_bytes().decode("utf-8"))
    spec = importlib.util.spec_from_file_location("modeling_bailingmm", path)
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(
        diagnostic=diagnostic, DecodeLimit=DecodeLimit, MingInferenceError=MingInferenceError
    )
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(module.__name__, None)
        raise
    return module


def split_fragment(text):
    """Prefer sentence/word boundaries; keep inline vocal tags indivisible."""
    spans = [(m.start(), m.end()) for m in re.finditer(r"\[[^\]]*\]", text)]
    midpoint = len(text) / 2

    def valid(p):
        return 0 < p < len(text) and not any(a < p < b for a, b in spans)

    boundaries = [m.end() for m in re.finditer(r"[.!?。！？]+\s*|\s+", text)]
    boundaries = [p for p in boundaries if valid(p) and text[:p].strip() and text[p:].strip()]
    if not boundaries:
        boundaries = [p for p in range(1, len(text)) if valid(p)]
    if not boundaries:
        raise MingInferenceError("Ming cannot split this fragment safely; shorten the inline tag.")
    position = min(boundaries, key=lambda p: abs(p - midpoint))
    left, right = text[:position].strip(), text[position:].strip()
    if not left or not right:
        raise MingInferenceError("Ming fragment cannot be split into non-empty text.")
    return left, right


def input_positions(model, arguments):
    """Use the actual trained prompt contract, including transcript/audio slots."""
    import prompt_contract

    latent = arguments.get("prompt_latent")
    transcript = arguments.get("prompt_text")
    latent_steps = 0
    if latent is not None and transcript is not None:
        if latent.size(1) == 0 or latent.size(1) % model.patch_size:
            raise MingInferenceError("Ming reference has empty or unaligned acoustic latents.")
        latent_steps = latent.size(1) // model.patch_size
    ids, _, _ = prompt_contract.build_input_ids(
        model.tokenizer,
        model.model_type,
        arguments["prompt"],
        arguments["text"],
        num_speakers=len(arguments.get("spk_emb") or []),
        instruction=arguments.get("instruction"),
        prompt_text=transcript,
        prompt_latent_steps=latent_steps,
    )
    return len(ids), latent_steps


def install_safe_generation(tts):
    """Split with fixed cloned conditioning; never promote generated clone chunks."""
    import torch

    model = tts.model
    original = model.generate
    prepare_prompt = tts.prepare_prompt

    def checked_prompt(*args, **kwargs):
        latent, speakers = prepare_prompt(*args, **kwargs)
        diagnostic(
            "reference",
            latent_shape=list(latent.shape),
            speakers=len(speakers or []),
            sample_rate=tts.sample_rate,
            patch_size=model.patch_size,
        )
        if latent.numel() == 0 or not torch.isfinite(latent).all():
            raise MingInferenceError("Ming reference encoder returned empty or non-finite latents.")
        if any(e.numel() == 0 or not torch.isfinite(e).all() for e in (speakers or [])):
            raise MingInferenceError("Ming reference produced invalid speaker embeddings.")
        return latent, speakers

    tts.prepare_prompt = checked_prompt

    def generate(**arguments):
        retries = 0

        def run(fragment, depth=0):
            nonlocal retries
            current = {**arguments, "text": fragment}
            positions, latent_steps = input_positions(model, current)
            diagnostic(
                "fragment",
                depth=depth,
                characters=len(fragment),
                input_positions=positions,
                reference_positions=latent_steps,
                transcript_characters=len(current.get("prompt_text") or ""),
                speakers=len(current.get("spk_emb") or []),
            )
            if depth > 24:
                raise MingInferenceError("Ming exceeded the safe text splitting depth.")
            if positions > CONTEXT - DECODE_RESERVE:
                base, _ = input_positions(model, {**current, "text": ""})
                if base >= CONTEXT - DECODE_RESERVE:
                    raise MingInferenceError(
                        f"Ming reference/transcript/instruction uses {base}/512 positions. "
                        "Use a shorter reference clip with its exact matching transcript, "
                        "or shorten the instruction. Reference conditioning was preserved."
                    )
            else:
                try:
                    chunk = original(**current)
                    if chunk.numel() == 0 or not torch.isfinite(chunk).all():
                        raise MingInferenceError("Ming decoder returned empty or non-finite audio.")
                    return chunk
                except DecodeLimit as exc:
                    retries += 1
                    diagnostic("fragment_retry", depth=depth, reason=str(exc))
                    if retries >= 8:
                        raise MingInferenceError(
                            "Ming repeatedly failed to signal completion after eight attempts. "
                            "Check the local inference log before retrying."
                        ) from exc
            if len(fragment.strip()) <= 1:
                raise MingInferenceError(
                    "Ming could not complete even the smallest fragment. "
                    "Check the local inference log for context and stop diagnostics."
                )
            left, right = split_fragment(fragment)
            return torch.cat([run(left, depth + 1), run(right, depth + 1)], dim=-1)

        return run(arguments["text"])

    model.generate = generate
