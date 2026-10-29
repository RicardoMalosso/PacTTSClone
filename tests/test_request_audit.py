import io
import json
import logging

from pacttsclone.cli import PollingAccessFilter
from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest
from pacttsclone.models import ChannelConfig
from pacttsclone.service import GenerationService
from pacttsclone.studio import Studio
from pacttsclone.worker import ProcessRunner

from .conftest import wait_job


def test_all_generation_origins_and_blocked_chat_are_audited(tmp_path, engine, mp3):
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    studio = Studio(service)
    try:
        voice = studio.voices.create(
            io.BytesIO(mp3.read_bytes()), "Audit voice", "voice.mp3", "Known text"
        )
        local = studio.voices.generate(
            voice["id"], GenerationRequest(text="Local speech", requester_name="Local tester")
        )
        wait_job(service, local["id"])
        studio.save_channel(
            ChannelConfig(
                name="audit",
                commands={"!voice": voice["id"]},
                custom_filters=["blocked phrase"],
                user_cooldown_seconds=0,
            )
        )
        studio.store.patch("channel", "audit", enabled=True)
        twitch = studio.receive("audit", "Viewer", "!voice Twitch speech")
        wait_job(service, twitch["id"])
        assert studio.receive("audit", "Viewer", "!voice blocked phrase") is None
        records = service.request_history()
        assert len(records) == 3
        blocked = next(r for r in records if r["status"] == "blocked")
        chat = service.get(twitch["id"])
        assert blocked["origin"] == chat["origin"] == "twitch"
        assert blocked["requester_id"] == chat["requester_id"]
        assert blocked["origin_id"] == chat["origin_id"]
        assert service.get(local["id"])["origin"] == "local"
        assert blocked["origin_id"] != service.get(local["id"])["origin_id"]
        persisted = [
            json.loads(line) for line in (service.logs / "requests.jsonl").read_text().splitlines()
        ]
        assert len(persisted) == 5  # two submitted/finished jobs and one moderation rejection
        assert any(r["event"] == "blocked" for r in persisted)
    finally:
        studio.close()


def test_residency_cleared_on_worker_reset(tmp_path):
    runner = ProcessRunner(Settings(data_dir=tmp_path))
    runner.model_state = {"loaded": True, "device": "cuda"}
    runner.reset()
    assert runner.model_state == {"loaded": False, "device": None}


def test_polling_access_filter_keeps_errors_and_generation_requests():
    filter_ = PollingAccessFilter()

    def record(path, status):
        return logging.LogRecord(
            "uvicorn.access",
            logging.INFO,
            "",
            0,
            "%s %s %s %s %s",
            ("local", "GET", path, "1.1", status),
            None,
        )

    assert not filter_.filter(record("/api/state", 200))
    assert not filter_.filter(record("/api/discord", 200))
    assert not filter_.filter(record("/api/channels/playbackMain/player/tick", 200))
    assert filter_.filter(record("/api/session", 403))
    assert filter_.filter(record("/api/jobs", 202))


def test_channel_and_unrendered_requests_survive_restart(tmp_path, engine):
    settings = Settings(data_dir=tmp_path / "data")
    service = GenerationService(settings, engine)
    studio = Studio(service)
    studio.save_channel(ChannelConfig(name="persisted", commands={}, enabled=False))
    service.reject_request("Blocked speech", "filter", channel="persisted", username="Viewer")
    for status in ("queued", "running", "failed", "cancelled"):
        service.store.put(
            "job",
            status,
            {
                "id": status,
                "status": status,
                "kind": "speech",
                "channel": "persisted",
                "created_at": 1,
                "request": {"text": status},
                "workspace": "",
                "metrics": {},
            },
        )
    studio.close()
    service = GenerationService(settings, engine)
    studio = Studio(service)
    try:
        assert studio.store.get("channel", "persisted")["enabled"] is False
        assert len(service.request_history()) == 5
        for key in ("queued", "running", "failed", "cancelled"):
            job = service.get(key)
            assert job["status"] == ("failed" if key == "failed" else "cancelled")
            assert job["request"]["text"] == key
        assert any(r["status"] == "blocked" for r in service.request_history())
    finally:
        studio.close()


def test_vram_warning_threshold_and_transition_logging(tmp_path, engine):
    service = GenerationService(Settings(data_dir=tmp_path), engine)
    try:
        low = {"gpus": [{"total_bytes": 6000 * 1024**2, "used_bytes": 5900 * 1024**2}]}
        warning = service.check_gpu_pressure(low)
        assert warning["free_bytes"] == 100 * 1024**2
        service.check_gpu_pressure(low)
        service.check_gpu_pressure({"gpus": [{"total_bytes": 6000 * 1024**2, "used_bytes": 0}]})
        rows = [
            json.loads(line)
            for line in (service.logs / "gpu-status.jsonl").read_text().splitlines()
        ]
        assert [r["event"] for r in rows] == ["low_vram", "vram_recovered"]
        service.config.vram_warning_mib = 0
        assert service.check_gpu_pressure(low) is None
        assert service.check_gpu_pressure({"gpus": []}) is None
    finally:
        service.close()
