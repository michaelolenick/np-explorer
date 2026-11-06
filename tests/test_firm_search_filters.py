"""Firm and DAF searches take the place and category filters and ignore the Form D ones (a 500 on 2026-11-05/06)."""

from starlette.testclient import TestClient

from app import db, main


def test_firm_and_daf_searches_render():
    try:
        db.pool.open(wait=False)
    except Exception:  # noqa: BLE001 - already open
        pass
    client = TestClient(main.app)
    for url in ("/search?q=deloitte&type=firm", "/search?q=fidelity&type=daf",
                "/search?q=deloitte&type=firm&state=NY&fd_cat=Real+Estate&fund=hedge"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert "<h1>" in r.text and ("Firms" in r.text or "DAF sponsors" in r.text)
