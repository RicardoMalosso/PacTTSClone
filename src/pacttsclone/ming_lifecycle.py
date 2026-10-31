"""Ming lifecycle coordinated with the application's serialized generation queue."""

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import psutil

from .domain import BusyError, UserError
from .ming_install import MARKER, RUNTIME_RESERVE, manifests, python_path, receipt_valid


class MingLifecycle:
    profile = "ming"
    engine_id = "ming-3"
    display_name = "Ming"
    worker_file = "ming_runtime_worker.py"
    response_marker = "@@PACTTS_MING@@"

    def assets(self):
        return manifests() if self.profile == "ming" else manifests(self.profile)

    def installed(self):
        return (
            receipt_valid(self.root)
            if self.profile == "ming"
            else receipt_valid(self.root, self.profile)
        )

    def __init__(self, setup):
        self.setup = setup
        self.service = setup.service
        self.root = self.service.settings.data_dir / "engines" / self.engine_id
        self.process = None
        self.thread = None
        self.cancelled = threading.Event()
        self.state = dict(setup.state.get(self.profile, {}))
        if self.state.get("status") == "running":
            self.update(
                status="cancelled",
                error=f"{self.display_name} installation was interrupted. Retry to resume.",
            )
        setattr(self.service, f"{self.profile}_installed", self.installed)

    def update(self, **values):
        self.state.update(values)
        self.setup.update(**{self.profile: dict(self.state)})

    def _idle(self):
        if self.service.setup_busy or self.service.pending() or self.service.active_id:
            raise BusyError("Finish or cancel generation/setup before changing engines.")

    def start(self):
        with self.service._lock:
            self._idle()
            self.service.setup_busy = True
            self.cancelled.clear()
            self.update(status="running", stage="prepare", error=None)
            self.thread = threading.Thread(
                target=self._install, daemon=True, name=f"{self.profile}-install"
            )
            self.thread.start()
        return dict(self.state)

    def _install(self):
        log = self.service.logs / f"{self.profile}-install.log"
        try:
            with log.open("a", encoding="utf-8") as output:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-u",
                        "-m",
                        "pacttsclone.ming_install",
                        "--profile",
                        self.profile,
                        "--root",
                        str(self.root),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    start_new_session=os.name == "posix",
                )
                self.process = process
                if self.cancelled.is_set():
                    self._kill()
                for line in process.stdout:
                    output.write(line)
                    output.flush()
                    if line.startswith(MARKER):
                        self.update(**json.loads(line[len(MARKER) :]))
                code = process.wait()
                process.stdout.close()
                if self.cancelled.is_set():
                    self.update(status="cancelled", stage="cancelled")
                elif code or not self.installed():
                    self.update(
                        status="failed",
                        error=self.state.get("error")
                        or f"{self.display_name} installation failed. See its installation log.",
                    )
                else:
                    self.update(status="succeeded", stage="installed", error=None)
        except Exception as exc:
            self.update(status="failed", error=str(exc)[:1000])
        finally:
            self.process = None
            with self.service._lock:
                self.service.setup_busy = False

    def _kill(self):
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                for child in psutil.Process(process.pid).children(recursive=True):
                    try:
                        child.kill()
                    except psutil.Error:
                        pass
                process.kill()
            except (psutil.Error, OSError):
                pass
            if process.poll() is None:
                process.kill()

    def cancel(self):
        self.cancelled.set()
        self._kill()
        return dict(self.state)

    def close(self):
        self.cancel()
        if self.thread:
            self.thread.join(timeout=10)

    def activate(self):
        with self.service._lock:
            self._idle()
            if not self.installed():
                raise UserError(f"Install and verify {self.display_name} before activation.")
            command = [
                str(python_path(self.root)),
                "-u",
                str(Path(__file__).with_name(self.worker_file)),
                "--source",
                str(self.root / "source"),
                "--model",
                str(self.root / "model"),
                "--preflight",
            ]
            env = {
                **os.environ,
                "PYTHONNOUSERSITE": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
            }
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise UserError(
                    f"{self.display_name} activation preflight failed; previous engine retained."
                ) from exc
            response_marker = self.response_marker

            messages = [
                json.loads(line[len(response_marker) :])
                for line in result.stdout.splitlines()
                if line.startswith(response_marker)
            ]
            if result.returncode or not messages or not messages[-1].get("ok"):
                raise UserError(
                    messages[-1].get("error", f"{self.display_name} preflight failed.")
                    if messages
                    else f"{self.display_name} preflight failed; check the isolated runtime."
                )
            self.service.runner.reset()
            settings = replace(
                self.service.settings,
                engine_id=self.engine_id,
                model_revision=self.assets()[1]["revision"],
                model=str(self.root / "model"),
                offline=True,
            )
            self.service.settings = self.service.runner.settings = settings
            self.setup.update(active_engine=self.engine_id, engine_enabled=True)
        return dict(self.state)

    def uninstall(self):
        with self.service._lock:
            self._idle()
            if self.setup.state.get("active_engine") == self.engine_id and self.setup.state.get(
                "engine_enabled", True
            ):
                raise UserError(f"Deactivate {self.display_name} before uninstalling it.")
            # Only this dedicated owned directory is removed. Never follow a replaced
            # directory/symlink into shared caches or user assets.
            if any(p.is_symlink() for p in [self.root, *self.root.parents]):
                raise UserError(
                    f"Unsafe {self.display_name} installation directory; no files removed."
                )
            if self.root.exists():
                shutil.rmtree(self.root)
            self.update(status="idle", stage="uninstalled", error=None)
        return dict(self.state)

    def row(self):
        source, model = self.assets()
        installed = self.installed()
        total = sum(e["size"] for m in (source, model) for e in m["files"])
        try:
            installed_bytes = json.loads((self.root / "installation.json").read_text()).get(
                "installed_bytes", total
            )
        except (OSError, ValueError, TypeError):
            installed_bytes = total
        return {
            "id": self.engine_id,
            "name": "Ming 3.0 · 0.5B dense",
            "supported": True,
            "installed": installed,
            "active": installed
            and self.setup.state.get("active_engine") == self.engine_id
            and self.setup.state.get("engine_enabled", True),
            "installed_bytes": installed_bytes if installed else 0,
            "download_bytes": total,
            "runtime_reserve_bytes": RUNTIME_RESERVE,
            "models": [{"repo": model["repo"], "revision": model["revision"]}],
            "license": "MIT",
            "runtime": "Private Python 3.12; CUDA 12.4; native BF16 GPU (Ampere+)",
            "ram": "Not verified",
            "languages": (
                "English, Chinese, German, Spanish, French, Korean, Japanese; no Portuguese"
            ),
            "source": "https://github.com/inclusionAI/Ming-3.0-tts",
            "capabilities": {
                "Voice cloning": "Supported",
                "Vocal tags": "14 upstream tags",
                "Style / emotion": "Separate emotion, attributes, freeform and voice design tasks",
                "Streaming": "Not exposed",
                "Voice conversion": "Not exposed",
                "Singing": "Not verified",
            },
            "vram": "Native BF16 CUDA GPU required; minimum VRAM not verified",
            "features": "Reference cloning; inline vocal tags; isolated runtime",
            "status": self.state.get("status", "idle"),
            "installation": dict(self.state),
        }
