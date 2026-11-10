from playwright.sync_api import expect

from tests.test_tournaments import seed_clip

from .test_ui import live_server as live_server


def test_create_tournament_play_report_and_reload(page, live_server, mp3):
    url, app = live_server
    content = mp3.read_bytes()
    seed_clip(app.state.service, "clip-a", content)
    seed_clip(app.state.service, "clip-b", content + b"\0")

    page.goto(url)
    page.locator('[data-tab="tournaments"]').click()
    page.get_by_role("button", name="Create tournament").click()
    pair = page.locator("#tournament-pair")
    expect(pair.locator("audio")).to_have_count(2)
    clip = pair.locator("audio").first
    clip.evaluate("audio => audio.load()")
    page.wait_for_function("document.querySelector('#tournament-pair audio').duration > 0")
    page.get_by_role("button", name="Terrible horrible (A)", exact=True).click()
    expect(page.locator("#tournament-status")).to_have_text("Clip removed · shit from a butt")
    expect(pair).to_have_text("No more matchups available.")

    page.reload()
    page.locator('[data-tab="tournaments"]').click()
    expect(pair).to_have_text("No more matchups available.")
    page.get_by_role("button", name="Bracket", exact=True).click()
    expect(page.locator("#tournament-bracket")).to_contain_text("Out of ranking")
    expect(page.locator("#tournament-clips li")).to_have_count(2)
    expect(page.locator("#tournament-clips")).to_contain_text("shit from a butt")
    page.get_by_role("button", name="Ranking", exact=True).click()
    expect(page.locator("#tournament-ranking li")).to_have_count(1)
