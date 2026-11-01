"""Verified application-only overlays; activation occurs at the next Python launch."""

import ast
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from packaging.requirements import Requirement
from packaging.version import Version

from . import __version__

REPOSITORY = "RicardoMalosso/PacTTSClone"
API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100"
PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
MAX_DOWNLOAD = 128 * 1024 * 1024


def fetch(url, limit):
    with urlopen(
        Request(url, headers={"User-Agent": "PacTTSClone-updater"}), timeout=30
    ) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Update download exceeds its size limit")
    return data


CONTROL_VERSION = 1
ACTIVE_INSTANCE = None


def release_catalog(releases, include_experimental=True):
    candidates = []
    for release in releases:
        if release.get("draft") or "<!-- pactts-update-bridge -->" in release.get("body", ""):
            continue
        tag = release.get("tag_name", "")
        if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tag):
            continue
        version = Version(tag[1:].replace("-rc.", "rc"))
        experimental = version.is_prerelease or bool(release.get("prerelease"))
        if version < Version("2.1.0") or (experimental and not include_experimental):
            continue
        name = f"pacttsclone-{version}-py3-none-any.whl"
        assets = [a for a in release.get("assets", []) if a.get("name") == name]
        if len(assets) != 1:
            continue
        asset = assets[0]
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", asset.get("digest") or ""):
            continue
        if asset.get("browser_download_url") != f"{PREFIX}{tag}/{name}":
            continue
        if not 0 < asset.get("size", 0) <= MAX_DOWNLOAD:
            continue
        published = release.get("published_at") or ""
        try:
            timestamp = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
        except ValueError:
            timestamp = 0
        candidates.append(dict(tag=tag, version=str(version), experimental=experimental,
                               published_at=published, timestamp=timestamp, asset=asset))
    return sorted(candidates, key=lambda row: (row["timestamp"], Version(row["version"])),
                  reverse=True)


def select_release(releases, current, include_experimental=True, target="latest"):
    rows = release_catalog(releases, include_experimental)
    row = next((r for r in rows if target == "latest" or r["tag"] == target), None)
    if row is None or Version(row["version"]) == Version(current):
        return None
    return Version(row["version"]), row["asset"]


def extract_wheel(data, destination, version):
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        total = 0
        metadata = []
        for member in archive.infolist():
            path = Path(member.filename)
            total += member.file_size
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or ":" in member.filename
                or total > 256 * 1024 * 1024
            ):
                raise ValueError("Unsafe update archive")
            if path.parts[0] not in {"pacttsclone", f"pacttsclone-{version}.dist-info"}:
                raise ValueError("Unexpected wheel contents")
            if member.filename.endswith(".dist-info/METADATA"):
                metadata.append(archive.read(member).decode())
        if len(metadata) != 1:
            raise ValueError("Missing update metadata")
        from email.parser import Parser

        info = Parser().parsestr(metadata[0])
        if info["Name"] != "pacttsclone" or Version(info["Version"]) != version:
            raise ValueError("Update identity mismatch")
        for value in info.get_all("Requires-Dist", []):
            requirement = Requirement(value)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            installed = importlib.metadata.version(requirement.name)
            if installed not in requirement.specifier:
                raise ValueError(f"Update needs dependency repair: {requirement.name}")
        archive.extractall(destination)
    if not (destination / "pacttsclone" / "cli.py").is_file():
        raise ValueError("Missing application entry point")


