import json
import os
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.domain import UserError
from pacttsclone.models import ChannelConfig, EventRule
from pacttsclone.twitch_events import CHAT, EVENT_TYPES, REWARD_UPDATE, EventSubClient
from pacttsclone.twitch_oauth import FEATURE_SCOPES, TwitchAccounts, TwitchAPIError
from tests.conftest import wait_job

CLIENT_ID = "publicclient123456789"


class FakeTwitch:
    def __init__(self):
        self.calls = []
        self.login = "streamer"
        self.pending = False
        self.fail_subscription = None
        self.fail_patch = False
        self.refreshes = 0

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("/device"):
            return dict(
                device_code="private-device",
                user_code="ABCD",
                expires_in=120,
                interval=1,
                verification_uri="https://www.twitch.tv/activate",
            )
        if url.endswith("/token"):
            if kwargs["form"]["grant_type"] == "refresh_token":
                self.refreshes += 1
                return dict(access_token="new-access", refresh_token="new-refresh")
            if self.pending:
                raise TwitchAPIError(400, "authorization_pending")
            return dict(access_token="secret-access", refresh_token="secret-refresh")
        if url.endswith("/validate"):
            return dict(
                client_id=CLIENT_ID,
                login=self.login,
                user_id="123",
                scopes=list(FEATURE_SCOPES.values()),
            )
        if "/eventsub/subscriptions" in url:
            if kwargs["body"]["type"] == self.fail_subscription:
                raise TwitchAPIError(403)
            return {"data": [{"id": "sub1"}]}
        if "/custom_rewards/redemptions" in url:
            if self.fail_patch:
                raise TwitchAPIError(503)
            return {"data": []}
        if "/custom_rewards" in url:
            return {
                "data": [
                    {"id": "reward1", "title": "Voice reward", "cost": 500, "is_enabled": True}
                ]
            }
        raise AssertionError(url)


def wait(check):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out")


def seed_account(accounts):
    accounts.accounts["streamer"] = dict(
        client_id=CLIENT_ID,
        access_token="secret-access",
        refresh_token="secret-refresh",
        login="streamer",
        user_id="123",
        scopes=list(FEATURE_SCOPES.values()),
        validated_at=time.time(),
    )
    accounts._save()


def metadata(key="message1", age=0):
    return {
        "message_id": key,
        "message_timestamp": (datetime.now(UTC) - timedelta(seconds=age)).isoformat(),
    }


@pytest.fixture
def event_studio(tmp_path, engine, mp3):
    app = create_app(Settings(data_dir=tmp_path / "data"), engine)
    studio = app.state.studio
    studio.events.close()  # Settlement is driven explicitly by these assertions.
    fake = FakeTwitch()
    studio.accounts.http = fake
    seed_account(studio.accounts)
    with mp3.open("rb") as source:
        voice = studio.voices.create(source, "Voice", "reference.mp3", "Known transcript")
    rules = [
        EventRule(kind="reward", reward_id="reward1", voice_id=voice["id"]),
        EventRule(kind="bits", min_bits=100, voice_id=voice["id"]),
        EventRule(kind="gift", voice_id=voice["id"], template="{username} gifted {total} subs"),
        EventRule(kind="subscribe", voice_id=voice["id"], template="Welcome {username}"),
    ]
    studio.save_channel(
        ChannelConfig(
            name="streamer",
            transport="oauth",
            enabled=True,
            event_rules=rules,
            commands={"!voice": voice["id"]},
            user_cooldown_seconds=0,
            delay_seconds=0,
        )
    )
    studio.events.rewards("streamer")
    try:
        yield app, studio, fake, voice
    finally:
        studio.close()


def redemption(text="Hello world", key="redeem1"):
    return dict(
        id=key,
        broadcaster_user_id="123",
        user_name="Viewer",
        user_input=text,
        status="unfulfilled",
        reward={"id": "reward1", "title": "Voice reward"},
    )


