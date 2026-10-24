import io
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.domain import BusyError, GenerationRequest, UserError
from pacttsclone.hotkey import GlobalHotkey, parse_hotkey
from pacttsclone.models import AppConfig, ChannelConfig
from pacttsclone.moderation import blocked_reason
from pacttsclone.resources import Resources
from pacttsclone.service import GenerationService
from pacttsclone.store import Store
from pacttsclone.studio import Studio
from pacttsclone.twitch import TwitchClient, parse_irc
from pacttsclone.worker import ProcessRunner

from .conftest import wait_job
from .worker_fake import ProcessFakeEngine


def wait_until(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.03)
    raise AssertionError("Condition did not become true")


class FakeIRC:
    def __init__(self, channel, callback):
        self.status, self.error = "disconnected", None

    def start(self):
        self.status = "connected"

    def close(self):
        self.status = "disconnected"


@pytest.fixture
def studio(tmp_path, engine):
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    value = Studio(service, twitch_factory=FakeIRC)
    value.start()
    try:
        yield value
    finally:
        value.close()


def voice(studio, mp3, transcript="Known exact reference."):
    with mp3.open("rb") as ref:
        return studio.voices.create(ref, "Lula test voice", "lula.mp3", transcript)


def channel(studio, voice_id, **changes):
    return studio.save_channel(
        ChannelConfig(name="testchannel", enabled=True, commands={"!lula": voice_id}, **changes)
    )


@pytest.mark.parametrize(
    "level,text,blocked",
    [
        ("slurs", "oi bom dia", False),
        ("slurs", "porra", False),
        ("profanity", "porra", True),
        ("strict", "pornografia", True),
        ("slurs", "FAGGOT", True),
        ("slurs", "fagg0t", True),
        ("slurs", "fag\u200bgot", True),
        ("slurs", "sapatão", True),
        ("profanity", "classical music", False),
    ],
)
def test_filter_levels_and_normalization(level, text, blocked):
    assert bool(blocked_reason(text, level, [])) is blocked


def test_custom_phrase_uses_boundaries():
    assert blocked_reason("um segredo oculto!", "slurs", ["SÉGREDO oculto"])
    assert not blocked_reason("passage", "slurs", ["ass"])
    assert not blocked_reason("ordinary words", "slurs", ["[.*]"])


@pytest.mark.parametrize("value", ["https://twitch.tv/user", "../escape", "abc def", "static"])
def test_invalid_channel(value):
    with pytest.raises(ValueError):
        ChannelConfig(name=value)


@pytest.mark.parametrize("value", ["F9", "Ctrl+F12", "Win+F9", "Ctrl+"])
def test_invalid_global_hotkey(value):
    with pytest.raises(ValueError):
        parse_hotkey(value)


def test_hotkey_parse_and_unavailable_platform(monkeypatch):
    assert parse_hotkey("Ctrl+Alt+F9") == (0x4003, 0x78)
    monkeypatch.setattr("pacttsclone.hotkey.sys.platform", "linux")
    hotkey = GlobalHotkey(lambda: None)
    assert "Unavailable" in hotkey.configure("Ctrl+Alt+F9")
    hotkey.close()


def test_store_persistence_and_atomic_patch(tmp_path):
    store = Store(tmp_path)
    store.put("voice", "one", {"title": "Lula", "transcript": "reference"})
    store.patch("voice", "one", title="New title")
    store.close()
    store = Store(tmp_path)
    try:
        assert store.get("voice", "one") == {"title": "New title", "transcript": "reference"}
    finally:
        store.close()


def test_saved_voice_thumbnail_transcript_and_edit(studio, mp3):
    thumbnail = io.BytesIO()
    Image.new("RGB", (640, 480)).save(thumbnail, "PNG")
    with mp3.open("rb") as ref:
        value = studio.voices.create(
            ref, "Lula", "../../original.mp3", "Exact text", thumbnail.getvalue()
        )
    assert value["original_filename"] == "original.mp3"
    assert value["status"] == "ready"
    path = studio.voices.root / value["id"] / "thumbnail.jpg"
    with Image.open(path) as image:
        assert max(image.size) <= 320
    studio.voices.update(value["id"], "Edited", "Updated text")
    assert studio.store.get("voice", value["id"])["transcript"] == "Updated text"


