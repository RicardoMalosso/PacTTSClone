from playwright.sync_api import expect

from pacttsclone.app import create_app
from pacttsclone.config import Settings
from tests.browser.test_ui import live_server as live_server


def test_config_and_optional_import_available_before_initial_setup(
    page, live_server, tmp_path, engine, mp3
):
    url, app = live_server
    old = create_app(Settings(data_dir=tmp_path / "previous/data"), engine)
    try:
        with mp3.open("rb") as source:
            old.state.studio.voices.create(source, "Imported before setup", "ref.mp3", "Saved text")
        app.state.runtime_setup.update(status="failed", stage="idle", error=None)
        page.goto(url)
        expect(page.locator("#generate")).to_be_disabled()
        expect(page.locator('[data-tab="config"]')).to_be_enabled()
        expect(page.locator('[data-tab="voices"]')).to_be_disabled()
        page.locator('[data-tab="config"]').click()
        expect(page.locator("#import-card")).to_be_visible()
        expect(page.locator("#weight-import")).to_be_visible()
        expect(page.locator("#personal-import")).to_be_visible()
        page.locator("#personal-import-source").fill(str(old.state.service.settings.data_dir))
        page.locator('#personal-import-sections input[value="config"]').uncheck()
        page.locator('#personal-import-sections input[value="outputs"]').uncheck()
        page.locator("#personal-import").click()
        expect(page.locator("#optional-import-status")).to_contain_text("succeeded", timeout=10000)
        expect(page.locator("#optional-import-result")).to_contain_text("Imported voices: 1")
        expect(page.locator("#pane-config")).to_be_visible()
        expect(page.locator("#generate")).to_be_disabled()
        assert not app.state.runtime_setup.snapshot()["ready"]
        assert app.state.studio.store.all("voice")[0]["transcript"] == "Saved text"
        assert old.state.studio.store.all("voice")[0]["transcript"] == "Saved text"
        # Models and personal data are independent actions, neither starts installation.
        requests = []

        def capture(route):
            requests.append(route.request.post_data_json)
            route.fulfill(json=app.state.runtime_setup.snapshot())

        page.route("**/api/import/start", capture)
        page.locator("#weight-search-roots").fill(str(tmp_path / "previous/data/cache"))
        page.locator("#weight-move").uncheck()
        with page.expect_response("**/api/import/start"):
            page.locator("#weight-import").click()
        assert requests[0]["category"] == "models"
        assert requests[0]["move_weights"] is False
        assert not app.state.runtime_setup.thread
    finally:
        old.state.studio.close()
