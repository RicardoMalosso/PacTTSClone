import time
from datetime import date, datetime, timedelta
from datetime import time as clock

from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from pacttsclone.tournaments import TournamentStore


def seed_clip(service, clip, content, *, age=0, status="succeeded"):
    service.output_path(clip).write_bytes(content)
    service.store.put(
        "job",
        clip,
        {
            "id": clip,
            "kind": "speech",
            "status": status,
            "request": {"text": clip},
            "created_at": time.time() - age * 86400,
        },
    )


def test_local_tournament_and_persisted_votes(tmp_path, engine):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, engine)
    base = "/api/tournaments"
    # Existing installations probe the candidate app before activating an update.
    assert any(route.path == "/api/updates/manager" for route in app.routes)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        service = app.state.service
        seed_clip(service, "a", b"audio a")
        seed_clip(service, "b", b"audio b")
        seed_clip(service, "duplicate", b"audio a")
        seed_clip(service, "old", b"older clip", age=8)
        seed_clip(service, "failed", b"ineligible clip", status="failed")
        assert client.post(base, json={"period": "week"}).status_code == 403
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        tournament = client.post(base, json={"period": "week"}).json()["id"]
        endpoint = f"{base}/{tournament}"
        seed_clip(service, "new", b"new clip")
        match = client.post(endpoint + "/pair").json()
        assert {match["a"], match["b"]} == {"a", "b"}
        assert client.post(endpoint + "/pair").json() == match
        vote = {"match_id": match["id"], "result": "a"}
        assert client.post(endpoint + "/vote", json=vote).status_code == 200
        assert client.post(endpoint + "/vote", json=vote).status_code == 200
        assert client.post(endpoint + "/vote", json={**vote, "result": "b"}).status_code == 409
        assert client.post(endpoint + "/pair").json() is None
        assert client.get(f"/api/jobs/{match['a']}/audio").headers["content-type"] == "audio/mpeg"

    with TestClient(create_app(settings, engine), base_url="http://127.0.0.1") as client:
        assert client.get(base).json()[0]["id"] == tournament
        winner, loser = client.get(endpoint + "/leaderboard").json()
        assert winner["clip"] == match["a"]
        assert winner["comparisons"] == loser["comparisons"] == 1
        assert winner["score"] > loser["score"]


