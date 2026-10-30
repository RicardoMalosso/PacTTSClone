import threading
import time
from datetime import UTC, datetime, timedelta

from playwright.sync_api import expect

from pacttsclone.models import ChannelConfig

from .test_ui import add_ready_voice
from .test_ui import live_server as live_server


def open_tab(page, name):
    page.get_by_role("button", name=name, exact=True).click()


def wait_until(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.03)
    raise AssertionError("Condition did not become true")


def test_voice_screen_transcription_edit_config_persistence(page, live_server, mp3):
    url, app = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    open_tab(page, "Voices")
    page.locator("#voice-title").fill("Lula test")
    page.locator("#voice-reference").set_input_files(mp3)
    page.get_by_role("button", name="Save voice", exact=True).click()
    card = page.locator(".voice-card").filter(has=page.get_by_role("heading", name="Lula test"))
    expect(card.locator(".pill")).to_have_text("ready", timeout=15000)
    expect(card.get_by_label("Saved transcript")).not_to_have_value("")
    card.get_by_label("Saved transcript").fill("An edited reference transcript.")
    card.get_by_role("button", name="Save edits").click()
    wait_until(
        lambda: (
            app.state.service.store.all("voice")[0]["transcript"]
            == "An edited reference transcript."
        )
    )
    open_tab(page, "Configuration")
    page.locator("#config-device").select_option("cuda")
    page.locator("#config-threads").fill("2")
    page.locator("#config-hotkey").fill("Ctrl+Alt+F8")
    page.get_by_role("button", name="Save configuration").click()
    expect(page.locator("#health")).to_contain_text("Configuration saved")
    page.reload()
    expect(page.locator("#generate")).to_be_enabled()
    open_tab(page, "Configuration")
    expect(page.locator("#config-device")).to_have_value("cuda")
    expect(page.locator("#config-threads")).to_have_value("2")
    expect(page.locator("#config-hotkey")).to_have_value("Ctrl+Alt+F8")


def test_progress_timer_and_cancel_interface(page, live_server, mp3):
    url, app = live_server
    engine = app.state.service.engine
    original = engine.synthesize
    release = threading.Event()
    entered = threading.Event()

    def blocked(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)

    engine.synthesize = blocked
    try:
        page.goto(url)
        expect(page.locator("#generate")).to_be_enabled()
        add_ready_voice(page, mp3)
        page.locator("#text").fill("Cancel this generation")
        page.locator("#generate").click()
        expect(page.locator("#cancel-job")).to_be_visible()
        assert entered.wait(3)
        expect(page.locator("#timer")).not_to_have_text("00:00.0")
        assert page.locator("#overall-progress").count() == 1
        assert page.locator("#stage-list progress").count() == 6
        page.locator("#cancel-job").click()
        release.set()
        expect(page.locator("#error")).to_contain_text("Cancelled", timeout=15000)
        expect(page.locator("#player")).to_be_hidden()
        expect(page.locator("#generate")).to_be_enabled()
    finally:
        release.set()


def test_obs_countdown_cancel_and_replay(browser, page, live_server, mp3):
    url, app = live_server
    studio = app.state.studio
    with mp3.open("rb") as ref:
        voice = studio.voices.create(ref, "Lula", "lula.mp3", "Exact reference")
    studio.save_channel(ChannelConfig(name="localtest", commands={"!lula": voice["id"]}))
    # Inject an IRC message through the production handler, without making a network connection.
    studio.store.patch("channel", "localtest", enabled=True)
    page.goto(url + "/localtest/control")
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator("#pane-channels")).to_be_visible()
    obs = page.context.new_page()
    obs.goto(url + "/localtest")
    obs.locator("body").click(position={"x": 1, "y": 1}, force=True)
    try:
        job = studio.receive("localtest", "viewer", "!lula bom dia")
        assert job
        expect(page.locator("#channel-queue")).to_contain_text("countdown", timeout=15000)
        page.get_by_role("button", name="Cancel audio", exact=True).click()
        wait_until(lambda: studio.playback.items("localtest")[0]["status"] == "cancelled")
        assert obs.locator("#audio").evaluate("a => a.paused")
        studio.store.patch("channel", "localtest", delay_seconds=0)
        open_tab(page, "History")
        page.get_by_role("button", name="Replay on OBS").click()
        wait_until(lambda: len(studio.playback.items("localtest")) == 2)
        # Chromium's test policy may block autoplay, exactly as a normal browser can.
        wait_until(
            lambda: (
                studio.playback.items("localtest")[-1]["status"] in {"playing", "played", "error"}
            )
        )
        item = studio.playback.items("localtest")[-1]
        if item["status"] == "error":
            expect(obs.locator("#enable")).to_be_visible()
        else:
            wait_until(lambda: studio.playback.items("localtest")[-1]["status"] == "played")
        assert len(studio.service.history()) == 1  # replay did not regenerate
        with page.expect_download() as download:
            page.get_by_role("link", name="Download MP3", exact=True).click()
        assert download.value.suggested_filename.endswith(".mp3")
    finally:
        obs.close()


