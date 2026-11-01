import asyncio
import json
import threading

from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest
from pacttsclone.events import EventDispatcher
from pacttsclone.models import ChannelConfig
from pacttsclone.store import Store


class Connected:
    async def is_disconnected(self):
        return False


def test_slow_consumers_keep_only_latest_per_topic_and_immutable_data():
    events = EventDispatcher()
    value = {"progress": 0}
    for i in range(10000):
        value["progress"] = i
        events.publish("state", value)
    value["progress"] = "mutated"
    cursor, frames = events.read(0)
    assert cursor == 10000
    assert len(frames) == len(events.latest) == 1
    assert json.loads(frames[0][2]) == {"progress": 9999}
    events.publish("state", {"progress": 9999})
    assert events.read(cursor) == (cursor, [])


def test_threaded_store_invalidations_observe_committed_state(tmp_path):
    events = EventDispatcher()
    store = Store(tmp_path, events)
    try:
        threads = [threading.Thread(target=store.put, args=("voice", str(i), {"id": str(i)}))
                   for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert events.changes() == {"voice"}
        assert len(store.all("voice")) == 20
        store.patch("voice", "0", title="saved")
        assert events.changes() == {"voice"}
        assert store.get("voice", "0")["title"] == "saved"
        store.delete("voice", "0")
        assert events.changes() == {"voice"}
        assert store.get("voice", "0") is None
    finally:
        store.close()


def test_multiple_streams_reconnect_resync_and_cancellation_cleanup():
    async def check():
        events = EventDispatcher()
        events.publish("state", {"stale": True})
        a, b = events.stream(Connected()), events.stream(Connected())
        assert "event: sync" in await anext(a)
        assert "event: sync" in await anext(b)
        assert events.connections == 2
        events.publish("state", {"succeeded": True})
        for stream in (a, b):
            frame = await anext(stream)
            assert '"succeeded":true' in frame and '"stale"' not in frame
        await a.aclose()
        assert events.connections == 1
        waiting = asyncio.create_task(anext(b))
        await asyncio.sleep(0.01)
        waiting.cancel()
        try:
            await waiting
        except asyncio.CancelledError:
            pass
        assert events.connections == 0
        reconnected = events.stream(Connected())
        assert "event: sync" in await anext(reconnected)
        events.closed = True
        assert [frame async for frame in reconnected] == []
        assert events.connections == 0
    asyncio.run(check())


def test_sse_boundary_and_quick_tunnel_fallback(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine)
    tunnel = app.state.tunnel
    tunnel.url, tunnel.status = "https://events-test.trycloudflare.com", "running"
    tunnel.admin_key = "admin-event-key"
    tunnel.player_keys["playbackMain"] = "player-event-key"
    with TestClient(app, base_url=tunnel.url) as remote:
        assert remote.get("/api/events").status_code == 403
        origin = {"Origin": tunnel.url}
        assert remote.post("/api/remote/session", headers=origin,
                           json={"key": tunnel.admin_key}).status_code == 200
        assert remote.get("/api/session").json()["realtime"]["sse"] is False
        assert remote.get("/api/events").status_code == 204
        remote.cookies.clear()
        assert remote.post("/api/remote/session", headers=origin, json={
            "key": "player-event-key", "channel": "playbackMain",
        }).status_code == 200
        assert remote.get("/api/events").status_code == 403
        assert remote.get("/api/events", headers={"Origin": "https://evil.test"}).status_code == 403
        tunnel.admin_key = None
        tunnel.player_keys.clear()
        assert remote.get("/api/events").status_code == 403


def test_sampler_coalesces_changes_and_preserves_section_versions(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine)
    service, sampler = app.state.service, app.state.dashboard_events
    try:
        service.events.changes()
        service.store.put("voice", "test", {"id": "test", "title": "latest"})
        service.store.put("channel", "test", {"name": "test", "kind": "general"})
        sampler.sample(False)
        _, frames = service.events.read(0)
        packet = json.loads(next(frame[2] for frame in frames if frame[1] == "state"))
        assert packet["versions"]["voice"] == packet["versions"]["channel"] == 1
        assert any(v["title"] == "latest" for v in packet["value"]["voices"])
        service.store.delete("voice", "test")
        sampler.sample(False)
        _, frames = service.events.read(0)
        packet = json.loads(next(frame[2] for frame in frames if frame[1] == "state"))
        assert packet["versions"]["voice"] == 2
        assert packet["versions"]["channel"] == 1
    finally:
        app.state.tunnel.close()
        app.state.studio.close()


def test_generation_twitch_playback_and_discord_delivery_need_no_browser(tmp_path, engine, mp3):
    app = create_app(Settings(data_dir=tmp_path / "headless"), engine)
    studio, service = app.state.studio, app.state.service
    delivered = []
    studio.discord.enqueue = lambda job: delivered.append(job["id"])
    finished = threading.Event()

    def completed(job):
        studio.completed(job)
        finished.set()

    service.on_finished = completed
    try:
        with mp3.open("rb") as stream:
            voice = studio.voices.create(stream, "Headless", "reference.mp3", "Reference text")
        local = studio.voices.generate(voice["id"], GenerationRequest(
            text="Local without a browser", autoqueue_general=True,
        ))
        assert finished.wait(10)
        finished.clear()
        assert service.get(local["id"])["general_playback_item_id"]
        studio.save_channel(ChannelConfig(name="headless", enabled=True,
                                          commands={"!speak": voice["id"]}))
        twitch = studio.receive("headless", "viewer", "!speak Twitch without a browser")
        assert finished.wait(10)
        assert service.get(twitch["id"])["status"] == "succeeded"
        assert any(item["job_id"] == twitch["id"] for item in studio.playback.items("headless"))
        assert delivered == [local["id"], twitch["id"]]
        assert service.events.connections == 0
    finally:
        app.state.tunnel.close()
        studio.close()
