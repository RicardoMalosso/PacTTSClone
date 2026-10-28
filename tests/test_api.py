import io
import threading

import pytest
from fastapi.testclient import TestClient

from pacttsclone.app import create_app
from pacttsclone.config import MAX_BODY_BYTES, Settings

from .conftest import wait_job


@pytest.fixture
def app(tmp_path, engine):
    return create_app(Settings(data_dir=tmp_path / "data"), engine)


@pytest.fixture
def client(app):
    with TestClient(app, base_url="http://127.0.0.1:7860") as client:
        yield client


def submit(client, mp3, **changes):
    data = {"text": "Olá, teste local.", "ref_text": "Referência", **changes}
    token = client.get("/api/session").json()["token"]
    return client.post(
        "/api/jobs",
        files={"reference": ("voice.mp3", mp3.read_bytes(), "audio/mpeg")},
        data=data,
        headers={"X-PacTTS-Token": token},
    )


def test_full_api_pipeline(client, app, mp3):
    result = submit(client, mp3)
    assert result.status_code == 202
    assert result.json()["request"]["language"] == "auto"
    job_id = result.json()["id"]
    done = wait_job(app.state.service, job_id)
    assert done["status"] == "succeeded"
    assert client.get(f"/api/jobs/{job_id}").json() == done
    response = client.get(done["output_url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert len(response.content) > 1000
    partial = client.get(done["output_url"], headers={"Range": "bytes=0-99"})
    assert partial.status_code == 206
    assert len(partial.content) == 100
    app.state.service.output_path(job_id).unlink()
    assert client.get(done["output_url"]).status_code == 404


def test_static_and_health_do_not_load_engine(client, engine):
    assert "PacTTSClone" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    health = client.get("/api/health").json()
    assert health["ffmpeg_available"]
    assert engine.calls == []
    assert client.get("/api/session").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "header,value",
    [
        ("Host", "evil.example"),
        ("Host", "127.0.0.1.evil.example"),
        ("Host", "evil@127.0.0.1:7860"),
        ("Host", "127.0.0.1:invalid"),
        ("Origin", "https://evil.example"),
        ("Origin", "null"),
        ("Origin", "http://127.0.0.1:9999"),
    ],
)
def test_rejects_foreign_browser(client, header, value):
    assert client.get("/api/session", headers={header: value}).status_code == 403


def test_accepts_same_origin(client):
    assert (
        client.get("/api/session", headers={"Origin": "http://127.0.0.1:7860"}).status_code == 200
    )


@pytest.mark.parametrize("token", ["", "wrong", "á"])
def test_token_required(client, mp3, token):
    response = client.post(
        "/api/jobs",
        files={"reference": ("voice.mp3", mp3.read_bytes())},
        data={"text": "Olá"},
        headers={"X-PacTTS-Token": token.encode("utf8")},
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"text": " "},
        {"text": "a" * 2001},
        {"language": "xx"},
        {"speed": "nan"},
        {"steps": "100"},
        {"speed": "2"},
    ],
)
def test_api_rejects_invalid_request(client, mp3, changes):
    assert submit(client, mp3, **changes).status_code == 422


def test_missing_and_wrong_file(client):
    token = client.get("/api/session").json()["token"]
    headers = {"X-PacTTS-Token": token}
    assert client.post("/api/jobs", data={"text": "Olá"}, headers=headers).status_code == 422
    assert (
        client.post(
            "/api/jobs",
            files={"reference": ("voice.wav", b"x")},
            data={"text": "Olá"},
            headers=headers,
        ).status_code
        == 422
    )


def test_corrupt_audio_returns_job_error(client, app, tmp_path):
    path = tmp_path / "bad.mp3"
    path.write_bytes(b"bad mp3")
    response = submit(client, path)
    result = wait_job(app.state.service, response.json()["id"])
    assert result["status"] == "failed"
    assert "MP3" in result["error"]
    assert client.get(f"/api/jobs/{result['id']}/audio").status_code == 409


def test_upload_body_limit(client):
    response = client.post(
        "/api/jobs",
        content=b"x",
        headers={
            "Content-Length": str(MAX_BODY_BYTES + 1),
            "X-PacTTS-Token": client.get("/api/session").json()["token"],
        },
    )
    assert response.status_code == 413


def test_chunked_body_limit(client):
    response = client.post(
        "/api/jobs",
        content=iter([b"x" * MAX_BODY_BYTES, b"y"]),
        headers={"X-PacTTS-Token": client.get("/api/session").json()["token"]},
    )
    assert response.status_code == 413


def test_unknown_and_path_traversal(client):
    assert client.get("/api/jobs/nonexistent").status_code == 404
    assert client.get("/api/jobs/nonexistent/audio").status_code == 404
    assert client.get("/api/jobs/%2e%2e%2fsecret/audio").status_code == 404


def test_busy_api(client, app, engine, mp3):
    entered = threading.Event()
    release = threading.Event()
    original = engine.synthesize

    def blocking(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    engine.synthesize = blocking
    try:
        job = submit(client, mp3).json()
        assert entered.wait(5)
        assert client.get(f"/api/jobs/{job['id']}/audio").status_code == 409
        assert submit(client, mp3).status_code == 409
    finally:
        release.set()


def test_filename_never_used_as_path(client, app, mp3):
    token = client.get("/api/session").json()["token"]
    response = client.post(
        "/api/jobs",
        files={"reference": ("../../escape.mp3", io.BytesIO(mp3.read_bytes()))},
        data={"text": "Olá"},
        headers={"X-PacTTS-Token": token},
    )
    job = wait_job(app.state.service, response.json()["id"])
    assert job["status"] == "succeeded"
    assert app.state.service.output_path(job["id"]).name == job["id"] + ".mp3"