def test_channel_form_defaults_and_custom_filters(page, live_server, mp3):
    url, app = live_server
    studio = app.state.studio
    with mp3.open("rb") as ref:
        v = studio.voices.create(ref, "Dilma", "dilma.mp3", "Reference transcript")
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    open_tab(page, "Twitch & OBS")
    expect(page.locator("#channel-delay")).to_have_value("5")
    expect(page.locator("#channel-filter")).to_have_value("slurs")
    page.locator("#channel-name").fill("testchannel")
    page.locator(".command-row input").fill("!dilma")
    page.locator(".command-row select").select_option(v["id"])
    page.locator("#channel-custom").fill("private phrase\nother phrase")
    page.get_by_role("button", name="Save channel", exact=True).click()
    expect(page.get_by_label("OBS source URL")).to_have_value(url + "/testchannel")
    studio.store.patch("channel", "testchannel", enabled=True)
    assert studio.receive("testchannel", "viewer", "!dilma private phrase") is None
    expect(page.locator("#chat-events")).to_contain_text("custom word filter")
    assert studio.service.history() == []


def test_browser_language_auto_detection_and_flag_override(browser, live_server):
    url, app = live_server
    context = browser.new_context(locale="pt-BR")
    page = context.new_page()
    try:
        page.goto(url)
        expect(page.locator("#generate")).to_be_enabled()
        expect(page.get_by_role("heading", name="Suas vozes. Seu computador.")).to_be_visible()
        expect(page.locator("html")).to_have_attribute("lang", "pt-BR")
        page.get_by_role("button", name="English (Canada)", exact=True).click()
        expect(page.get_by_role("heading", name="Your voices. Your machine.")).to_be_visible()
        expect(page.locator("html")).to_have_attribute("lang", "en-CA")
        page.reload()
        expect(page.locator("#generate")).to_be_enabled()
        expect(page.get_by_role("heading", name="Your voices. Your machine.")).to_be_visible()
        page.get_by_role("button", name="Português (Brasil)", exact=True).click()
        page.get_by_role("button", name="Configuração", exact=True).click()
        expect(page.get_by_role("button", name="Salvar configuração", exact=True)).to_be_visible()
        assert app.state.service.history() == []
    finally:
        context.close()


def test_tunnel_buttons_and_scoped_links(page, live_server, monkeypatch):
    url, app = live_server
    tunnel = app.state.tunnel

    def start(port):
        assert port == int(url.rsplit(":", 1)[1])
        tunnel.url = "https://test-sharing.trycloudflare.com"
        tunnel.status = "running"
        tunnel.admin_key = "test-admin-key"
        return tunnel.snapshot()

    monkeypatch.setattr(tunnel, "start", start)
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator("#tunnel-card")).to_be_hidden()
    open_tab(page, "Configuration")
    page.get_by_role("button", name="Start secure tunnel", exact=True).click()
    expect(page.locator("#tunnel-stop")).to_be_visible()
    expect(page.locator("#tunnel-links input").first).to_have_value(
        "https://test-sharing.trycloudflare.com/#admin=test-admin-key"
    )
    page.get_by_role("button", name="Stop sharing", exact=True).click()
    expect(page.locator("#tunnel-start")).to_be_visible()
    assert tunnel.url is None


