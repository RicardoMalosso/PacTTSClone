import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.domain import UserError
from pacttsclone.models import ChannelConfig
from pacttsclone.tunnel import TUNNEL_HOST


@pytest.fixture
def shared_app(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path / "shared"), engine)
    tunnel = app.state.tunnel
    tunnel.url = "https://local-test.trycloudflare.com"
    tunnel.status = "running"
    tunnel.admin_key = "admin-key-" + "x" * 40
    tunnel.player_keys = {
        "channelone": "player-one-" + "x" * 40,
        "channeltwo": "player-two-" + "x" * 40,
    }
    for name in ["channelone", "channeltwo"]:
        app.state.studio.save_channel(ChannelConfig(name=name))
    try:
        yield app
    finally:
        tunnel.close()
        app.state.studio.close()


def test_remote_admin_bootstrap_cookie_scope_and_no_tunnel_control(shared_app):
    with TestClient(shared_app, base_url="https://local-test.trycloudflare.com") as client:
        origin = {"Origin": "https://local-test.trycloudflare.com"}
        assert client.get("/").status_code == 200
        assert client.get("/api/config").status_code == 403
        response = client.post(
            "/api/remote/session", json={"key": shared_app.state.tunnel.admin_key}, headers=origin
        )
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        token = client.get("/api/session").json()["token"]
        assert client.get("/api/config").status_code == 200
        assert client.get("/api/tunnel").status_code == 403
        assert client.get("/api/setup").status_code == 403
        assert client.get("/api/setup/log").status_code == 403
        assert (
            client.post(
                "/api/setup/start",
                json={"device": "cpu"},
                headers={**origin, "X-PacTTS-Token": token},
            ).status_code
            == 403
        )
        assert (
            client.post("/api/tunnel/stop", headers={**origin, "X-PacTTS-Token": token}).status_code
            == 403
        )
        assert (
            client.post("/api/panic", headers={**origin, "X-PacTTS-Token": token}).status_code
            == 200
        )
        assert client.post("/api/panic", headers={"X-PacTTS-Token": token}).status_code == 403
        assert (
            client.post(
                "/api/panic",
                headers={**origin, "Origin": "https://evil.example", "X-PacTTS-Token": token},
            ).status_code
            == 403
        )


def test_remote_player_cannot_access_admin_other_channels_or_audio(shared_app):
    tunnel = shared_app.state.tunnel
    with TestClient(shared_app, base_url="https://local-test.trycloudflare.com") as client:
        origin = {"Origin": tunnel.url}
        key = tunnel.player_keys["channelone"]
        assert (
            client.post(
                "/api/remote/session", json={"key": key, "channel": "channeltwo"}, headers=origin
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/remote/session", json={"key": key, "channel": "channelone"}, headers=origin
            ).status_code
            == 200
        )
        token = client.get("/api/session").json()["token"]
        headers = {**origin, "X-PacTTS-Token": token}
        assert (
            client.post(
                "/api/channels/channelone/player/tick", json={"client_id": "OBS"}, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/channels/channeltwo/player/tick", json={"client_id": "OBS"}, headers=headers
            ).status_code
            == 403
        )
        for path in ["/api/config", "/api/state", "/api/voices", "/api/logs", "/api/channels"]:
            assert client.get(path).status_code == 403
        assert client.post("/api/cancel-all", headers=headers).status_code == 403
        job_id = "a" * 32
        shared_app.state.service.store.put(
            "job", job_id, {"id": job_id, "status": "succeeded", "channel": "channeltwo"}
        )
        assert client.get(f"/api/jobs/{job_id}/audio").status_code == 403
        tunnel.close()
        assert client.get("/api/session").status_code == 403


def test_forced_host_header_never_treated_as_loopback_owner(shared_app):
    with TestClient(shared_app, base_url="http://" + TUNNEL_HOST) as client:
        assert client.get("/api/config").status_code == 403
        assert (
            client.post(
                "/api/remote/session",
                json={"key": shared_app.state.tunnel.admin_key},
                headers={"Origin": "https://evil.example"},
            ).status_code
            == 403
        )


