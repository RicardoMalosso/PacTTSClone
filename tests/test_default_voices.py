import hashlib
import json
from pathlib import Path

import pytest

from pacttsclone.config import Settings
from pacttsclone.domain import GenerationRequest, UserError
from pacttsclone.service import GenerationService
from pacttsclone.studio import Studio

from .conftest import wait_job

CATALOG = Path(__file__).parents[1] / "src/pacttsclone/assets/voices/catalog.json"


def test_default_references_valid_and_seed_is_lazy_idempotent(tmp_path, engine, monkeypatch):
    monkeypatch.setattr("pacttsclone.voices.BUILTIN_CATALOG", CATALOG)
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    studio = Studio(service)
    try:
        voices = studio.store.all("voice")
        assert {v["title"] for v in voices} == {"Akuma Lady", "Dilma", "Chrétien", "lula"}
        assert {v["status"] for v in voices} == {"unprepared"}
        assert service.history() == []
        for entry in json.loads(CATALOG.read_text(encoding="utf-8")):
            source = CATALOG.parent / entry["filename"]
            assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"]
            destination = tmp_path / (entry["key"] + ".wav")
            service.audio.decode(source, destination)
            assert destination.read_bytes()[:4] == b"RIFF"
        voice = next(v for v in voices if v["title"] == "lula")
        with pytest.raises(UserError, match="not ready"):
            studio.voices.generate(voice["id"], GenerationRequest(text="Hello"))
        studio.voices.seed_defaults()
        assert len(studio.store.all("voice")) == 4
        studio.voices.delete(voice["id"])
        studio.voices.seed_defaults()
        assert len(studio.store.all("voice")) == 3
        assert studio.store.get("voice", voice["id"]) is None
    finally:
        studio.close()


def test_default_prepare_once_and_preserve_edits(tmp_path, engine, monkeypatch):
    monkeypatch.setattr("pacttsclone.voices.BUILTIN_CATALOG", CATALOG)
    settings = Settings(data_dir=tmp_path / "data")
    service = GenerationService(settings, engine)
    studio = Studio(service)
    try:
        voice = studio.store.all("voice")[0]
        pending = studio.voices.prepare(voice["id"])
        job = wait_job(service, pending["preparation_job_id"])
        assert job["status"] == "succeeded"
        ready = studio.voices.prepare(voice["id"])
        assert ready["status"] == "ready"
        assert ready["transcript"]
        assert ready["preparation_job_id"] == pending["preparation_job_id"]
        assert len(service.history()) == 1
        studio.voices.update(voice["id"], "My renamed voice", "My exact reference transcript.")
        studio.voices.seed_defaults()
        assert studio.store.get("voice", voice["id"])["title"] == "My renamed voice"
    finally:
        studio.close()
    restarted = GenerationService(settings, engine)
    studio = Studio(restarted)
    try:
        assert len(studio.store.all("voice")) == 4
        assert (
            studio.store.get("voice", voice["id"])["transcript"] == "My exact reference transcript."
        )
        assert restarted.pending() == []
    finally:
        studio.close()