def test_modes_and_rule_validation():
    assert ChannelConfig(name="legacy").transport == "irc"
    for template in [
        "{text.__class__}",
        "{username[0]}",
        "{bits:10000000}",
        "{text!r}",
        "{bad}",
        "{",
    ]:
        with pytest.raises(ValidationError):
            EventRule(kind="bits", voice_id="v", template=template)
    with pytest.raises(ValidationError):
        ChannelConfig(name="channel", transport="pubsub")
    with pytest.raises(ValidationError):
        ChannelConfig(name="channel", event_rules=[EventRule(kind="reward", voice_id="v")])
    with pytest.raises(ValidationError):
        ChannelConfig(name="channel", event_rules=[EventRule(kind="bits", voice_id="v")] * 2)


def test_device_flow_storage_refresh_and_forget(tmp_path):
    fake, changes = FakeTwitch(), []
    accounts = TwitchAccounts(tmp_path, changes.append, http=fake)
    try:
        result = accounts.start("streamer", CLIENT_ID, ["chat", "rewards", "bits"])
        assert result["pending"] and result["user_code"] == "ABCD"
        assert "private-device" not in json.dumps(result)
        wait(lambda: accounts.snapshot("streamer")["authorized"])
        wait(lambda: changes == ["streamer"])
        assert "secret-access" not in json.dumps(accounts.snapshot("streamer"))
        restored = TwitchAccounts(tmp_path, lambda _: None, http=fake)
        assert restored.account("streamer")["user_id"] == "123"
        assert any(url.endswith("/validate") for _, url, _ in fake.calls)
        if os.name != "nt":
            assert accounts.path.stat().st_mode & 0o777 == 0o600
        else:
            assert "secret-access" not in accounts.path.read_text()
        accounts._refresh("streamer")
        assert accounts.accounts["streamer"]["refresh_token"] == "new-refresh"
        accounts.forget("streamer")
        assert not accounts.snapshot("streamer")["authorized"]
        assert not TwitchAccounts(tmp_path, lambda _: None, http=fake).accounts
        restored.close()
    finally:
        accounts.close()


def test_device_flow_wrong_account_and_cancel(tmp_path):
    fake = FakeTwitch()
    fake.login = "wronguser"
    accounts = TwitchAccounts(tmp_path, lambda _: None, http=fake)
    try:
        accounts.start("streamer", CLIENT_ID, ["bits"])
        wait(lambda: not accounts.snapshot("streamer")["pending"])
        assert not accounts.snapshot("streamer")["authorized"]
        assert "matching" in accounts.snapshot("streamer")["error"]
        fake.pending = True
        accounts.start("streamer", CLIENT_ID, ["bits"])
        accounts.forget("streamer")
        assert not accounts.snapshot("streamer")["pending"]
        assert not accounts.snapshot("streamer")["authorized"]
    finally:
        accounts.close()


def test_api_401_refresh_retry_once(tmp_path):
    fake = FakeTwitch()
    accounts = TwitchAccounts(tmp_path, lambda _: None, http=fake)
    seed_account(accounts)
    attempts = []

    def http(method, url, **kwargs):
        if "/helix/" in url:
            attempts.append(kwargs["headers"]["Authorization"])
            if len(attempts) == 1:
                raise TwitchAPIError(401)
            return {"data": []}
        return fake(method, url, **kwargs)

    accounts.http = http
    assert accounts.api("streamer", "GET", "/users") == {"data": []}
    assert attempts == ["Bearer secret-access", "Bearer new-access"]
    assert fake.refreshes == 1
    accounts.close()