def test_tunnel_keys_are_distinct_and_revoked(shared_app):
    tunnel = shared_app.state.tunnel
    snapshot = tunnel.snapshot()
    assert "#admin=" in snapshot["admin_url"]
    assert "#play=" in snapshot["players"]["channelone"]
    assert snapshot["admin_url"].split("#")[1] != snapshot["players"]["channelone"].split("#")[1]
    assert tunnel.capability("not-a-key") is None
    assert tunnel.capability(tunnel.player_keys["channelone"]) == ("player", "channelone")
    tunnel.close()
    assert tunnel.capability("admin-key-" + "x" * 40) is None
    shared_app.state.studio.close()


class Download(io.BytesIO):
    headers = {}


def test_tunnel_auto_download_checks_digest(shared_app, monkeypatch):
    tunnel = shared_app.state.tunnel
    monkeypatch.setattr("pacttsclone.tunnel.shutil.which", lambda name: None)
    monkeypatch.setattr("pacttsclone.tunnel.platform.machine", lambda: "x86_64")
    monkeypatch.setattr("pacttsclone.tunnel.platform.system", lambda: "Linux")
    import os

    name = "cloudflared-windows-amd64.exe" if os.name == "nt" else "cloudflared-linux-amd64"
    data = {
        "tag_name": "test",
        "assets": [
            {
                "name": name,
                "browser_download_url": "https://github.com/cloudflare/cloudflared/releases/download/test/"
                + name,
                "digest": "sha256:" + hashlib.sha256(b"expected").hexdigest(),
                "size": 8,
            }
        ],
    }
    replies = iter([Download(json.dumps(data).encode()), Download(b"wrong-data")])
    monkeypatch.setattr(
        "pacttsclone.tunnel.urllib.request.urlopen", lambda *args, **kwargs: next(replies)
    )
    with pytest.raises(UserError, match="checksum"):
        tunnel._binary()
    assert not list((shared_app.state.service.settings.data_dir / "tools").iterdir())
    shared_app.state.studio.close()


@pytest.mark.parametrize("key", [None, {}, 123, "é"])
def test_invalid_remote_keys_return_forbidden_not_server_error(shared_app, key):
    with TestClient(shared_app, base_url="https://local-test.trycloudflare.com") as client:
        response = client.post(
            "/api/remote/session",
            json={"key": key},
            headers={"Origin": shared_app.state.tunnel.url},
        )
        assert response.status_code == 403


def test_remote_identity_history_and_shared_media_are_available(shared_app, mp3):
    import uuid

    from .conftest import wait_job

    with mp3.open("rb") as stream:
        voice = shared_app.state.studio.voices.create(
            stream, "Shared voice", "voice.mp3", "Known text"
        )
    with TestClient(shared_app, base_url="https://local-test.trycloudflare.com") as client:
        origin = {"Origin": "https://local-test.trycloudflare.com"}
        client.post(
            "/api/remote/session", json={"key": shared_app.state.tunnel.admin_key}, headers=origin
        ).raise_for_status()
        session = client.get("/api/session").json()
        assert session["remote_access"] and session["setup_ready"]
        headers = {**origin, "X-PacTTS-Token": session["token"]}
        requester = uuid.uuid4().hex
        response = client.post(
            f"/api/voices/{voice['id']}/generate",
            json={"text": "Shared speech", "requester_name": "Friend", "requester_id": requester},
            headers=headers,
        )
        assert response.status_code == 202
        done = wait_job(shared_app.state.service, response.json()["id"])
        assert done["origin"] == "cloudflare"
        assert done["requester_name"] == "Friend"
        assert done["requester_id"] == requester
        assert len(done["origin_id"]) == 32
        state = client.get("/api/state").json()
        assert any(v["id"] == voice["id"] for v in state["voices"])
        assert any(
            j["id"] == done["id"] and j["origin"] == "cloudflare" for j in state["request_history"]
        )
        assert client.get(done["output_url"]).status_code == 200
        assert client.get("/api/request-logs").status_code == 200
        assert "#play=" in state["player_links"]["playbackMain"]
        records = [
            json.loads(line)
            for line in (shared_app.state.service.logs / "requests.jsonl").read_text().splitlines()
        ]
        assert [r["event"] for r in records if r["id"] == done["id"]] == ["submitted", "finished"]
        assert all("key" not in r and "workspace" not in r for r in records)