class Updater:
    def __init__(self):
        global ACTIVE_INSTANCE
        ACTIVE_INSTANCE = self
        self.enabled = (bool(os.environ.get("PACTTS_APP_ROOT")) and sys.platform == "win32"
                        and os.environ.get("PACTTS_DISABLE_UPDATES") != "1")
        self.root = Path(os.environ.get("PACTTS_APP_ROOT", ".")) / "updates"
        self.preferences = {"include_experimental": True, "target": "latest"}
        try:
            prefs = json.loads((self.root / "preferences.json").read_text())
            self._validate(prefs)
            self.preferences.update(prefs)
        except (OSError, ValueError, TypeError):
            pass
        self.catalog = []
        self.state = {"status": "idle" if self.enabled else "source_install",
                      "version": __version__, "error": None, "next_version": None}
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = None

    @staticmethod
    def _validate(prefs):
        if (set(prefs) != {"include_experimental", "target"}
                or type(prefs["include_experimental"]) is not bool
                or not isinstance(prefs["target"], str)
                or not re.fullmatch(r"latest|v\d+\.\d+\.\d+(?:-rc\.\d+)?", prefs["target"])):
            raise ValueError("Invalid update selection")
        if not prefs["include_experimental"] and "-rc." in prefs["target"]:
            raise ValueError("Enable experimental builds before selecting an RC")

    def snapshot(self):
        return {**self.state, **self.preferences, "enabled": self.enabled,
                "releases": [{k: v for k, v in row.items() if k not in {"asset", "timestamp"}}
                             for row in self.catalog]}

    def set_preferences(self, prefs):
        self._validate(prefs)
        if not self.enabled:
            raise ValueError("Source installations update through Git")
        with self.lock:
            self.root.mkdir(parents=True, exist_ok=True)
            temp = self.root / "preferences.new"
            temp.write_text(json.dumps(prefs))
            temp.replace(self.root / "preferences.json")
            self.preferences = dict(prefs)

    def start(self):
        if self.enabled:
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()

    def close(self):
        self.stop.set()

    def run(self):
        while not self.stop.is_set():
            self.check()
            self.stop.wait(6 * 60 * 60)

    def _controller(self, staging=None):
        source = Path(__file__).parent
        if staging:
            candidate = staging / "pacttsclone"
            try:
                tree = ast.parse((candidate / "updater.py").read_text())
                revision = next(ast.literal_eval(n.value) for n in tree.body
                                if isinstance(n, ast.Assign) and any(
                                    isinstance(t, ast.Name) and t.id == "CONTROL_VERSION"
                                    for t in n.targets))
                if revision > CONTROL_VERSION:
                    source = candidate
            except (OSError, ValueError, StopIteration, SyntaxError):
                pass
        names = ["updater.py", "update_bridge.py", "static/update_panel.js"]
        payload = {name: (source / name).read_bytes() for name in names}
        identity = hashlib.sha256(b"".join(payload.values())).hexdigest()
        controller = self.root / "controllers" / identity
        payload["pacttsclone_update_bootstrap.py"] = payload["update_bridge.py"]
        for name, data in payload.items():
            path = controller / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_bytes() != data:
                temp = path.with_suffix(".new")
                temp.write_bytes(data)
                temp.replace(path)
        return controller

    def _activate(self, target, controller):
        import pacttsclone

        pth = Path(sysconfig.get_path("purelib")) / "pacttsclone_update.pth"
        running = Path(pacttsclone.__file__).parent.parent
        bootstrap = (f"sys.path.insert(0, {str(controller)!r}); "
                     "import pacttsclone_update_bootstrap; pacttsclone_update_bootstrap.install()")
        (self.root / "rollback.pth").write_text(
            f"import sys; sys.path.insert(0, {str(running)!r}); {bootstrap}\n")
        temp = pth.with_suffix(".new")
        temp.write_text(f"import sys; sys.path.insert(0, {str(target)!r}); {bootstrap}\n")
        temp.replace(pth)

    def check(self):
        if not self.enabled or not self.lock.acquire(blocking=False):
            return dict(self.state)
        previous = self.state["next_version"]
        try:
            self.state.update(status="checking", error=None)
            raw = json.loads(fetch(API, 4 * 1024 * 1024))
            self.catalog = release_catalog(raw)
            eligible = release_catalog(raw, self.preferences["include_experimental"])
            target_tag = self.preferences["target"]
            row = next((r for r in eligible
                        if target_tag == "latest" or r["tag"] == target_tag), None)
            if row is None:
                if target_tag != "latest":
                    raise ValueError("Selected release is unavailable or excluded by the channel")
                self.state.update(status="up_to_date")
                return dict(self.state)
            version, asset = Version(row["version"]), row["asset"]
            if version == Version(__version__):
                if previous:
                    import pacttsclone
                    self._activate(Path(pacttsclone.__file__).parent.parent, self._controller())
                self.state.update(status="up_to_date", next_version=None)
                return dict(self.state)
            if str(version) == previous:
                self.state.update(status="restart_required")
                return dict(self.state)
            self.state.update(status="downloading", next_version=str(version))
            data = fetch(asset["browser_download_url"], MAX_DOWNLOAD)
            if (len(data) != asset["size"]
                    or "sha256:" + hashlib.sha256(data).hexdigest() != asset["digest"]):
                raise ValueError("Update checksum mismatch")
            self.root.mkdir(parents=True, exist_ok=True)
            target = self.root / str(version)
            staging = self.root / (str(version) + ".partial")
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir()
            try:
                extract_wheel(data, staging, version)
                clean = ("import sys; sys.meta_path[:] = [f for f in sys.meta_path "
                         "if type(f).__name__ != 'ControllerFinder']; "
                         "sys.modules.pop('pacttsclone_update_bootstrap', None); ")
                probe = (clean + f"sys.path.insert(0, {str(staging)!r}); "
                         f"import pacttsclone; assert pacttsclone.__version__ == {str(version)!r}; "
                         "import pacttsclone.app, pacttsclone.cli")
                subprocess.run([sys.executable, "-c", probe], cwd=staging,
                               check=True, timeout=60, capture_output=True)
                controller = self._controller(staging)
                probe = (clean + f"sys.path.insert(0, {str(staging)!r}); "
                         f"sys.path.insert(0, {str(controller)!r}); "
                         "import pacttsclone_update_bootstrap as b; b.install(); "
                         "from tempfile import TemporaryDirectory; "
                         "from pathlib import Path; "
                         "import pacttsclone.voices as v; v.BUILTIN_CATALOG=None; "
                         "from pacttsclone.app import create_app; "
                         "from pacttsclone.config import Settings; "
                         f"d=TemporaryDirectory(dir={str(self.root)!r}); "
                         "a=create_app(Settings(data_dir=Path(d.name))); "
                         "assert any(r.path == '/api/updates/manager' for r in a.routes); "
                         "d.cleanup()")
                subprocess.run([sys.executable, "-c", probe], cwd=staging,
                               check=True, timeout=60, capture_output=True)
                if target.exists():
                    shutil.rmtree(target)
                staging.rename(target)
                self._activate(target, controller)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            self.state.update(status="restart_required")
        except Exception as exc:
            self.state.update(status="failed", error=str(exc), next_version=previous)
        finally:
            self.lock.release()
        return dict(self.state)