def test_shared_admin_and_obs_cookie_bootstrap(browser, live_server):
    from pacttsclone.models import ChannelConfig
    from pacttsclone.tunnel import TUNNEL_HOST

    url, app = live_server
    app.state.studio.save_channel(ChannelConfig(name="sharedchannel"))
    tunnel = app.state.tunnel
    tunnel.url = "https://pactts-test.trycloudflare.com"
    tunnel.status = "running"
    tunnel.admin_key = "test-admin-" + "x" * 40
    tunnel.player_keys = {"sharedchannel": "test-player-" + "x" * 40}
    context = browser.new_context()
    obs_context = browser.new_context()

    def forward(route):
        # Emulate cloudflared's forced origin Host; no public internet required.
        request = route.request
        headers = {**request.all_headers(), "host": TUNNEL_HOST}
        response = route.fetch(url=url + request.url.split(".com", 1)[1], headers=headers)
        route.fulfill(response=response)

    context.route("https://pactts-test.trycloudflare.com/**", forward)
    obs_context.route("https://pactts-test.trycloudflare.com/**", forward)
    try:
        page = context.new_page()
        page.goto(tunnel.url + "/#admin=" + tunnel.admin_key)
        expect(page.locator("#generate")).to_be_enabled(timeout=15000)
        assert "#" not in page.url
        assert page.evaluate("document.cookie") == ""  # capability is HttpOnly
        expect(page.locator("#tunnel-card")).to_be_hidden()
        obs = obs_context.new_page()
        obs.goto(tunnel.url + "/sharedchannel#play=" + tunnel.player_keys["sharedchannel"])
        obs.wait_for_function("!location.hash")
        assert obs.evaluate("async () => (await fetch('/api/config')).status") == 403
        assert obs.evaluate("async () => (await fetch('/api/session')).status") == 200
        assert obs.evaluate("document.cookie") == ""
    finally:
        context.unroute_all(behavior="ignoreErrors")
        obs_context.unroute_all(behavior="ignoreErrors")
        context.close()
        obs_context.close()


def test_backend_panic_stops_browser_audio_without_key_focus(page, live_server, mp3):
    url, app = live_server
    with mp3.open("rb") as ref:
        voice = app.state.studio.voices.create(ref, "Preview voice", "ref.mp3", "Known text")
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    page.locator("#player").evaluate(
        "async (audio, src) => { audio.src = src; audio.hidden = false; await audio.play(); }",
        f"/api/voices/{voice['id']}/reference",
    )
    assert page.locator("#player").evaluate("audio => !audio.paused")
    # Exactly the backend callback invoked by the native Windows hotkey.
    app.state.studio.playback.panic()
    page.wait_for_function("document.getElementById('player').paused")
    assert page.locator("#player").evaluate("audio => audio.currentTime === 0")


def test_languages_persist_across_tabs_and_reload(page, live_server):
    url, _ = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    page.get_by_text("Generation settings", exact=True).click()
    page.locator("#language").select_option("auto")
    page.locator('[data-locale="pt"]').click()
    for tab in ["voices", "channels", "history", "config", "studio"]:
        page.locator(f'[data-tab="{tab}"]').click()
        expect(page.locator("html")).to_have_attribute("lang", "pt-BR")
    expect(page.locator("#language")).to_have_value("auto")
    page.reload()
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator("html")).to_have_attribute("lang", "pt-BR")
    expect(page.locator("#language")).to_have_value("auto")
    page.locator('[data-locale="en"]').click()
    for tab in ["voices", "channels", "studio"]:
        page.locator(f'[data-tab="{tab}"]').click()
        expect(page.locator("html")).to_have_attribute("lang", "en-CA")
    expect(page.locator("#generate")).to_have_text("Generate MP3 ↗")


def test_command_voices_refresh_without_losing_drafts(page, live_server, mp3):
    url, _ = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    open_tab(page, "Twitch & OBS")
    page.locator(".command-row input").fill("!test")
    expect(page.locator(".command-row select option")).to_have_count(1)
    open_tab(page, "Voices")
    page.locator("#voice-title").fill("New voice")
    page.locator("#voice-reference").set_input_files(mp3)
    page.get_by_role("button", name="Save voice", exact=True).click()
    expect(page.locator(".voice-card .pill")).to_have_text("ready", timeout=15000)
    open_tab(page, "Twitch & OBS")
    select = page.locator(".command-row select")
    expect(select.locator("option")).to_have_count(2)
    select.select_option(label="New voice")
    selected = select.input_value()
    page.locator('[data-locale="pt"]').click()
    expect(select).to_have_value(selected)
    expect(page.locator(".command-row input")).to_have_value("!test")
    expect(select.locator("option").first).to_have_text("Selecione a voz")


