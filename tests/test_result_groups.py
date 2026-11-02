"""Results come in three folding groups (owner, 2026-11-02): SEC Form D and Form ADV first, then the 990s, then
state business registrations, trademarks, patents and schools. The fake check shows the last two under its own
SEC check, in the same order."""

from starlette.testclient import TestClient

from app import db, main

SEC = "<summary>SEC filings: Form D and Form ADV</summary>"
IRS = "<summary>IRS 990s: organizations and people</summary>"
OTHER = "<summary>Everything else: state business registrations, trademarks, patents, schools</summary>"


def _client():
    db.pool.open(wait=False)          # as tests/test_attribution.py: no `with`, its lifespan closes the shared pool
    return TestClient(main.app)


def test_search_shows_sec_then_990s_then_everything_else():
    html = _client().get("/search", params={"q": "smith", "type": "name"}).text
    assert html.index('class="filters"') < html.index(SEC) < html.index(IRS) < html.index(OTHER)
    assert html.count('<details class="result-group" open>') == 3
    assert html.index("<h1>People:") > html.index(IRS)
    assert html.count('id="popup"') == 1                # the person popup stays on the page (end of the 990s group)


def test_fake_check_shows_990s_then_everything_else_under_its_sec_check():
    html = _client().get("/how-to-spot-a-fake", params={"q": "smith"}).text
    assert SEC not in html                                   # its own SEC check, with the red flags, stays first
    assert html.index("Results for") < html.index("Form ADV, FINRA") < html.index(IRS) < html.index(OTHER) \
        < html.index("The short version")
