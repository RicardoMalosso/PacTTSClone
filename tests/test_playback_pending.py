from types import SimpleNamespace

from pacttsclone.playback import Playback
from pacttsclone.store import Store


def test_old_pending_playback_survives_history_limit(tmp_path):
    store = Store(tmp_path)
    try:
        playback = Playback(SimpleNamespace(store=store))
        channel = {"name": "demo", "paused": False, "delay_seconds": 0,
                   "filter_level": "basic", "custom_filters": []}
        store.put("channel", "demo", channel)
        item = {"id": "old", "channel": "demo", "text": "hello", "created_at": 0}
        store.put("playback", "old", {**item, "status": "queued"})
        for i in range(1000):
            store.put("playback", str(i), {**item, "id": str(i),
                                         "created_at": i + 1, "status": "cancelled"})
        assert any(row["id"] == "old" for row in playback.snapshot("demo")["items"])
        assert playback.tick("demo", "browser")["item"]["id"] == "old"
        playback.panic()
        assert store.get("playback", "old")["status"] == "cancelled"
    finally:
        store.close()
