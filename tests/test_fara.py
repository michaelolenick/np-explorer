"""Foreign agents (loader/fara.py, app/fara.py): dates, the menu submenu and the pages (owner, 2026-11-04)."""

import datetime as dt

from loader import fara


def test_dates_and_strings():
    assert fara._date("10/29/2026") == dt.date(2026, 10, 29)
    assert fara._date("") is None and fara._date("2026-10-29") is None and fara._date("13/40/2026") is None
    assert fara._s("  Javelin Advisors LLC ") == "Javelin Advisors LLC" and fara._s("   ") is None


def test_menu_submenu_and_more_page():
    base = open("templates/base.html").read()
    pol = base[base.index('nav-drop-head">Politics and lobbying'):base.index('nav-drop-head">Federal spending')]
    assert '<a href="/fara">Foreign agents (FARA)</a>' in pol
    for sub in ("/fara/registrants", "/fara/principals", "/fara/people"):
        assert f'class="nav-drop-sub" href="{sub}"' in pol
    from app import fara as app_fara
    assert app_fara.KINDS == {"registrants": "Registrants", "principals": "Foreign principals", "people": "Short-form registrants"}


def test_pages():
    from app import fara as app_fara
    if not app_fara.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    hub = c.get("/fara")
    if hub.status_code == 404:          # tables not loaded on this database
        return
    assert "<h1>Foreign agents (FARA)</h1>" in hub.text and 'href="/fara/registrants"' in hub.text
    assert "<h1>FARA registrants</h1>" in c.get("/fara/registrants?q=javelin").text
    assert "<h1>FARA foreign principals</h1>" in c.get("/fara/principals?country=ISRAEL").text
    assert "<h1>FARA short-form registrants</h1>" in c.get("/fara/people?all=1").text
    assert c.get("/fara/registrant/abc").status_code == 404
    assert c.get("/fara/registrant/99999999").status_code == 404
    more = c.get("/more").text
    assert '<a href="/fara">' in more
