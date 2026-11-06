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
