"""The home page's permanent-link note sits in the search form's "More options" row, and only on the home page."""

import re

from starlette.testclient import TestClient

from app import main

client = TestClient(main.app)            # no `with`: keeps the shared pool open
NOTE = "Every search has its own link. Bookmark it, share it, cite it."


def test_note_in_the_search_form_on_home_only():
    html = client.get("/").text
    form = re.search(r'<form class="search".*?</form>', html, re.S).group(0)
    assert NOTE in form and form.index("More options") < form.index(NOTE)
    assert NOTE not in html[html.index("</form>"):]          # not crowding "Or ask:"
    assert NOTE not in client.get("/search?q=smith").text
