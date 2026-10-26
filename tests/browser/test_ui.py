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
def live_server(tmp_path, engine, page):
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
        # Browser's persistent EventSource must disconnect before Uvicorn drains
        # active HTTP streams during graceful shutdown.
        try:
            if not page.is_closed():
                page.goto("about:blank", wait_until="commit", timeout=5000)
        except Exception:
            pass
        server.should_exit = True
        thread.join(10)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture
def live_app(live_server):
    return live_server[0]


def add_ready_voice(page, mp3, title="Browser voice"):
    expect(page.locator("#generate")).to_be_enabled()
    page.locator('[data-tab="voices"]').click()
    page.locator("#voice-title").fill(title)
    page.locator("#voice-reference").set_input_files(mp3)
    page.locator("#voice-transcript").fill("Known reference transcript.")
    page.get_by_role("button", name="Save voice", exact=True).click()
    expect(
        page.locator(".voice-card").filter(has=page.locator('input[value="' + title + '"]'))
    ).to_be_visible()
    page.locator('[data-tab="studio"]').click()
    page.locator("#voice-select").select_option(label=title)
    page.locator("#requester-name").fill("Browser tester")


def prepare(page, live_app, mp3):
    page.goto(live_app)
    expect(page.get_by_role("button", name="Generate MP3")).to_be_enabled()
    add_ready_voice(page, mp3)
    page.locator("#text").fill("Olá, este é um teste local.")


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
    page.goto(live_app)
    expect(page.locator("#generate")).to_be_enabled()
    page.locator('[data-tab="voices"]').click()
    page.locator("#voice-title").fill("Retry voice")
    page.locator("#voice-reference").set_input_files(bad)
    page.locator("#voice-transcript").fill("Known text")
    page.get_by_role("button", name="Save voice", exact=True).click()
    expect(page.locator("#error")).to_contain_text("MP3")
    expect(page.locator(".voice-card")).to_have_count(0)
    page.locator("#voice-reference").set_input_files(mp3)
    page.get_by_role("button", name="Save voice", exact=True).click()
    expect(page.locator(".voice-card")).to_have_count(1)
    page.locator('[data-tab="studio"]').click()
    page.locator("#voice-select").select_option(label="Retry voice")
    page.locator("#requester-name").fill("Retry tester")
    page.locator("#text").fill("Retry successful")
    page.locator("#generate").click()
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
    # The test mocks polling state; block the real SSE stream from overwriting it.
    page.route("**/api/setup/stream", lambda route: route.abort())
    page.route("**/api/setup", lambda route: route.fulfill(json=state))

    def start(route):
        assert route.request.post_data_json == {"device": "cuda"}
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
    page.locator("#setup-device").select_option("cuda")
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


def test_initial_setup_countermeasures_prompt_once(page, live_server):
    url, app = live_server
    setup = app.state.runtime_setup
    setup.update(
        status="running",
        stage="pytorch",
        device="cpu",
        completed_steps=0,
        total_steps=5,
        initial_setup_completed=False,
        started_at=time.time() - 31,
    )
    page.goto(url)
    expect(page.locator("#setup-too-long")).to_be_visible(timeout=5000)
    expect(page.locator("#setup-elapsed")).not_to_have_text("00:00.0")
    page.locator("#setup-too-long-yes").click()
    expect(page.locator("#countermeasure-loading")).to_be_visible()
    expect(page.locator("#countermeasure-video")).to_be_visible(timeout=5000)
    page.wait_for_function(
        'document.querySelector("#countermeasure-video")?.videoWidth > 0',
        timeout=10000,
    )
    video = page.locator("#countermeasure-video")
    expect(video).to_have_attribute("loop", "")
    page.wait_for_function(
        'document.querySelector("#countermeasure-video")?.currentTime > 0',
        timeout=10000,
    )
    assert video.evaluate("(v) => !v.muted && v.volume > 0 && !v.paused")
    # Observe two real end-to-start wraps, rather than merely checking loop=true.
    video.evaluate("""(v) => {
        window.clipWraps = 0;
        let previous = v.currentTime;
        v.addEventListener('timeupdate', () => {
            if (previous > v.duration - 1 && v.currentTime < 1) window.clipWraps++;
            previous = v.currentTime;
        });
    }""")
    page.wait_for_function("window.clipWraps >= 2", timeout=15000)
    assert video.evaluate("(v) => v.webkitAudioDecodedByteCount > 0")
    assert video.evaluate("(v) => v.videoWidth === 640 && v.videoHeight === 360")
    assert video.evaluate("(v) => !v.paused && !v.ended && !v.muted && v.volume > 0")
    page.locator("#countermeasure-close").click()
    expect(page.locator("#countermeasure-modal")).to_be_hidden()
    assert video.evaluate("(v) => v.paused && v.currentTime === 0")
    page.reload()
    expect(page.locator("#setup-too-long")).to_be_hidden()
