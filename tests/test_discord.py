import asyncio
import json
import os
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.discord_bot import DiscordBot
from pacttsclone.discord_credentials import DiscordCredential
from pacttsclone.domain import GenerationSettings, UserError
from pacttsclone.models import DiscordConfig
from pacttsclone.tunnel import TUNNEL_HOST

from .conftest import wait_job
from .test_v2 import wait_until

TOKEN = "test-bot-credential-not-a-real-token"
GUILD = "123456789012345678"
CHANNEL = "234567890123456789"


class FakeBot:
    instances = []

    def __init__(self, integration):
        self.integration = integration
        self.closed = threading.Event()
        self.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def start(self, token, reconnect=True):
        self.received_token = token
        self.integration.connected("345678901234567890")
        while not self.closed.is_set():
            await asyncio.sleep(0.01)

    async def close(self):
        self.closed.set()


@pytest.fixture
def discord_app(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path / "data"), engine)
    app.state.studio.discord.bot_factory = FakeBot
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        yield app, client


def enable(app, client, voice_id=""):
    assert client.put("/api/discord/token", json={"token": TOKEN}).status_code == 200
    result = client.put(
        "/api/discord/config",
        json={
            "enabled": True,
            "guild_id": GUILD,
            "channel_ids": [CHANNEL],
            "default_voice_id": voice_id,
            "custom_filters": ["blocked phrase"],
        },
    )
    assert result.status_code == 200, result.text
    manager = app.state.studio.discord
    wait_until(lambda: manager.snapshot()["status"] == "connected")
    return manager


def add_voice(app, mp3):
    with mp3.open("rb") as stream:
        return app.state.studio.voices.create(stream, "Discord voice", "ref.mp3", "Known text.")


def submit(manager, **changes):
    args = dict(
        guild_id=GUILD,
        channel_id=CHANNEL,
        user_id="456789012345678901",
        username="Discord tester",
        interaction_id="567890123456789012",
        text="Hello there.",
    )
    return manager.submit(**{**args, **changes})


def interaction(**changes):
    return SimpleNamespace(
        **{
            **dict(
                guild_id=int(GUILD),
                channel_id=int(CHANNEL),
                user=SimpleNamespace(id=456789012345678901, display_name="Discord tester"),
                id=567890123456789012,
                response=SimpleNamespace(defer=AsyncMock()),
                followup=SimpleNamespace(send=AsyncMock()),
                filesize_limit=10 * 1024 * 1024,
            ),
            **changes,
        }
    )


def test_local_token_persistence_redaction_and_removal(discord_app):
    app, client = discord_app
    assert not client.get("/api/discord").json()["token_saved"]
    manager = enable(app, client)
    assert manager.bot.received_token == TOKEN
    snapshot = client.get("/api/discord")
    assert snapshot.headers["cache-control"] == "no-store"
    assert snapshot.json()["token_saved"]
    assert "permissions=274877942784" in snapshot.json()["invite_url"]
    for endpoint in ("/api/discord", "/api/config", "/api/state"):
        assert TOKEN not in client.get(endpoint).text
    with app.state.service.store.lock:
        rows = app.state.service.store.db.execute("SELECT data FROM records").fetchall()
    assert TOKEN not in json.dumps(rows)
    saved = DiscordCredential(app.state.service.settings.data_dir)
    assert saved.token == TOKEN
    if os.name != "nt":
        assert saved.path.stat().st_mode & 0o777 == 0o600
    manager.stop()
    manager.start()
    wait_until(lambda: manager.snapshot()["status"] == "connected")
    assert manager.bot.received_token == TOKEN
    assert client.delete("/api/discord/token").status_code == 200
    assert not manager.config.enabled
    assert manager.snapshot()["status"] == "disconnected"
    assert not DiscordCredential(app.state.service.settings.data_dir).token
    assert not saved.path.exists()


def test_windows_credential_uses_dpapi(tmp_path, monkeypatch):
    import pacttsclone.discord_credentials as credentials

    calls = []

    def protect(data, decrypt=False):
        calls.append(decrypt)
        return data.removeprefix(b"protected:") if decrypt else b"protected:" + data

    monkeypatch.setattr(credentials, "os", SimpleNamespace(**{**vars(os), "name": "nt"}))
    monkeypatch.setattr(credentials, "_protect", protect)
    vault = DiscordCredential(tmp_path)
    vault.save(TOKEN)
    assert json.loads(vault.path.read_text())["protection"] == "dpapi"
    assert DiscordCredential(tmp_path).token == TOKEN
    assert calls == [False, True]


