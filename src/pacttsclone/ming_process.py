"""Persistent isolated Ming subprocess owned by the cancellable process worker."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from .domain import UserError, Waveform
from .ming_engine import generation_arguments

MARKER = "@@PACTTS_MING@@"


class MingProcessEngine:
    engine_id = "ming-3"
    worker_file = "ming_runtime_worker.py"
    marker = MARKER
    label = "Ming"
    external_runtime = True

    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.device = None
        self.observer = lambda *args: None
        self.residency_observer = lambda *args: None
        self.last_gpu_seconds = None

    def _response(self):
        for line in self.process.stdout:
            if line.startswith(self.marker):
                value = json.loads(line[len(self.marker) :])
                if not value.get("ok"):
                    self._close()
                    raise UserError(self.label + ": " + value.get("error", "Runtime failed."))
                return value
        self._close()
        raise UserError(f"{self.label} runtime stopped. Check the installation log.")

    def _close(self):
        if self.process is not None:
            self.process.stdin.close()
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdout.close()
            self.process = None
        self.residency_observer(False, self.device)

    def _load(self):
        if self.process is not None and self.process.poll() is None:
            return
        root = self.settings.data_dir / "engines" / self.engine_id
        python = root / "runtime" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            raise UserError(f"Install {self.label} from Engines before generation.")
        env = {
            **os.environ,
            "PYTHONNOUSERSITE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        self.observer("load_model", "cuda")
        self.process = subprocess.Popen(
            self._command(python, root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(root),
        )
        self._response()
        self.device = "cuda"
        self.residency_observer(True, self.device)

    def close(self):
        self._close()

    def _command(self, python, root):
        return [
            str(python),
            "-u",
            str(Path(__file__).with_name(self.worker_file)),
            "--source",
            str(root / "source"),
            "--model",
            self.settings.model,
        ]

    def transcribe(self, reference):
        if not Path(self.settings.asr_model).is_dir():
            raise UserError(
                "Add an exact transcript, or install the shared Whisper model "
                "through Initial Setup."
            )
        self._load()
        self.observer("transcribe", "cpu")
        self.process.stdin.write(
            json.dumps(
                {"kind": "transcribe", "reference": reference, "asr_model": self.settings.asr_model}
            )
            + "\n"
        )
        self.process.stdin.flush()
        return self._response()["transcript"]

    def arguments(self, reference, request):
        return generation_arguments(reference, request)

    def synthesize(self, reference, request):
        arguments = self.arguments(reference, request)
        self._load()
        self.observer("inference", "cuda")
        with tempfile.TemporaryDirectory(prefix="ming-", dir=Path(reference).parent) as directory:
            output = Path(directory) / "speech.wav"
            try:
                self.process.stdin.write(
                    json.dumps({"arguments": arguments, "output": str(output)}) + "\n"
                )
                self.process.stdin.flush()
                self._response()
                samples, rate = sf.read(output, dtype="float32")
                if samples.ndim != 1 or not samples.size or not np.isfinite(samples).all():
                    raise UserError(f"{self.label} returned invalid mono audio.")
                return Waveform(samples, rate)
            except (OSError, ValueError) as exc:
                self._close()
                raise UserError(f"{self.label} output failed; CPU fallback is disabled.") from exc
