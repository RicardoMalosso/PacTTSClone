import socket
import threading
import time

import httpx
import pytest
import uvicorn
from playwright.sync_api import expect

from pacttsclone.app import create_app
from pacttsclone.config import Settings


@pytest.fixture
def live_server(tmp_path, engine):
    # Bind before starting the server, retaining the socket to avoid port races.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(16)
    app = create_app(Settings(data_dir=tmp_path / "data"), engine)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if httpx.get(url + "/api/session", trust_env=False).status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(0.02)
        else:
            raise AssertionError("Server did not start")
        yield url, app
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture
def live_app(live_server):
    return live_server[0]


def prepare(page, live_app, mp3):
    page.goto(live_app)
    expect(page.get_by_role("button", name="Generate MP3")).to_be_enabled()
    page.locator("#reference").set_input_files(mp3)
    page.locator("#text").fill("Olá, este é um teste local.")
    page.locator("#ref-text").fill("Referência.")


def test_generate_play_download_stop(page, live_app, mp3, tmp_path):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    prepare(page, live_app, mp3)
    page.get_by_role("button", name="Generate MP3").click()
    player = page.locator("#player")
    expect(player).to_be_visible(timeout=15000)
    expect(player).to_have_attribute("controls", "")
    page.wait_for_function("document.getElementById('player').readyState >= 1")
    assert page.locator("#player").evaluate("el => el.duration") > 0.9
    # Use actual media playback API, also used by native controls.
    page.locator("#player").evaluate("async el => { el.volume = .4; await el.play(); }")
    page.wait_for_function("!document.getElementById('player').paused")
    page.locator("#player").evaluate("el => { el.pause(); el.currentTime = .5; }")
    page.get_by_role("button", name="Stop / restart").click()
    assert player.evaluate("el => el.paused && el.currentTime === 0")
    with page.expect_download() as info:
        page.get_by_role("link", name="Download MP3").click()
    target = tmp_path / info.value.suggested_filename
    info.value.save_as(target)
    assert target.stat().st_size > 1000
    assert errors == []


def test_error_message_and_retry(page, live_app, mp3, tmp_path):
    bad = tmp_path / "broken.mp3"
    bad.write_bytes(b"not mp3")
    prepare(page, live_app, bad)
    page.get_by_role("button", name="Generate MP3").click()
    expect(page.locator("#error")).to_be_visible(timeout=15000)
    expect(page.locator("#error")).to_contain_text("MP3")
    expect(page.locator("#player")).to_be_hidden()
    page.locator("#reference").set_input_files(mp3)
    page.get_by_role("button", name="Generate MP3").click()
    expect(page.locator("#player")).to_be_visible(timeout=15000)
    expect(page.locator("#error")).to_be_hidden()


def test_blocked_autoplay_has_manual_fallback(page, live_app, mp3):
    page.add_init_script(
        "HTMLMediaElement.prototype.play = () => Promise.reject(new Error('blocked'))"
    )
    prepare(page, live_app, mp3)
    page.locator("#autoplay").check()
    page.get_by_role("button", name="Generate MP3").click()
    expect(page.locator("#playback-note")).to_contain_text("blocked", timeout=15000)
    expect(page.locator("#player")).to_be_visible()
    expect(page.get_by_role("link", name="Download MP3")).to_be_visible()
    page.reload()
    expect(page.locator("#autoplay")).to_be_checked()


def test_small_viewport_and_counter(page, live_app):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(live_app)
    page.locator("#text").fill("Olá")
    expect(page.locator("#count")).to_have_text("3 / 2000")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_initial_setup_gate_progress_cancel_and_unlock(page, live_app):
    state = dict(ready=False, status="idle", stage="idle", completed_steps=0)
    page.route("**/api/setup", lambda route: route.fulfill(json=state))

    def start(route):
        assert route.request.post_data_json == {"device": "cpu"}
        state.update(
            status="running",
            stage="models",
            completed_steps=3,
            download=dict(
                repo="owner/model",
                file="weights.safetensors",
                phase="resuming download",
                file_bytes=50,
                file_total=100,
                reused_files=2,
            ),
        )
        route.fulfill(json=state)

    def cancel(route):
        state.update(status="cancelled", stage="cancelled", error="Setup cancelled.")
        route.fulfill(json=state)

    page.route("**/api/setup/start", start)
    page.route("**/api/setup/cancel", cancel)
    page.goto(live_app)
    expect(page.locator("#pane-setup")).to_be_visible()
    for tab in ["studio", "voices", "channels"]:
        expect(page.locator(f'[data-tab="{tab}"]')).to_be_disabled()
    expect(page.locator("#tunnel-card")).to_be_hidden()
    page.locator("#setup-device").select_option("cpu")
    page.locator("#setup-start").click()
    expect(page.locator("#setup-file-progress")).to_have_attribute("value", "50")
    expect(page.locator("#setup-download-status")).to_contain_text("resuming download")
    expect(page.locator("#setup-download-status")).to_contain_text("2 verified cached files reused")
    expect(page.locator("#setup-start")).to_be_disabled()
    page.locator("#setup-cancel").click()
    expect(page.locator("#setup-error")).to_contain_text("Setup cancelled.")
    expect(page.locator("#setup-start")).to_be_enabled()
    expect(page.locator('[data-tab="voices"]')).to_be_disabled()
    state.update(ready=True, status="succeeded", stage="ready", error=None)
    expect(page.locator('[data-tab="voices"]')).to_be_enabled()
    page.locator('[data-tab="voices"]').click()
    expect(page.locator("#pane-voices")).to_be_visible()
