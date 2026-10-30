from playwright.sync_api import expect

from .test_ui import live_server as live_server


def test_update_status_manual_check_and_localization(page, live_server):
    url, _ = live_server
    page.goto(url)
    page.locator('[data-tab="config"]').click()
    expect(page.locator('#updates-card')).to_be_visible()
    page.locator('#update-check').click()
    expect(page.locator('#update-status')).to_contain_text('source_install')
    page.locator('[data-locale="pt"]').click()
    expect(page.locator('#updates-card h2')).to_have_text('Atualizações do aplicativo')
    page.locator('#update-check').click()
    expect(page.locator('#update-status')).to_contain_text('atualize pelo Git')
