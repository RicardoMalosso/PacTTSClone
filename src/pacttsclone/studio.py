import threading
import time
import uuid

from .discord_integration import DiscordIntegration
from .domain import GenerationRequest, UserError
from .hotkey import GlobalHotkey
from .models import AppConfig, ChannelConfig
from .moderation import blocked_reason
from .playback import GENERAL_PLAYER, Playback
from .twitch import TwitchClient
from .twitch_actions import TwitchActions
from .twitch_events import EventSubClient
from .twitch_oauth import TwitchAccounts
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
        self.event_clients = {}
        self.cooldowns = {}
        self.chat_lock = threading.RLock()
        self.hotkey = GlobalHotkey(self.playback.panic)
        service.on_finished = self.completed
        self.started = False
        self.client_modes = {}
        self.accounts = TwitchAccounts(service.settings.data_dir, self.authorization_changed)
        self.events = TwitchActions(self)
        self.discord = DiscordIntegration(service, self.voices)

    def start(self):
        self.started = True
        self.hotkey.configure(self.service.config.hotkey)
        self.discord.start()
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
        for voice_id in [*value.commands.values(), *[r.voice_id for r in value.event_rules]]:
            if not self.store.get("voice", voice_id):
                raise UserError("A command refers to a voice that does not exist.")
        old = self.store.get("channel", value.name)
        config = self.store.put("channel", value.name, value.model_dump())
        if old and (
            old.get("transport", "irc") != value.transport
            or old.get("commands") != config["commands"]
            or old.get("event_rules", []) != config["event_rules"]
        ):
            event_client = self.event_clients.pop(value.name, None)
            if event_client:
                event_client.close()
        if self.started:
            self.connect(config)
        return config

    def set_channel_connection(self, name, enabled):
        with self.chat_lock:
            config = self.store.get("channel", name)
            if not config or config.get("kind") == "general":
                raise UserError("Twitch channel not found.")
            config = self.store.patch("channel", name, enabled=enabled)
        self.connect(config)
        return config

    def delete_channel(self, name):
        with self.chat_lock:
            config = self.store.get("channel", name)
            if not config or config.get("kind") == "general":
                raise UserError("Twitch channel not found.")
            self.store.patch("channel", name, enabled=False)
            for job in self.service.pending():
                if job.get("channel") == name:
                    self.service.cancel(job["id"])
            with self.playback.lock:
                for item in self.playback.items(name):
                    self.playback.cancel(item["id"])
                self.playback.leases.pop(name, None)
                self.store.delete("channel", name)
            client = self.clients.pop(name, None)
            event_client = self.event_clients.pop(name, None)
            self.cooldowns = {k: v for k, v in self.cooldowns.items() if k[0] != name}
        # A closing IRC thread may be waiting for chat_lock.
        if client:
            client.close()
        if event_client:
            event_client.close()
        self.accounts.forget(name)
        self.client_modes.pop(name, None)
        return {"deleted": name}

    def disconnect_client(self, name):
        client = self.clients.pop(name, None)
        self.client_modes.pop(name, None)
        if client:
            client.close()
        event_client = self.event_clients.pop(name, None)
        if event_client:
            event_client.close()

    def authorization_changed(self, name):
        client = self.event_clients.pop(name, None)
        if client:
            client.close()
        config = self.store.get("channel", name)
        if self.started and config:
            self.connect(config)

    def connect(self, config):
        if not self.service.setup_ready():
            return
        if config.get("kind") == "general":
            return
        name = config["name"]
        mode = config.get("transport", "irc")
        if not config["enabled"]:
            self.disconnect_client(name)
            return
        if name not in self.clients:
            client = self.twitch_factory(name, self.receive_irc)
            self.clients[name] = client
            client.start()
        self.client_modes[name] = mode
        if mode != "oauth" or not self.accounts.snapshot(name)["authorized"]:
            client = self.event_clients.pop(name, None)
            if client:
                client.close()
            return
        if name not in self.event_clients:
            client = EventSubClient(
                name, self.accounts, self.store, self.events.receive,
                on_connected=self.events.reconcile,
            )
            self.event_clients[name] = client
            client.start()

    def channels(self):
        result = []
        for config in self.store.all("channel"):
            if config.get("kind") == "general":
                continue
            client = self.clients.get(config["name"])
            events = self.event_clients.get(config["name"])
            result.append(
                {
                    **config,
                    "playback_queue": [
                        item for item in self.playback.items(config["name"])
                        if item["status"] in {"queued", "countdown", "playing"}
                    ],
                    "connection": client.status if client else "disconnected",
                    "connection_error": client.error if client else None,
                    "oauth_authorized": self.accounts.snapshot(config["name"])["authorized"],
                    "event_connection": events.status if events else (
                        "Authorization required" if config.get("transport") == "oauth"
                        and config["enabled"] else "disconnected"
                    ),
                    "event_connection_error": events.error if events else None,
                    "event_subscriptions": getattr(events, "subscriptions", []),
                    "event_errors": getattr(events, "subscription_errors", {}),
                    "event_gap_since": getattr(events, "gap_since", None),
                    "reward_recovery": self.store.get("twitch_recovery", config["name"]),
                }
            )
        return result

    def receive_irc(self, channel, username, message, message_id=None):
        config = self.store.get("channel", channel)
        if config:
            return self.receive(channel, username, message, message_id)
        return None

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
            if reason:
                self.service.reject_request(
                    text,
                    reason,
                    channel=channel,
                    username=username,
                    voice_id=config["commands"][parts[0].casefold()],
                )
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
        self.discord.enqueue(job)
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
        self.discord.configure(self.discord.config.model_copy(update={"enabled": False}))
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
        self.started = False
        self.discord.stop()
        self.accounts.close()
        for client in [*self.clients.values(), *self.event_clients.values()]:
            client.close()
        self.events.close()
        self.hotkey.close()
        self.service.close()
