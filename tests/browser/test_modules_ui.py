from urllib.parse import urlsplit

from playwright.sync_api import expect

from .test_events_ui import load_dashboard
from .test_ui import live_server as live_server


def test_module_graph_loads_on_control_route_and_reload(page, live_server):
    url, app = live_server
    errors, scripts = [], {}
    page.on("pageerror", lambda error: errors.append(str(error)))

    def response_received(response):
        path = urlsplit(response.url).path
        if path.startswith("/static/") and path.endswith(".js"):
            scripts[path] = (response.status, response.headers.get("content-type", ""))

    page.on("response", response_received)
    for navigate in (lambda: page.goto(url + "/playbackMain/control"), page.reload):
        navigate()
        load_dashboard(page)
        page.wait_for_function("testDashboard.realtime?.healthy")
        expect(page.locator("#pane-studio")).to_be_visible()
        expect(page.locator("#general-form")).to_be_visible()
        assert app.state.service.events.connections == 1
        assert page.evaluate("typeof window.api") == "undefined"
        assert page.evaluate("typeof window.session") == "undefined"
        # Browser module caching must yield one shared state object.
        assert page.evaluate("""async () => {
            const first = await import('/static/state.js');
            const second = await import('/static/state.js');
            return first.dashboard === second.dashboard;
        }""")
    for module in ("api", "state", "voices", "twitch", "engines", "monitor", "config"):
        status, content_type = scripts[f"/static/{module}.js"]
        assert status == 200
        assert "javascript" in content_type
    assert errors == []