def test_general_player_generate_queue_and_controls(page, live_server, mp3):
    url, app = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    add_ready_voice(page, mp3)
    page.locator("#text").fill("General player browser test")
    page.locator("#generate").click()
    expect(page.locator("#send-general")).to_be_visible(timeout=15000)
    page.locator("#send-general").click()
    expect(page.locator("#playback-note")).to_have_text("Queued on local OBS source.")
    open_tab(page, "Local")
    expect(page.locator("nav button").last).to_have_text("Local")
    expect(page.locator('[data-tab="setup"]')).to_be_hidden()
    expect(page.locator("#channel-queue")).to_contain_text("General player browser test")
    expect(page.locator("#channel-form")).to_be_hidden()
    page.locator("#general-delay").fill("0")
    page.get_by_role("button", name="Save playback settings", exact=True).click()
    wait_until(lambda: app.state.service.store.get("channel", "playbackMain")["delay_seconds"] == 0)
    obs = page.context.new_page()
    try:
        obs.goto(url + "/playbackMain")
        wait_until(
            lambda: (
                app.state.studio.playback.items("playbackMain")[0]["status"]
                in {"playing", "played"}
            )
        )
    finally:
        obs.close()
    page.goto(url + "/playbackMain/control")
    expect(page.locator("#general-form")).to_be_visible()
    expect(page.locator("#channel-form")).to_be_hidden()
    expect(page.get_by_label("OBS source URL")).to_have_value(url + "/playbackMain")


def test_default_voice_first_use_preparation(page, live_server, monkeypatch):
    from pathlib import Path

    url, app = live_server
    catalog = Path(__file__).parents[2] / "src/pacttsclone/assets/voices/catalog.json"
    monkeypatch.setattr("pacttsclone.voices.BUILTIN_CATALOG", catalog)
    app.state.studio.voices.seed_defaults()
    entered, release = threading.Event(), threading.Event()

    def transcribe(reference):
        entered.set()
        release.wait(10)
        return "Saved first-use reference transcript."

    app.state.service.engine.transcribe = transcribe
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    page.locator("#prepare-voices").click()
    card = page.locator(".voice-card").filter(
        has=page.get_by_role("heading", name="Akuma Lady", exact=True)
    )
    expect(card).to_contain_text("Not prepared for first use.")
    assert app.state.service.history() == []
    card.get_by_role("button", name="Prepare for first use", exact=True).click()
    try:
        wait_until(entered.is_set)
        expect(card).to_contain_text("Preparing for first use…")
        expect(card.get_by_role("button", name="Cancel preparation")).to_be_visible()
        expect(card.locator("progress")).to_be_visible()
    finally:
        release.set()
    expect(card.locator(".pill")).to_have_text("ready", timeout=15000)
    expect(card.get_by_label("Saved transcript")).to_have_value(
        "Saved first-use reference transcript."
    )
    page.locator('[data-tab="studio"]').click()
    expect(page.locator("#voice-select option").filter(has_text="Akuma Lady")).to_have_count(1)
    page.reload()
    expect(page.locator("#generate")).to_be_enabled()
    assert len(app.state.service.history()) == 1


def test_bug_video_ready_before_tab_and_200ms_autoplay(page, live_server):
    url, _ = live_server
    script = """
    window.YT = {Player: function(mount, options) {
      const frame = document.createElement('iframe');
      frame.src = 'https://www.youtube-nocookie.com/embed/b2eEl2oKXLA';
      frame.allow = 'autoplay'; mount.replaceWith(frame);
      this.getIframe = () => frame;
      this.playVideo = () => { window.videoPlays = (window.videoPlays || 0) + 1; };
      this.destroy = () => frame.remove();
      window.readyBugPlayer = () => options.events.onReady({target: this});
    }};
    window.onYouTubeIframeAPIReady();
    """
    page.route(
        "https://www.youtube.com/iframe_api",
        lambda r: r.fulfill(content_type="application/javascript", body=script),
    )
    page.route("https://www.youtube-nocookie.com/**", lambda r: r.fulfill(body="player stub"))
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    assert page.locator("#bug-video iframe").count() == 0
    page.locator('[data-tab="bugs"]').click()
    page.wait_for_function("() => typeof window.readyBugPlayer === 'function'")
    expect(page.locator("#pane-bugs")).to_be_hidden()
    page.clock.install()
    page.evaluate("window.readyBugPlayer()")
    expect(page.locator("#pane-bugs")).to_be_visible()
    expect(page.locator("#bug-youtube-link")).to_be_hidden()
    page.clock.pause_at(datetime.now(UTC) + timedelta(seconds=1))
    # The clock may advance to pause_at, so reset the play counter and verify
    # cancellation on a fresh ready event using the controlled clock below.
    page.locator('[data-tab="voices"]').click()
    expect(page.locator("#bug-video iframe")).to_have_count(0)
    page.evaluate("window.videoPlays = 0")
    page.locator('[data-locale="pt"]').click()
    page.locator('[data-tab="bugs"]').click()
    expect(page.locator("#pane-bugs")).to_be_hidden()
    page.evaluate("window.readyBugPlayer()")
    expect(page.locator("#bug-video iframe")).to_have_attribute(
        "title", "Guia para relatar problemas"
    )
    page.clock.run_for(199)
    assert page.evaluate("window.videoPlays") == 0
    expect(page.locator("#bug-youtube-link")).to_be_hidden()
    page.clock.run_for(1)
    assert page.evaluate("window.videoPlays") == 1
    page.clock.run_for(1799)
    expect(page.locator("#bug-youtube-link")).to_be_hidden()
    page.clock.run_for(1)
    expect(page.locator("#bug-youtube-link")).to_be_visible()
    page.locator('[data-tab="studio"]').click()
    expect(page.locator("#bug-youtube-link")).to_be_hidden()
    page.locator('[data-tab="bugs"]').click()
    page.evaluate("window.readyBugPlayer()")
    expect(page.locator("#bug-youtube-link")).to_be_hidden()
    page.locator('[data-tab="studio"]').click()
    page.clock.run_for(500)
    assert page.evaluate("window.videoPlays") == 1
    expect(page.locator("#bug-video iframe")).to_have_count(0)
    page.unroute_all(behavior="wait")


