import io
import threading

import pytest

from pacttsclone.config import MAX_UPLOAD_BYTES, Settings
from pacttsclone.domain import BusyError, GenerationRequest, UserError
from pacttsclone.service import GenerationService

from .conftest import wait_job


def test_success_persists_mp3_cleans_reference(mp3, tmp_path, engine):
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    try:
        with mp3.open("rb") as source:
            job = service.submit(source, GenerationRequest(text="Olá."))
        result = wait_job(service, job["id"])
        assert result["status"] == "succeeded"
        assert result["output_url"].endswith("/audio")
        assert service.output_path(job["id"]).stat().st_size > 1000
        assert not list(service.temporary.iterdir())
        assert engine.calls[0][1].text == "Olá."
    finally:
        service.close()


def test_busy_and_recovery(mp3, tmp_path, engine):
    entered = threading.Event()
    release = threading.Event()
    original = engine.synthesize

    def blocking(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    engine.synthesize = blocking
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    try:
        job = service.submit(io.BytesIO(mp3.read_bytes()), GenerationRequest(text="Primeiro"))
        assert entered.wait(5)
        with pytest.raises(BusyError):
            service.submit(io.BytesIO(mp3.read_bytes()), GenerationRequest(text="Segundo"))
        release.set()
        assert wait_job(service, job["id"])["status"] == "succeeded"
        next_job = service.submit(io.BytesIO(mp3.read_bytes()), GenerationRequest(text="Terceiro"))
        assert wait_job(service, next_job["id"])["status"] == "succeeded"
    finally:
        release.set()
        service.close()


def test_failure_releases_worker_and_removes_files(mp3, tmp_path, engine):
    service = GenerationService(Settings(data_dir=tmp_path / "data"), engine)
    original = engine.synthesize

    def fail(*args):
        raise UserError("Memória insuficiente")

    engine.synthesize = fail
    try:
        job = service.submit(io.BytesIO(mp3.read_bytes()), GenerationRequest(text="Olá"))
        result = wait_job(service, job["id"])
        assert result["status"] == "failed"
        assert result["error"] == "Memória insuficiente"
        assert not list(service.temporary.iterdir())
        assert not list(service.outputs.iterdir())
        engine.synthesize = original
        second = service.submit(io.BytesIO(mp3.read_bytes()), GenerationRequest(text="Olá"))
        assert wait_job(service, second["id"])["status"] == "succeeded"
    finally:
        service.close()


@pytest.mark.parametrize("payload", [b"", b"x" * (MAX_UPLOAD_BYTES + 1)])
def test_reject_upload_and_recover(payload, tmp_path, engine):
    service = GenerationService(Settings(data_dir=tmp_path), engine)
    try:
        for _ in range(2):
            with pytest.raises(UserError):
                service.submit(io.BytesIO(payload), GenerationRequest(text="Olá"))
        assert not list(service.temporary.iterdir())
    finally:
        service.close()


def test_rejects_submission_after_shutdown(tmp_path, engine):
    service = GenerationService(Settings(data_dir=tmp_path), engine)
    service.close()
    with pytest.raises(UserError, match="encerrando"):
        service.submit(io.BytesIO(b"x"), GenerationRequest(text="Olá"))
