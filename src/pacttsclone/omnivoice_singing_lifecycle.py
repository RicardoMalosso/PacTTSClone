"""Optional Singing checkpoint lifecycle, sharing the unchanged OmniVoice runtime."""

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from .domain import UserError
from .engine import dependencies_available
from .ming_lifecycle import MingLifecycle
from .omnivoice_singing_install import MARKER, MODEL_KEY, MODEL_REPO

DOWNLOAD_MARKER = "@@PACTTS_SETUP@@"


class OmniVoiceSingingLifecycle(MingLifecycle):
    profile = "omnivoice_singing"
    engine_id = "omnivoice-singing"
    display_name = "OmniVoice Singing"

    def _receipt(self):
        try:
            return json.loads((self.root / "installation.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}

    def assets(self):
        # EngineManager only uses the model's pinned revision on startup.
        return ({}, {"revision": self._receipt().get("revision", "")})

    def installed(self):
        receipt = self._receipt()
        model = self.root / "model"
        files = receipt.get("files")
        if (
            receipt.get("repo") != MODEL_REPO
            or not re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("revision", "")))
            or not isinstance(files, list)
            or not files
            or model.is_symlink()
            or not model.is_dir()
        ):
            return False
        if not {"config.json"}.issubset({f.get("name") for f in files if isinstance(f, dict)}):
            return False
        if not any(
            isinstance(f, dict) and str(f.get("name", "")).endswith(".safetensors")
            for f in files
        ):
            return False
        for entry in files:
            if not isinstance(entry, dict):
                return False
            name, size = entry.get("name"), entry.get("size")
            if not isinstance(name, str) or not isinstance(size, int) or size < 0:
                return False
            path = Path(name)
            if (
                not name
                or path.is_absolute()
                or ".." in path.parts
                or ":" in name
                or "\\" in name
                or any((model / part).is_symlink() for part in [path, *list(path.parents)[:-1]])
            ):
                return False
            target = model / path
            if not target.is_file() or target.is_symlink() or target.stat().st_size != size:
                return False
        return True

    def start(self):
        # Only weights are installed; never repair/reinstall PyTorch or OmniVoice here.
        if not dependencies_available() or not self.setup._models_present():
            raise UserError("Complete the original OmniVoice Initial Setup first.")
        if self.installed():
            self.update(status="succeeded", stage="installed", error=None)
            return dict(self.state)
        return super().start()

    def _install(self):
        log = self.service.logs / f"{self.profile}-install.log"
        try:
            with log.open("a", encoding="utf-8") as output:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-u",
                        "-m",
                        "pacttsclone.omnivoice_singing_install",
                        "--root",
                        str(self.root),
                        "--hf-cache",
                        os.environ.get(
                            "HF_HUB_CACHE", str(Path.home() / ".cache/huggingface/hub")
                        ),
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
                    if line.startswith(DOWNLOAD_MARKER):
                        status = json.loads(line[len(DOWNLOAD_MARKER) :])
                        download = status.get("download")
                        if download:
                            self.update(
                                stage=download.get("phase", "downloading"),
                                completed_bytes=download.get("completed_bytes", 0),
                                total_bytes=download.get("total_bytes"),
                            )
                    elif line.startswith(MARKER):
                        self.update(**json.loads(line[len(MARKER) :]))
                code = process.wait()
                process.stdout.close()
                if self.cancelled.is_set():
                    self.update(status="cancelled", stage="cancelled")
                elif code or not self.installed():
                    self.update(
                        status="failed",
                        error=f"Singing model installation failed. See {log.name}.",
                    )
                else:
                    self.update(status="succeeded", stage="installed", error=None)
        except Exception as exc:
            self.update(status="failed", error=str(exc)[:1000])
        finally:
            self.process = None
            with self.service._lock:
                self.service.setup_busy = False

    def activate(self):
        with self.service._lock:
            self._idle()
            if not self.installed():
                raise UserError("Install and verify OmniVoice Singing before activation.")
            if not dependencies_available():
                raise UserError("The shared OmniVoice inference runtime is unavailable.")
            self.service.runner.reset()
            self.service.settings = self.service.runner.settings = replace(
                self.service.settings,
                engine_id=self.engine_id,
                model=str(self.root / "model"),
                model_revision=self._receipt()["revision"],
                offline=True,
            )
            self.setup.update(active_engine=self.engine_id, engine_enabled=True)
        return dict(self.state)

    def row(self):
        receipt = self._receipt()
        installed = self.installed()
        plan_file = self.root / "download" / f"{MODEL_KEY}.json"
        try:
            plan = json.loads(plan_file.read_text(encoding="utf-8"))
            download_bytes = sum(f["size"] for f in plan["files"])
        except (OSError, ValueError, TypeError, KeyError):
            download_bytes = receipt.get("installed_bytes")
        return {
            "id": self.engine_id,
            "directory": str(self.root),
            "name": "OmniVoice · Singing + Emotion",
            "supported": True,
            "installed": installed,
            "active": installed
            and self.setup.state.get("active_engine") == self.engine_id
            and self.setup.state.get("engine_enabled", True),
            "installed_bytes": receipt.get("installed_bytes", 0) if installed else 0,
            "download_bytes": download_bytes,
            "runtime_reserve_bytes": None,
            "models": ([{"repo": MODEL_REPO, "revision": receipt["revision"]}]
                       if receipt.get("revision") else []),
            "license": "Apache-2.0 model card; training datasets include noncommercial restrictions",
            "runtime": "Uses the existing OmniVoice/PyTorch CUDA runtime; no new dependencies",
            "ram": "Not verified",
            "languages": "Multilingual; non-English singing quality varies (publisher claim)",
            "source": "https://huggingface.co/ModelsLab/omnivoice-singing",
            "capabilities": {
                "Voice cloning": "Upstream API compatible (publisher claim)",
                "Style / emotion": "[happy] [sad] [angry] [nervous] [whisper] [calm] [excited]",
                "Vocal tags": "Use tags directly in the text; no forced tag insertion",
                "Streaming": "Not exposed",
                "Voice conversion": "Not exposed",
                "Singing": "[singing] (melodic voice, not musical accompaniment)",
            },
            "vram": "6 GB compatibility unverified; one model resident at a time",
            "features": "Optional Singing/Emotion checkpoint; shared cloned voices and generation settings",
            "status": self.state.get("status", "idle"),
            "installation": dict(self.state),
        }
