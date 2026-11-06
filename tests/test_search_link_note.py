"""The permanent-link note: on results pages, with the refinements (owner, 2026-10-23: moved off the home page)."""

import re

from starlette.testclient import TestClient

from app import main

client = TestClient(main.app)            # no `with`: keeps the shared pool open
NOTE = "Every search has its own link. Bookmark it, share it, cite it."


def test_note_on_results_not_home():
    html = client.get("/search?q=smith").text
    form = re.search(r'<form class="search".*?</form>', html, re.S).group(0)
    assert NOTE in form and form.index("More options") < form.index(NOTE)
    # The home page has no search refinements (its own More options, since 2026-11-05, holds links, not fields).
    home = client.get("/").text
    assert NOTE not in home and 'class="more-fields"' not in home and 'name="ntee"' not in home
    assert 'class="more-options home-options"' in home
