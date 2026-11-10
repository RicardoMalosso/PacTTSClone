import re
from datetime import date

from playwright.sync_api import expect

from tests.test_tournaments import seed_clip

from .test_ui import live_server as live_server


def test_create_tournament_play_report_and_reload(page, live_server, mp3):
    url, app = live_server
    content = mp3.read_bytes()
    seed_clip(app.state.service, "clip-a", content)
    seed_clip(app.state.service, "clip-b", content + b"\0")

    page.goto(url)
    tab = page.get_by_role("button", name="TTS Tourney", exact=True)
    expect(tab).to_have_attribute(
        "title", "Compare generated MP3s, review head-to-head matchups, and see the rankings."
    )
    tab.click()
    mode = page.get_by_label("Mode", exact=True)
    expect(mode).to_have_value("elimination")
    expect(mode.locator('option[value="community"]')).to_be_disabled()
    expect(mode.locator('option[value="comparison"]')).to_be_disabled()
    expect(mode.locator("option")).to_have_text(
        ["Single elimination", "Local comparisons (INDEV)", "Community Voting (INDEV)"]
    )
    pool = page.get_by_label("Audio pool")
    expect(pool.locator("option")).to_have_text(
        ["Today", "Last week", "Date picker", "Previous Winners", "All", "Random 16"]
    )
    expect(page.get_by_label("Beginning")).to_be_hidden()
    pool.select_option("range")
    today = date.today().isoformat()
    page.get_by_label("Beginning").fill(today)
    page.get_by_label("End", exact=True).fill(today)
    page.get_by_role("button", name="Create tournament").click()
    pair = page.locator("#tournament-pair")
    expect(pair.locator("audio")).to_have_count(2)
    expect(page.get_by_role("button", name="Pick A", exact=True)).to_have_attribute(
        "title", "Count a local win for Clip A."
    )
    clip = pair.locator("audio").first
    clip.evaluate("audio => audio.load()")
    page.wait_for_function("document.querySelector('#tournament-pair audio').duration > 0")
    page.get_by_role("button", name="Terrible horrible (A)", exact=True).click()
    expect(page.locator("#tournament-status")).to_have_text("Clip removed · shit from a butt")
    expect(pair).to_have_text(re.compile(r"^Champion: Clip [12]$"))

    page.reload()
    page.locator('[data-tab="tournaments"]').click()
    expect(pair).to_have_text(re.compile(r"^Champion: Clip [12]$"))
    page.get_by_role("button", name="Bracket", exact=True).click()
    expect(page.locator("#tournament-bracket")).to_contain_text("advances by walkover")
    expect(page.locator("#tournament-clips li")).to_have_count(2)
    expect(page.locator("#tournament-clips")).to_contain_text("shit from a butt")
    page.get_by_role("button", name="Ranking", exact=True).click()
    expect(page.locator("#tournament-ranking li")).to_have_count(1)
