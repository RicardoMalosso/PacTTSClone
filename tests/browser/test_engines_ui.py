from playwright.sync_api import expect

from .test_ui import live_server as live_server


def test_engines_catalog_has_honest_future_controls(page, live_server):
    url, app = live_server
    page.goto(url)
    page.locator('[data-tab="engines"]').click()
    expect(page.locator("#engine-rows tr")).to_have_count(3)
    omni = page.locator("#engine-rows tr").filter(has_text="OmniVoice")
    expect(omni.get_by_role("button", name="Install", exact=True)).to_be_visible()
    ming = page.locator("#engine-rows tr").filter(has_text="Ming 3.0")
    expect(ming.get_by_role("button", name="Install", exact=True)).to_be_visible()
    expect(page.locator("#engine-rows tr").filter(has_text="KittenTTS2")).to_contain_text(
        "115 preset voices"
    )
    expect(page.locator("#engine-storage")).to_contain_text(
        str(app.state.service.settings.data_dir)
    )
    page.locator('[data-locale="pt"]').click()
    expect(page.locator('[data-tab="engines"]')).to_have_text("Motores")
    page.reload()
    page.locator('[data-tab="engines"]').click()
    expect(page.locator("#engine-rows tr")).to_have_count(3)


def test_deactivate_uninstall_preserves_voice_and_requires_activation(page, live_server):
    url, app = live_server
    setup = app.state.runtime_setup
    root = app.state.service.settings.data_dir / "models"
    root.mkdir(exist_ok=True)
    model = root / "weights.safetensors"
    model.write_bytes(b"fixture")
    personal = app.state.service.settings.data_dir / "voices" / "keep.mp3"
    personal.write_bytes(b"personal")
    setup.update(models={"files": [{"path": str(model), "size": 7}]})
    page.goto(url)
    page.locator('[data-tab="engines"]').click()
    row = page.locator("#engine-rows tr").filter(has_text="OmniVoice")
    expect(row.get_by_role("button", name="Uninstall", exact=True)).to_be_disabled()
    row.get_by_role("button", name="Deactivate", exact=True).click()
    expect(row.get_by_role("button", name="Activate", exact=True)).to_be_visible()
    page.on("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Uninstall", exact=True).click()
    expect(row.get_by_role("button", name="Install", exact=True)).to_be_visible()
    assert not model.exists()
    assert personal.read_bytes() == b"personal"
    page.reload()
    page.locator('[data-tab="engines"]').click()
    expect(row.get_by_role("button", name="Install", exact=True)).to_be_visible()
