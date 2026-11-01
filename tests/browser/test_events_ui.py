import time
from urllib.parse import urlsplit

from playwright.sync_api import expect

from .test_ui import live_server as live_server


def load_dashboard(page):
    # Test-only handle: production state stays inside the native module.
    page.evaluate("""async () => {
        window.testDashboard = (await import('/static/state.js')).dashboard;
    }""")


def test_two_browsers_receive_changes_and_disconnect_independently(page, browser, live_server):
    url, app = live_server
    other = browser.new_context()
    second = other.new_page()
    requests = []
    page.on("request", lambda request: requests.append(urlsplit(request.url).path))
    try:
        for view in (page, second):
            view.goto(url)
            load_dashboard(view)
            view.wait_for_function("testDashboard.realtime?.healthy")
            view.locator('[data-tab="voices"]').click()
        assert app.state.service.events.connections == 2
        requests.clear()
        started = time.monotonic()
        app.state.service.store.put("voice", "streamed", {
            "id": "streamed", "title": "SSE voice", "status": "ready",
            "transcript": "Reference", "original_filename": "sample.mp3",
        })
        for view in (page, second):
            expect(view.locator('.voice-card input[value="SSE voice"]')).to_be_visible()
        assert time.monotonic() - started < 4
        # No REST state/voice fetch is necessary to receive this update.
        assert "/api/state" not in requests
        assert "/api/voices" not in requests
        other.close()
        page.wait_for_function("testDashboard.realtime?.healthy")
        app.state.service.store.patch("voice", "streamed", title="Still connected")
        expect(page.locator('.voice-card input[value="Still connected"]')).to_be_visible()
    finally:
        other.close()


def test_reconnect_synchronizes_missed_changes_and_refreshes_csrf(page, live_server):
    url, app = live_server
    page.goto(url)
    load_dashboard(page)
    page.wait_for_function("testDashboard.realtime?.healthy")
    original_token = page.evaluate("testDashboard.session.token")
    page.context.set_offline(True)
    page.evaluate("testDashboard.session.token = 'old-server-token'")
    app.state.service.store.put("voice", "missed", {
        "id": "missed", "title": "Created while offline", "status": "ready",
        "transcript": "Reference", "original_filename": "sample.mp3",
    })
    page.context.set_offline(False)
    page.wait_for_function("testDashboard.session.token !== 'old-server-token'", timeout=15000)
    assert page.evaluate("testDashboard.session.token") == original_token
    page.locator('[data-tab="voices"]').click()
    expect(page.locator('.voice-card input[value="Created while offline"]')).to_be_visible()
    assert page.evaluate("testDashboard.realtime.healthy")


def test_no_eventsource_uses_slower_rest_fallback(page, live_server):
    url, app = live_server
    page.add_init_script("window.EventSource = undefined")
    state_requests = []
    page.on("request", lambda request: state_requests.append(request.url)
            if urlsplit(request.url).path == "/api/state" else None)
    page.goto(url)
    load_dashboard(page)
    page.wait_for_function("testDashboard.realtime !== null")
    page.locator('[data-tab="voices"]').click()
    before = len(state_requests)
    app.state.service.store.put("voice", "fallback", {
        "id": "fallback", "title": "Fallback voice", "status": "ready",
        "transcript": "Reference", "original_filename": "sample.mp3",
    })
    expect(page.locator('.voice-card input[value="Fallback voice"]')).to_be_visible(timeout=9000)
    assert len(state_requests) - before <= 2
    assert app.state.service.events.connections == 0


def test_stale_stream_switches_to_fallback_then_recovers(page, live_server):
    url, app = live_server
    page.goto(url)
    load_dashboard(page)
    page.wait_for_function("testDashboard.realtime?.healthy")
    page.locator('[data-tab="voices"]').click()
    page.evaluate("""() => {
        testDashboard.realtime.source.close();
        testDashboard.realtime.lastEvent = Date.now() - 21000;
    }""")
    app.state.service.store.put("voice", "stale", {
        "id": "stale", "title": "Recovered by polling", "status": "ready",
        "transcript": "Reference", "original_filename": "sample.mp3",
    })
    expect(page.locator('.voice-card input[value="Recovered by polling"]')).to_be_visible(
        timeout=9000
    )
    # Bring forward the retry deadline rather than waiting thirty seconds.
    page.evaluate("testDashboard.realtime.retryAt = 0")
    page.wait_for_function("testDashboard.realtime.healthy", timeout=9000)
    app.state.service.store.patch("voice", "stale", title="Recovered by SSE")
    expect(page.locator('.voice-card input[value="Recovered by SSE"]')).to_be_visible()