def test_subscription_conditions_partial_revocation_and_identity(event_studio):
    _, studio, fake, _ = event_studio
    fake.fail_subscription = EVENT_TYPES["bits"]
    client = EventSubClient("streamer", studio.accounts, studio.store, lambda *a: calls.append(a))
    calls = []
    client.subscribe("socket1")
    assert client.status == "partial"
    assert EVENT_TYPES["bits"] in client.subscription_errors
    bodies = [kw["body"] for _, url, kw in fake.calls if "/eventsub/" in url]
    assert not any(b["type"] == CHAT for b in bodies)
    assert all(b["condition"] == {"broadcaster_user_id": "123"} for b in bodies)
    notification = {
        "metadata": {"message_type": "notification", "subscription_type": EVENT_TYPES["reward"]},
        "payload": {"event": {"broadcaster_user_id": "wrong"}},
    }
    client.handle(notification)
    assert not calls
    notification["payload"]["event"]["broadcaster_user_id"] = "123"
    client.handle(notification)
    assert len(calls) == 1
    client.handle(
        {
            "metadata": {"message_type": "revocation"},
            "payload": {"subscription": {"type": EVENT_TYPES["reward"]}},
        }
    )
    assert EVENT_TYPES["reward"] not in client.subscriptions
    with pytest.raises(UserError):
        client.handle(
            {
                "metadata": {"message_type": "session_reconnect"},
                "payload": {"session": {"reconnect_url": "wss://evil.invalid/ws"}},
            }
        )


def test_reward_dedup_playback_then_fulfill(event_studio):
    _, studio, fake, _ = event_studio
    events = studio.events
    events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata())
    events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata())
    events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata("new-envelope"))
    assert len(studio.store.all("twitch_event")) == 1
    event = studio.store.all("twitch_event")[0]
    job = wait_job(studio.service, event["job_id"])
    wait(lambda: bool(studio.playback.items("streamer")))
    events.settle()
    assert studio.store.get("twitch_event", event["id"])["settlement"] == "pending"
    studio.playback.tick("streamer", "obs")
    item = studio.playback.tick("streamer", "obs")["item"]
    studio.playback.acknowledge("streamer", "obs", item["id"], "playing")
    studio.playback.acknowledge("streamer", "obs", item["id"], "played")
    events.settle()
    assert job["status"] == "succeeded"
    assert studio.store.get("twitch_event", event["id"])["settlement"] == "FULFILLED"
    patches = [kw["body"] for method, _, kw in fake.calls if method == "PATCH"]
    assert patches == [{"status": "FULFILLED"}]
    events.settle()
    assert len([c for c in fake.calls if c[0] == "PATCH"]) == 1


def test_blocked_reward_refunds_without_generation_and_retry(event_studio):
    _, studio, fake, _ = event_studio
    studio.store.patch("channel", "streamer", custom_filters=["blocked"])
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption("blocked"), metadata())
    event = studio.store.all("twitch_event")[0]
    assert event["status"] == "blocked" and not studio.service.history()
    fake.fail_patch = True
    studio.events.settle()
    value = studio.store.get("twitch_event", event["id"])
    assert value["settlement"] == "pending" and value["settlement_error"]
    fake.fail_patch = False
    studio.store.patch("twitch_event", event["id"], retry_at=0)
    studio.events.settle()
    assert studio.store.get("twitch_event", event["id"])["settlement"] == "CANCELED"


def test_bits_minimum_gift_once_and_chat_command(event_studio):
    _, studio, _, _ = event_studio
    event = dict(
        bits=99,
        user_name="Viewer",
        broadcaster_user_id="123",
        message={
            "text": "cheer100 hello",
            "fragments": [
                {"type": "cheermote", "text": "cheer100"},
                {"type": "text", "text": " hello"},
            ],
        },
    )
    studio.events.receive("streamer", EVENT_TYPES["bits"], event, metadata())
    assert not studio.service.history()
    event["bits"] = 100
    studio.events.receive("streamer", EVENT_TYPES["bits"], event, metadata("bits"))
    assert studio.service.history()[0]["request"]["text"] == "hello"
    studio.events.receive(
        "streamer",
        EVENT_TYPES["subscribe"],
        dict(is_gift=True, user_name="Recipient"),
        metadata("recipient"),
    )
    assert len(studio.service.history()) == 1
    studio.events.receive(
        "streamer", EVENT_TYPES["gift"], dict(total=5, user_name="Gifter"), metadata("gift")
    )
    studio.events.receive(
        "streamer",
        CHAT,
        dict(chatter_user_name="Chatter", message={"text": "!voice command speech"}),
        metadata("chat"),
    )
    assert len(studio.service.history()) == 3
    assert any(j["request"]["text"] == "Gifter gifted 5 subs" for j in studio.service.history())


