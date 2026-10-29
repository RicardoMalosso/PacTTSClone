from playwright.sync_api import expect

from tests.test_discord import FakeBot, add_voice

from .test_ui import live_server as live_server


def test_discord_settings_token_connection_and_reload(page, live_server, mp3, tmp_path):
    url, app = live_server
    manager = app.state.studio.discord
    manager.bot_factory = FakeBot
    voice = add_voice(app, mp3)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.locator('[data-tab="config"]').click()
    expect(page.locator("#discord-form")).to_be_visible()
    expect(page.locator("#discord-token-status")).to_have_text("No bot token saved")
    expect(page.locator("#discord-token")).to_have_attribute("type", "password")
    page.locator("#discord-token").fill("browser-test-credential-not-a-real-token")
    page.locator("#discord-guild").fill("123456789012345678")
    page.locator("#discord-channels").fill("234567890123456789")
    page.locator("#discord-voice").select_option(voice["id"])
    page.locator("#discord-custom").fill("blocked phrase")
    page.locator("#discord-enabled").check()
    page.locator("#discord-save").click()
    expect(page.locator("#discord-token")).to_have_value("")
    expect(page.locator("#discord-token-status")).to_have_text("Bot token saved locally")
    expect(page.locator("#discord-status")).to_contain_text("connected")
    expect(page.locator("#discord-invite")).to_be_visible()
    assert manager.config.default_voice_id == voice["id"]
    assert page.evaluate("!JSON.stringify(localStorage).includes('browser-test-credential')")
    page.reload()
    page.locator('[data-tab="config"]').click()
    expect(page.locator("#discord-enabled")).to_be_checked()
    expect(page.locator("#discord-token")).to_have_value("")
    expect(page.locator("#discord-voice")).to_have_value(voice["id"])
    expect(page.locator("#discord-custom")).to_have_value("blocked phrase")
    # Polling must not overwrite a settings draft.
    page.locator("#discord-guild").fill("999999999999999999")
    page.wait_for_timeout(2300)
    expect(page.locator("#discord-guild")).to_have_value("999999999999999999")
    page.locator("#discord-disconnect").click()
    expect(page.locator("#discord-enabled")).not_to_be_checked()
    expect(page.locator("#discord-status")).to_contain_text("disconnected")
    expect(page.locator("#discord-token-status")).to_have_text("Bot token saved locally")
    page.locator('[data-locale="pt"]').click()
    expect(page.locator("#discord-form h2")).to_have_text("Integração com Discord")
    expect(page.locator("#discord-token-status")).to_have_text("Token do bot salvo localmente")
    page.screenshot(path=str(tmp_path / "discord-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=str(tmp_path / "discord-mobile.png"), full_page=True)
    page.locator("#discord-forget").click()
    expect(page.locator("#discord-token-status")).to_have_text("Nenhum token de bot salvo")
    assert not manager.credential.token
    assert errors == []
