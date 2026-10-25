from playwright.sync_api import expect

from pacttsclone.models import ChannelConfig
from tests.browser.test_ui import live_server as live_server
from tests.test_twitch_events import CLIENT_ID, FakeTwitch, metadata, seed_account


def test_twitch_modes_authorization_and_rule_persistence(page, live_server, mp3, monkeypatch):
    url, app = live_server
    studio = app.state.studio
    studio.accounts.http = FakeTwitch()
    monkeypatch.setattr("pacttsclone.twitch_events.EventSubClient.start", lambda _: None)
    with mp3.open("rb") as source:
        voice = studio.voices.create(source, "Event voice", "ref.mp3", "Exact transcript")
    studio.save_channel(ChannelConfig(name="streamer"))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.locator('[data-tab="channels"]').click()
    page.locator("#channel-select").select_option("streamer")
    expect(page.locator("#channel-transport")).to_have_value("irc")
    expect(page.locator("#twitch-oauth-panel")).to_be_hidden()
    page.locator("#channel-transport").select_option("oauth")
    expect(page.locator("#twitch-oauth-panel")).to_be_visible()
    page.locator("#twitch-client-id").fill(CLIENT_ID)
    page.locator("#twitch-authorize").click()
    expect(page.locator("#twitch-user-code")).to_have_text("ABCD")
    expect(page.locator("#twitch-auth-status")).to_contain_text(
        "Authorized broadcaster", timeout=10000
    )
    if page.locator("#commands-list .command-row").count():
        page.locator("#commands-list .command-row button").click()
    page.locator("#add-event-rule").click()
    row = page.locator(".event-rule")
    row.get_by_label("Event type", exact=True).select_option("bits")
    row.get_by_label("Event voice", exact=True).select_option(voice["id"])
    row.get_by_label("Minimum Bits", exact=True).fill("100")
    row.get_by_label("Event text template", exact=True).fill("{username}: {text}")
    page.locator("#channel-enabled").check()
    page.get_by_role("button", name="Save channel", exact=True).click()
    expect(page.locator("#channel-list")).to_contain_text("OAuth / EventSub")
    page.reload()
    page.locator('[data-tab="channels"]').click()
    page.locator("#channel-select").select_option("streamer")
    expect(page.locator("#channel-transport")).to_have_value("oauth")
    expect(page.locator(".event-rule").get_by_label("Minimum Bits", exact=True)).to_have_value(
        "100"
    )
    expect(
        page.locator(".event-rule").get_by_label("Event text template", exact=True)
    ).to_have_value("{username}: {text}")
    page.locator('[data-locale="pt"]').click()
    expect(page.locator("#channel-transport option:checked")).to_have_text(
        "OAuth · chat, pontos do canal, Bits e inscrições"
    )
    expect(page.locator(".event-rule").get_by_label("Mínimo de Bits", exact=True)).to_have_value(
        "100"
    )
    page.locator('[data-locale="en"]').click()
    expect(page.locator(".event-rule").get_by_label("Minimum Bits", exact=True)).to_have_value(
        "100"
    )
    page.locator("#twitch-load-rewards").click()
    expect(page.locator("#twitch-rewards")).to_contain_text("Voice reward")
    page.locator("#twitch-reward-title").fill("Read with voice")
    page.locator("#twitch-create-reward").click()
    expect(page.locator(".event-rule")).to_have_count(2)
    page.locator("#twitch-forget").click()
    expect(page.locator("#twitch-auth-status")).to_have_text("Not authorized")
    assert not studio.accounts.snapshot("streamer")["authorized"]
    assert not errors


def test_event_generation_appears_in_monitor_and_event_history(page, live_server, mp3, monkeypatch):
    from pacttsclone.models import EventRule
    from pacttsclone.twitch_events import EVENT_TYPES

    url, app = live_server
    studio = app.state.studio
    seed_account(studio.accounts)
    studio.accounts.http = FakeTwitch()
    monkeypatch.setattr("pacttsclone.twitch_events.EventSubClient.start", lambda _: None)
    with mp3.open("rb") as source:
        voice = studio.voices.create(source, "Event voice", "ref.mp3", "Exact transcript")
    studio.save_channel(
        ChannelConfig(
            name="streamer",
            transport="oauth",
            enabled=True,
            event_rules=[EventRule(kind="bits", voice_id=voice["id"])],
            user_cooldown_seconds=0,
        )
    )
    page.goto(url)
    page.locator('[data-tab="channels"]').click()
    page.locator("#channel-select").select_option("streamer")
    studio.events.receive(
        "streamer",
        EVENT_TYPES["bits"],
        {
            "bits": 100,
            "user_name": "Viewer",
            "message": {"text": "Speak this event"},
        },
        metadata(),
    )
    expect(page.locator("#twitch-event-history")).to_contain_text("Speak this event", timeout=15000)
    expect(page.locator("#twitch-event-history")).to_contain_text("accepted")
    page.locator('[data-tab="history"]').click()
    expect(page.locator("#history-list")).to_contain_text("Speak this event")
    assert studio.service.history()[0]["channel"] == "streamer"