def test_old_events_irc_mode_and_persistent_claims(event_studio):
    _, studio, _, _ = event_studio
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata(age=601))
    assert not studio.store.all("twitch_event")
    studio.store.patch("channel", "streamer", transport="irc")
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata())
    assert not studio.store.all("twitch_event")
    studio.store.patch("channel", "streamer", transport="oauth")
    studio.store.put("twitch_seen", "streamer:message1", {"id": "streamer:message1"})
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata())
    assert not studio.store.all("twitch_event")


def test_cancelled_redemption_stops_queued_audio(event_studio):
    _, studio, _, _ = event_studio
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata())
    event = studio.store.all("twitch_event")[0]
    wait_job(studio.service, event["job_id"])
    wait(lambda: bool(studio.playback.items("streamer")))
    studio.events.receive(
        "streamer", REWARD_UPDATE, dict(id="redeem1", status="canceled"), metadata("update")
    )
    assert studio.playback.items("streamer")[0]["status"] == "cancelled"
    assert studio.store.get("twitch_event", event["id"])["settlement"] == "CANCELED"


def test_oauth_routes_are_host_only_and_never_leak_tokens(event_studio):
    app, studio, _, _ = event_studio
    studio.store.patch("channel", "streamer", enabled=False)
    with TestClient(app, base_url="http://127.0.0.1:7860") as client:
        headers = {"X-PacTTS-Token": client.get("/api/session").json()["token"]}
        snapshot = client.get("/api/twitch/streamer/authorization")
        assert snapshot.status_code == 200
        assert "secret-access" not in snapshot.text and "secret-refresh" not in snapshot.text
        assert client.post("/api/twitch/streamer/authorization", json={}).status_code == 403
        assert (
            client.post(
                "/api/twitch/streamer/rewards", json={"title": "TTS", "cost": 500}, headers=headers
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/twitch/streamer/rewards", json={"title": "", "cost": -1}, headers=headers
            ).status_code
            == 422
        )
        tunnel = app.state.tunnel
        tunnel.url, tunnel.status, tunnel.admin_key = (
            "https://public.example",
            "running",
            "admin-key",
        )
        remote = {"Host": "public.example", "Origin": "https://public.example"}
        assert (
            client.post(
                "/api/remote/session", json={"key": "admin-key"}, headers=remote
            ).status_code
            == 200
        )
        remote["Cookie"] = "pactts_admin=admin-key"
        assert client.get("/api/twitch/streamer/authorization", headers=remote).status_code == 403
        assert (
            client.delete(
                "/api/twitch/streamer/authorization", headers={**remote, **headers}
            ).status_code
            == 403
        )
        assert client.get("/api/state", headers=remote).status_code == 200
        assert "secret-access" not in client.get("/api/state", headers=remote).text


def test_websocket_reconnect_transfers_without_resubscription(event_studio):
    _, studio, _, _ = event_studio
    client = EventSubClient("streamer", studio.accounts, studio.store, lambda *a: None)
    order, subscriptions = [], []
    welcome = {
        "metadata": {"message_type": "session_welcome"},
        "payload": {"session": {"id": "session", "keepalive_timeout_seconds": 30}},
    }

    class Socket:
        def __init__(self, number):
            self.number, self.count = number, 0

        def recv(self, timeout):
            self.count += 1
            if self.count == 1:
                order.append(("welcome", self.number))
                return json.dumps(welcome)
            if self.number == 1:
                if self.count > 2:
                    raise TimeoutError
                return json.dumps(
                    {
                        "metadata": {"message_type": "session_reconnect"},
                        "payload": {
                            "session": {
                                "reconnect_url": "wss://eventsub.wss.twitch.tv/ws?reconnect=1"
                            }
                        },
                    }
                )
            client.stop.set()
            return json.dumps({"metadata": {"message_type": "session_keepalive"}})

        def close(self):
            order.append(("close", self.number))

    connections = []

    def connector(url, **kwargs):
        connections.append(url)
        return Socket(len(connections))

    client.connector = connector
    client.subscribe = subscriptions.append
    client._run()
    assert subscriptions == ["session"]
    assert len(connections) == 2
    assert order.index(("welcome", 2)) < order.index(("close", 1))