def test_local_autoqueue_checkbox_persists_and_queues_without_autoplay(page, live_server, mp3):
    url, app = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator("#autoqueue")).not_to_be_checked()
    page.locator("#autoqueue").check()
    page.reload()
    expect(page.locator("#autoqueue")).to_be_checked()
    expect(page.locator("#autoplay")).not_to_be_checked()
    add_ready_voice(page, mp3)
    page.locator("#text").fill("Automatically queue my local generation")
    page.locator("#generate").click()
    expect(page.locator("#autoqueue-note")).to_have_text(
        "Queued on local OBS source.", timeout=15000
    )
    assert len(app.state.studio.playback.items("playbackMain")) == 1
    assert page.locator("#player").evaluate("audio => audio.paused")
    page.locator('[data-tab="studio"]').click()
    expect(page.locator("#channel-queue")).to_contain_text(
        "Automatically queue my local generation"
    )
    page.locator('[data-tab="studio"]').click()
    page.locator("#autoqueue").uncheck()
    page.locator("#generate").click()
    expect(page.locator("#status")).to_contain_text("MP3 ready", timeout=15000)
    assert len(app.state.studio.playback.items("playbackMain")) == 1


def test_obs_and_control_links_open_new_tabs_without_polling_race(page, live_server):
    url, app = live_server
    app.state.studio.save_channel(ChannelConfig(name="testchannel"))
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    open_tab(page, "Twitch & OBS")
    page.locator("#channel-select").select_option("testchannel")
    player = page.locator("#channel-links").get_by_role("link", name="Open OBS player", exact=True)
    expect(player).to_have_attribute("target", "_blank")
    # Polling must not replace a link while a physical click is in progress.
    node = player.element_handle()
    page.wait_for_timeout(1600)
    assert node.evaluate("node => node.isConnected")
    for label, path in [
        ("Open OBS player", "/testchannel"),
        ("Open separate control page", "/testchannel/control"),
    ]:
        with page.expect_popup() as popup:
            page.locator("#channel-links").get_by_role("link", name=label, exact=True).click()
        popup.value.wait_for_url(url + path)
        assert page.url == url + "/"
        popup.value.close()
    open_tab(page, "Local")
    for label, path in [
        ("Open local OBS player", "/playbackMain"),
        ("Open local OBS control page", "/playbackMain/control"),
    ]:
        with page.expect_popup() as popup:
            page.locator("#general-form").get_by_role("link", name=label, exact=True).click()
        popup.value.wait_for_url(url + path)
        assert page.url == url + "/"
        popup.value.close()


