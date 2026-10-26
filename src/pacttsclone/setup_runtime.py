"""Explicit local-owner dependency installation; no inference imports in the web process."""

import contextlib
import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import psutil

from .data_import import import_personal_data
from .domain import BusyError, UserError
from .engine import dependencies_available
from .model_cache import default_roots, scan_weights, validate_roots


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
        self.state.setdefault("initial_setup_completed", self.state["status"] == "succeeded")
        self.state.setdefault("countermeasures_offered", False)
        if self.state["status"] == "running":
            self.state.update(
                status="cancelled", stage="interrupted", error="Setup was interrupted. Retry setup."
            )
        try:
            self.lines = self.log_path.read_text(encoding="utf-8").splitlines()[-500:]
        except OSError:
            self.lines = []
        self.import_thread = None
        self.import_status = {"status": "idle"}
        self.scan_thread = None
        self.scan_stop = threading.Event()
        self.discovery = {"status": "idle", "files": [], "checked_files": 0, "limited": False}
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
                        and self.state.get("device") == "cuda"
                        and self.state["status"] == "succeeded"
                        and self._models_present()
                    )
                )
            )
            return {
                **self.state,
                "ready": ready,
                "lines": self.lines[-500:],
                "weight_discovery": self.discovery,
                "import_status": self.import_status,
            }

    def update(self, **values):
        with self.lock:
            self.state.update(values)
            if "weight_discovery" in values:
                self.discovery = values["weight_discovery"]
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state), encoding="utf-8")
            tmp.replace(self.state_path)

    def discover_weights(self, roots):
        roots = validate_roots(roots)
        with self.lock:
            if self.service.setup_busy or (self.scan_thread and self.scan_thread.is_alive()):
                raise BusyError("Wait for the current setup or model search to finish.")
            self.update(weight_search_roots=roots)
            self.scan_stop.clear()
            self.discovery = {
                "status": "running",
                "files": [],
                "checked_files": 0,
                "limited": False,
            }

            def report(result):
                with self.lock:
                    self.discovery = result

            def run():
                report(
                    scan_weights(
                        [*default_roots(self.service.settings.data_dir), *roots],
                        stop=self.scan_stop,
                        report=report,
                    )
                )

            self.scan_thread = threading.Thread(target=run, daemon=True, name="model-discovery")
            self.scan_thread.start()
        return self.snapshot()

    def start_import(self, studio, value):
        category = value.get("category")
        if category not in {"models", "personal"}:
            raise UserError("Choose models or personal data to import.")
        with self.service._lock:
            if self.service.setup_busy or self.service.pending():
                raise BusyError("Wait for setup/generation to finish before importing.")
            if any(c["enabled"] for c in studio.channels()):
                raise BusyError("Disconnect Twitch channels before importing data.")
            if self.scan_thread and self.scan_thread.is_alive():
                raise BusyError("Wait for the model search to finish before importing.")
            self.service.setup_busy = True
            self.service.runner.reset()
            self.cancelled.clear()
            self.import_status = {
                "status": "running",
                "category": category,
                "bytes": 0,
                "started_at": time.time(),
            }
            self.import_thread = threading.Thread(
                target=self._import, args=(studio, dict(value)), daemon=True, name="optional-import"
            )
            self.import_thread.start()
        return self.snapshot()

    def _import(self, studio, value):
        try:
            if value["category"] == "personal":

                def report_import(result):
                    with self.lock:
                        self.import_status = {**self.import_status, **result}

                result = import_personal_data(
                    studio,
                    value.get("source"),
                    value.get("sections"),
                    value.get("replace_config", False),
                    self.cancelled,
                    report_import,
                )
            else:
                roots = validate_roots(value.get("search_roots", []))
                if not roots:
                    raise UserError("Choose the old model/cache folders to import from.")
                if not isinstance(value.get("move_weights", False), bool):
                    raise UserError("Choose copy or move for model weights.")
                ids = self.state.get("model_ids") or self.model_ids
                command = [
                    sys.executable,
                    "-m",
                    "pacttsclone.model_setup",
                    "--root",
                    str(self.service.settings.data_dir / "models"),
                    "--model",
                    ids[0],
                    "--asr-model",
                    ids[1],
                    "--hf-cache",
                    os.environ.get("HF_HUB_CACHE", str(Path.home() / ".cache/huggingface/hub")),
                    "--import-only",
                ]
                for root in roots:
                    command.extend(["--search-root", root])
                if value.get("move_weights"):
                    command.append("--move-weights")
                self.update(imported_models=None, weight_import=None)
                with self.log_path.open("a", encoding="utf-8") as log:
                    self._run_command(command, log)
                result = self.state.get("imported_models") or {}
            self.import_status = {**self.import_status, "status": "succeeded", "result": result}
        except InterruptedError as exc:
            self.import_status.update(status="cancelled", error=str(exc))
        except Exception as exc:
            self.import_status.update(status="failed", error=str(exc))
        finally:
            with self.service._lock:
                self.service.setup_busy = False
            with self.lock:
                self.process = None

    def offer_countermeasures(self):
        """Atomically claim the once-only prompt, including across browser reloads."""
        with self.lock:
            eligible = (
                self.state["status"] == "running"
                and not self.state.get("initial_setup_completed", False)
                and not self.state.get("countermeasures_offered", False)
                and time.time() - self.state.get("started_at", time.time()) >= 30
            )
            if eligible:
                self.update(countermeasures_offered=True)
            return {"offered": bool(eligible)}

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
        self.scan_stop.set()
        self.cancelled.set()
        if self.import_thread:
            self._kill()
            self.import_thread.join(5)
        if self.scan_thread:
            self.scan_thread.join(2)
        self.cancel()
        if self.thread:
            self.thread.join(5)

    def start(self, device, search_roots=None, move_weights=False):
        if not isinstance(move_weights, bool):
            raise UserError("Choose copy or move for the selected old model folders.")
        if search_roots is not None:
            search_roots = validate_roots(search_roots)
        if self.scan_thread and self.scan_thread.is_alive():
            raise BusyError("Wait for the model search to finish before installing.")
        if device not in {"cpu", "cuda"}:
            raise UserError("Choose CPU or NVIDIA CUDA.")
        # Re-selecting an installed CUDA runtime is a no-op, not a repair.
        # Configuration changes never call the installer. A successful prior manifest
        # is checked for presence/size only; downloads/imports retain full hashing.
        if (
            device == "cuda"
            and self.state.get("device") == "cuda"
            and self.state.get("status") == "succeeded"
            and dependencies_available()
            and self._models_present()
        ):
            with self.service._lock:
                from .models import AppConfig

                self.service.configure(
                    AppConfig(**{**self.service.config.model_dump(), "device": "cuda"})
                )
            return self.snapshot()
        with self.service._lock:
            if self.service.pending() or self.service.setup_busy:
                raise BusyError("Finish or cancel generation/setup before installing dependencies.")
            if "torch" in sys.modules:
                raise UserError("Restart the application before changing inference dependencies.")
            if search_roots is not None:
                self.update(weight_search_roots=search_roots)
            self.update(move_weights=move_weights)
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
                dependency_progress=None,
                started_at=time.time(),
                finished_at=None,
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
        # pip --progress-bar raw reports genuine byte counts through a pipe.
        prefix = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--progress-bar",
            "raw",
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
                    constraints.name,
                    "--index-url",
                    f"https://download.pytorch.org/whl/{variant}",
                ]
                + torch,
            ),
            (
                "inference",
                prefix
                + ["--constraint", constraints.name, "--index-url", "https://pypi.org/simple"]
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

    def _record_setup_line(self, log, message):
        """Record application-authored milestones in both the saved and live log."""
        now = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
        line = f"[{now}] {message}"
        log.write(line + "\n")
        log.flush()
        with self.lock:
            self.lines.append(line)
            self.lines = self.lines[-500:]

    def _run_command(self, command, log):
        env = {
            **os.environ,
            "UV_CACHE_DIR": str(self.root / "cache"),
            "PIP_CACHE_DIR": str(self.root / "cache"),
            "UV_NO_CONFIG": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_PROGRESS_BAR": "raw",
            "TEMP": str(self.root / "temporary"),
            "TMP": str(self.root / "temporary"),
        }
        Path(env["TEMP"]).mkdir(exist_ok=True)
        with self.lock:
            if self.cancelled.is_set():
                raise InterruptedError("Setup cancelled.")
            self._record_setup_line(log, "Running: " + json.dumps(command))
            self.process = subprocess.Popen(
                command,
                cwd=self.root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            process = self.process
        last_package = None
        last_sample_bytes = 0
        last_sample_at = time.monotonic()
        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            timestamp = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
            formatted = f"[{timestamp}] {line}"
            log.write(formatted + "\n")
            log.flush()
            if line.startswith("@@PACTTS_SETUP@@"):
                self.update(**json.loads(line[len("@@PACTTS_SETUP@@") :]))
                continue
            if self.state.get("stage") in {"pytorch", "inference"}:
                package = re.match(r"\s*(?:Downloading|Using cached)\s+(.+)", line)
                if package:
                    last_package = package.group(1)
                    last_sample_bytes = 0
                    last_sample_at = time.monotonic()
                    self.update(
                        dependency_progress={
                            "package": last_package,
                            "message": line.strip(),
                            "phase": "downloading",
                            "timestamp": time.time(),
                        }
                    )
                else:
                    progress = re.match(r"^Progress (\d+) of (\d+)$", line.strip())
                    if progress:
                        current, total = map(int, progress.groups())
                        now = time.monotonic()
                        elapsed = now - last_sample_at
                        speed = max(0, current - last_sample_bytes) / elapsed if elapsed > 0 else 0
                        self.update(
                            dependency_progress={
                                "package": last_package,
                                "message": last_package or "Downloading package",
                                "phase": "downloading",
                                "downloaded_bytes": current,
                                "total_bytes": total,
                                "percent": round(100 * current / total, 1) if total else None,
                                "speed_bytes_per_second": round(speed) if speed else None,
                                "eta_seconds": (
                                    round((total - current) / speed) if total and speed else None
                                ),
                                "timestamp": time.time(),
                            }
                        )
                        last_sample_at = now
                        last_sample_bytes = current
                    elif "Installing collected packages" in line:
                        self.update(
                            dependency_progress={
                                "message": line.strip(),
                                "phase": "installing",
                                "timestamp": time.time(),
                            }
                        )
                    elif "Successfully installed" in line:
                        self.update(
                            dependency_progress={
                                "message": line.strip(),
                                "phase": "complete",
                                "timestamp": time.time(),
                            }
                        )
            with self.lock:
                self.lines.append(formatted)
                self.lines = self.lines[-500:]
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
                log.write("\n")
                self._record_setup_line(log, f"Setup requested: {device}")
                self.update(model_ids=self.state.get("model_ids") or list(self.model_ids))
                # uv venvs omit pip, so install pip once into the private runtime.
                # This is only a dependency-installer bootstrap; the app stays local.
                if importlib.util.find_spec("pip") is None:
                    uv = os.environ.get("PACTTS_SETUP_UV")
                    if uv and Path(uv).is_file():
                        self._run_command(
                            [uv, "pip", "install", "--python", sys.executable, "pip>=25,<27"],
                            log,
                        )
                    else:
                        self._run_command([sys.executable, "-m", "ensurepip", "--upgrade"], log)
                    importlib.invalidate_caches()
                for number, (stage, command) in enumerate(self._commands(device), 1):
                    if self.cancelled.is_set():
                        raise InterruptedError("Setup cancelled.")
                    if stage == "models" and self._models_present():
                        self._record_setup_line(
                            log,
                            "Reusing verified model manifest; files present with matching sizes.",
                        )
                        continue
                    self.update(
                        stage=stage,
                        completed_steps=number - 1,
                        dependency_progress=None,
                        download=None,
                    )
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
                    status="succeeded",
                    stage="ready",
                    completed_steps=5,
                    finished_at=time.time(),
                    initial_setup_completed=True,
                )
                self._apply_models()
        except InterruptedError as exc:
            self.update(
                status="cancelled",
                stage="cancelled",
                error=str(exc),
                finished_at=time.time(),
            )
        except Exception as exc:
            self.update(status="failed", stage="failed", error=str(exc), finished_at=time.time())
        finally:
            with self.service._lock:
                self.service.setup_busy = False
            with self.lock:
                self.process = None
        if self.state["status"] == "succeeded":
            self.on_ready()