def test_voice_automatic_transcription_saved_once(studio, mp3, engine):
    v = voice(studio, mp3, transcript="")
    wait_until(lambda: studio.store.get("voice", v["id"])["status"] == "ready")
    saved = studio.store.get("voice", v["id"])
    assert saved["transcript"]
    for _ in range(2):
        job = studio.voices.generate(v["id"], GenerationRequest(text="New speech"))
        result = wait_job(studio.service, job["id"])
        assert result["status"] == "succeeded"
        assert result["request"]["ref_text"] == saved["transcript"]
    assert len(engine.calls) == 2


def test_invalid_voice_does_not_persist(studio, tmp_path):
    with pytest.raises(UserError):
        studio.voices.create(io.BytesIO(b"not mp3"), "Bad", "bad.mp3")
    assert studio.store.all("voice") == []
    assert list(studio.voices.root.iterdir()) == []


def test_chat_filter_before_generation_and_cooldown(studio, mp3):
    v = voice(studio, mp3)
    channel(studio, v["id"], custom_filters=["private phrase"])
    assert studio.receive("testchannel", "alice", "!lula private phrase") is None
    assert studio.service.history() == []
    job = studio.receive("testchannel", "alice", "!lula bom dia")
    assert job
    assert studio.receive("testchannel", "alice", "!lula outra mensagem") is None
    assert studio.receive("testchannel", "bob", "!unknown hello") is None
    assert studio.receive("testchannel", "bob", "!lula FAGGOT") is None
    done = wait_job(studio.service, job["id"])
    assert done["status"] == "succeeded"
    wait_until(lambda: studio.playback.items("testchannel"))
    assert len(studio.playback.items("testchannel")) == 1
    events = studio.store.all("chat")
    assert len(events) == 4
    assert any(e["reason"] == "user cooldown" for e in events)


def rendered(studio, mp3):
    v = voice(studio, mp3)
    channel(studio, v["id"], user_cooldown_seconds=0)
    job = studio.receive("testchannel", "alice", "!lula bom dia")
    result = wait_job(studio.service, job["id"])
    wait_until(lambda: studio.playback.items("testchannel"))
    return result


def test_playback_countdown_fifo_lease_cancel_replay(studio, mp3):
    job = rendered(studio, mp3)
    now = [100.0]
    # Existing queue is kept; replace the clock only for deterministic countdowns.
    studio.playback.clock = lambda: now[0]
    playback = studio.playback
    first = playback.tick("testchannel", "OBS1")
    assert first["item"]["status"] == "countdown"
    assert first["item"]["deadline"] == 105
    assert not playback.tick("testchannel", "OBS2")["owner"]
    now[0] = 104
    assert playback.tick("testchannel", "OBS1")["item"]["status"] == "countdown"
    now[0] = 105
    ready = playback.tick("testchannel", "OBS1")["item"]
    assert ready["status"] == "ready"
    playback.cancel(ready["id"])
    with pytest.raises(UserError):
        playback.acknowledge("testchannel", "OBS1", ready["id"], "playing")
    replay = playback.enqueue(job, replay=True)
    assert replay["job_id"] == job["id"]
    assert len(studio.service.history()) == 1
    now[0] = 106
    assert playback.tick("testchannel", "OBS1")["item"]["id"] == replay["id"]
    now[0] = 111
    playback.tick("testchannel", "OBS1")
    playback.acknowledge("testchannel", "OBS1", replay["id"], "playing")
    playback.acknowledge("testchannel", "OBS1", replay["id"], "played")
    assert playback.tick("testchannel", "OBS1")["item"] is None


def test_panic_pauses_and_blocks_future_playback(studio, mp3):
    rendered(studio, mp3)
    item = studio.playback.tick("testchannel", "OBS")["item"]
    studio.playback.panic()
    assert studio.store.get("playback", item["id"])["status"] == "cancelled"
    assert studio.playback.tick("testchannel", "OBS")["paused"]


def test_player_disconnect_does_not_repeat_audio(studio, mp3):
    rendered(studio, mp3)
    now = [100.0]
    studio.playback.clock = lambda: now[0]
    studio.playback.tick("testchannel", "one")
    now[0] = 105
    item = studio.playback.tick("testchannel", "one")["item"]
    studio.playback.acknowledge("testchannel", "one", item["id"], "playing")
    now[0] = 120
    state = studio.playback.tick("testchannel", "two")
    assert state["paused"]
    assert studio.store.get("playback", item["id"])["status"] == "interrupted"


