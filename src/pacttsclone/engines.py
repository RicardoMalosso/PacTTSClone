"""Host-owned engine catalogue and model lifecycle, sharing Initial Setup downloads."""

import shutil
from pathlib import Path

from .domain import BusyError, UserError


class EngineManager:
    def __init__(self, setup):
        self.setup = setup
        self.service = setup.service
        original_ready = self.service.setup_ready
        self.service.setup_ready = lambda: (
            original_ready() and self.setup.state.get("engine_enabled", True)
        )

    def snapshot(self):
        setup = self.setup.snapshot()
        files = setup.get("models", {}).get("files", [])
        installed = self.setup._models_present()
        enabled = setup.get("engine_enabled", True)
        rows = []
        for key, name in (
            ("omnivoice", "OmniVoice"),
            ("ming-3", "Ming 3.0"),
            ("kittentts2", "KittenTTS2"),
        ):
            supported = key == "omnivoice"
            rows.append(
                {
                    "id": key,
                    "name": name,
                    "supported": supported,
                    "installed": installed if supported else False,
                    "active": bool(installed and enabled) if supported else False,
                    "installed_bytes": sum(f["size"] for f in files) if supported else None,
                    "download_bytes": (setup.get("download") or {}).get("total_bytes")
                    if supported
                    else None,
                    "vram": "Not verified (varies with input and settings)",
                    "features": "Reference voice cloning; multilingual speech; speed, duration, CFG"
                    if supported
                    else "Integration planned; capabilities not verified",
                    "status": setup["status"] if supported else "Planned",
                }
            )
        return {
            "engines": rows,
            "directory": str(self.service.settings.data_dir / "models"),
            "free_bytes": shutil.disk_usage(self.service.settings.data_dir).free,
            "busy": self.service.setup_busy,
            "setup": setup,
        }

    def change(self, engine_id, operation):
        if engine_id != "omnivoice":
            raise UserError("This engine integration is not available yet.")
        if operation == "install":
            return self.setup.start("cuda")
        if operation == "cancel":
            return self.setup.cancel()
        if operation not in {"activate", "deactivate", "uninstall"}:
            raise UserError("Unknown engine operation.")
        with self.service._lock, self.setup.lock:
            if self.service.setup_busy or self.service.pending() or self.service.active_id:
                raise BusyError("Finish or cancel generation/setup before changing engines.")
            if operation == "activate" and not self.setup._models_present():
                raise UserError("Install this engine first.")
            if operation == "uninstall" and self.setup.state.get("engine_enabled", True):
                raise UserError("Deactivate this engine before uninstalling it.")
            self.service.runner.reset()
            if operation == "uninstall":
                root = self.service.settings.data_dir / "models"
                # Validate every path before deleting any file. External imported source
                # files, shared HF caches and personal assets are never removed.
                paths = []
                for entry in self.setup.state.get("models", {}).get("files", []):
                    path = Path(entry["path"])
                    if (
                        not path.is_absolute()
                        or path.is_symlink()
                        or not path.resolve().is_relative_to(root.resolve())
                        or any(p.is_symlink() for p in path.parents)
                    ):
                        raise UserError("Model manifest contains an unsafe path; no files removed.")
                    paths.append(path)
                for path in paths:
                    path.unlink(missing_ok=True)
                self.setup.update(models={}, status="idle", stage="uninstalled")
            self.setup.update(engine_enabled=operation == "activate")
        return self.snapshot()