def test_monitor_follows_twitch_jobs_across_tabs_and_after_reload(page, live_server, mp3):
    url, app = live_server
    studio = app.state.studio
    with mp3.open("rb") as reference:
        voice = studio.voices.create(reference, "Monitor Voice", "voice.mp3", "Known transcript")
    studio.save_channel(
        ChannelConfig(name="monitortest", commands={"!voice": voice["id"]}, user_cooldown_seconds=0)
    )
    # Test chat ingestion without opening a real IRC connection.
    studio.store.patch("channel", "monitortest", enabled=True)
    original = studio.service.engine.synthesize
    releases = [threading.Event(), threading.Event()]
    entered = [threading.Event(), threading.Event()]
    calls = []

    def blocked(*args):
        number = len(calls)
        calls.append(number)
        entered[number].set()
        assert releases[number].wait(15)
        return original(*args)

    studio.service.engine.synthesize = blocked
    try:
        page.goto(url)
        expect(page.locator("#generate")).to_be_enabled()
        open_tab(page, "Twitch & OBS")
        first = studio.receive("monitortest", "viewerone", "!voice First speech")
        assert entered[0].wait(3)
        expect(page.locator("#live-generation")).to_be_visible()
        expect(page.locator("#live-generation-source")).to_contain_text(
            "Twitch · #monitortest · viewerone"
        )
        expect(page.locator("#live-generation-source")).to_contain_text("Monitor Voice")
        expect(page.locator("#live-generation-timer")).not_to_have_text("00:00.0")
        second = studio.receive("monitortest", "viewertwo", "!voice Second speech")
        page.wait_for_timeout(900)
        expect(page.locator("#live-generation-source")).to_contain_text("viewerone")
        page.reload()
        expect(page.locator("#monitor-source")).to_contain_text("viewerone")
        expect(page.locator("#cancel-job")).to_be_visible()
        page.locator("#cancel-job").click()
        releases[0].set()
        assert entered[1].wait(5)
        expect(page.locator("#monitor-source")).to_contain_text("viewertwo")
        assert studio.service.get(first["id"])["status"] == "cancelled"
        assert studio.service.get(second["id"])["status"] == "running"
        # Monitoring a Twitch job must not autoplay it in the admin page.
        expect(page.locator("#player")).to_be_hidden()
        open_tab(page, "Configuration")
        expect(page.locator("#live-generation-source")).to_contain_text("viewertwo")
        page.locator("#view-monitor").click()
        expect(page.locator("#pane-studio")).to_be_visible()
    finally:
        for release in releases:
            release.set()


def test_voice_only_generation_and_channel_dashboard(page, live_server):
    from tests.test_v2 import FakeIRC

    url, app = live_server
    app.state.studio.twitch_factory = FakeIRC
    app.state.studio.save_channel(ChannelConfig(name="channelone"))
    app.state.studio.save_channel(ChannelConfig(name="channeltwo"))
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    expect(page.locator('#pane-studio input[type="file"]')).to_have_count(0)
    expect(page.locator('#pane-voices input[type="file"]')).to_have_count(2)
    expect(page.locator("#tunnel-card")).to_be_hidden()
    open_tab(page, "Twitch & OBS")
    first = page.locator('[data-channel="channelone"]')
    second = page.locator('[data-channel="channeltwo"]')
    expect(first).to_contain_text("disconnected")
    first.get_by_role("button", name="Turn on", exact=True).click()
    expect(first.get_by_role("button", name="Turn off", exact=True)).to_be_visible()
    assert app.state.studio.clients["channelone"].status == "connected"
    expect(second.get_by_role("button", name="Turn on", exact=True)).to_be_visible()
    first.get_by_role("button", name="Turn off", exact=True).click()
    expect(first.get_by_role("button", name="Turn on", exact=True)).to_be_visible()
    assert not app.state.studio.store.get("channel", "channelone")["enabled"]
    first.get_by_role("button", name="Delete channel", exact=True).click()
    expect(first).to_have_count(0)
    expect(second).to_be_visible()
    page.reload()
    open_tab(page, "Twitch & OBS")
    expect(page.locator('[data-channel="channelone"]')).to_have_count(0)
    open_tab(page, "Local")
    expect(page.locator("#channel-dashboard")).to_be_hidden()
    open_tab(page, "Configuration")
    expect(page.locator("#tunnel-start")).to_be_visible()