def test_replay_rechecks_changed_filter(studio, mp3):
    job = rendered(studio, mp3)
    studio.store.patch("channel", "testchannel", custom_filters=["bom dia"])
    with pytest.raises(UserError, match="filter"):
        studio.playback.enqueue(job, replay=True)


def test_metrics_report_and_jsonl(studio, mp3):
    v = voice(studio, mp3)
    job = studio.voices.generate(v["id"], GenerationRequest(text="Hello"))
    result = wait_job(studio.service, job["id"])
    assert result["metrics"]["worker_cpu_seconds"] >= 0
    assert {s["name"] for s in result["metrics"]["stages"]} >= {"decode", "encode"}
    assert all(s["wall_seconds"] >= 0 for s in result["metrics"]["stages"])
    assert "not GPU busy" in result["metrics"]["accounting_note"]
    report = json.loads((studio.service.logs / "generation.jsonl").read_text().splitlines()[-1])
    assert report["id"] == job["id"]
    assert report["voice_title"] == v["title"]
    assert report["metrics"] == result["metrics"]


def test_queue_limit_config_and_cancel_queued(studio, mp3, engine):
    release = threading.Event()
    original = engine.synthesize
    engine.synthesize = lambda *args: release.wait(5) and original(*args)
    studio.configure(AppConfig(max_queue=2))
    v = voice(studio, mp3)
    try:
        first = studio.voices.generate(v["id"], GenerationRequest(text="one"))
        second = studio.voices.generate(v["id"], GenerationRequest(text="two"))
        with pytest.raises(BusyError):
            studio.voices.generate(v["id"], GenerationRequest(text="three"))
        with pytest.raises(BusyError):
            studio.configure(AppConfig(device="cpu"))
        studio.cancel_job(second["id"])
        assert studio.service.get(second["id"])["status"] == "cancelled"
    finally:
        release.set()
        wait_job(studio.service, first["id"])


def test_actual_spawn_cancel_recovery_and_cleanup(tmp_path, mp3):
    settings = Settings(data_dir=tmp_path / "isolated")
    runner = ProcessRunner(settings, engine_factory=ProcessFakeEngine)
    service = GenerationService(settings, runner=runner)
    try:
        with mp3.open("rb") as ref:
            first = service.submit(ref, GenerationRequest(text="hang", ref_text="known"))
        wait_until(lambda: service.get(first["id"])["stage"] == "inference")
        old_pid = runner.pid
        assert old_pid
        started = time.monotonic()
        service.cancel(first["id"])
        wait_until(lambda: service.get(first["id"])["status"] == "cancelled")
        assert time.monotonic() - started < 5
        assert runner.pid is None
        assert not service.output_path(first["id"]).exists()
        assert not list(service.temporary.iterdir())
        with mp3.open("rb") as ref:
            second = service.submit(ref, GenerationRequest(text="works", ref_text="known"))
        assert wait_job(service, second["id"])["status"] == "succeeded"
        assert runner.pid != old_pid
    finally:
        service.close()


def test_irc_parse_ping_dedupe_and_channel_boundary():
    received, sent = [], []
    client = TwitchClient("target", lambda *args: received.append(args))
    client.handle("PING :tmi.twitch.tv", sent.append)
    assert sent == ["PONG :tmi.twitch.tv\r\n"]
    line = (
        "@id=123;display-name=Some\\sName :user!user@user.tmi.twitch.tv PRIVMSG #target :!lula oi"
    )
    client.handle(line, sent.append)
    client.handle(line, sent.append)
    client.handle(line.replace("#target", "#other").replace("123", "456"), sent.append)
    assert received == [("target", "user", "!lula oi", "123")]
    assert parse_irc(line)["tags"]["display-name"] == "Some Name"
    with pytest.raises(ConnectionError):
        client.handle("RECONNECT", sent.append)


def test_cancel_all_disconnects_and_preserves_completed_audio(studio, mp3):
    result = rendered(studio, mp3)
    studio.cancel_all()
    assert not studio.store.get("channel", "testchannel")["enabled"]
    assert studio.store.get("channel", "testchannel")["paused"]
    assert studio.service.output_path(result["id"]).is_file()
    assert not [
        i for i in studio.playback.items("testchannel") if i["status"] in {"queued", "playing"}
    ]


def test_resources_available_or_null_without_failure():
    snapshot = Resources().sample()
    assert snapshot["system_ram_total_bytes"] > 0
    assert snapshot["process_ram_bytes"] is None or snapshot["process_ram_bytes"] > 0


