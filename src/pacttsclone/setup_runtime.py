"""Explicit local-owner dependency installation; no inference imports in the web process."""

import contextlib
import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import psutil

from .domain import BusyError, UserError
from .engine import dependencies_available


class RuntimeSetup:
    def __init__(self, service):
        self.service = service
        self.root = service.settings.data_dir / "setup"
        self.root.mkdir(exist_ok=True)
        self.model_ids = (service.settings.model, service.settings.asr_model)
        self.state_path = self.root / "runtime.json"
        self.log_path = service.logs / "runtime-setup.log"
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.process = None
        self.thread = None
        try:
            self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {"status": "idle", "stage": "idle", "device": None, "error": None}
        if self.state["status"] == "running":
            self.state.update(
                status="cancelled", stage="interrupted", error="Setup was interrupted. Retry setup."
            )
        self.lines = []
        self.on_ready = lambda: None
        self._apply_models()
        service.setup_ready = lambda: self.snapshot()["ready"]

    def _models_present(self):
        files = self.state.get("models", {}).get("files", [])
        try:
            return bool(files) and all(
                Path(f["path"]).is_file() and Path(f["path"]).stat().st_size == f["size"]
                for f in files
            )
        except OSError:
            return False

    def _apply_models(self):
        if self.state["status"] == "succeeded" and self._models_present():
            paths = list(self.state["models"]["paths"].values())
            settings = replace(
                self.service.settings, model=paths[0], asr_model=paths[1], offline=True
            )
            self.service.settings = settings
            self.service.runner.settings = settings

    def snapshot(self):
        with self.lock:
            ready = (
                not self.service.setup_busy
                and self.state["status"] not in {"running", "failed", "cancelled"}
                and (
                    self.service.engine is not None
                    or (
                        dependencies_available()
                        and self.state["status"] == "succeeded"
                        and self._models_present()
                    )
                )
            )
            return {**self.state, "ready": ready, "lines": self.lines[-100:]}

    def update(self, **values):
        with self.lock:
            self.state.update(values)
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state), encoding="utf-8")
            tmp.replace(self.state_path)

    def _kill(self):
        with self.lock:
            process = self.process
        if process and process.poll() is None:
            with contextlib.suppress(psutil.Error):
                for child in psutil.Process(process.pid).children(recursive=True):
                    with contextlib.suppress(psutil.Error):
                        child.kill()
            with contextlib.suppress(OSError):
                process.kill()

    def cancel(self):
        self.cancelled.set()
        self._kill()
        return self.snapshot()

    def close(self):
        self.cancel()
        if self.thread:
            self.thread.join(5)

    def start(self, device):
        if device not in {"cpu", "cuda"}:
            raise UserError("Choose CPU or NVIDIA CUDA.")
        with self.service._lock:
            if self.service.pending() or self.service.setup_busy:
                raise BusyError("Finish or cancel generation/setup before installing dependencies.")
            if "torch" in sys.modules:
                raise UserError("Restart the application before changing inference dependencies.")
            self.service.setup_busy = True
            self.service.runner.reset()
            self.cancelled.clear()
            self.lines = []
            self.update(
                status="running",
                stage="prepare",
                device=device,
                error=None,
                completed_steps=0,
                total_steps=5,
                download=None,
            )
            self.thread = threading.Thread(
                target=self._run, args=(device,), daemon=True, name="runtime-setup"
            )
            self.thread.start()
        return self.snapshot()

    def _commands(self, device):
        # Freeze loaded base distributions so package installation cannot replace
        # numpy/Pydantic/etc while the web process is using them.
        mapping = importlib.metadata.packages_distributions()
        names = {
            name for module in list(sys.modules) for name in mapping.get(module.split(".")[0], [])
        }
        constraints = self.root / "base-constraints.txt"
        constraints.write_text(
            "\n".join(
                f"{name}=={importlib.metadata.version(name)}"
                for name in sorted(names)
                if name.lower() not in {"torch", "torchaudio", "omnivoice", "transformers"}
            ),
            encoding="utf-8",
        )
        uv = os.environ.get("PACTTS_SETUP_UV")
        if uv and Path(uv).is_file():
            prefix = [uv, "--color", "never", "pip", "install", "--python", sys.executable]
            extra = [
                "--index",
                f"https://download.pytorch.org/whl/{'cu128' if device == 'cuda' else 'cpu'}",
                "--index-strategy",
                "unsafe-best-match",
            ]
        else:
            prefix = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--progress-bar",
                "off",
            ]
            extra = [
                "--extra-index-url",
                f"https://download.pytorch.org/whl/{'cu128' if device == 'cuda' else 'cpu'}",
            ]
        variant = "cu128" if device == "cuda" else "cpu"
        torch = [f"torch==2.8.0+{variant}", f"torchaudio==2.8.0+{variant}"]
        if sys.platform == "darwin" and device == "cpu":
            torch, extra = ["torch==2.8.0", "torchaudio==2.8.0"], []
        commands = [
            (
                "pytorch",
                prefix
                + [
                    "--constraint",
                    str(constraints),
                    "--index-url",
                    f"https://download.pytorch.org/whl/{variant}",
                ]
                + torch,
            ),
            (
                "inference",
                prefix
                + ["--constraint", str(constraints), "--index-url", "https://pypi.org/simple"]
                + extra
                + torch
                + ["omnivoice==0.2.1", "transformers==5.20.2"],
            ),
            (
                "verify",
                [
                    sys.executable,
                    "-c",
                    "import torch, torchaudio, omnivoice; "
                    + (
                        "assert torch.cuda.is_available(), "
                        "'CUDA unavailable: select CPU or fix driver'; "
                        if device == "cuda"
                        else ""
                    )
                    + "print('Inference runtime verified')",
                ],
            ),
        ]

        model_ids = self.state.get("model_ids") or self.model_ids
        commands.append(
            (
                "models",
                [
                    sys.executable,
                    "-m",
                    "pacttsclone.model_setup",
                    "--root",
                    str(self.service.settings.data_dir / "models"),
                    "--model",
                    model_ids[0],
                    "--asr-model",
                    model_ids[1],
                    "--hf-cache",
                    os.environ.get("HF_HUB_CACHE", str(Path.home() / ".cache/huggingface/hub")),
                ],
            )
        )
        return commands

    def _run_command(self, command, log):
        env = {
            **os.environ,
            "UV_CACHE_DIR": str(self.root / "cache"),
            "PIP_CACHE_DIR": str(self.root / "cache"),
            "UV_NO_CONFIG": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PIP_CONFIG_FILE": os.devnull,
            "TEMP": str(self.root / "temporary"),
            "TMP": str(self.root / "temporary"),
        }
        Path(env["TEMP"]).mkdir(exist_ok=True)
        with self.lock:
            if self.cancelled.is_set():
                raise InterruptedError("Setup cancelled.")
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            process = self.process
        for line in process.stdout:
            log.write(line)
            log.flush()
            if line.startswith("@@PACTTS_SETUP@@"):
                self.update(**json.loads(line[len("@@PACTTS_SETUP@@") :]))
                continue
            with self.lock:
                self.lines.append(line.rstrip())
                self.lines = self.lines[-100:]
            if self.cancelled.is_set():
                self._kill()
        code = process.wait()
        process.stdout.close()
        if self.cancelled.is_set():
            raise InterruptedError("Setup cancelled.")
        if code:
            raise UserError(f"Dependency setup failed (exit {code}). See the setup log and retry.")

    def _run(self, device):
        try:
            with self.log_path.open("a", encoding="utf-8") as log:
                log.write(f"\nSetup requested: {device}\n")
                self.update(model_ids=self.state.get("model_ids") or list(self.model_ids))
                for number, (stage, command) in enumerate(self._commands(device), 1):
                    if self.cancelled.is_set():
                        raise InterruptedError("Setup cancelled.")
                    self.update(stage=stage, completed_steps=number - 1)
                    self._run_command(command, log)
                importlib.invalidate_caches()
                if self.cancelled.is_set():
                    raise InterruptedError("Setup cancelled.")
                self.update(stage="activate", completed_steps=4)
                with self.service._lock:
                    from .models import AppConfig

                    self.service.configure(
                        AppConfig(**{**self.service.config.model_dump(), "device": device})
                    )
                self.update(
                    status="succeeded", stage="ready", completed_steps=5, finished_at=time.time()
                )
                self._apply_models()
        except InterruptedError as exc:
            self.update(status="cancelled", stage="cancelled", error=str(exc))
        except Exception as exc:
            self.update(status="failed", stage="failed", error=str(exc))
        finally:
            with self.service._lock:
                self.service.setup_busy = False
            with self.lock:
                self.process = None
        if self.state["status"] == "succeeded":
            self.on_ready()