def test_long_voice_crop_notice_and_existing_thumbnail_upload(
    page, live_server, long_mp3, tmp_path
):
    from PIL import Image

    url, app = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    page.locator('[data-tab="voices"]').click()
    page.locator("#voice-title").fill("Long voice")
    page.locator("#voice-reference").set_input_files(long_mp3)
    page.locator("#voice-transcript").fill("First thirty seconds.")
    page.get_by_role("button", name="Save voice", exact=True).click()
    expect(page.locator("#voice-upload-note")).to_have_text(
        "mp3 was cropped to 30 seconds, will process anyway"
    )
    card = page.locator(".voice-card")
    expect(card.locator(".notice")).to_contain_text("cropped to 30 seconds")
    thumbnail = tmp_path / "thumbnail.png"
    Image.new("RGB", (600, 300), "green").save(thumbnail)
    card.get_by_label("Replace thumbnail", exact=True).set_input_files(thumbnail)
    expect(card.locator("img")).to_be_visible()
    page.wait_for_function('document.querySelector(".voice-card img")?.naturalWidth === 320')
    page.reload()
    expect(page.locator("#generate")).to_be_enabled()
    page.locator('[data-tab="voices"]').click()
    expect(page.locator(".voice-card img")).to_be_visible()
    page.locator('[data-locale="pt"]').click()
    expect(page.locator(".voice-card .notice")).to_contain_text("cortado para 30 segundos")
    expect(page.locator(".voice-card img")).to_be_visible()


def test_shared_admin_voices_history_scoped_obs_and_revocation(browser, live_server, mp3):
    from pacttsclone.tunnel import TUNNEL_HOST
    from tests.conftest import wait_job

    url, app = live_server
    studio = app.state.studio
    with mp3.open("rb") as stream:
        voice = studio.voices.create(stream, "Remote voice", "remote.mp3", "Known text")
    job = studio.voices.generate(
        voice["id"],
        __import__("pacttsclone.domain", fromlist=["GenerationRequest"]).GenerationRequest(
            text="Visible remote history"
        ),
    )
    wait_job(studio.service, job["id"])
    tunnel = app.state.tunnel
    tunnel.url, tunnel.status, tunnel.admin_key = (
        "https://remote-test.trycloudflare.com",
        "running",
        "admin-test-key",
    )
    contexts = [browser.new_context(), browser.new_context()]
    requests = []

    def forward(route):
        request = route.request
        requests.append(request.url)
        response = route.fetch(
            url=url + request.url.split(".com", 1)[1],
            headers={**request.all_headers(), "host": TUNNEL_HOST},
        )
        route.fulfill(response=response)

    for context in contexts:
        context.route("https://remote-test.trycloudflare.com/**", forward)
    try:
        page = contexts[0].new_page()
        page.goto(tunnel.url + "/#admin=" + tunnel.admin_key)
        expect(page.locator('[data-tab="voices"]')).to_be_enabled()
        expect(page.locator("#player")).to_be_visible()
        assert page.locator("#player").evaluate("audio => audio.paused")
        open_tab(page, "Voices")
        expect(page.locator(".voice-card")).to_contain_text("Remote voice")
        open_tab(page, "History")
        expect(page.locator("#history-list")).to_contain_text("Visible remote history")
        assert (
            page.get_by_role("link", name="Download MP3", exact=True).evaluate(
                "async a => (await fetch(a.href)).status"
            )
            == 200
        )
        open_tab(page, "Local")
        link = page.locator("#local-obs-player-link").get_attribute("href")
        assert "#play=" in link
        obs = contexts[1].new_page()
        obs.goto(link)
        obs.wait_for_function("!location.hash")
        assert obs.evaluate('async () => (await fetch("/api/session")).status') == 200
        # Cookie loss is recoverable while the original capability is still valid.
        contexts[1].clear_cookies()
        page.wait_for_timeout(1000)
        assert obs.evaluate('async () => (await fetch("/api/session")).status') == 200
        tunnel.player_keys["playbackMain"] = "replacement-key"
        expect(obs.locator("#message")).to_contain_text("Shared link expired", timeout=10000)
        before = len(requests)
        page.wait_for_timeout(1200)
        assert not any("/player/tick" in u for u in requests[before:])
        assert not any("/api/setup" in u or "/api/tunnel" in u for u in requests)
        open_tab(page, "Configuration")
        expect(page.locator("#discord-form")).to_be_hidden()
        assert not any("/api/discord" in u for u in requests)
    finally:
        for context in contexts:
            context.unroute_all(behavior="ignoreErrors")
            context.close()