@pytest.mark.parametrize("token", [None, 123, "short", "Bot " + TOKEN, {"secret": TOKEN}])
def test_bad_token_errors_do_not_echo_input(discord_app, token):
    _, client = discord_app
    result = client.put("/api/discord/token", json={"token": token})
    assert result.status_code == 422
    assert TOKEN not in result.text
    assert not client.get("/api/discord").json()["token_saved"]


def test_discord_credentials_and_settings_are_host_only(discord_app):
    app, client = discord_app
    tunnel = app.state.tunnel
    tunnel.url, tunnel.status, tunnel.admin_key = (
        "https://test.trycloudflare.com",
        "running",
        "admin-key",
    )
    headers = {"host": TUNNEL_HOST, "origin": tunnel.url, "cookie": "pactts_admin=admin-key"}
    for method, path, body in [
        ("GET", "/api/discord", None),
        ("PUT", "/api/discord/config", {"guild_id": GUILD}),
        ("PUT", "/api/discord/token", {"token": TOKEN}),
        ("DELETE", "/api/discord/token", None),
    ]:
        response = client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403
    assert not app.state.studio.discord.credential.token
    assert (
        client.put(
            "/api/discord/token", json={"token": TOKEN}, headers={"X-PacTTS-Token": "wrong"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"guild_id": "https://discord.gg/hello"},
        {"guild_id": "0"},
        {"guild_id": "18446744073709551616"},
        {"channel_ids": [""]},
        {"user_cooldown_seconds": -1},
        {"max_message_chars": 2001},
        {"custom_filters": [""]},
        {"filter_level": "none"},
        {"token": TOKEN},
    ],
)
def test_discord_config_validation(changes):
    with pytest.raises(ValidationError):
        DiscordConfig(**changes)


def test_enable_requires_credentials_and_guild_and_setup(discord_app, monkeypatch):
    app, client = discord_app
    assert client.put("/api/discord/config", json={"enabled": True}).status_code == 422
    manager = app.state.studio.discord
    monkeypatch.setattr(manager.service, "setup_ready", lambda: False)
    manager.credential.save(TOKEN)
    manager.configure(DiscordConfig(enabled=True, guild_id=GUILD))
    assert manager.snapshot()["status"] == "Waiting for setup"
    assert manager.thread is None
    monkeypatch.setattr(manager.service, "setup_ready", lambda: True)
    app.state.studio.start()
    wait_until(lambda: manager.snapshot()["status"] == "connected")


