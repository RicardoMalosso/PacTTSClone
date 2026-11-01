import json
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.discord_credentials import DiscordWebhookCredential
from pacttsclone.discord_integration import send_webhook, webhook_content
from pacttsclone.domain import GenerationRequest, UserError
from pacttsclone.models import DiscordConfig
from pacttsclone.tunnel import TUNNEL_HOST

from .conftest import wait_job
from .test_v2 import wait_until

URL = "https://discord.com/api/webhooks/123456789012345678/" + "a" * 40


@pytest.fixture
def webhook_app(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path / "data"), engine)
    deliveries = []
    app.state.studio.discord.sender = lambda url, path=None, content=None: deliveries.append(
        (url, path, content)
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        yield app, client, deliveries


def enable(app, client, **kwargs):
    assert client.put("/api/discord/webhook", json={"url": URL}).status_code == 200
    response = client.put("/api/discord/config", json={"enabled": True, **kwargs})
    assert response.status_code == 200, response.text
    return app.state.studio.discord


def test_credential_protection_redaction_test_and_remove(webhook_app):
    app, client, deliveries = webhook_app
    enable(app, client)
    for endpoint in ["/api/discord", "/api/state", "/api/config"]:
        assert URL not in client.get(endpoint).text
    stored = DiscordWebhookCredential(app.state.service.settings.data_dir)
    assert stored.token == URL
    if os.name != "nt":
        assert stored.path.stat().st_mode & 0o777 == 0o600
    rows = app.state.service.store.db.execute("SELECT data FROM records").fetchall()
    assert URL not in json.dumps(rows)
    assert client.post("/api/discord/test").json()["status"] == "test_sent"
    assert deliveries == [(URL, None, None)]
    assert client.delete("/api/discord/webhook").json()["enabled"] is False
    assert not stored.path.exists()
    assert client.put("/api/discord/token", json={"token": "obsolete"}).status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/api/webhooks/1/" + "a" * 40,
        "http://discord.com/api/webhooks/1/" + "a" * 40,
        URL + "?wait=true",
        URL + "/extra",
        "https://discord.com@localhost/" + "a" * 40,
    ],
)
def test_invalid_urls_are_rejected_without_reflection(webhook_app, url):
    _, client, _ = webhook_app
    response = client.put("/api/discord/webhook", json={"url": url})
    assert response.status_code == 422
    assert url not in response.text


def test_completed_mp3_delivery_and_duplicate_suppression(webhook_app, mp3):
    app, client, deliveries = webhook_app
    manager = enable(app, client)
    with mp3.open("rb") as stream:
        voice = app.state.studio.voices.create(stream, "Test", "ref.mp3", "Known text.")
    job = app.state.studio.voices.generate(
        voice["id"], GenerationRequest(text="Hello", requester_name="Ricardo")
    )
    finished = wait_job(app.state.service, job["id"])
    assert finished["status"] == "succeeded"
    wait_until(
        lambda: (manager.store.get("discord_delivery", job["id"]) or {}).get("status") == "sent"
    )
    manager.enqueue(finished)
    assert len(deliveries) == 1
    assert deliveries[0][1].stat().st_size > 0
    assert deliveries[0][2] == "Ricardo sent a 'Test' TTS:\n```\nHello\n```"


def test_selection_skips_history_transcription_and_other_sources(webhook_app):
    app, client, deliveries = webhook_app
    manager = enable(
        app,
        client,
        include_local=False,
        include_twitch=True,
        channels=["foo"],
        voice_ids=["voice1"],
    )
    base = {
        "id": "selected",
        "status": "succeeded",
        "kind": "speech",
        "channel": "foo",
        "voice_id": "voice1",
    }
    for changes in [
        {"channel": None},
        {"channel": "bar"},
        {"voice_id": "voice2"},
        {"status": "failed"},
        {"kind": "transcribe"},
    ]:
        manager.enqueue({**base, **changes})
    assert not deliveries
    assert manager.store.get("discord_delivery", "selected") is None
    manager.sender = lambda *args: (_ for _ in ()).throw(UserError("Upload failed"))
    manager.enqueue(base)
    wait_until(lambda: manager.store.get("discord_delivery", "selected")["status"] == "failed")
    assert manager.snapshot()["error"]


def test_webhook_apis_are_host_only(webhook_app):
    _, client, _ = webhook_app
    for method, path in [
        ("get", "/api/discord"),
        ("put", "/api/discord/webhook"),
        ("post", "/api/discord/test"),
        ("delete", "/api/discord/webhook"),
    ]:
        response = getattr(client, method)(path, headers={"Host": TUNNEL_HOST})
        assert response.status_code in {401, 403}


def test_reconfiguration_cancels_queued_delivery(webhook_app):
    app, client, _ = webhook_app
    manager = enable(app, client)
    manager.stop()
    manager.enqueue({"id": "queued", "status": "succeeded", "kind": "speech"})
    manager.configure(DiscordConfig(enabled=False))
    manager.start()
    wait_until(lambda: manager.store.get("discord_delivery", "queued")["status"] == "cancelled")


def test_multipart_upload_disables_mentions_and_rejects_redirects(tmp_path, monkeypatch):
    captured = []
    response = SimpleNamespace(status=200, read=lambda limit: b"{}")

    class Connection:
        def __init__(self, host, timeout):
            assert host == "discord.com"

        def request(self, *args):
            captured.append(args)

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr("pacttsclone.discord_integration.http.client.HTTPSConnection", Connection)
    path = tmp_path / "file.mp3"
    path.write_bytes(b"mp3-sample")
    send_webhook(URL, path, "viewer sent Hello")
    assert b"viewer sent Hello" in captured[0][2]
    assert b'"allowed_mentions": {"parse": []}' in captured[0][2]
    assert b"files[0]" in captured[0][2] and b"mp3-sample" in captured[0][2]
    for status in [302, 401, 404, 429, 500]:
        response.status = status
        with pytest.raises(UserError):
            send_webhook(URL, path)
    path.write_bytes(b"")
    with pytest.raises(UserError, match="10 MiB"):
        send_webhook(URL, path)


def test_sender_text_bounds_and_literal_formatting():
    content = webhook_content(
        {
            "username": "viewer",
            "requester_name": "other",
            "request": {"text": "Olá @everyone ```hello```\n" + "x" * 2000},
        },
        "Lula",
    )
    assert content.startswith("viewer sent a 'Lula' TTS:")
    assert "Olá @everyone ˋˋˋhelloˋˋˋ" in content
    assert len(content) <= 2000
    assert content.count("```") == 2
    assert "Unknown requester" in webhook_content({})


def test_twitch_delivery_includes_sender_and_message(webhook_app, mp3):
    app, client, deliveries = webhook_app
    manager = enable(app, client, include_twitch=True)
    with mp3.open("rb") as stream:
        voice = app.state.studio.voices.create(stream, "Lula", "ref.mp3", "Known text.")
    job = app.state.studio.voices.generate(
        voice["id"], GenerationRequest(text="Olá chat!"), "channel", "viewer"
    )
    assert wait_job(app.state.service, job["id"])["status"] == "succeeded"
    wait_until(
        lambda: (manager.store.get("discord_delivery", job["id"]) or {}).get("status") == "sent"
    )
    assert deliveries[0][2] == "viewer sent a 'Lula' TTS:\n```\nOlá chat!\n```"
    assert len(webhook_content({"request": {"text": "😀" * 2000}}).encode("utf-16-le")) <= 4000
