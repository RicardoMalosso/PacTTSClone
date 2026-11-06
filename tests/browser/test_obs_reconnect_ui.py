import pytest
from playwright.sync_api import expect

from .test_ui import live_server as live_server


@pytest.mark.parametrize("startup_offline", [False, True])
def test_obs_recovers_rotated_token_or_server_startup_without_reload(
    page, live_server, startup_offline
):
    url, app = live_server
    calls = []

    def session(route):
        calls.append("session")
        if len(calls) == 1:
            if startup_offline:
                route.abort("connectionrefused")
            else:
                response = route.fetch()
                value = response.json()
                value["token"] = "old-process-token"
                route.fulfill(response=response, json=value)
        else:
            route.continue_()

    page.route("**/api/session", session)
    with page.expect_response(
        lambda response: response.url.endswith("/player/tick") and response.status == 200
    ):
        page.goto(url + "/playbackMain")
    # A successful lease proves a post-403 tick used the refreshed session token.
    assert app.state.studio.playback.leases.get("playbackMain")
    assert len(calls) >= 2
    assert page.evaluate("halted") is False
    expect(page.locator("#message")).not_to_contain_text("Shared link expired")


@pytest.mark.parametrize("observed_queue, expected_offset", [(True, 0), (False, 0.8)])
def test_mirror_keeps_new_clip_start_and_seeks_only_for_late_join(
    page,
    live_server,
    mp3,
    observed_queue,
    expected_offset,
):
    url, _ = live_server
    ticks = []
    page.add_init_script("""
      window.seekRequests = [];
      const descriptor = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
      Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
        ...descriptor, set(value) { seekRequests.push(value); descriptor.set.call(this, value); }
      });
      HTMLMediaElement.prototype.play = async function() {};
    """)
    page.route(
        "**/test-audio", lambda route: route.fulfill(path=str(mp3), content_type="audio/mpeg")
    )

    def tick(route):
        ticks.append(1)
        queued = observed_queue and len(ticks) == 1
        route.fulfill(
            json={
                "owner": False,
                "paused": False,
                "server_time": 50,
                "item": {
                    "id": "first",
                    "status": "countdown" if queued else "playing",
                    "started_at": 49.2,
                    "output_url": "/test-audio",
                },
            }
        )

    page.route("**/player/tick", tick)
    page.goto(url + "/playbackMain")
    page.wait_for_function("seekRequests.length > 0")
    assert page.evaluate("seekRequests[0]") == pytest.approx(expected_offset)
    assert page.evaluate("halted") is False


def test_idle_obs_source_reconnects_after_app_process_restart(page, tmp_path, mp3):
    import socket
    import subprocess
    import sys
    import time
    from contextlib import contextmanager

    import httpx

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    @contextmanager
    def running_app():
        process = subprocess.Popen([
            sys.executable, "-c", "from pacttsclone.cli import main; main()",
            "--offline", "--no-browser", "--data-dir", str(tmp_path), "--port", str(port),
        ])
        try:
            deadline = time.monotonic() + 15
            with httpx.Client(trust_env=False) as client:
                while time.monotonic() < deadline:
                    assert process.poll() is None
                    try:
                        if client.get(url + "/api/session").is_success:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(0.1)
                else:
                    pytest.fail("Application did not start")
            yield
        finally:
            process.terminate()
            process.wait(timeout=10)

    def successful_tick(response):
        return response.url.endswith("/player/tick") and response.status == 200

    with running_app():
        with page.expect_response(successful_tick):
            page.goto(url + "/playbackMain")
        document_id = page.evaluate("client")
        response = page.request.post(
            url + "/api/sfx",
            headers={"X-PacTTS-Token": page.evaluate("token")},
            multipart={
                "title": "Restart test", "triggers": "[bell]",
                "audio": {"name": "bell.mp3", "mimeType": "audio/mpeg", "buffer": mp3.read_bytes()},
            },
        )
        assert response.status == 201, response.text()
        effect = response.json()
        audio_url = url + effect["audio_url"]
        saved_audio = page.request.get(audio_url).body()
        assert saved_audio.startswith(b"RIFF")
    expect(page.locator("#message")).to_be_visible(timeout=10000)
    with page.expect_response(successful_tick, timeout=20000), running_app():
        expect(page.locator("#message")).to_be_hidden(timeout=20000)
        assert page.evaluate("client") == document_id
        assert page.request.get(url + "/api/sfx").json() == [effect]
        assert page.request.get(audio_url).body() == saved_audio
        assert page.url == url + "/playbackMain"
        assert page.evaluate("halted") is False
