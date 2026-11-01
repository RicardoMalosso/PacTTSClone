"""Execute the pinned upstream sampler with simulated tensors, never real inference."""

import ast
import contextlib
import logging
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pacttsclone.ming_inference import (
    DecodeLimit,
    MingInferenceError,
    diagnostic,
    input_positions,
    install_safe_generation,
    load_patched_model,
    patched_source,
    split_fragment,
)

FIXTURES = Path(__file__).with_name("fixtures")


class Tensor(np.ndarray):
    device = "cpu"

    def to(self, *args, **kwargs):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self

    def float(self):
        return self

    def clone(self):
        return self.copy()

    def numel(self):
        return self.size

    def masked_fill_(self, mask, value):
        self[mask] = value
        return self

    def softmax(self, dim):
        result = np.exp(self - self.max(axis=dim, keepdims=True))
        return result / result.sum(axis=dim, keepdims=True)


def tensor(value):
    return np.asarray(value, dtype=float).view(Tensor)


@pytest.fixture
def fake_torch(monkeypatch):
    torch = SimpleNamespace(
        autocast=lambda **kwargs: contextlib.nullcontext(),
        bfloat16="bf16",
        zeros=lambda *shape, **kwargs: tensor(np.zeros(shape)),
        ones=lambda *shape: tensor(np.ones(shape[0] if len(shape) == 1 else shape)),
        cat=lambda values, dim: tensor(np.concatenate(values, axis=dim)),
        isfinite=np.isfinite,
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def sampler(fake_torch, positions, stop_after=5, max_steps=1000, patched=True):
    source = (FIXTURES / "ming_modeling_bailingmm.txt").read_text()
    tree = ast.parse(patched_source(source) if patched else source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods = [
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name in {"sample", "generate"}
    ]
    for node in methods:
        node.decorator_list = []
    namespace = dict(
        torch=fake_torch,
        tqdm=lambda value: value,
        logger=SimpleNamespace(info=lambda *args: None),
        diagnostic=diagnostic,
        DecodeLimit=DecodeLimit,
        MingInferenceError=MingInferenceError,
        MAX_CACHE_LEN=512,
    )
    exec(compile(ast.Module(body=methods, type_ignores=[]), "upstream-sampler", "exec"), namespace)
    calls = []

    def backbone(**kwargs):
        calls.append(kwargs["position_ids"].copy())
        return SimpleNamespace(past_key_values=None, hidden_states=[tensor(np.ones((1, 1, 2)))])

    model = SimpleNamespace(
        model_type="dense",
        patch_size=4,
        history_patch_size=8,
        latent_dim=2,
        prepare_input_embed=lambda **kwargs: (
            tensor(np.ones((1, positions))),
            tensor(np.ones((1, positions, 2))),
        ),
        tokenizer=SimpleNamespace(decode=lambda value: "redacted"),
        model=backbone,
        flowloss=SimpleNamespace(sample=lambda *args, **kwargs: tensor(np.ones((1, 4, 2)))),
        linear_proj_audio=lambda value: tensor(np.ones((1, 1, 2))),
        stop_head=lambda z: tensor([[[0, 10 if len(calls) >= stop_after else -10]]]),
        encode_prompt_latent=lambda value: value,
        audio=SimpleNamespace(decode=lambda value, **kwargs: (tensor(np.ones((1, 1, 80))),)),
    )
    model.sample = types.MethodType(namespace["sample"], model)
    model.generate = types.MethodType(namespace["generate"], model)
    return model, calls, dict(prompt="prompt", text="hi", max_decode_steps=max_steps)


def test_reproduces_upstream_empty_cat_and_guards_fixed_path(fake_torch):
    original, _, args = sampler(fake_torch, 512, patched=False)
    with pytest.raises(ValueError, match="at least one array"):
        original.generate(**args)
    fixed, calls, args = sampler(fake_torch, 512)
    with pytest.raises(DecodeLimit, match="fewer than five"):
        fixed.generate(**args)
    assert not calls


def test_one_position_per_audio_patch_and_learned_stop(fake_torch):
    original, original_calls, args = sampler(fake_torch, 480, stop_after=13, patched=False)
    original.generate(**args)  # Original silently truncates after eight steps.
    assert len(original_calls) == 8
    fixed, calls, args = sampler(fake_torch, 480, stop_after=13)
    assert fixed.generate(**args).numel() == 80
    assert len(calls) == 13
    assert fixed._pactts_decode["stop_reason"] == "stop_head"
    assert fixed._pactts_decode["budget"] == 32
    assert calls[1].item() == 480  # Four audio latents consume one LLM position.


@pytest.mark.parametrize("max_steps,reason", [(1000, "context_limit"), (6, "max_decode_steps")])
def test_limit_is_never_silently_returned_as_complete(fake_torch, max_steps, reason):
    fixed, _, args = sampler(fake_torch, 500, stop_after=100, max_steps=max_steps)
    with pytest.raises(DecodeLimit, match="without a stop signal"):
        fixed.generate(**args)
    assert fixed._pactts_decode["stop_reason"] == reason


def test_stop_cannot_empty_latent_list_even_if_probability_starts_high(fake_torch):
    fixed, calls, args = sampler(fake_torch, 100, stop_after=0)
    fixed.generate(**args)
    assert len(calls) == 5


def test_guard_against_an_unexpected_empty_generator(fake_torch):
    fixed, _, args = sampler(fake_torch, 100)
    fixed._pactts_decode = {"stop_reason": "unknown"}
    fixed.sample = lambda **kwargs: iter(())
    with pytest.raises(MingInferenceError, match="no audio latents"):
        fixed.generate(**args)


@pytest.fixture
def contract(monkeypatch):
    module = types.ModuleType("prompt_contract")
    exec((FIXTURES / "ming_prompt_contract.txt").read_text(), module.__dict__)
    monkeypatch.setitem(sys.modules, "prompt_contract", module)
    return module


class Tokenizer:
    def encode(self, value, **kwargs):
        return [self.convert_tokens_to_ids(t) for t in re.findall(r"<[^>]+>|\S", value)]

    def convert_tokens_to_ids(self, token):
        return {"<|vision_start|>": 1001, "<|vision_pad|>": 1002}.get(token, 1)


def safe_model(fake_torch):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return tensor(np.ones((1, len(kwargs["text"]))))

    model = SimpleNamespace(
        generate=generate, tokenizer=Tokenizer(), model_type="dense", patch_size=4
    )
    tts = SimpleNamespace(model=model, prepare_prompt=lambda *args: None, sample_rate=24000)
    install_safe_generation(tts)
    return model, calls


def test_token_chunking_preserves_every_character_and_reference(fake_torch, contract):
    model, calls = safe_model(fake_torch)
    # No spaces: tokenizer-aware recursion must handle a long unbroken string.
    text = "你" * 2000
    latent = SimpleNamespace(size=lambda axis: 400)
    speakers = [tensor([1, 2])]
    args = dict(
        prompt="prompt",
        text=text,
        prompt_text="reference words",
        prompt_latent=latent,
        spk_emb=speakers,
        instruction=None,
    )
    audio = model.generate(**args)
    assert audio.numel() == len(text)
    assert "".join(c["text"] for c in calls) == text
    assert len(calls) > 1
    for call in calls:
        assert call["prompt_latent"] is latent
        assert call["spk_emb"] is speakers
        assert call["prompt_text"] == "reference words"
        assert input_positions(model, call)[0] <= 448


def test_non_stopping_fragment_splits_without_switching_voice(fake_torch, contract):
    model, calls = safe_model(fake_torch)
    original = model.generate
    # Install around a model whose full fragment hits its decode limit.
    tts = SimpleNamespace(model=model, sample_rate=24000, prepare_prompt=lambda *args: None)
    model.generate = lambda **kwargs: (
        (_ for _ in ()).throw(DecodeLimit("no stop"))
        if len(kwargs["text"]) > 5
        else original(**kwargs)
    )
    install_safe_generation(tts)
    assert model.generate(prompt="p", text="abcdefghij").numel() == 10
    assert [c["text"] for c in calls] == ["abcde", "fghij"]


def test_reference_overflow_never_discards_transcript_or_acoustic_prompt(fake_torch, contract):
    model, calls = safe_model(fake_torch)
    with pytest.raises(MingInferenceError, match="exact matching transcript"):
        model.generate(
            prompt="p",
            text="hi",
            prompt_text="x" * 600,
            prompt_latent=SimpleNamespace(size=lambda axis: 4),
        )
    assert not calls


def test_non_stopping_retries_are_bounded(fake_torch, contract):
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        # Some small fragments finish, but larger fragments keep failing.
        if len(kwargs["text"]) <= 2:
            return tensor(np.ones((1, 4)))
        raise DecodeLimit("never stopped")

    model = SimpleNamespace(
        generate=fail, tokenizer=Tokenizer(), model_type="dense", patch_size=4
    )
    tts = SimpleNamespace(model=model, prepare_prompt=lambda *args: None, sample_rate=24000)
    install_safe_generation(tts)
    with pytest.raises(MingInferenceError, match="eight attempts"):
        model.generate(prompt="p", text="x" * 64)
    assert len([c for c in calls if len(c["text"]) > 2]) == 8


@pytest.mark.parametrize("samples", [[], [float("nan")]])
def test_invalid_decoder_audio_is_not_replaced_with_silence(fake_torch, contract, samples):
    model, _ = safe_model(fake_torch)
    model.generate = lambda **kwargs: tensor(samples)
    tts = SimpleNamespace(model=model, prepare_prompt=lambda *args: None, sample_rate=24000)
    install_safe_generation(tts)
    with pytest.raises(MingInferenceError, match="empty or non-finite"):
        model.generate(prompt="p", text="hello")


@pytest.mark.parametrize("text", ["[Laughter] hello world", "你好世界", "hello. next sentence"])
def test_tag_safe_split(text):
    left, right = split_fragment(text)
    assert (left + right).replace(" ", "") == text.replace(" ", "")
    assert left.count("[") == left.count("]")
    assert right.count("[") == right.count("]")


def test_unsplittable_tag_and_source_drift_fail_explicitly():
    with pytest.raises(MingInferenceError, match="inline tag"):
        split_fragment("[Laughter]")
    with pytest.raises(MingInferenceError, match="source revision"):
        patched_source("different source")


def test_real_module_loader_repairs_in_memory_without_changing_cached_source(
    tmp_path, monkeypatch, fake_torch, contract
):
    fake_torch.inference_mode = lambda: (lambda function: function)
    fake_torch.nn = types.ModuleType("torch.nn")
    monkeypatch.setitem(sys.modules, "torch.nn", fake_torch.nn)
    imports = {
        "transformers": dict(PreTrainedModel=object, Qwen2ForCausalLM=object, Qwen2Config=object),
        "tqdm": dict(tqdm=lambda value: value),
        "loguru": dict(logger=SimpleNamespace(info=lambda *args: None)),
        "configuration_bailingmm": dict(BailingMMConfig=object),
        "fm.dit": dict(Aggregator=object),
        "fm.flowloss": dict(FlowLoss=object),
        "audio_tokenizer.modeling_audio_vae": dict(AudioVAE=object),
    }
    for name, values in imports.items():
        module = types.ModuleType(name)
        module.__dict__.update(values)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, "modeling_bailingmm", None)
    path = tmp_path / "modeling_bailingmm.py"
    original = (FIXTURES / "ming_modeling_bailingmm.txt").read_bytes()
    # Normalize Git's potential checkout newline conversion for the download fixture.
    original = original.replace(b"\r\n", b"\n")
    path.write_bytes(original)
    module = load_patched_model(tmp_path)
    assert path.read_bytes() == original
    assert module.__spec__.name == "modeling_bailingmm"
    assert module.BailingMMNativeForConditionalGeneration.generate.__globals__["DecodeLimit"] is (
        DecodeLimit
    )


def test_diagnostics_include_counts_and_stop_probabilities(fake_torch, caplog):
    fixed, _, args = sampler(fake_torch, 480)
    with caplog.at_level(logging.INFO, logger="pactts.ming.inference"):
        fixed.generate(**args)
    assert '"input_positions": 480' in caplog.text
    assert '"stop_reason": "stop_head"' in caplog.text
    assert '"last_stop_probability"' in caplog.text
