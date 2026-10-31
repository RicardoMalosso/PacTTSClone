from dataclasses import replace

from playwright.sync_api import expect

from .test_ui import add_ready_voice
from .test_ui import live_server as live_server


def test_ming_task_controls_saved_separately_and_restored(page, live_server, mp3):
    # UI/API test with explicit fake inference. No CUDA/model quality claim.
    url, app = live_server
    page.goto(url)
    add_ready_voice(page, mp3, title="Ming test voice")
    service = app.state.service
    service.settings = service.runner.settings = replace(service.settings, engine_id="ming-3")
    service.ming_installed = lambda: True
    app.state.runtime_setup.update(active_engine="ming-3", engine_enabled=True)
    page.reload()
    page.locator('[data-tab="voices"]').click()
    editor = page.locator(".voice-generation-settings")
    editor.locator(":scope > summary").click()
    options = editor.locator(".ming-options")
    expect(options).to_be_visible()
    expect(editor.locator('[data-setting="speed"]')).to_be_hidden()
    options.locator('[data-ming="task"]').select_option("EMOTION")
    options.locator('[data-ming="emotion"]').select_option("happy")
    expect(options.locator('[data-ming="language"]')).to_be_hidden()
    editor.get_by_role("button", name="Save generation defaults", exact=True).click()
    expect(editor.locator('[data-ming="emotion"]')).to_have_value("happy")
    voice = service.store.all("voice")[0]
    assert voice["generation_settings"]["speed"] == 1
    assert voice["engine_generation_settings"]["ming-3"]["ming"]["task"] == "EMOTION"
    page.reload()
    page.locator('[data-tab="studio"]').click()
    page.locator("#voice-select").select_option(label="Ming test voice")
    page.get_by_text("Generation settings", exact=True).click()
    expect(page.locator('#generate-form [data-ming="task"]')).to_have_value("EMOTION")
    expect(page.locator('#generate-form [data-ming="emotion"]')).to_have_value("happy")