def test_public_scope_selection_rejects_unknown(tmp_path):
    accounts = TwitchAccounts(tmp_path, lambda _: None, http=FakeTwitch())
    for features in [[], ["admin"], "bits", [None]]:
        with pytest.raises(UserError):
            accounts.start("streamer", CLIENT_ID, features)
    accounts.close()


def test_reconnect_recovers_only_old_unclaimed_managed_redemptions(event_studio):
    _, studio, fake, _ = event_studio
    original = studio.accounts.http
    old = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    new = datetime.now(UTC).isoformat()

    def http(method, url, **kwargs):
        if method == "GET" and "/custom_rewards/redemptions" in url:
            return {
                "data": [
                    dict(id="missed", redeemed_at=old, user_name="Viewer"),
                    dict(id="new", redeemed_at=new, user_name="Viewer"),
                ],
                "pagination": {},
            }
        return original(method, url, **kwargs)

    studio.accounts.http = http
    studio.events.reconcile("streamer")
    events = studio.store.all("twitch_event")
    assert len(events) == 1 and events[0]["redemption_id"] == "missed"
    assert not studio.service.history()
    studio.events.settle()
    assert studio.store.get("twitch_event", events[0]["id"])["settlement"] == "CANCELED"
    studio.events.reconcile("streamer")
    assert len(studio.store.all("twitch_event")) == 1
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption(key="missed"), metadata())
    assert not studio.service.history()
    assert [kw["body"] for method, _, kw in fake.calls if method == "PATCH"] == [
        {"status": "CANCELED"}
    ]


def test_power_up_without_message_and_scope_failure_are_visible(event_studio):
    _, studio, _, voice = event_studio
    studio.store.patch(
        "channel",
        "streamer",
        event_rules=[
            EventRule(
                kind="bits", voice_id=voice["id"], template="{username} used {bits} Bits"
            ).model_dump()
        ],
    )
    studio.events.receive(
        "streamer",
        EVENT_TYPES["bits"],
        dict(bits=100, message=None, user_name="Viewer"),
        metadata(),
    )
    assert studio.service.history()[0]["request"]["text"] == "Viewer used 100 Bits"


def test_irc_and_oauth_switch_closes_old_client(tmp_path, engine, monkeypatch):
    app = create_app(Settings(data_dir=tmp_path / "data"), engine)
    studio = app.state.studio
    created = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.status, self.error, self.closed = "connected", None, False
            created.append(self)

        def start(self):
            pass

        def close(self):
            self.closed = True

    studio.twitch_factory = Client
    monkeypatch.setattr("pacttsclone.studio.EventSubClient", Client)
    seed_account(studio.accounts)
    studio.start()
    try:
        studio.save_channel(ChannelConfig(name="streamer", enabled=True))
        first = studio.clients["streamer"]
        studio.save_channel(ChannelConfig(name="streamer", enabled=True, transport="oauth"))
        assert not first.closed
        assert studio.clients["streamer"] is first
        second = studio.event_clients["streamer"]
        assert studio.clients["streamer"] is not second
        assert studio.client_modes["streamer"] == "oauth"
        studio.save_channel(ChannelConfig(name="streamer", enabled=True, transport="irc"))
        assert second.closed and studio.client_modes["streamer"] == "irc"
        assert "streamer" not in studio.event_clients
        studio.save_channel(ChannelConfig(name="streamer", enabled=True, transport="oauth"))
        irc, events = studio.clients["streamer"], studio.event_clients["streamer"]
        studio.set_channel_connection("streamer", False)
        assert irc.closed and events.closed
        assert "streamer" not in studio.clients and "streamer" not in studio.event_clients
    finally:
        studio.close()


