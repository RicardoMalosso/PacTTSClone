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
    page.locator("#sfx-add-toggle").click()
    form = page.locator("#sfx-form")
    form.locator('[name="title"]').fill("Fart")
    form.locator('[name="audio"]').set_input_files(mp3)
    form.locator('[name="triggers"]').fill("[fart]\n****")
    form.get_by_role("button", name="Save new sound effect", exact=True).click()
    card = page.locator(".sfx-card")
    expect(card.get_by_role("heading", name="Fart")).to_be_visible()
    card.get_by_role("button", name="Edit sound effect").click()
    card.get_by_label("SFX volume (%)").fill("45")
    card.get_by_label("SFX duration (seconds)").fill("0.3")
    with page.expect_response(
        lambda response: "/api/sfx/" in response.url and response.request.method == "PUT"
    ) as saved:
        card.get_by_role("button", name="Save sound effect", exact=True).click()
    assert saved.value.status == 200
    page.reload()
    expect(page.locator('[data-tab="sfx"]')).to_be_enabled()
    page.locator('[data-tab="sfx"]').click()
    card.get_by_role("button", name="Edit sound effect").click()
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


def test_many_saved_effects_are_visible_and_editing_one_preserves_another(page, live_server, mp3):
    from pacttsclone.sfx import SfxSettings

    url, app = live_server
    effects = []
    for name in ("Bleep", "Fart", "Bell"):
        with mp3.open("rb") as stream:
            effects.append(
                app.state.studio.sfx.save(
                    SfxSettings(title=name, triggers=["[" + name.lower() + "]"]),
                    stream,
                )
            )
    page.goto(url)
    page.locator('[data-tab="sfx"]').click()
    expect(page.locator("#sfx-count")).to_have_text("3")
    expect(page.locator("#sfx-create")).to_be_hidden()
    expect(page.locator(".sfx-card")).to_have_count(3)
    first = page.locator(".sfx-card").filter(has=page.get_by_role("heading", name="Bleep"))
    second = page.locator(".sfx-card").filter(has=page.get_by_role("heading", name="Fart"))
    first.get_by_role("button", name="Edit sound effect").click()
    first.get_by_label("Sound effect name").fill("Unsaved bleep edit")
    second.get_by_role("button", name="Edit sound effect").click()
    second.get_by_label("SFX volume (%)").fill("30")
    with page.expect_response(lambda r: "/api/sfx/" in r.url and r.request.method == "PUT"):
        second.get_by_role("button", name="Save sound effect", exact=True).click()
    expect(second.locator("form")).to_be_hidden()
    expect(first.get_by_label("Sound effect name")).to_have_value("Unsaved bleep edit")
    page.locator("#sfx-search").fill("bell")
    expect(page.locator(".sfx-card:visible")).to_have_count(1)
    expect(page.locator(".sfx-card:visible").get_by_role("heading")).to_have_text("Bell")


def test_save_rejection_is_visible_in_form_and_keeps_upload(page, live_server, mp3):
    url, app = live_server
    page.goto(url)
    page.locator('[data-tab="sfx"]').click()
    page.locator("#sfx-add-toggle").click()
    form = page.locator("#sfx-form")
    form.locator('[name="title"]').fill("Invalid tag")
    form.locator('[name="audio"]').set_input_files(mp3)
    form.locator('[name="triggers"]').fill("[happy]")
    form.get_by_role("button", name="Save new sound effect").click()
    expect(page.locator("#sfx-save-status")).to_be_visible()
    expect(page.locator("#sfx-save-status")).to_contain_text("reserved")
    expect(form.locator('[name="title"]')).to_have_value("Invalid tag")
    assert form.locator('[name="audio"]').evaluate("input => input.files.length") == 1
    assert app.state.service.store.all("sfx") == []
    form.locator('[name="triggers"]').fill("[fixed]")
    with page.expect_response(
        lambda r: r.url.endswith("/api/sfx") and r.request.method == "POST"
    ) as retry:
        form.get_by_role("button", name="Save new sound effect").click()
    assert retry.value.status == 201, retry.value.text()
    expect(page.locator("#sfx-create")).to_be_hidden()
    expect(page.locator("#sfx-feedback")).to_contain_text("saved")
    expect(page.locator("#sfx-count")).to_have_text("1")
    page.reload()
    page.locator('[data-tab="sfx"]').click()
    expect(page.locator(".sfx-card")).to_have_count(1)


def test_rejected_audio_replacement_preserves_saved_effect_and_draft(page, live_server, mp3):
    from pacttsclone.sfx import SfxSettings

    url, app = live_server
    with mp3.open("rb") as stream:
        effect = app.state.studio.sfx.save(SfxSettings(title="Bell", triggers=["[bell]"]), stream)
    page.goto(url)
    page.locator('[data-tab="sfx"]').click()
    card = page.locator(".sfx-card")
    card.get_by_role("button", name="Edit sound effect").click()
    card.get_by_label("Sound effect name").fill("Edited bell")
    upload = card.get_by_label("Replace audio")
    upload.set_input_files({"name": "broken.mp3", "mimeType": "audio/mpeg", "buffer": b"bad"})
    card.get_by_role("button", name="Save sound effect", exact=True).click()
    expect(card.get_by_role("status")).to_have_class("error")
    assert app.state.service.store.get("sfx", effect["id"]) == effect
    expect(card.get_by_label("Sound effect name")).to_have_value("Edited bell")
    upload.set_input_files(mp3)
    card.get_by_role("button", name="Save sound effect", exact=True).click()
    expect(card.get_by_role("heading", name="Edited bell")).to_be_visible()


def test_create_requires_saved_effect_in_catalogue_before_confirming(page, live_server, mp3):
    url, _ = live_server
    page.goto(url)
    page.locator('[data-tab="sfx"]').click()
    page.locator("#sfx-add-toggle").click()
    form = page.locator("#sfx-form")
    form.locator('[name="title"]').fill("Bell")
    form.locator('[name="audio"]').set_input_files(mp3)
    form.locator('[name="triggers"]').fill("[bell]")

    def missing_from_readback(route):
        if route.request.method == "GET":
            route.fulfill(json=[])
        else:
            route.continue_()

    page.route("**/api/sfx", missing_from_readback)
    form.get_by_role("button", name="Save new sound effect").click()
    expect(page.locator("#sfx-save-status")).to_contain_text("missing from the saved list")
    expect(form.locator('[name="title"]')).to_have_value("Bell")
    assert form.locator('[name="audio"]').evaluate("input => input.files.length") == 1
    expect(page.locator("#sfx-feedback")).to_be_hidden()
