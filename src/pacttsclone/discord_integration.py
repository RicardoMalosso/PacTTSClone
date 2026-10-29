"""Host-owned Discord lifecycle and moderated access to the existing local worker."""

import asyncio
import threading
import time
import uuid

from .discord_credentials import DiscordCredential
from .domain import GenerationRequest, UserError
from .models import DiscordConfig
from .moderation import blocked_reason


class DiscordIntegration:
    def __init__(self, service, voices, bot_factory=None):
        self.service, self.store, self.voices = service, service.store, voices
        saved = self.store.get("discord", "config") or {}
        self.config = DiscordConfig.model_validate(saved)
        self.credential = DiscordCredential(service.settings.data_dir)
        self.bot_factory = bot_factory
        self.control_lock = threading.RLock()
        self.lock = threading.RLock()
        self.thread = self.loop = self.bot = None
        self.stopping = True
        self.status, self.error, self.application_id = "disconnected", None, None
        self.cooldowns, self.seen, self.pending = {}, {}, set()

    def snapshot(self):
        with self.lock:
            invite = None
            if self.application_id:
                # View Channel, Send Messages, Attach Files, Send Messages in Threads.
                invite = (
                    "https://discord.com/oauth2/authorize"
                    f"?client_id={self.application_id}&scope=bot%20applications.commands"
                    f"&permissions=274877942784&guild_id={self.config.guild_id}"
                    "&disable_guild_select=true"
                )
            return {
                **self.config.model_dump(),
                "token_saved": bool(self.credential.token),
                "status": self.status,
                "error": self.error or self.credential.error,
                "application_id": self.application_id,
                "invite_url": invite,
            }

    def configure(self, config):
        with self.control_lock:
            if config.enabled and (not config.guild_id or not self.credential.token):
                raise UserError("Save a bot token and enter a Discord server ID before enabling.")
            if config.enabled and config.default_voice_id:
                voice = self.store.get("voice", config.default_voice_id)
                if not voice or voice["status"] != "ready":
                    raise UserError("Choose a ready saved voice for Discord.")
            self.stop()
            with self.lock:
                self.store.put("discord", "config", config.model_dump())
                self.config = config
            self.start()
            return self.snapshot()

    def save_token(self, token):
        with self.control_lock:
            self.credential.save(token)
            self.stop()
            self.application_id = None
            self.start()
            return self.snapshot()

    def forget_token(self):
        with self.control_lock:
            self.stop()
            self.credential.forget()
            with self.lock:
                self.config = self.config.model_copy(update={"enabled": False})
                self.store.put("discord", "config", self.config.model_dump())
                self.application_id = None
            return self.snapshot()

    def start(self):
        with self.control_lock, self.lock:
            if self.thread and self.thread.is_alive():
                return
            if not self.config.enabled or not self.credential.token:
                return
            if not self.service.setup_ready():
                self.status = "Waiting for setup"
                return
            self.stopping, self.status, self.error = False, "connecting", None
            self.thread = threading.Thread(target=self._run, daemon=True, name="discord-bot")
            self.thread.start()

    def _run(self):
        try:
            asyncio.run(self._session())
        except Exception:
            # SDK exceptions may contain interaction URLs/tokens. Never forward them.
            with self.lock:
                if not self.stopping:
                    self.status = "error"
                    self.error = "Discord connection failed. Check the bot token and connection."
        finally:
            self._cancel_pending()
            with self.lock:
                self.stopping = True
                self.loop = self.bot = None

    async def _session(self):
        from .discord_bot import DiscordBot

        bot = (self.bot_factory or DiscordBot)(self)
        with self.lock:
            self.loop, self.bot = asyncio.get_running_loop(), bot
            if self.stopping:
                return
            token = self.credential.token
        async with bot:
            await bot.start(token, reconnect=True)

    def connected(self, application_id):
        with self.lock:
            self.application_id = str(application_id)
            if not self.stopping:
                self.status, self.error = "connected", None

    def _cancel_pending(self):
        with self.lock:
            pending = list(self.pending)
            self.pending.clear()
        for job_id in pending:
            job = self.service.get(job_id)
            if job and job["status"] in {"queued", "running"}:
                self.service.cancel(job_id)

    def stop(self):
        with self.control_lock:
            with self.lock:
                self.stopping, self.status = True, "disconnected"
                self.error = None
                loop, bot, thread = self.loop, self.bot, self.thread
            self._cancel_pending()
            if loop and bot and loop.is_running():
                asyncio.run_coroutine_threadsafe(bot.close(), loop)
            if thread and thread is not threading.current_thread():
                thread.join(5)
                if thread.is_alive():
                    raise UserError("Discord is still disconnecting. Retry in a few seconds.")

    def check_access(self, guild_id, channel_id):
        with self.lock:
            if self.stopping or not self.config.enabled:
                raise UserError("Discord integration is disconnected.")
            if str(guild_id) != self.config.guild_id:
                raise UserError("This Discord server is not enabled in PacTTSClone.")
            if self.config.channel_ids and str(channel_id) not in self.config.channel_ids:
                raise UserError("This Discord channel is not enabled in PacTTSClone.")

    def ready_voices(self, guild_id, channel_id):
        self.check_access(guild_id, channel_id)
        return [v for v in self.store.all("voice") if v["status"] == "ready"]

    def submit(self, *, guild_id, channel_id, user_id, username, interaction_id, text, voice_id=""):
        with self.lock:
            self.check_access(guild_id, channel_id)
            config = self.config
            voice_id = voice_id or config.default_voice_id
            text = text.strip()
            identity = self.service.identity(
                "discord",
                username,
                uuid.uuid5(uuid.NAMESPACE_URL, f"discord:user:{user_id}").hex,
                source=f"{guild_id}:{channel_id}",
            )
            now = time.monotonic()
            # Bound memory; the window also covers Discord's interaction lifetime.
            self.seen = {k: v for k, v in self.seen.items() if now - v < 900}
            self.cooldowns = {k: v for k, v in self.cooldowns.items() if now - v < 600}
            if str(interaction_id) in self.seen:
                raise UserError("This Discord request has already been handled.")
            if len(self.seen) >= 5000:
                raise UserError("Too many Discord requests. Try again later.")
            self.seen[str(interaction_id)] = now
            reason = None
            if not text or len(text) > config.max_message_chars:
                reason = "empty or overlong message"
            if not reason:
                reason = blocked_reason(text, config.filter_level, config.custom_filters)
            if not reason and now - self.cooldowns.get(str(user_id), -1000) < (
                config.user_cooldown_seconds
            ):
                reason = "user cooldown"
            if not reason and not voice_id:
                reason = "Choose a voice in /tts or save a default voice in Configuration."
            if not reason and len(self.pending) >= self.service.config.max_queue:
                reason = "Discord delivery queue is full. Try again later."
            if reason:
                self.service.reject_request(
                    text,
                    reason,
                    channel=None,
                    username=username,
                    voice_id=voice_id,
                    identity=identity,
                )
                raise UserError(reason)
            try:
                job = self.voices.generate(
                    voice_id,
                    GenerationRequest(text=text),
                    username=username,
                    identity=identity,
                )
            except UserError as exc:
                self.service.reject_request(
                    text,
                    str(exc),
                    channel=None,
                    username=username,
                    voice_id=voice_id,
                    identity=identity,
                )
                raise
            # No interaction token or webhook URL is persisted in job/audit data.
            self.store.patch(
                "job",
                job["id"],
                discord_guild_id=str(guild_id),
                discord_channel_id=str(channel_id),
            )
            self.pending.add(job["id"])
            self.cooldowns[str(user_id)] = now
            return job

    def finished(self, job_id):
        # A cancelled/failed delivery must not orphan queued GPU work. Successful
        # files remain in History even when their Discord upload fails.
        job = self.service.get(job_id)
        if job and job["status"] in {"queued", "running"}:
            self.service.cancel(job_id)
        with self.lock:
            self.pending.discard(job_id)