def test_requester_name_persists_identity_and_fixed_status(page, live_server, mp3):
    url, app = live_server
    page.goto(url)
    expect(page.locator("#generate")).to_be_enabled()
    add_ready_voice(page, mp3)
    page.locator("#requester-name").fill("")
    page.locator("#text").fill("Identity test")
    page.locator("#generate").click()
    assert app.state.service.history() == []
    page.locator("#requester-name").fill("Named tester")
    identity = page.evaluate('localStorage.getItem("pactts-requester-id")')
    page.reload()
    expect(page.locator("#requester-name")).to_have_value("Named tester")
    expect(page.locator("#generate")).to_be_enabled()
    page.locator("#voice-select").select_option(label="Browser voice")
    page.locator("#text").fill("Identity test")
    page.locator("#generate").click()
    expect(page.locator("#player")).to_be_visible(timeout=15000)
    done = app.state.service.history()[0]
    assert done["requester_name"] == "Named tester"
    assert done["requester_id"] == identity.replace("-", "")
    open_tab(page, "History")
    expect(page.locator("#history-list")).to_contain_text("Named tester")
    expect(page.locator("#history-list")).to_contain_text(done["origin_id"])
    assert (
        page.locator("#live-generation").evaluate("node => getComputedStyle(node).position")
        == "fixed"
    )
    assert page.locator('header [data-locale="en"]').count() == 1
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    assert page.locator("#live-generation").bounding_box()["y"] == 0

def test_voice_generation_tuning_presets_and_per_job_override(page, live_server, mp3):
    url, app = live_server
    page.goto(url)
    add_ready_voice(page, mp3)
    open_tab(page, "Voices")
    card = page.locator(".voice-card").first
    card.locator(".voice-generation-settings summary").click()
    expect(card.get_by_label("Language", exact=True)).to_have_value("auto")
    card.get_by_label("Language", exact=True).select_option("en")
    card.get_by_label("Output volume (%)", exact=True).fill("150")
    card.get_by_label("Speed", exact=True).fill("0.75")
    card.get_by_label("Inference Steps").fill("14")
    card.get_by_label("Duration (seconds)").fill("7.5")
    card.get_by_label("Denoise").uncheck()
    card.get_by_role("button", name="Save generation defaults").click()
    wait_until(
        lambda: app.state.service.store.all("voice")[0]
        .get("generation_settings", {})
        .get("steps") == 14
    )
    page.reload()
    open_tab(page, "Voices")
    card = page.locator(".voice-card").first
    card.locator(".voice-generation-settings summary").click()
    expect(card.get_by_label("Language", exact=True)).to_have_value("en")
    expect(card.get_by_label("Output volume (%)", exact=True)).to_have_value("150")
    expect(card.get_by_label("Inference Steps")).to_have_value("14")
    expect(card.get_by_label("Denoise")).not_to_be_checked()
    open_tab(page, "Local")
    page.locator("#voice-select").select_option(label="Browser voice")
    expect(page.locator("#language")).to_have_value("en")
    expect(page.locator("#volume")).to_have_value("150")
    expect(page.locator("#steps")).to_have_value("14")
    expect(page.locator("#duration")).to_have_value("7.5")
    page.get_by_text("Generation settings", exact=True).click()
    page.locator("#language").select_option("pt")
    page.locator("#volume").fill("75")
    page.locator("#steps").fill("22")
    page.locator("#text").fill("Voice settings smoke test")
    page.locator("#generate").click()
    expect(page.locator("#player")).to_be_visible(timeout=15000)
    jobs = [job for job in app.state.service.history() if job["kind"] == "speech"]
    assert jobs[0]["request"]["language"] == "pt"
    assert jobs[0]["request"]["volume"] == 75
    assert jobs[0]["request"]["steps"] == 22
    assert jobs[0]["request"]["denoise"] is False
    assert jobs[0]["request"]["duration"] == 7.5
    assert app.state.service.store.all("voice")[0]["generation_settings"]["steps"] == 14
    assert app.state.service.store.all("voice")[0]["generation_settings"]["language"] == "en"
    open_tab(page, "Voices")
    card = page.locator(".voice-card").first
    if not card.locator(".voice-generation-settings").evaluate("node => node.open"):
        card.locator(".voice-generation-settings summary").click()
    card.get_by_role("button", name="Restore OmniVoice defaults").click()
    expect(card.get_by_label("Output volume (%)", exact=True)).to_have_value("100")
    expect(card.get_by_label("Language", exact=True)).to_have_value("auto")
    card.get_by_role("button", name="Save generation defaults").click()
    wait_until(
        lambda: app.state.service.store.all("voice")[0]["generation_settings"]["language"] == "auto"
    )


def test_old_browser_language_does_not_override_voice_default(page, live_server, mp3):
    url, _ = live_server
    page.goto(url)
    page.evaluate("localStorage.setItem('pactts-speech-language', 'pt')")
    page.reload()
    add_ready_voice(page, mp3)
    open_tab(page, "Local")
    page.locator("#voice-select").select_option(label="Browser voice")
    expect(page.locator("#language")).to_have_value("auto")