def attach_manager(app, updater):
    if getattr(app.state, "update_manager_attached", False):
        return
    from fastapi import HTTPException, Request
    from fastapi.responses import FileResponse

    app.state.update_manager_attached = True
    app.state.updater = updater

    def owner(request):
        if request.state.remote_access:
            raise HTTPException(403, "Updates are host-only")

    @app.get("/api/updates/manager")
    def manager(request: Request):
        owner(request)
        return updater.snapshot()

    @app.get("/api/updates/panel.js")
    def panel(request: Request):
        owner(request)
        return FileResponse(Path(__file__).parent / "static/update_panel.js",
                            media_type="text/javascript", headers={"Cache-Control": "no-store"})

    @app.post("/api/updates/select")
    def select(request: Request, value: dict):
        owner(request)
        try:
            updater.set_preferences(value)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        updater.check()
        return updater.snapshot()

    app.add_middleware(UpdatePanelInjection)


class UpdatePanelInjection:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] != "http" or scope["path"] != "/" or scope["method"] != "GET"
                or dict(scope.get("headers", [])).get(b"host", b"").split(b":")[0]
                not in {b"localhost", b"127.0.0.1", b"["}):
            return await self.app(scope, receive, send)
        start, chunks = None, []

        async def intercept(message):
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if not message.get("more_body"):
                    body = b"".join(chunks)
                    if start["status"] == 200:
                        body = body.replace(b"</body>",
                                            b'<script src="/api/updates/panel.js"></script></body>')
                    start["headers"] = [(k, v) for k, v in start["headers"]
                                        if k.lower() not in {b"content-length", b"etag"}]
                    start["headers"].append((b"content-length", str(len(body)).encode()))
                    await send(start)
                    await send({"type": "http.response.body", "body": body})
            else:
                await send(message)
        await self.app(scope, receive, intercept)
