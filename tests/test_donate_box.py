"""Home page donation box: a one-time amount box and a DONATE button posting to checkout. The "Help us raise
money" line was taken off at the owner's request (2026-10-21)."""

import re

from starlette.testclient import TestClient

from app import main


def test_donate_box_on_home():
    html = TestClient(main.app).get("/").text          # no `with`: keeps the shared pool open
    box = re.search(r'<section class="donate-box".*?</section>', html, re.S).group(0)
    assert "Help us raise money" not in html
    assert 'action="/support/checkout" method="post"' in box and 'name="kind" value="once"' in box
    assert 'name="amount_dollars"' in box and 'min="5"' in box and ">DONATE</button>" in box
    assert "Not tax-deductible (yet)." in box
    assert html.index("donate-box") < html.index('id="ideas"')    # under the search box, above the ideas
