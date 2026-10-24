"""Spawned, reusable inference process. Hard cancellation never kills the web server."""

import contextlib
import multiprocessing as mp
import os
import queue
import signal
import threading
import time
import traceback
from dataclasses import asdict
from pathlib import Path

import psutil

from .audio import AudioPipeline
from .config import Settings
from .domain import GenerationRequest, UserError
from .engine import OmniVoiceEngine
from .resources import Resources


class Cancelled(UserError):
    pass


class Reporter:
    def __init__(self, emit, engine):
        self.emit = emit
        self.engine = engine
        self.resources = Resources()
        self.lock = threading.RLock()
        self.start = time.monotonic()
        self.stage_start = self.start
        self.cpu_start = time.process_time()
        self.total_cpu_start = self.cpu_start
        self.stage_name = "starting"
        self.device = "cpu"
        self.completed = []
        self.done = threading.Event()
        self.peak_ram = 0
        self.stage_peak_ram = 0
        self.stage_peak_cuda = 0
        self.peak_cuda = 0
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def _finish_stage(self):
        self.send()
        wall = time.monotonic() - self.stage_start
        self.completed.append(
            {
                "name": self.stage_name,
                "device": self.device,
                "wall_seconds": round(wall, 4),
                "sampled_peak_worker_ram_bytes": self.stage_peak_ram,
                "sampled_peak_cuda_allocated_bytes": self.stage_peak_cuda,
                "worker_cpu_seconds": round(time.process_time() - self.cpu_start, 4),
                "gpu_stage_wall_seconds": round(wall, 4)
                if self.device == "cuda" and self.stage_name == "inference"
                else 0,
            }
        )

    def stage(self, name, device="cpu"):
        with self.lock:
            self._finish_stage()
            self.stage_name, self.device = name, device
            self.stage_peak_ram = self.stage_peak_cuda = 0
            self.stage_start, self.cpu_start = time.monotonic(), time.process_time()
            self.send()

    def send(self):
        with self.lock:
            sample = self.resources.sample()
            self.peak_ram = max(self.peak_ram, sample["process_ram_bytes"] or 0)
            self.stage_peak_ram = max(self.stage_peak_ram, sample["process_ram_bytes"] or 0)
            cuda = {}
            # Reading PyTorch allocator counters is optional and does not allocate CUDA memory.
            if self.engine and getattr(self.engine, "device", None) == "cuda":
                with contextlib.suppress(Exception):
                    import torch

                    cuda = {
                        "allocated_bytes": torch.cuda.memory_allocated(),
                        "reserved_bytes": torch.cuda.memory_reserved(),
                        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                    }
                    self.peak_cuda = max(self.peak_cuda, cuda["peak_allocated_bytes"])
                    self.stage_peak_cuda = max(self.stage_peak_cuda, cuda["allocated_bytes"])
            self.emit(
                {
                    "type": "progress",
                    "stage": self.stage_name,
                    "device": self.device,
                    "stage_elapsed_seconds": round(time.monotonic() - self.stage_start, 2),
                    "resources": {**sample, "cuda": cuda},
                    "stages": list(self.completed),
                    "worker_cpu_seconds": round(time.process_time() - self.total_cpu_start, 4),
                    "peak_ram_bytes": self.peak_ram,
                    "peak_cuda_allocated_bytes": self.peak_cuda,
                }
            )

    def _monitor(self):
        while not self.done.wait(0.5):
            self.send()

    def finish(self):
        self.done.set()
        self.thread.join(2)
        with self.lock:
            self._finish_stage()
            return {
                "stages": self.completed,
                "hardware": self.resources.hardware(),
                "worker_cpu_seconds": round(time.process_time() - self.total_cpu_start, 4),
                "peak_ram_bytes": self.peak_ram,
                "peak_cuda_allocated_bytes": self.peak_cuda,
                "cuda_stream_elapsed_seconds": getattr(self.engine, "last_gpu_seconds", None),
                "resource_sample_interval_seconds": 0.5,
                "accounting_note": "CPU seconds count worker threads, exclude external FFmpeg. "
                "GPU stage/stream elapsed time includes CPU launch gaps; not GPU busy time. "
                "NVML GPU utilization/memory is device-wide, including other applications.",
            }