def test_new_api_voice_configuration_and_obs_routes(tmp_path, mp3, engine):
    app = create_app(Settings(data_dir=tmp_path / "api"), engine)
    app.state.studio.twitch_factory = FakeIRC
    with TestClient(app, base_url="http://127.0.0.1:7860") as client:
        token = client.get("/api/session").json()["token"]
        headers = {"X-PacTTS-Token": token}
        result = client.post(
            "/api/voices",
            files={"reference": ("lula.mp3", mp3.read_bytes())},
            data={"title": "Lula", "transcript": "reference"},
            headers=headers,
        )
        assert result.status_code == 201
        v = result.json()
        assert client.get("/api/voices").json()[0]["id"] == v["id"]
        assert (
            client.get(f"/api/voices/{v['id']}/reference").headers["content-type"] == "audio/mpeg"
        )
        config = ChannelConfig(name="testchannel", commands={"!lula": v["id"]}).model_dump()
        assert (
            client.put("/api/channels/testchannel", json=config, headers=headers).status_code == 200
        )
        assert "obs.js" in client.get("/testchannel").text
        assert "app.js" in client.get("/testchannel/control").text
        assert client.get("/unknown").status_code == 404
        assert (
            client.put(
                "/api/config", json=AppConfig(device="cpu").model_dump(), headers=headers
            ).status_code
            == 200
        )
        assert client.get("/api/config").json()["device"] == "cpu"
        assert client.get("/api/resources").status_code == 200
        assert client.post("/api/panic").status_code == 403
        assert client.post("/api/panic", headers=headers).status_code == 200
        assert client.post("/api/cancel-all", headers=headers).status_code == 200


def test_secondary_obs_mirrors_without_advancing_queue(studio, mp3):
    rendered(studio, mp3)
    clock = [100.0]
    studio.playback.clock = lambda: clock[0]
    studio.playback.tick("testchannel", "coordinator")
    clock[0] = 105
    item = studio.playback.tick("testchannel", "coordinator")["item"]
    studio.playback.acknowledge("testchannel", "coordinator", item["id"], "playing")
    mirror = studio.playback.tick("testchannel", "friend-OBS")
    assert not mirror["owner"]
    assert mirror["item"]["id"] == item["id"]
    assert mirror["item"]["started_at"] == 105
    with pytest.raises(UserError):
        studio.playback.acknowledge("testchannel", "friend-OBS", item["id"], "played")
    assert studio.store.get("playback", item["id"])["status"] == "playing"


def test_native_windows_hotkey_message_loop(monkeypatch):
    import ctypes
    from types import SimpleNamespace
    from unittest.mock import Mock

    hotkey = None
    dispatched = [False]
    callback = Mock(side_effect=lambda: hotkey.stop.set())

    def peek(pointer, *args):
        if dispatched[0]:
            return 0
        dispatched[0] = True
        pointer._obj.message = 0x0312
        return 1

    native = SimpleNamespace(
        RegisterHotKey=Mock(return_value=1), PeekMessageW=peek, UnregisterHotKey=Mock()
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=native), raising=False)
    monkeypatch.setattr("pacttsclone.hotkey.sys.platform", "win32")
    hotkey = GlobalHotkey(callback)
    assert "Active" in hotkey.configure("Ctrl+Alt+F9")
    wait_until(lambda: callback.call_count == 1)
    hotkey.close()
    native.UnregisterHotKey.assert_called_once()


def test_irc_client_frames_and_reconnect():
    received, sent = [], []
    rounds = [0]
    client = None

    class Socket:
        def __init__(self, lines):
            self.lines = iter(lines)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send(self, line):
            sent.append(line)

        def recv(self, timeout):
            try:
                return next(self.lines)
            except StopIteration:
                client.stop.set()
                raise TimeoutError() from None

        def close(self):
            pass

    def connector(url, **kwargs):
        assert url == "wss://irc-ws.chat.twitch.tv:443"
        rounds[0] += 1
        if rounds[0] == 1:
            return Socket(
                [
                    ":srv 001 guest :Welcome\r\nPING :tmi.",
                    "twitch.tv\r\n@id=a :u!u@h PRIVMSG #target :!lula oi\r\nRECONNECT\r\n",
                ]
            )
        return Socket(
            [
                "@id=a :u!u@h PRIVMSG #target :!lula oi\r\n",
                "@id=b :u!u@h PRIVMSG #target :!lula again\r\n",
            ]
        )

    client = TwitchClient("target", lambda *args: received.append(args), connector)
    client.start()
    try:
        wait_until(lambda: len(received) == 2)
        assert rounds[0] == 2
        assert "PONG :tmi.twitch.tv\r\n" in sent
        assert not any(s.startswith("PRIVMSG") for s in sent)
    finally:
        client.close()


