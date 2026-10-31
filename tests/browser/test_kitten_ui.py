from dataclasses import replace

from playwright.sync_api import expect

from .test_ui import add_ready_voice
from .test_ui import live_server as live_server


def test_kitten_controls_presets_and_engine_settings_persist(page, live_server, mp3, tmp_path):
    # Explicit fake inference server. This covers UI/API, not model quality.
    url, app = live_server
    page.goto(url)
    add_ready_voice(page, mp3, title="Kitten test voice")
    service = app.state.service
    profile = service.store.all("voice")[0]
    service.store.patch("voice", profile["id"], status="unprepared", transcript="")
    service.settings = service.runner.settings = replace(service.settings, engine_id="kittentts2")
    service.kitten_installed = lambda: True
    app.state.runtime_setup.update(active_engine="kittentts2", engine_enabled=True)
    page.reload()
    page.locator('[data-tab="voices"]').click()
    editor = page.locator(".voice-generation-settings")
    editor.locator(":scope > summary").click()
    expect(editor.locator(".kitten-options")).to_be_visible()
    for setting in [
        "language",
        "speed",
        "duration",
        "steps",
        "guidance_scale",
        "postprocess_output",
    ]:
        expect(editor.locator(f'[data-setting="{setting}"]')).to_be_hidden()
    editor.locator('[data-kitten="mode"]').select_option("preset")
    expect(editor.locator('[data-kitten="voice"] option')).to_have_count(115)
    editor.locator('[data-kitten="voice"]').select_option("Bruno")
    editor.locator('[data-kitten="preset"]').select_option("expressive")
    editor.locator('[data-kitten="seed"]').fill("42")
    with page.expect_response(
        lambda response: (
            response.url.endswith("/generation-settings") and response.request.method == "PUT"
        )
    ) as saved_response:
        editor.get_by_role("button", name="Save generation defaults", exact=True).click()
    assert saved_response.value.status == 200
    expect(editor.locator('[data-kitten="seed"]')).to_have_value("42")
    saved = service.store.all("voice")[0]
    assert saved["engine_generation_settings"]["kittentts2"]["kitten"]["mode"] == "preset"
    assert saved["generation_settings"]["speed"] == 1
    page.reload()
    page.locator('[data-tab="studio"]').click()
    page.locator("#voice-select").select_option(label="Kitten test voice")
    page.get_by_text("Generation settings", exact=True).click()
    expect(page.locator('#generate-form [data-kitten="preset"]')).to_have_value("expressive")
    expect(page.locator('#generate-form [data-kitten="seed"]')).to_have_value("42")
    page.locator("#text").fill("Olá do preset Kitten.")
    page.locator("#requester-name").fill("Preset test")
    page.locator("#generate").click()
    expect(page.locator("#player")).to_be_visible(timeout=15000)
    assert service.store.get("voice", profile["id"])["transcript"] == ""
    page.locator('#generate-form [data-kitten="mode"]').select_option("clone")
    expect(page.locator('#generate-form [data-kitten="voice"]')).to_be_hidden()
    page.locator('[data-locale="pt"]').click()
    expect(page.locator("#generate-form .kitten-options legend")).to_have_text(
        "Configurações do KittenTTS2"
    )
    expect(page.locator('#generate-form [data-kitten="mode"]')).to_have_value("clone")
    expect(page.locator('#generate-form [data-kitten="seed"]')).to_have_value("42")
    page.screenshot(path=str(tmp_path / "kitten-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    page.screenshot(path=str(tmp_path / "kitten-mobile.png"), full_page=True)
