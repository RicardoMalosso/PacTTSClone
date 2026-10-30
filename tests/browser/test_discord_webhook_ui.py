from playwright.sync_api import expect

from tests.test_discord_webhook import URL

from .test_ui import live_server as live_server


def test_webhook_configuration_hint_persistence_and_test(page, live_server):
    url, app = live_server
    sent = []
    app.state.studio.discord.sender = lambda *args: sent.append(args)
    page.goto(url)
    page.locator('[data-tab="config"]').click()
    page.get_by_text("How to configure Discord", exact=True).click()
    expect(page.locator("#discord-form")).to_contain_text(
        "Server Settings → Integrations → Webhooks"
    )
    page.locator("#discord-webhook").fill(URL)
    page.locator("#discord-enabled").check()
    page.locator("#discord-twitch").check()
    page.locator("#discord-channels").fill("foo")
    page.locator("#discord-save").click()
    expect(page.locator("#discord-token-status")).to_have_text("Webhook saved locally")
    expect(page.locator("#discord-webhook")).to_have_value("")
    page.locator("#discord-test").click()
    expect(page.locator("#discord-status")).to_contain_text("test_sent")
    assert len(sent) == 1
    page.reload()
    page.locator('[data-tab="config"]').click()
    expect(page.locator("#discord-channels")).to_have_value("foo")
    expect(page.locator("#discord-twitch")).to_be_checked()
    assert page.locator("#discord-guild").count() == 0
    page.locator("#discord-forget").click()
    expect(page.locator("#discord-token-status")).to_have_text("No webhook saved")
