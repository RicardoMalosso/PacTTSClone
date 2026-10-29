"""Gateway slash commands. No public endpoint or privileged intents required."""

import asyncio
import contextlib
import time

import discord
from discord import app_commands

from .domain import UserError


class DiscordBot(discord.Client):
    def __init__(self, integration):
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.integration = integration
        self.tasks = set()
        self.synced = False
        self.tree = app_commands.CommandTree(self)
        self.guild = discord.Object(id=int(integration.config.guild_id))

        @self.tree.command(name="tts", description="Generate speech locally and post its MP3")
        @app_commands.describe(text="Text to speak", voice="Saved voice (or configured default)")
        @app_commands.guild_only()
        async def tts(interaction: discord.Interaction, text: str, voice: str = ""):
            await self.speech(interaction, text, voice)

        @tts.autocomplete("voice")
        async def voice_choices(interaction: discord.Interaction, current: str):
            try:
                voices = integration.ready_voices(interaction.guild_id, interaction.channel_id)
            except UserError:
                return []
            return [
                app_commands.Choice(name=v["title"][:100], value=v["id"])
                for v in voices
                if current.casefold() in v["title"].casefold()
            ][:25]

        @self.tree.command(name="voices", description="List ready PacTTSClone voices")
        @app_commands.guild_only()
        async def voices(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                ready = integration.ready_voices(interaction.guild_id, interaction.channel_id)
                content = "\n".join(f"{v['title']} · {v['id']}" for v in ready)
                await interaction.followup.send(
                    content=(content[:1900] or "No ready voices. Prepare a voice in PacTTSClone."),
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except UserError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)

        @self.tree.error
        async def command_error(
            interaction: discord.Interaction,
            error: app_commands.AppCommandError,
        ):
            # Do not let default SDK handlers log interaction tokens in tracebacks.
            with contextlib.suppress(discord.HTTPException):
                message = "Discord command failed. Check PacTTSClone and try again."
                if interaction.response.is_done():
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.response.send_message(message, ephemeral=True)

    async def setup_hook(self):
        self.integration.application_id = str(self.application_id)
        self.tree.copy_global_to(guild=self.guild)
        try:
            await self.tree.sync(guild=self.guild)
            self.synced = True
        except discord.Forbidden:
            # Login gives us the application ID needed to generate the invite URL.
            # First installation can then finish without a second token entry.
            self.integration.status = "Invite bot to server"

    async def on_ready(self):
        if self.synced:
            self.integration.connected(self.application_id)
        else:
            self.integration.status = "Invite bot to server"

    async def on_guild_join(self, guild):
        if guild.id == self.guild.id:
            await self.tree.sync(guild=self.guild)
            self.synced = True
            self.integration.connected(self.application_id)

    async def on_disconnect(self):
        with self.integration.lock:
            if not self.integration.stopping:
                self.integration.status = "reconnecting"

    async def on_resumed(self):
        # A resumed Gateway session does not emit on_ready again.
        if self.synced:
            self.integration.connected(self.application_id)

    async def on_error(self, event_method, *args, **kwargs):
        with self.integration.lock:
            self.integration.error = "Discord command failed. Check permissions and retry."

    async def speech(self, interaction, text, voice=""):
        # Acknowledge before any local queue/file work; synthesis can take minutes.
        await interaction.response.defer(thinking=True)
        task = asyncio.current_task()
        self.tasks.add(task)
        job = None
        submission = None
        deadline = time.monotonic() + 840
        try:
            submission = asyncio.create_task(
                asyncio.to_thread(
                    self.integration.submit,
                    guild_id=interaction.guild_id,
                    channel_id=interaction.channel_id,
                    user_id=interaction.user.id,
                    username=interaction.user.display_name,
                    interaction_id=interaction.id,
                    text=text,
                    voice_id=voice,
                )
            )
            # Cancelling to_thread cannot stop its underlying thread. Retain the
            # result so cancellation can also stop any job it allocates.
            job = await asyncio.shield(submission)
            while True:
                current = self.integration.service.get(job["id"])
                if current["status"] == "succeeded":
                    break
                if current["status"] in {"failed", "cancelled"}:
                    raise UserError("Speech failed or was cancelled. Check PacTTSClone history.")
                if time.monotonic() >= deadline:
                    raise UserError(
                        "Discord request timed out and was cancelled. Try shorter text."
                    )
                await asyncio.sleep(0.5)
            path = self.integration.service.output_path(job["id"])
            limit = getattr(interaction, "filesize_limit", 10 * 1024 * 1024)
            if path.stat().st_size > limit:
                raise UserError(
                    "MP3 exceeds Discord's upload limit. Download it from local History."
                )
            self.integration.check_access(interaction.guild_id, interaction.channel_id)
            with contextlib.closing(
                discord.File(path, filename=f"pactts-{job['id']}.mp3")
            ) as attachment:
                await interaction.followup.send(
                    file=attachment,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except asyncio.CancelledError:
            if submission and job is None:
                with contextlib.suppress(UserError):
                    job = await submission
            raise
        except UserError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except (discord.HTTPException, OSError):
            with contextlib.suppress(discord.HTTPException):
                await interaction.followup.send(
                    "Could not post the MP3. Check Discord permissions; "
                    "local History keeps the result.",
                    ephemeral=True,
                )
        finally:
            if job:
                self.integration.finished(job["id"])
            self.tasks.discard(task)

    async def close(self):
        tasks = [task for task in self.tasks if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await super().close()
