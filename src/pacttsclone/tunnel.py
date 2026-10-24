"""Opt-in Cloudflare Quick Tunnel, with distinct admin and channel player capabilities."""

import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import threading
import urllib.request
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from .domain import UserError

TUNNEL_HOST = "pacttsclone-tunnel.internal"


class Tunnel:
    def __init__(self, service):
        self.service = service
        self.lock = threading.RLock()
        self.process = None
        self.thread = None
        self.stop_event = threading.Event()
        self.admin_key = None
        self.player_keys = {}
        self.url = None
        self.status = "stopped"
        self.error = None
        self.downloaded = 0
        self.total = None
        self.version = None

    def public_host(self):
        with self.lock:
            return urlsplit(self.url).netloc if self.url else None

    def capability(self, key):
        with self.lock:
            if (
                not self.url
                or self.status != "running"
                or not isinstance(key, str)
                or len(key) > 256
            ):
                return None
            if self.admin_key and secrets.compare_digest(key.encode(), self.admin_key.encode()):
                return ("admin", None)
            for channel, value in self.player_keys.items():
                if secrets.compare_digest(key.encode(), value.encode()):
                    return ("player", channel)
        return None

    def request_capability(self, cookie):
        values = SimpleCookie()
        try:
            values.load(cookie)
        except Exception:
            return None
        for name in ["pactts_admin", *[k for k in values if k.startswith("pactts_play_")]]:
            if name in values:
                cap = self.capability(values[name].value)
                if cap:
                    return cap
        return None

    def permitted(self, capability, path, method):
        if not capability:
            return False
        if path.startswith("/api/tunnel"):
            return False  # Tunnel lifecycle stays local, even for shared admins.
        if capability[0] == "admin":
            return True
        channel = capability[1]
        if method == "GET" and path == "/api/session":
            return True
        if method == "POST" and path in {
            f"/api/channels/{channel}/player/tick",
            f"/api/channels/{channel}/player/ack",
        }:
            return True
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/audio", path)
        if method in {"GET", "HEAD"} and match:
            job = self.service.get(match[1])
            assigned = job and job.get("channel") == channel
            if channel == "playbackMain":
                assigned = any(
                    item["job_id"] == match[1]
                    for item in self.service.store.channel_records("playback", channel)
                )
            return bool(job and assigned and job["status"] == "succeeded")
        return False

    def snapshot(self):
        with self.lock:
            channels = self.service.store.all("channel")
            if self.status == "running":
                for c in channels:
                    self.player_keys.setdefault(c["name"], secrets.token_urlsafe(32))
            return {
                "status": self.status,
                "error": self.error,
                "url": self.url,
                "downloaded_bytes": self.downloaded,
                "total_bytes": self.total,
                "binary_version": self.version,
                "admin_url": f"{self.url}/#admin={self.admin_key}" if self.url else None,
                "players": {
                    c["name"]: f"{self.url}/{c['name']}#play={self.player_keys[c['name']]}"
                    for c in channels
                    if self.url and c["name"] in self.player_keys
                },
            }

    def _binary(self):
        command = shutil.which("cloudflared")
        if command:
            return command
        machine = platform.machine().lower()
        arch = (
            "amd64"
            if machine in {"amd64", "x86_64"}
            else "arm64"
            if machine in {"arm64", "aarch64"}
            else None
        )
        system = "windows" if os.name == "nt" else platform.system().lower()
        if not arch or system not in {"windows", "linux"}:
            raise UserError("Install cloudflared manually on this platform and add it to PATH.")
        asset_name = f"cloudflared-{system}-{arch}" + (".exe" if system == "windows" else "")
        folder = self.service.settings.data_dir / "tools"
        folder.mkdir(exist_ok=True)
        target = folder / ("cloudflared.exe" if os.name == "nt" else "cloudflared")
        if target.is_file():
            return str(target)
        self.status = "downloading"
        request = urllib.request.Request(
            "https://api.github.com/repos/cloudflare/cloudflared/releases/latest",
            headers={"User-Agent": "PacTTSClone", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            release = json.load(response)
        asset = next((a for a in release["assets"] if a["name"] == asset_name), None)
        if not asset:
            raise UserError("No supported cloudflared download was found. Install it manually.")
        expected = asset.get("digest", "")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", expected):
            raise UserError(
                "Release has no SHA-256 digest. Install cloudflared manually via winget."
            )
        url = asset["browser_download_url"]
        if not url.startswith("https://github.com/cloudflare/cloudflared/releases/download/"):
            raise UserError("Unexpected cloudflared asset URL.")
        partial = target.with_suffix(".download")
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(url, timeout=20) as response, partial.open("wb") as output:
                length = response.headers.get("Content-Length")
                self.total = int(length) if length else asset.get("size")
                while chunk := response.read(256 * 1024):
                    if self.stop_event.is_set():
                        raise UserError("Tunnel startup cancelled.")
                    output.write(chunk)
                    digest.update(chunk)
                    self.downloaded += len(chunk)
            if digest.hexdigest() != expected.split(":", 1)[1]:
                raise UserError("cloudflared checksum did not match. Download discarded.")
            partial.chmod(0o700)
            partial.replace(target)
            self.version = release["tag_name"]
            return str(target)
        finally:
            partial.unlink(missing_ok=True)

    def start(self, port):
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise UserError("Invalid local port.")
        with self.lock:
            if self.thread and self.thread.is_alive():
                return self.snapshot()
            self.stop_event = threading.Event()
            self.admin_key = secrets.token_urlsafe(32)
            self.player_keys = {}
            self.status, self.error, self.url = "starting", None, None
            self.downloaded, self.total = 0, None
            self.thread = threading.Thread(target=self._run, args=(port,), daemon=True)
            self.thread.start()
            return self.snapshot()

    def _run(self, port):
        try:
            binary = self._binary()
            if self.stop_event.is_set():
                return
            self.status = "starting"
            # A forced non-loopback Host prevents proxy traffic from gaining local-owner access.
            args = [
                binary,
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{port}",
                "--http-host-header",
                TUNNEL_HOST,
                "--protocol",
                "http2",
            ]
            self.process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            tail = []
            for line in self.process.stdout:
                if self.stop_event.is_set():
                    break
                match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com\b", line)
                if match:
                    with self.lock:
                        self.url, self.status = match[0], "running"
                # Keep error context in memory only; never log capability URLs/secrets.
                tail = (tail + [line.strip()])[-8:]
            code = self.process.wait()
            if code and not self.stop_event.is_set():
                raise UserError("cloudflared exited. " + " ".join(tail)[-1000:])
        except Exception as exc:
            if not self.stop_event.is_set():
                self.error = str(exc)[:1200]
                self.status = "failed"
        finally:
            with self.lock:
                self.url = None
                self.admin_key = None
                self.player_keys = {}
                if self.stop_event.is_set():
                    self.status = "stopped"

    def close(self):
        self.stop_event.set()
        with self.lock:
            self.url, self.admin_key, self.player_keys = None, None, {}
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(3)
        self.status = "stopped"