@pytest.mark.parametrize(
    "kind", ["resub", "subscription_end", "follow", "raid", "online", "offline"]
)
def test_other_event_rules_use_same_generation_queue(event_studio, kind):
    _, studio, _, voice = event_studio
    studio.store.patch(
        "channel",
        "streamer",
        event_rules=[
            EventRule(
                kind=kind, voice_id=voice["id"], template="{username} event {viewers} {months}"
            ).model_dump()
        ],
    )
    studio.events.receive(
        "streamer",
        EVENT_TYPES[kind],
        dict(user_name="Viewer", viewers=42, cumulative_months=6),
        metadata(),
    )
    assert studio.service.history()[0]["request"]["text"] == "Viewer event 42 6"


def test_unmanaged_reward_never_calls_fulfillment_api(event_studio):
    _, studio, fake, _ = event_studio
    studio.store.put(
        "twitch_rewards", "streamer", {"rewards": [{"id": "reward1", "manageable": False}]}
    )
    studio.events.receive("streamer", EVENT_TYPES["reward"], redemption(), metadata())
    event = studio.store.all("twitch_event")[0]
    assert event["settlement"] == "external"
    wait_job(studio.service, event["job_id"])
    studio.events.settle()
    assert not [c for c in fake.calls if c[0] == "PATCH"]


def test_lost_fulfillment_response_reconciles_terminal_status(event_studio):
    _, studio, _, _ = event_studio
    studio.store.put(
        "twitch_event",
        "lost",
        dict(
            id="lost",
            channel="streamer",
            kind="reward",
            settlement="pending",
            created_at=time.time(),
            status="blocked",
            job_id=None,
            redemption_id="redeem1",
            reward_id="reward1",
        ),
    )
    original = studio.accounts.http

    def http(method, url, **kwargs):
        if "/custom_rewards/redemptions" in url:
            if method == "PATCH":
                raise TwitchAPIError(404)
            return {"data": [{"id": "redeem1", "status": "FULFILLED"}]}
        return original(method, url, **kwargs)

    studio.accounts.http = http
    studio.events.settle()
    assert studio.store.get("twitch_event", "lost")["settlement"] == "FULFILLED"


def test_oauth_errors_do_not_leak_request_or_response_secrets(monkeypatch):
    import io
    import urllib.error

    from pacttsclone.twitch_oauth import http_json

    def failed(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://id.twitch.tv/oauth2/token",
            400,
            "error",
            {},
            io.BytesIO(b'{"message":"authorization_pending"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", failed)
    with pytest.raises(TwitchAPIError) as caught:
        http_json("POST", "https://id.twitch.tv/oauth2/token", form={"device_code": "secret"})
    assert caught.value.code == "authorization_pending"
    assert "secret" not in str(caught.value)


def test_handoff_drains_notifications_while_new_welcome_is_pending(event_studio):
    _, studio, _, _ = event_studio
    received, order = [], []
    client = EventSubClient(
        "streamer", studio.accounts, studio.store, lambda *args: received.append(args)
    )
    client.subscriptions = [CHAT]
    release = threading.Event()

    class NewSocket:
        def recv(self, timeout):
            assert release.wait(2)
            order.append("new welcome")
            return json.dumps(
                {
                    "metadata": {"message_type": "session_welcome"},
                    "payload": {"session": {"id": "new", "keepalive_timeout_seconds": 30}},
                }
            )

        def close(self):
            order.append("new close")

    class OldSocket:
        count = 0

        def recv(self, timeout):
            self.count += 1
            if self.count == 1:
                release.set()
                return json.dumps(
                    {
                        "metadata": {"message_type": "notification", "subscription_type": CHAT},
                        "payload": {
                            "event": {
                                "broadcaster_user_id": "123",
                                "message": {"text": "during handoff"},
                            }
                        },
                    }
                )
            time.sleep(0.01)
            raise TimeoutError

        def close(self):
            order.append("old close")

    new, session = client._handoff(
        OldSocket(), lambda *a, **kw: NewSocket(), "wss://eventsub.wss.twitch.tv/ws?reconnect=1"
    )
    assert session["id"] == "new" and isinstance(new, NewSocket)
    assert received[0][2]["message"]["text"] == "during handoff"
    assert order.index("new welcome") < order.index("old close")
