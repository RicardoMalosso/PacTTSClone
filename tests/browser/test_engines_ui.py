from playwright.sync_api import expect

from .test_ui import live_server as live_server


def test_engines_catalog_has_honest_future_controls(page, live_server):
    url, app = live_server
    page.goto(url)
    page.locator('[data-tab="engines"]').click()
    expect(page.locator('#engine-rows tr')).to_have_count(3)
    omni = page.locator('#engine-rows tr').filter(has_text='OmniVoice')
    expect(omni.get_by_role('button', name='Install', exact=True)).to_be_visible()
    ming = page.locator('#engine-rows tr').filter(has_text='Ming 3.0')
    expect(ming).to_contain_text('Available in a later release')
    expect(ming.get_by_role('button')).to_have_count(0)
    expect(page.locator('#engine-storage')).to_contain_text(str(app.state.service.settings.data_dir))
    page.locator('[data-locale="pt"]').click()
    expect(page.locator('[data-tab="engines"]')).to_have_text('Motores')
    page.reload()
    page.locator('[data-tab="engines"]').click()
    expect(page.locator('#engine-rows tr')).to_have_count(3)