def execute_task(engine, settings, task, emit):
    if hasattr(engine, "last_gpu_seconds"):
        engine.last_gpu_seconds = None
    report = Reporter(emit, engine)
    if hasattr(engine, "observer"):
        engine.observer = report.stage
    try:
        report.stage("configure")
        try:
            import torch

            torch.set_num_threads(task.get("cpu_threads", 4))
        except ImportError:
            pass
        pipeline = AudioPipeline(settings)
        workspace = Path(task["workspace"])
        report.stage("decode")
        reference = workspace / "reference.wav"
        pipeline.decode(workspace / "reference.mp3", reference)
        request = GenerationRequest(**task["request"])
        transcript = request.ref_text
        if not transcript:
            if not hasattr(engine, "transcribe"):
                # Explicit test engines may provide a deterministic transcript.
                transcript = "Test reference transcript."
            else:
                transcript = engine.transcribe(str(reference))
            if not transcript or not transcript.strip():
                raise UserError("No speech transcription was returned. Enter the reference text.")
            emit({"type": "transcript", "text": transcript})
            request = request.model_copy(update={"ref_text": transcript})
        if task.get("kind") != "transcribe":
            if not hasattr(engine, "observer"):
                report.stage("inference", "test/cpu")
            waveform = engine.synthesize(str(reference), request)
            report.stage("encode")
            pipeline.encode(waveform, workspace, Path(task["output"]))
        return {
            "type": "result",
            "ok": True,
            "transcript": transcript,
            "metrics": report.finish(),
            "device": getattr(engine, "device", None) or "test/cpu",
        }
    except Exception as exc:
        traceback.print_exc()
        return {
            "type": "result",
            "ok": False,
            "error": str(exc)
            if isinstance(exc, UserError)
            else "Generation failed. See the terminal for details.",
            "metrics": report.finish(),
        }
    finally:
        if hasattr(engine, "observer"):
            engine.observer = lambda *args: None


def worker_main(settings, commands, events, engine_factory):
    if os.name == "posix":
        os.setsid()
    settings = Settings(**settings)
    engine = engine_factory(settings) if engine_factory else OmniVoiceEngine(settings)

    def emit(value):
        with contextlib.suppress(queue.Full, OSError):
            events.put(value, timeout=0.2)

    while True:
        task = commands.get()
        if task is None:
            break
        emit(execute_task(engine, settings, task, emit))


class ProcessRunner:
    def __init__(self, settings, engine_factory=None):
        self.settings = settings
        self.factory = engine_factory
        self.process = None
        self.commands = None
        self.events = None
        self.fingerprint = None
        self.lock = threading.RLock()

    @property
    def pid(self):
        return self.process.pid if self.process and self.process.is_alive() else None

    def execute(self, task, config, on_event, cancelled):
        from dataclasses import replace

        settings = replace(self.settings, device=config["device"])
        fingerprint = (settings.device, config["cpu_threads"])
        with self.lock:
            if self.fingerprint != fingerprint or not self.pid:
                self.reset()
                ctx = mp.get_context("spawn")
                self.commands, self.events = ctx.Queue(2), ctx.Queue(512)
                self.process = ctx.Process(
                    target=worker_main,
                    args=(asdict(settings), self.commands, self.events, self.factory),
                    daemon=True,
                )
                self.process.start()
                self.fingerprint = fingerprint
            task = {**task, "cpu_threads": config["cpu_threads"]}
            self.commands.put(task)
        while True:
            if cancelled.is_set():
                self.reset(hard=True)
                raise Cancelled("Cancelled by the streamer.")
            try:
                event = self.events.get(timeout=0.15)
            except queue.Empty:
                if not self.pid:
                    raise UserError("Inference process stopped unexpectedly. Try again.") from None
                continue
            if event["type"] == "result":
                return event
            on_event(event)

    def reset(self, hard=False):
        with self.lock:
            if self.process:
                if self.process.is_alive() and not hard and self.commands:
                    with contextlib.suppress(Exception):
                        self.commands.put(None, timeout=0.2)
                        self.process.join(2)
                if os.name == "posix" and self.process.is_alive():
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(self.process.pid, signal.SIGKILL)
                with contextlib.suppress(psutil.Error, OSError):
                    for child in psutil.Process(self.process.pid).children(recursive=True):
                        with contextlib.suppress(psutil.Error):
                            child.kill()
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(1)
                if self.process.is_alive():
                    self.process.kill()
                    self.process.join(1)
                self.process.close()
                self.process = None
            for value in [self.commands, self.events]:
                if value:
                    value.cancel_join_thread()
                    value.close()
            self.fingerprint = None


class InlineRunner:
    """Explicit lightweight test injection, never used by the normal application."""

    def __init__(self, settings, engine):
        self.settings, self.engine = settings, engine
        self.pid = None

    def execute(self, task, config, on_event, cancelled):
        if cancelled.is_set():
            raise Cancelled("Cancelled")
        return execute_task(self.engine, self.settings, task, on_event)

    def reset(self):
        pass
