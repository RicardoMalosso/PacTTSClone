import threading
import time
import uuid

from .domain import GenerationRequest, UserError
from .hotkey import GlobalHotkey
from .models import AppConfig, ChannelConfig
from .moderation import blocked_reason
from .playback import GENERAL_PLAYER, Playback
from .twitch import TwitchClient
from .voices import Voices


class Studio:
    def __init__(self, service, twitch_factory=TwitchClient):
        self.service, self.store = service, service.store
        self.voices = Voices(service)
        self.voices.seed_defaults()
        if not self.store.get("channel", GENERAL_PLAYER):
            general = ChannelConfig(name="general").model_dump()
            self.store.put(
                "channel", GENERAL_PLAYER, {**general, "name": GENERAL_PLAYER, "kind": "general"}
            )
        self.playback = Playback(service)
        self.twitch_factory = twitch_factory
        self.clients = {}
        self.cooldowns = {}
        self.chat_lock = threading.RLock()
        self.hotkey = GlobalHotkey(self.playback.panic)
        service.on_finished = self.completed
        self.started = False

    def start(self):
        self.started = True
        self.hotkey.configure(self.service.config.hotkey)
        if self.service.setup_ready():
            for channel in self.store.all("channel"):
                self.connect(channel)

    def configure(self, value: AppConfig):
        if self.service.setup_busy:
            from .domain import BusyError

            raise BusyError("Dependency setup is running. Wait or cancel it first.")
        self.service.configure(value)
        self.hotkey.configure(value.hotkey)
        return {**value.model_dump(), "hotkey_status": self.hotkey.status}

    def save_channel(self, value: ChannelConfig):
        for voice_id in value.commands.values():
            if not self.store.get("voice", voice_id):
                raise UserError("A command refers to a voice that does not exist.")
        config = self.store.put("channel", value.name, value.model_dump())
        if self.started:
            self.connect(config)
        return config

    def connect(self, config):
        if not self.service.setup_ready():
            return
        if config.get("kind") == "general":
            return
        name = config["name"]
        old = self.clients.get(name)
        if not config["enabled"]:
            if old:
                old.close()
                del self.clients[name]
            return
        if not old:
            client = self.twitch_factory(name, self.receive)
            self.clients[name] = client
            client.start()

    def channels(self):
        result = []
        for config in self.store.all("channel"):
            if config.get("kind") == "general":
                continue
            client = self.clients.get(config["name"])
            result.append(
                {
                    **config,
                    "connection": client.status if client else "disconnected",
                    "connection_error": client.error if client else None,
                }
            )
        return result

    def receive(self, channel, username, message, message_id=None):
        with self.chat_lock:
            config = self.store.get("channel", channel)
            if not config or not config["enabled"]:
                return None
            parts = message.strip().split(maxsplit=1)
            if not parts or parts[0].casefold() not in config["commands"]:
                return None
            text = parts[1].strip() if len(parts) > 1 else ""
            reason = None
            if not text or len(text) > config["max_message_chars"]:
                reason = "empty or overlong message"
            if not reason:
                reason = blocked_reason(text, config["filter_level"], config["custom_filters"])
            now = time.time()
            key = (channel, username.casefold())
            if not reason and now - self.cooldowns.get(key, 0) < config["user_cooldown_seconds"]:
                reason = "user cooldown"
            job = None
            if not reason:
                try:
                    job = self.voices.generate(
                        config["commands"][parts[0].casefold()],
                        GenerationRequest(text=text),
                        channel,
                        username,
                    )
                    self.cooldowns[key] = now
                except (UserError, OSError) as exc:
                    reason = str(exc)
            event_id = uuid.uuid4().hex
            self.store.put(
                "chat",
                event_id,
                {
                    "id": event_id,
                    "channel": channel,
                    "username": username,
                    "text": message[:2200],
                    "message_id": message_id,
                    "created_at": now,
                    "accepted": job is not None,
                    "reason": reason,
                    "job_id": job["id"] if job else None,
                },
            )
            # Bound ancillary moderation history and cooldown memory.
            for old in self.store.all("chat", 100000)[1000:]:
                self.store.delete("chat", old["id"])
            if len(self.cooldowns) > 5000:
                self.cooldowns = {k: v for k, v in self.cooldowns.items() if now - v < 600}
            return job

    def completed(self, job):
        self.voices.completed(job)
        if job.get("channel") and job["kind"] == "speech" and job["status"] == "succeeded":
            try:
                self.playback.enqueue(job)
            except UserError as exc:
                self.store.patch("job", job["id"], playback_error=str(exc))

        if (
            not job.get("channel")
            and job["kind"] == "speech"
            and job["status"] == "succeeded"
            and job["request"].get("autoqueue_general")
        ):
            try:
                with self.playback.lock:
                    current = self.store.get("job", job["id"])
                    if current.get("general_playback_item_id"):
                        return
                    item = self.playback.enqueue(job, destination=GENERAL_PLAYER)
                    self.store.patch("job", job["id"], general_playback_item_id=item["id"])
            except UserError as exc:
                self.store.patch("job", job["id"], playback_error=str(exc))

    def cancel_job(self, job_id):
        result = self.service.cancel(job_id)
        for item in self.store.all("playback", 100000):
            if item["job_id"] == job_id:
                self.playback.cancel(item["id"])
        return result

    def cancel_all(self):
        with self.chat_lock:
            channels = self.store.all("channel")
            for channel in channels:
                self.store.patch("channel", channel["name"], enabled=False)
            self.service.cancel_all()
            self.playback.cancel_all()
        # Closing sockets can wait for a message callback; never join under chat_lock.
        for channel in channels:
            self.connect({**channel, "enabled": False})

    def close(self):
        for client in self.clients.values():
            client.close()
        self.hotkey.close()
        self.service.close()
