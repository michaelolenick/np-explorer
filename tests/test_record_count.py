"""The record count on the home page (owner, 2026-11-13): counted from the planner's estimates, stored, refreshed
every eight hours, shown with the cross-reference note; the page keeps the standard menu and width."""
from datetime import datetime, timedelta, timezone

import pytest
from starlette.testclient import TestClient

from app import db, record_count


@pytest.fixture(scope="module", autouse=True)
def _pool():
    db.pool.open(wait=False)           # no `with`: the lifespan would close the pool for later modules


def _client():
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def test_count_is_stored_and_reused_until_stale(monkeypatch):
    record_count._mem.update(at=0.0, value=None)
    first = record_count.refresh()
    assert first["rows"] > 1_000_000_000 and first["tables"] > 500
    assert record_count.total()["rows"] == first["rows"]                      # from memory
    record_count._mem.update(at=0.0, value=None)
    assert record_count.total()["rows"] == first["rows"]                      # from the table, still fresh
    with db.conn() as conn:                                                   # make it stale: it recounts
        conn.execute("UPDATE site_counts SET at = %s WHERE key = %s",
                     (datetime.now(timezone.utc) - timedelta(hours=record_count.REFRESH_HOURS + 1), record_count.KEY))
    record_count._mem.update(at=0.0, value=None)
    again = record_count.total()
    assert again["at"] > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert record_count.short(1_502_149_857) == "1.5 billion" and record_count.short(24_000_000) == "24 million"


def test_home_page_shows_the_total_with_the_cross_reference_note():
    client = _client()
    r = client.get("/")
    assert r.status_code == 200 and 'class="wide contained"' in r.text
    n = record_count.total()["rows"]
    assert f"{n:,}" in r.text and "cross-referenced" in r.text and "records" in r.text
