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


def test_channel_version_selection(page, live_server, monkeypatch, tmp_path):
    from pacttsclone.updater import release_catalog
    from tests.test_updater import release

    url, app = live_server
    updater = app.state.updater
    updater.enabled = True
    updater.root = tmp_path / 'updates'
    first, second = release('v2.2.1'), release('v2.3.0-rc.1')
    first['published_at'] = '2026-11-01T00:00:00Z'
    second['published_at'] = '2026-10-31T00:00:00Z'
    updater.catalog = release_catalog([second, first])
    monkeypatch.setattr(updater, 'check', lambda: updater.state)
    page.goto(url)
    page.locator('[data-tab="config"]').click()
    expect(page.locator('#update-experimental')).to_be_checked()
    options = page.locator('#update-version option').all_text_contents()
    assert '2.2.1' in options[1] and '2.3.0-rc.1' in options[2]
    page.locator('#update-version').select_option('v2.3.0-rc.1')
    page.locator('#update-apply').click()
    expect(page.locator('#update-manager-status')).to_contain_text('Pinned')
    page.reload()
    page.locator('[data-tab="config"]').click()
    expect(page.locator('#update-version')).to_have_value('v2.3.0-rc.1')
    page.locator('#update-experimental').uncheck()
    expect(page.locator('#update-version')).to_have_value('latest')
    assert page.locator('#update-version option').count() == 2
    page.locator('[data-locale="pt"]').click()
    expect(page.locator('#update-channel-label')).to_contain_text('experimentais')
    page.locator('#updates-card').screenshot(path=str(tmp_path / 'updates.png'))
    page.locator('#update-apply').click()
    expect(page.locator('#update-manager-status')).not_to_contain_text('Fixada')
    assert updater.preferences == {'include_experimental': False, 'target': 'latest'}
