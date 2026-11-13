"""The query status bar (owner, 2026-11-13: "when a query is taking more than .2 sec put a status bar up"): one
script on every page (base.html), no inline code (the CSP), shown after 200 ms for searches, query links and
in-page requests, with the elapsed time."""
import re
from pathlib import Path

from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_the_bar_script_is_on_every_page_and_shows_after_200_ms():
    js = (ROOT / "static/progress.js").read_text()
    assert "SHOW_AFTER = 200" in js and "np-progress" in js and "submit" in js and "fetch" in js and "pageshow" in js
    css = (ROOT / "static/style.css").read_text()
    assert ".np-progress" in css and ".np-progress-bar" in css
    base = (ROOT / "templates/base.html").read_text()
    assert "/static/progress.js" in base
    from app import db
    from app.main import app
    db.pool.open(wait=False)
    client = TestClient(app)
    for path in ("/", "/boards", "/about"):
        r = client.get(path)
        assert r.status_code == 200 and "/static/progress.js" in r.text and 'class="wide contained"' in r.text, path
    assert not re.search(r"<script>[^<]*np-progress", base)      # nothing inline
