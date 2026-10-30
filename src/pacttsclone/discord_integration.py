"""Output-only Discord webhooks. No Gateway client or incoming commands."""

import http.client
import json
import queue
import threading
import uuid
from urllib.parse import urlsplit

from .discord_credentials import DiscordWebhookCredential
from .domain import UserError
from .models import DiscordConfig

MAX_FILE = 10 * 1024 * 1024


def send_webhook(url, path=None):
    boundary = "pactts" + uuid.uuid4().hex
    payload = json.dumps(
        {
            "content": "PacTTSClone audio" if path else "PacTTSClone webhook connected.",
            "allowed_mentions": {"parse": []},
        }
    )
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="payload_json"'
        f"\r\nContent-Type: application/json\r\n\r\n{payload}\r\n"
    ).encode()
    if path:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_FILE:
            raise UserError(
                "Discord upload requires an MP3 smaller than 10 MiB. Audio stays in History."
            )
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="files[0]"; '
            'filename="speech.mp3"\r\nContent-Type: audio/mpeg\r\n\r\n'
        ).encode()
        body += path.read_bytes() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    # Fixed host, no redirects, and no URL-bearing exception/log messages.
    connection = http.client.HTTPSConnection("discord.com", timeout=20)
    try:
        connection.request(
            "POST",
            urlsplit(url).path + "?wait=true",
            body,
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "PacTTSClone/2",
            },
        )
        response = connection.getresponse()
        response.read(65536)
        if response.status == 429:
            raise UserError(
                "Discord rate limit reached. Audio stays in History; no automatic retry."
            )
        if response.status in {401, 403, 404}:
            raise UserError("Discord rejected the webhook. Check its URL and channel permissions.")
        if not 200 <= response.status < 300:
            raise UserError("Discord upload failed. Audio stays in History; check the connection.")
    except UserError:
        raise
    except Exception:
        raise UserError(
            "Discord connection failed. Check the connection and webhook URL."
        ) from None
    finally:
        connection.close()


class DiscordIntegration:
    def __init__(self, service, voices):
        self.service, self.store = service, service.store
        # Old bot credentials/config are not compatible and never automatically enabled.
        old = service.settings.data_dir / "credentials" / "discord.json"
        old.unlink(missing_ok=True)
        self.store.delete("discord", "config")
        self.config = DiscordConfig.model_validate(
            self.store.get("discord_webhook", "config") or {}
        )
        self.credential = DiscordWebhookCredential(service.settings.data_dir)
        self.sender = send_webhook
        self.lock = threading.RLock()
        self.queue = queue.Queue(50)
        self.stopping = threading.Event()
        self.thread = None
        self.revision = 0
        self.status, self.error = "idle", None
        for item in self.store.all("discord_delivery", 100000):
            if item["status"] in {"queued", "sending"}:
                self.store.patch("discord_delivery", item["id"], status="interrupted")

    def snapshot(self):
        with self.lock:
            return {
                **self.config.model_dump(),
                "webhook_saved": bool(self.credential.token),
                "status": self.status,
                "error": self.error or self.credential.error,
            }

    def configure(self, config):
        with self.lock:
            if config.enabled and not self.credential.token:
                raise UserError("Save a Discord webhook URL before enabling.")
            self.revision += 1
            self.config = config
            self.store.put("discord_webhook", "config", config.model_dump())
            self.status, self.error = "enabled" if config.enabled else "disabled", None
            return self.snapshot()

    def save_webhook(self, url):
        with self.lock:
            self.credential.save(url)
            self.revision += 1
            return self.snapshot()

    def forget_webhook(self):
        with self.lock:
            self.credential.forget()
            self.configure(self.config.model_copy(update={"enabled": False}))
            return self.snapshot()

    def test(self):
        with self.lock:
            url = self.credential.token
        if not url:
            raise UserError("Save a Discord webhook URL first.")
        try:
            self.sender(url)
        except UserError as exc:
            with self.lock:
                self.status, self.error = "failed", str(exc)
            raise
        with self.lock:
            self.status, self.error = "test_sent", None
        return self.snapshot()

    def start(self):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return
            self.stopping.clear()
            self.thread = threading.Thread(target=self._run, daemon=True, name="discord-webhook")
            self.thread.start()

    def enqueue(self, job):
        with self.lock:
            config = self.config
            if (
                not config.enabled
                or not self.credential.token
                or job.get("kind") != "speech"
                or job.get("status") != "succeeded"
            ):
                return
            channel = job.get("channel")
            if channel:
                if not config.include_twitch or (
                    config.channels and channel not in config.channels
                ):
                    return
            elif not config.include_local:
                return
            if config.voice_ids and job.get("voice_id") not in config.voice_ids:
                return
            if self.store.get("discord_delivery", job["id"]):
                return
            entry = {"id": job["id"], "status": "queued"}
            self.store.put("discord_delivery", job["id"], entry)
            try:
                self.queue.put_nowait((job["id"], self.revision))
            except queue.Full:
                self.store.patch("discord_delivery", job["id"], status="failed", error="Queue full")
                self.status, self.error = (
                    "failed",
                    "Discord delivery queue full. Audio stays in History.",
                )

    def _run(self):
        while not self.stopping.is_set():
            try:
                job_id, revision = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            with self.lock:
                if self.stopping.is_set():
                    return
                if revision != self.revision or not self.config.enabled:
                    self.store.patch("discord_delivery", job_id, status="cancelled")
                    continue
                url = self.credential.token
                self.status, self.error = "sending", None
                self.store.patch("discord_delivery", job_id, status="sending")
            try:
                self.sender(url, self.service.output_path(job_id))
                with self.lock:
                    if self.stopping.is_set():
                        return
                    self.store.patch("discord_delivery", job_id, status="sent")
                    self.status, self.error = "sent", None
            except Exception as exc:
                error = str(exc) if isinstance(exc, UserError) else "Discord upload failed."
                with self.lock:
                    if self.stopping.is_set():
                        return
                    self.store.patch("discord_delivery", job_id, status="failed", error=error)
                    self.status, self.error = "failed", error

    def stop(self):
        self.stopping.set()
        if self.thread:
            self.thread.join(25)
