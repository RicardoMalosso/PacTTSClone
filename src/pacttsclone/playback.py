import threading
import time
import uuid

from .domain import UserError
from .moderation import blocked_reason

PENDING = {"queued", "countdown", "ready", "playing"}


class Playback:
    def __init__(self, service, clock=time.time):
        self.service, self.store, self.clock = service, service.store, clock
        self.lock = threading.RLock()
        self.leases = {}
        self.panic_revision = 0
        for item in self.store.all("playback", 100000):
            if item["status"] in PENDING:
                self.store.patch("playback", item["id"], status="interrupted")

    def items(self, channel):
        return sorted(
            self.store.channel_records("playback", channel), key=lambda item: item["created_at"]
        )

    def enqueue(self, job, replay=False):
        channel = self.store.get("channel", job.get("channel", ""))
        if not channel:
            raise UserError("Channel not found.")
        if job["status"] != "succeeded" or not self.service.output_path(job["id"]).is_file():
            raise UserError("This audio is not available.")
        if blocked_reason(
            job["request"]["text"], channel["filter_level"], channel["custom_filters"]
        ):
            raise UserError("The current channel filter blocks this text.")
        with self.lock:
            if sum(i["status"] in PENDING for i in self.items(channel["name"])) >= 100:
                raise UserError("Playback queue is full.")
            key = uuid.uuid4().hex
            item = {
                "id": key,
                "job_id": job["id"],
                "channel": channel["name"],
                "status": "queued",
                "created_at": self.clock(),
                "deadline": None,
                "username": job.get("username"),
                "text": job["request"]["text"],
                "voice_title": job.get("voice_title", "Voice"),
                "output_url": job["output_url"],
                "replay": replay,
                "error": None,
            }
            return self.store.put("playback", key, item)

    def snapshot(self, channel):
        with self.lock:
            config = self.store.get("channel", channel)
            if not config:
                raise UserError("Channel not found.")
            lease = self.leases.get(channel)
            now = self.clock()
            return {
                "items": self.items(channel)[-100:],
                "paused": config["paused"],
                "player_connected": bool(lease and lease["until"] > now),
                "server_time": now,
            }

    def pause(self, channel, paused=True):
        with self.lock:
            self.store.patch("channel", channel, paused=paused)
            if paused:
                for item in self.items(channel):
                    if item["status"] == "playing":
                        self.cancel(item["id"])
                    elif item["status"] in {"countdown", "ready"}:
                        self.store.patch("playback", item["id"], status="queued", deadline=None)
            return self.snapshot(channel)

    def cancel(self, key):
        with self.lock:
            item = self.store.get("playback", key)
            if item and item["status"] in PENDING:
                self.store.patch("playback", key, status="cancelled", finished_at=self.clock())
            return self.store.get("playback", key)

    def panic(self):
        with self.lock:
            self.panic_revision += 1
            for channel in self.store.all("channel"):
                self.store.patch("channel", channel["name"], paused=True)
                for item in self.items(channel["name"]):
                    if item["status"] in {"countdown", "ready", "playing"}:
                        self.cancel(item["id"])

    def cancel_all(self):
        with self.lock:
            self.panic()
            for item in self.store.all("playback", 100000):
                self.cancel(item["id"])

    def tick(self, channel, client_id):
        if not client_id or len(client_id) > 100:
            raise UserError("Invalid player identifier.")
        with self.lock:
            config = self.store.get("channel", channel)
            if not config:
                raise UserError("Channel not found.")
            now = self.clock()
            lease = self.leases.get(channel)
            if lease and lease["client"] != client_id and lease["until"] > now:
                return {
                    "owner": False,
                    "item": next((i for i in self.items(channel) if i["status"] in PENDING), None),
                    "paused": config["paused"],
                    "server_time": now,
                }
            if lease and lease["until"] <= now:
                for item in self.items(channel):
                    if item["status"] in {"playing", "ready"}:
                        self.store.patch(
                            "playback",
                            item["id"],
                            status="interrupted",
                            error="Player disconnected; not replayed automatically.",
                        )
                        self.store.patch("channel", channel, paused=True)
                        config["paused"] = True
                    elif item["status"] == "countdown":
                        self.store.patch("playback", item["id"], status="queued", deadline=None)
            self.leases[channel] = {"client": client_id, "until": now + 8}
            pending = [i for i in self.items(channel) if i["status"] in PENDING]
            item = pending[0] if pending else None
            if item and not config["paused"]:
                # Recheck filters if the policy changed while audio was waiting.
                if blocked_reason(item["text"], config["filter_level"], config["custom_filters"]):
                    self.cancel(item["id"])
                    item = None
                elif item["status"] == "queued":
                    item = self.store.patch(
                        "playback",
                        item["id"],
                        status="countdown",
                        deadline=now + config["delay_seconds"],
                    )
                elif item["status"] == "countdown" and now >= item["deadline"]:
                    item = self.store.patch("playback", item["id"], status="ready")
            return {"owner": True, "item": item, "paused": config["paused"], "server_time": now}

    def acknowledge(self, channel, client_id, key, status):
        if status not in {"playing", "played", "error"}:
            raise UserError("Invalid playback state.")
        with self.lock:
            lease = self.leases.get(channel)
            item = self.store.get("playback", key)
            if (
                not lease
                or lease["client"] != client_id
                or lease["until"] <= self.clock()
                or not item
                or item["channel"] != channel
            ):
                raise UserError("Player lease expired or item not found.")
            allowed = {"playing": {"ready"}, "played": {"playing"}, "error": {"ready", "playing"}}
            if item["status"] not in allowed[status]:
                raise UserError("Playback item was cancelled or changed.")
            self.store.patch(
                "playback",
                key,
                status=status,
                started_at=self.clock() if status == "playing" else item.get("started_at"),
                finished_at=self.clock() if status != "playing" else None,
            )
            if status == "error":
                self.store.patch("channel", channel, paused=True)
            return self.store.get("playback", key)
