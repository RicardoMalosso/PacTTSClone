from playwright.sync_api import expect

from pacttsclone.models import ChannelConfig

from .test_ui import live_server as live_server


def test_sfx_tab_upload_edit_channel_preview_and_reload(page, live_server, mp3):
    url, app = live_server
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    expect(page.locator('[data-tab="sfx"]')).to_be_enabled()
    # The dedicated tab immediately follows Voices.
    assert page.locator('[data-tab="voices"] + button').get_attribute("data-tab") == "sfx"
    page.locator('[data-tab="sfx"]').click()
    form = page.locator("#sfx-form")
    form.locator('[name="title"]').fill("Fart")
    form.locator('[name="audio"]').set_input_files(mp3)
    form.locator('[name="triggers"]').fill("[fart]\n****")
    form.get_by_role("button", name="Add sound effect", exact=True).click()
    card = page.locator(".sfx-card")
    expect(card.get_by_role("heading", name="Fart")).to_be_visible()
    card.get_by_label("SFX volume (%)").fill("45")
    card.get_by_label("SFX duration (seconds)").fill("0.3")
    with page.expect_response(lambda response: "/api/sfx/" in response.url
                              and response.request.method == "PUT") as saved:
        card.get_by_role("button", name="Save sound effect", exact=True).click()
    assert saved.value.status == 200
    expect(card.get_by_label("SFX volume (%)")).to_have_value("45")
    page.reload()
    expect(page.locator('[data-tab="sfx"]')).to_be_enabled()
    page.locator('[data-tab="sfx"]').click()
    expect(card.get_by_label("SFX volume (%)")).to_have_value("45")
    expect(card.get_by_label("SFX duration (seconds)")).to_have_value("0.3")
    with mp3.open("rb") as stream:
        voice = app.state.studio.voices.create(stream, "Pac", "pac.mp3", "Known reference")
    app.state.studio.save_channel(
        ChannelConfig(
            name="preview",
            commands={"!pac": voice["id"], "!lula": voice["id"]},
        )
    )
    page.locator('[data-tab="channels"]').click()
    expect(page.locator('#channel-select option[value="preview"]')).to_be_attached()
    page.locator("#channel-select").select_option("preview")
    page.get_by_text("Preview saved channel commands", exact=True).click()
    page.locator("#script-preview-text").fill("!pac hello [fart] !lula somethingelse ****")
    page.locator("#script-preview").click()
    expect(page.locator("#script-preview-result .event-row")).to_have_count(2)
    expect(page.locator("#script-preview-result")).to_contain_text("somethingelse")
    assert app.state.service.history() == []
    page.locator('[data-tab="sfx"]').click()
    card.get_by_role("button", name="Delete sound effect").click()
    expect(page.locator(".sfx-card")).to_have_count(0)
    assert errors == []
