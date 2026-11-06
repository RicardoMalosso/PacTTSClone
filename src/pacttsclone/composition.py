"""Whole-utterance synthesis, conservative word alignment and inline audio insertion."""

import re
from pathlib import Path

import numpy as np
import soundfile as sf

from .audio import AudioPipeline
from .domain import UserError, Waveform


def words(text):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)*", text.casefold(), re.UNICODE)


def insertion_points(parts, chunks, duration):
    """Only accept an exact word sequence and finite, monotonic timestamps.

    ASR timestamps are estimates, never a guarantee of phoneme-accurate cuts.
    Missing/repeated/misrecognized words make the request use segmented fallback.
    """
    expected = [w for p in parts if "text" in p for w in words(p["text"])]
    recognized, spans = [], []
    previous = 0.0
    for chunk in chunks:
        tokens = words(chunk["text"])
        start, end = chunk["timestamp"]
        if (
            len(tokens) != 1
            or start is None
            or end is None
            or not np.isfinite([start, end]).all()
            or not previous <= start < end <= duration
        ):
            raise UserError("Word timestamps are incomplete or ambiguous.")
        recognized += tokens
        spans.append((start, end))
        previous = end
    if recognized != expected or not expected:
        raise UserError("Word alignment did not exactly match the generated script.")
    count = 0
    points = []
    for part in parts:
        if "text" in part:
            count += len(words(part["text"]))
        else:
            if count == 0:
                point = 0.0
            elif count == len(expected):
                point = duration
            else:
                point = (spans[count - 1][1] + spans[count][0]) / 2
            points.append(point)
    return points


def align_words(engine, settings, waveform):
    # Test adapters can supply deterministic timestamps without downloading ASR.
    if hasattr(engine, "align_words"):
        return engine.align_words(waveform)
    aligner = getattr(engine, "_script_aligner", None)
    if aligner is None:
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        # Reuse the verified Whisper cache only. Never download a model implicitly.
        processor = AutoProcessor.from_pretrained(settings.asr_model, local_files_only=True)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            settings.asr_model,
            local_files_only=True,
            attn_implementation="eager",
        ).to("cpu")
        aligner = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            device=-1,
        )
        engine._script_aligner = aligner
    result = aligner(
        {
            "raw": np.asarray(waveform.samples, dtype=np.float32),
            "sampling_rate": waveform.sample_rate,
        },
        return_timestamps="word",
    )
    return result.get("chunks", [])


def execute_composition(engine, settings, task, emit):
    from .worker import execute_task

    pipeline = AudioPipeline(settings)
    root = Path(task["workspace"])
    assembled = []
    reports = []
    notes = []
    total_samples = 0

    def append(samples):
        nonlocal total_samples
        total_samples += len(samples)
        if total_samples > 48000 * 600:
            raise UserError("Combined audio exceeds 10 minutes.")
        assembled.append(samples)

    def synthesize(section, text, label):
        folder = root / label
        folder.mkdir()
        import shutil

        shutil.copyfile(root / section["reference"], folder / "reference.mp3")
        result = execute_task(
            engine,
            settings,
            {
                "workspace": str(folder),
                "kind": "speech",
                "request": {**section["request"], "text": text},
                "output": str(folder / "unused.mp3"),
                "pcm_only": True,
                "cpu_threads": task.get("cpu_threads", 4),
            },
            emit,
        )
        reports.append(result.get("metrics", {}))
        if not result["ok"]:
            raise UserError(f"Voice section {section['index']}: {result['error']}")
        # Normalize PCM before stitching, without an intermediate lossy MP3 encode.
        normalized = folder / "normalized.wav"
        pipeline._run(
            settings.ffmpeg,
            [
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(folder / "generated.wav"),
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(normalized),
            ],
        )
        return sf.read(normalized, dtype="float32")[0]

    def effect(part):
        samples, rate = sf.read(root / part["asset"], dtype="float32")
        if rate != 48000 or samples.ndim != 1 or not samples.size:
            raise UserError("Sound effect PCM is missing or invalid.")
        if part.get("duration") is not None:
            length = round(part["duration"] * rate)
            samples = np.tile(samples, max(1, int(np.ceil(length / len(samples)))))[:length]
        return np.clip(samples * part["volume"] / 100, -1, 1)

    try:
        for section in task["segments"]:
            parts = section["parts"]
            text = " ".join(p["text"] for p in parts if "text" in p)
            effects = [p for p in parts if "sfx_id" in p]
            if not text:
                for part in effects:
                    append(effect(part))
                continue
            speech = synthesize(section, text, f"section-{section['index']}")
            if not effects:
                append(speech)
                continue
            has_internal_effect = any(
                "sfx_id" in part
                and any("text" in p for p in parts[:i])
                and any("text" in p for p in parts[i + 1 :])
                for i, part in enumerate(parts)
            )
            try:
                if has_internal_effect:
                    emit({"type": "composition", "stage": "align", "section": section["index"]})
                    if getattr(engine, "external_runtime", False):
                        engine.alignment_workspace = root
                    chunks = align_words(engine, settings, Waveform(speech, 48000))
                    points = insertion_points(parts, chunks, len(speech) / 48000)
                else:
                    points = []
                    seen_text = False
                    for part in parts:
                        if "text" in part:
                            seen_text = True
                        else:
                            points.append(len(speech) / 48000 if seen_text else 0)
            except Exception as exc:
                # Never cut at a guessed character/time ratio. Record the fallback.
                notes.append(
                    {
                        "section": section["index"],
                        "mode": "segmented",
                        "reason": str(exc)[:300],
                    }
                )
                for i, part in enumerate(parts):
                    append(
                        effect(part)
                        if "sfx_id" in part
                        else synthesize(
                            section,
                            part["text"],
                            f"fallback-{section['index']}-{i}",
                        )
                    )
                continue
            cursor = 0
            for part, seconds in zip(effects, points, strict=True):
                position = round(seconds * 48000)
                append(speech[cursor:position])
                append(effect(part))
                cursor = position
            append(speech[cursor:])
            notes.append({"section": section["index"], "mode": "whole_utterance"})
        pipeline.encode(Waveform(np.concatenate(assembled), 48000), root, Path(task["output"]))
        metrics = {
            "stages": [s for r in reports for s in r.get("stages", [])],
            "worker_cpu_seconds": sum(r.get("worker_cpu_seconds", 0) for r in reports),
            "peak_ram_bytes": max((r.get("peak_ram_bytes", 0) for r in reports), default=0),
            "composition": notes,
            "accounting_note": "Speech stage samples only; alignment/assembly are excluded. "
            "Word timestamps are estimates. Segmented fallback is reported.",
        }
        return {
            "type": "result",
            "ok": True,
            "metrics": metrics,
            "device": getattr(engine, "device", None) or "test/cpu",
        }
    except Exception as exc:
        return {"type": "result", "ok": False, "error": str(exc), "metrics": {"composition": notes}}