def test_restart_marks_preparing_voice_retryable(tmp_path, engine):
    settings = Settings(data_dir=tmp_path / "restart")
    service = GenerationService(settings, engine)
    service.store.put(
        "voice",
        "saved",
        {
            "id": "saved",
            "title": "Voice",
            "status": "pending",
            "preparation_job_id": "lost",
            "transcript": "",
        },
    )
    service.close()
    next_service = GenerationService(settings, engine)
    studio = Studio(next_service)
    try:
        assert studio.store.get("voice", "saved")["status"] == "cancelled"
    finally:
        studio.close()


def test_general_player_reuses_local_and_channel_audio(studio, mp3):
    preset = voice(studio, mp3)
    local = studio.voices.generate(preset["id"], GenerationRequest(text="General player test"))
    local = wait_job(studio.service, local["id"])
    assert not local.get("channel")
    assert studio.channels() == []
    assert "playbackMain" not in studio.clients
    item = studio.playback.enqueue(local, destination="playbackMain")
    assert item["channel"] == "playbackMain"
    assert studio.service.get(local["id"]).get("channel") is None
    tick = studio.playback.tick("playbackMain", "OBS")
    assert tick["item"]["status"] == "countdown"
    studio.playback.cancel(item["id"])
    assert studio.playback.items("playbackMain")[0]["status"] == "cancelled"
    channel(studio, preset["id"])
    chat_job = studio.receive("testchannel", "viewer", "!lula Good morning")
    chat_job = wait_job(studio.service, chat_job["id"])
    copied = studio.playback.enqueue(chat_job, destination="playbackMain")
    assert copied["channel"] == "playbackMain"
    assert studio.service.get(chat_job["id"])["channel"] == "testchannel"
    studio.playback.panic()
    assert studio.playback.snapshot("playbackMain")["paused"]


def test_general_player_api_and_shared_audio_acl(tmp_path, engine, mp3):
    app = create_app(Settings(data_dir=tmp_path / "general"), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = {"X-PacTTS-Token": client.get("/api/session").json()["token"]}
        assert client.get("/playbackMain").status_code == 200
        assert client.get("/playbackMain/control").status_code == 200
        response = client.put(
            "/api/general-playback", json={"name": "general", "delay_seconds": 0}, headers=headers
        )
        assert response.status_code == 200
        studio = app.state.studio
        preset = voice(studio, mp3)
        job = wait_job(
            studio.service,
            studio.voices.generate(preset["id"], GenerationRequest(text="Hello there"))["id"],
        )
        other = wait_job(
            studio.service,
            studio.voices.generate(preset["id"], GenerationRequest(text="Private audio"))["id"],
        )
        cap = ("player", "playbackMain")
        assert not app.state.tunnel.permitted(cap, job["output_url"], "GET")
        queued = client.post(f"/api/channels/playbackMain/replay/{job['id']}", headers=headers)
        assert queued.status_code == 201
        assert app.state.tunnel.permitted(cap, job["output_url"], "GET")
        assert not app.state.tunnel.permitted(cap, other["output_url"], "GET")
        assert not app.state.tunnel.permitted(("player", "otherchannel"), job["output_url"], "GET")
        tick = studio.playback.tick("playbackMain", "test")
        assert tick["item"]["status"] == "countdown"
        tick = studio.playback.tick("playbackMain", "test")
        assert tick["item"]["status"] == "ready"
        studio.playback.acknowledge("playbackMain", "test", queued.json()["id"], "playing")
        studio.playback.acknowledge("playbackMain", "test", queued.json()["id"], "played")
        assert (
            client.put(
                "/api/general-playback",
                json={"name": "general", "delay_seconds": -1},
                headers=headers,
            ).status_code
            == 422
        )
        client.put(
            "/api/general-playback",
            json={"name": "general", "custom_filters": ["hello"]},
            headers=headers,
        )
        assert (
            client.post(
                f"/api/channels/playbackMain/replay/{job['id']}", headers=headers
            ).status_code
            == 422
        )