def test_one_local_report_tags_clip_and_voids_comparisons(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        service = app.state.service
        seed_clip(service, "a", b"audio a")
        seed_clip(service, "b", b"audio b")
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        tournament = client.post("/api/tournaments", json={"period": "all"}).json()["id"]
        endpoint = f"/api/tournaments/{tournament}"
        match = client.post(endpoint + "/pair").json()
        vote = {"match_id": match["id"], "result": "a"}
        assert client.post(endpoint + "/vote", json=vote).status_code == 200

        store = TournamentStore(service)
        pending = store.pair(tournament, "second")
        assert "a" in (pending["a"], pending["b"])

        report = endpoint + "/report/a"
        removed = {"removed": True, "tag": "shit from a butt"}
        assert client.post(report).json() == removed
        assert client.post(report).json() == removed
        assert store.pair(tournament, "second") is None
        assert client.post(endpoint + "/pair").json() is None
        assert client.get(endpoint + "/bracket").json() == {
            "clips": [
                {"id": "a", "tag": "shit from a butt", "playable": True},
                {"id": "b", "tag": None, "playable": True},
            ],
            "matches": [{"a": match["a"], "b": match["b"], "result": "a", "counts": False}],
        }
        assert client.get(endpoint + "/leaderboard").json() == [
            {"clip": "b", "score": 1.0, "comparisons": 0, "provisional": True},
        ]
        assert service.output_path("a").is_file()


def test_twitch_poll_is_advisory_and_posted_once_per_match(tmp_path, engine, monkeypatch):
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        service = app.state.service
        seed_clip(service, "a", b"audio a")
        seed_clip(service, "b", b"audio b")
        service.store.put("channel", "streamer", {"name": "streamer"})
        account = {"user_id": "1234", "scopes": []}
        monkeypatch.setattr(app.state.studio.accounts, "account", lambda channel: account)
        calls = []
        latest = [{"status": "ACTIVE"}]

        def helix(channel, method, path, **kwargs):
            calls.append((channel, method, path, kwargs))
            return {"data": latest if method == "GET" else [{"id": "poll-123"}]}

        monkeypatch.setattr(app.state.studio.accounts, "api", helix)
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        tournament = client.post("/api/tournaments", json={"period": "all"}).json()["id"]
        endpoint = f"/api/tournaments/{tournament}"
        match = client.post(endpoint + "/pair").json()
        poll = {"match_id": match["id"], "channel": "streamer"}
        assert client.post(endpoint + "/poll", json=poll).status_code == 403
        assert not calls
        account["scopes"].append("channel:manage:polls")
        assert client.post(endpoint + "/poll", json=poll).status_code == 409
        assert [call[1] for call in calls] == ["GET"]
        latest.clear()
        assert client.post(endpoint + "/poll", json=poll).json() == {"id": "poll-123"}
        assert client.post(endpoint + "/poll", json=poll).json() == {"id": "poll-123"}
        assert [call[1] for call in calls] == ["GET", "GET", "POST"]
        assert calls[-1][3]["body"]["choices"] == [{"title": "Clip A"}, {"title": "Clip B"}]
        assert all(row["comparisons"] == 0 for row in client.get(endpoint + "/leaderboard").json())
        vote = {"match_id": match["id"], "result": "b"}
        assert client.post(endpoint + "/vote", json=vote).status_code == 200
        assert client.get(endpoint + "/leaderboard").json()[0]["clip"] == match["b"]


def test_date_pools_use_local_calendar_boundaries(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        service = app.state.service
        midnight = datetime.combine(date.today(), clock.min)
        for clip, completed in (
            ("today-a", midnight),
            ("today-b", midnight),
            ("yesterday-a", midnight - timedelta(seconds=1)),
            ("yesterday-b", midnight - timedelta(hours=12)),
        ):
            seed_clip(service, clip, clip.encode())
            service.store.patch("job", clip, finished_at=completed.timestamp())
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        base = "/api/tournaments"

        def clips_for(selection):
            created = client.post(base, json=selection)
            assert created.status_code == 200
            bracket = client.get(f"{base}/{created.json()['id']}/bracket").json()
            return {clip["id"] for clip in bracket["clips"]}

        assert clips_for({"period": "today"}) == {"today-a", "today-b"}
        yesterday = (midnight.date() - timedelta(days=1)).isoformat()
        selection = {"period": "range", "start_date": yesterday, "end_date": yesterday}
        assert clips_for(selection) == {"yesterday-a", "yesterday-b"}
        assert client.post(base, json={"period": "range"}).status_code == 422
        assert client.post(base, json={**selection, "start_date": "9999-12-31"}).status_code == 422


def test_previous_winners_requires_distinct_clips_with_votes(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        service = app.state.service
        seed_clip(service, "a", b"audio a")
        seed_clip(service, "b", b"audio b")
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        base = "/api/tournaments"
        selection = {"period": "winners"}
        assert client.post(base, json=selection).status_code == 422
        for winner in ("a", "b"):
            tournament = client.post(base, json={"period": "all"}).json()["id"]
            endpoint = f"{base}/{tournament}"
            match = client.post(endpoint + "/pair").json()
            result = "a" if match["a"] == winner else "b"
            vote = {"match_id": match["id"], "result": result}
            assert client.post(endpoint + "/vote", json=vote).status_code == 200
        seed_clip(service, "c", b"audio c")
        tournament = client.post(base, json=selection).json()["id"]
        bracket = client.get(f"{base}/{tournament}/bracket").json()
        assert {clip["id"] for clip in bracket["clips"]} == {"a", "b"}


def test_provisional_status_does_not_rank_five_losses_first():
    from pacttsclone.tournaments import rank_clips

    opponents = list("bcdef")
    rows = rank_clips(["a", *opponents], [("a", clip, "b") for clip in opponents])
    assert rows[-1]["clip"] == "a"
    assert rows[-1]["comparisons"] == 5
    assert all(row["provisional"] for row in rows[:-1])


def test_unfinished_tournament_does_not_supply_previous_winner(tmp_path, engine):
    app = create_app(Settings(data_dir=tmp_path), engine)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.headers["X-PacTTS-Token"] = client.get("/api/session").json()["token"]
        base = "/api/tournaments"
        for clip in ("a", "b"):
            seed_clip(app.state.service, clip, clip.encode())
        for size in (2, 3):
            if size == 3:
                seed_clip(app.state.service, "c", b"c")
            tournament = client.post(base, json={"period": "all"}).json()["id"]
            endpoint = f"{base}/{tournament}"
            match = client.post(endpoint + "/pair").json()
            winner = min(match["a"], match["b"]) if size == 2 else max(match["a"], match["b"])
            vote = {"match_id": match["id"], "result": "a" if match["a"] == winner else "b"}
            assert client.post(endpoint + "/vote", json=vote).status_code == 200
        assert client.post(base, json={"period": "winners"}).status_code == 422
