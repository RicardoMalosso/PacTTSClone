"""Verified application-only overlays; activation occurs at the next Python launch."""

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


def select_release(releases, current):
    current = Version(current)
    candidates = []
    for release in releases:
        if release.get("draft"):
            continue
        tag = release.get("tag_name", "")
        if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-rc\.\d+)?", tag):
            continue
        version = Version(tag[1:].replace("-rc.", "rc"))
        if version <= current or (version.is_prerelease and not current.is_prerelease):
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
        candidates.append((version, asset))
    return max(candidates, key=lambda item: item[0], default=None)


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
        self.enabled = bool(os.environ.get("PACTTS_APP_ROOT")) and sys.platform == "win32"
        self.state = {
            "status": "idle" if self.enabled else "source_install",
            "version": __version__,
            "error": None,
            "next_version": None,
        }
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.thread = None

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

    def check(self):
        if not self.enabled or not self.lock.acquire(blocking=False):
            return dict(self.state)
        try:
            if self.state["status"] == "restart_required":
                return dict(self.state)
            self.state.update(status="checking", error=None)
            selected = select_release(json.loads(fetch(API, 4 * 1024 * 1024)), __version__)
            if not selected:
                self.state.update(status="up_to_date")
                return dict(self.state)
            version, asset = selected
            self.state.update(status="downloading", next_version=str(version))
            data = fetch(asset["browser_download_url"], MAX_DOWNLOAD)
            if (
                len(data) != asset["size"]
                or "sha256:" + hashlib.sha256(data).hexdigest() != asset["digest"]
            ):
                raise ValueError("Update checksum mismatch")
            root = Path(os.environ["PACTTS_APP_ROOT"]) / "updates"
            root.mkdir(parents=True, exist_ok=True)
            target = root / str(version)
            staging = root / (str(version) + ".partial")
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir()
            try:
                extract_wheel(data, staging, version)
                env = dict(os.environ, PYTHONPATH=str(staging))
                subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        f"import sys; sys.path.insert(0, {str(staging)!r}); "
                        f"import pacttsclone; assert pacttsclone.__version__ == {str(version)!r}; "
                        "import pacttsclone.app, pacttsclone.cli",
                    ],
                    env=env,
                    cwd=staging,
                    check=True,
                    timeout=60,
                    capture_output=True,
                )
                if target.exists():
                    shutil.rmtree(target)
                staging.rename(target)
                # .pth executes only on the NEXT launch, never in the running server.
                pth = Path(sysconfig.get_path("purelib")) / "pacttsclone_update.pth"
                previous = pth.read_text() if pth.exists() else ""
                (root / "rollback.pth").write_text(previous)
                temporary = pth.with_suffix(".new")
                temporary.write_text(f"import sys; sys.path.insert(0, {str(target)!r})\n")
                temporary.replace(pth)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            self.state.update(status="restart_required")
        except Exception as exc:
            self.state.update(status="failed", error=str(exc))
        finally:
            self.lock.release()
        return dict(self.state)