def test_speech_uses_saved_voice_queue_and_discord_identity(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    app.state.studio.voices.set_generation_settings(
        voice["id"],
        GenerationSettings(language="pt", steps=14, speed=0.8),
    )
    manager = enable(app, client, voice["id"])
    job = submit(manager)
    done = wait_job(manager.service, job["id"])
    assert done["status"] == "succeeded"
    assert done["origin"] == "discord"
    assert done["requester_name"] == "Discord tester"
    assert done["request"]["language"] == "pt"
    assert done["request"]["steps"] == 14
    assert done["request"]["speed"] == 0.8
    assert done["channel"] is None
    assert done["discord_guild_id"] == GUILD
    assert done["discord_channel_id"] == CHANNEL
    assert not app.state.studio.playback.items("playbackMain")
    assert TOKEN not in (manager.service.logs / "requests.jsonl").read_text()
    with pytest.raises(UserError, match="already been handled"):
        submit(manager)
    with pytest.raises(UserError, match="cooldown"):
        submit(manager, interaction_id="other", username="Changed display name")
    with pytest.raises(UserError, match="custom"):
        submit(manager, interaction_id="blocked", text="A blocked phrase here", user_id="other")
    assert len(manager.service.engine.calls) == 1
    blocked = [j for j in manager.service.request_history() if j["status"] == "blocked"]
    assert len(blocked) == 2 and all(j["origin"] == "discord" for j in blocked)


@pytest.mark.parametrize(
    "changes",
    [
        {"guild_id": None},
        {"guild_id": "999"},
        {"channel_id": "999"},
    ],
)
def test_wrong_server_channel_and_dm_cannot_allocate_jobs(discord_app, changes):
    app, client = discord_app
    manager = enable(app, client)
    with pytest.raises(UserError):
        submit(manager, **changes)
    assert not manager.service.history()


def test_bot_commands_defer_and_upload_real_generated_mp3(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client, voice["id"])
    bot = DiscordBot(manager)
    assert {c.name for c in bot.tree.get_commands()} == {"tts", "voices"}
    assert not bot.intents.message_content
    assert not bot.intents.members
    request = interaction()
    attachments = []

    async def posted(**kwargs):
        assert request.response.defer.await_count == 1
        attachment = kwargs["file"]
        attachments.append(attachment.fp.read())
        assert kwargs["allowed_mentions"].everyone is False

    request.followup.send.side_effect = posted
    asyncio.run(bot.speech(request, "Hello from Discord"))
    request.response.defer.assert_awaited_once_with(thinking=True)
    assert attachments[0][:3] == b"ID3"
    assert not manager.pending
    assert not bot.tasks


def test_voices_and_autocomplete_only_expose_ready_voices(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client)
    bot = DiscordBot(manager)
    request = interaction()
    asyncio.run(bot.tree.get_command("voices").callback(request))
    assert voice["title"] in request.followup.send.call_args.kwargs["content"]
    choices = asyncio.run(bot.tree.get_command("tts")._params["voice"].autocomplete(request, "Dis"))
    assert choices[0].value == voice["id"]
    app.state.service.store.patch("voice", voice["id"], status="unprepared")
    assert not asyncio.run(bot.tree.get_command("tts")._params["voice"].autocomplete(request, ""))


def test_upload_limit_keeps_local_result_and_reports_error(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client, voice["id"])
    request = interaction(filesize_limit=1)
    asyncio.run(DiscordBot(manager).speech(request, "Too large for this limit"))
    assert "upload limit" in request.followup.send.call_args.args[0]
    assert manager.service.history()[0]["status"] == "succeeded"
    assert not manager.pending


def test_disconnect_cancels_discord_jobs_and_cancel_all_disables_bot(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client, voice["id"])
    release = threading.Event()
    original = manager.service.engine.synthesize

    def blocked(*args):
        release.wait(5)
        return original(*args)

    manager.service.engine.synthesize = blocked
    try:
        job = submit(manager)
        app.state.studio.cancel_all()
        release.set()
        wait_until(lambda: manager.service.get(job["id"])["status"] == "cancelled")
        assert not manager.config.enabled
        assert not manager.thread.is_alive()
        assert not manager.pending
    finally:
        release.set()


@pytest.mark.parametrize("body", [TOKEN, [TOKEN], {"unexpected": TOKEN}])
def test_malformed_token_request_never_reflects_secret(discord_app, body):
    _, client = discord_app
    response = client.put("/api/discord/token", json=body)
    assert response.status_code == 422
    assert TOKEN not in response.text


def test_first_install_invite_and_guild_command_sync(discord_app):
    app, client = discord_app
    manager = enable(app, client)
    bot = DiscordBot(manager)
    bot._connection.application_id = 345678901234567890
    forbidden = discord.Forbidden(
        SimpleNamespace(status=403, reason="Forbidden"),
        {"code": 50001, "message": "Missing Access"},
    )
    bot.tree.sync = AsyncMock(side_effect=[forbidden, []])
    asyncio.run(bot.setup_hook())
    assert manager.snapshot()["status"] == "Invite bot to server"
    assert manager.snapshot()["invite_url"]
    assert {c.name for c in bot.tree.get_commands(guild=bot.guild)} == {"tts", "voices"}
    asyncio.run(bot.on_guild_join(SimpleNamespace(id=int(GUILD))))
    assert manager.snapshot()["status"] == "connected"
    assert bot.synced


def test_disconnect_works_after_default_voice_deleted(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client, voice["id"])
    app.state.studio.voices.delete(voice["id"])
    manager.configure(manager.config.model_copy(update={"enabled": False}))
    assert not manager.thread.is_alive()


def test_interaction_timeout_cancels_job_without_posting_audio(discord_app, monkeypatch):
    import pacttsclone.discord_bot as bot_module

    app, client = discord_app
    manager = enable(app, client)
    monkeypatch.setattr(manager, "submit", lambda **kwargs: {"id": "timeout-job"})
    monkeypatch.setattr(manager.service, "get", lambda job_id: {"status": "running"})
    cancelled = []
    monkeypatch.setattr(manager.service, "cancel", cancelled.append)
    ticks = iter([0, 841])
    monkeypatch.setattr(bot_module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    request = interaction()
    asyncio.run(DiscordBot(manager).speech(request, "Timeout test"))
    assert cancelled == ["timeout-job"]
    assert "timed out" in request.followup.send.call_args.args[0]
    assert "file" not in request.followup.send.call_args.kwargs


def test_connection_errors_never_leak_credentials(discord_app):
    app, client = discord_app

    class BrokenBot(FakeBot):
        async def start(self, token, reconnect=True):
            raise RuntimeError("Remote exception containing " + token)

    manager = app.state.studio.discord
    manager.bot_factory = BrokenBot
    manager.credential.save(TOKEN)
    manager.configure(DiscordConfig(enabled=True, guild_id=GUILD))
    wait_until(lambda: manager.snapshot()["status"] == "error")
    assert TOKEN not in json.dumps(manager.snapshot())


def test_enabled_connection_resumes_after_app_restart(tmp_path, engine):
    settings = Settings(data_dir=tmp_path / "persistent-data")
    first = create_app(settings, engine)
    first.state.studio.discord.bot_factory = FakeBot
    with TestClient(first, base_url="http://127.0.0.1") as client:
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        enable(first, client)
    second = create_app(settings, engine)
    manager = second.state.studio.discord
    manager.bot_factory = FakeBot
    with TestClient(second, base_url="http://127.0.0.1") as client:
        wait_until(lambda: manager.snapshot()["status"] == "connected")
        assert manager.bot.received_token == TOKEN
        assert manager.config.guild_id == GUILD
        assert manager.config.channel_ids == [CHANNEL]
        assert TOKEN not in client.get("/api/discord").text


def test_delivery_backpressure_prevents_more_generation(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client, voice["id"])
    manager.service.config = manager.service.config.model_copy(update={"max_queue": 1})
    manager.pending.add("completed-job-awaiting-upload")
    with pytest.raises(UserError, match="delivery queue is full"):
        submit(manager)
    assert not manager.service.history()
    assert manager.service.request_history()[0]["status"] == "blocked"


def test_gateway_resume_restores_connected_status(discord_app):
    app, client = discord_app
    manager = enable(app, client)
    bot = DiscordBot(manager)
    bot.synced = True
    bot._connection.application_id = 345678901234567890
    asyncio.run(bot.on_disconnect())
    assert manager.snapshot()["status"] == "reconnecting"
    asyncio.run(bot.on_resumed())
    assert manager.snapshot()["status"] == "connected"
    manager.stop()
    asyncio.run(bot.on_resumed())
    assert manager.snapshot()["status"] == "disconnected"


@pytest.mark.parametrize("during_submit", [True, False])
def test_cancelled_delivery_cancels_unfinished_generation(discord_app, monkeypatch, during_submit):
    app, client = discord_app
    manager = enable(app, client)
    entered, release = threading.Event(), threading.Event()
    cancelled = []

    def submit_slowly(**kwargs):
        entered.set()
        assert release.wait(5)
        manager.pending.add("cancelled-delivery")
        return {"id": "cancelled-delivery"}

    monkeypatch.setattr(manager, "submit", submit_slowly)
    monkeypatch.setattr(manager.service, "get", lambda job_id: {"status": "queued"})
    monkeypatch.setattr(manager.service, "cancel", cancelled.append)
    request = interaction()
    bot = DiscordBot(manager)

    async def run():
        task = asyncio.create_task(bot.speech(request, "Cancel me"))
        assert await asyncio.to_thread(entered.wait, 5)
        if not during_submit:
            release.set()
            while "cancelled-delivery" not in manager.pending:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.01)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(run())
        assert cancelled == ["cancelled-delivery"]
        assert not manager.pending
        assert not bot.tasks
        request.followup.send.assert_not_awaited()
    finally:
        release.set()


def test_upload_failure_preserves_completed_audio(discord_app, mp3):
    app, client = discord_app
    voice = add_voice(app, mp3)
    manager = enable(app, client, voice["id"])
    request = interaction()
    request.followup.send.side_effect = [
        discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "Missing access"),
        None,
    ]
    asyncio.run(DiscordBot(manager).speech(request, "Keep this local"))
    done = manager.service.history()[0]
    assert done["status"] == "succeeded"
    assert manager.service.output_path(done["id"]).exists()
    assert "Could not post" in request.followup.send.call_args.args[0]
    assert not manager.pending
