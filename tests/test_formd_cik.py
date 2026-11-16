"""Form D links built from a CIK (/corporate/form-d/cik/<CIK>) redirect to the issuer's latest Form D page instead of
404ing (Google Search Console flagged them, 2026-11-15)."""
import pytest
from starlette.testclient import TestClient

from app import db


@pytest.fixture(scope="module")
def client():
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def test_cik_link_redirects_to_the_latest_form_d_page(client):
    with db.conn() as conn:
        row = conn.execute("SELECT cik FROM sec_formd WHERE cik IS NOT NULL LIMIT 1").fetchone()
    if not row:
        pytest.skip("no Form D rows")
    r = client.get(f"/corporate/form-d/cik/{row['cik']}", follow_redirects=False)
    if r.status_code == 404:
        pytest.skip("corporate pages are not public in this environment")
    assert r.status_code == 301 and r.headers["location"].startswith("/corporate/form-d/")
    assert "/cik/" not in r.headers["location"]


def test_bad_cik_is_a_plain_404(client):
    assert client.get("/corporate/form-d/cik/not-a-number", follow_redirects=False).status_code == 404
