"""/opt-out: an address submitted is recorded as opted out and its outreach_contacts row is marked, same answer either way."""
import pytest
from starlette.testclient import TestClient

from app import db, outreach


@pytest.fixture(scope="module")
def client():
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def _clean():
    with db.conn() as conn:
        conn.execute("DELETE FROM outreach_optouts WHERE email LIKE 'zz-test-%@example.com'")
        conn.execute("DELETE FROM outreach_contacts WHERE sheet_row = -999")


def test_page_and_menu(client):
    r = client.get("/opt-out?e=zz-test-a@example.com")
    assert r.status_code == 200 and 'class="wide contained"' in r.text and "zz-test-a@example.com" in r.text
    assert "noindex" in r.text


def test_submit_marks_the_row_and_answers_the_same_for_unknown_addresses(client):
    try:
        with db.conn() as conn:
            conn.execute(outreach.DDL)
            conn.execute("""INSERT INTO outreach_contacts (sheet_row, email, status, send_ok) VALUES (-999, 'zz-test-b@example.com', 'Sent', false)
                            ON CONFLICT (sheet_row) DO UPDATE SET status = 'Sent'""")
        known = client.post("/opt-out", data={"email": "ZZ-Test-B@example.com"})
        unknown = client.post("/opt-out", data={"email": "zz-test-c@example.com"})
        assert known.status_code == unknown.status_code == 200 and "Done." in known.text and "Done." in unknown.text
        with db.conn() as conn:
            row = conn.execute("SELECT status, synced_to_sheet FROM outreach_contacts WHERE sheet_row = -999").fetchone()
            n = conn.execute("SELECT count(*) AS n FROM outreach_optouts WHERE email LIKE 'zz-test-%@example.com'").fetchone()["n"]
        assert row["status"] == "Opted out" and row["synced_to_sheet"] is False and n == 2
    finally:
        _clean()


def test_one_click_post_and_bad_address(client):
    try:
        r = client.post("/opt-out?e=zz-test-d@example.com", data={"List-Unsubscribe": "One-Click"})
        assert "Done." in r.text
        assert "look like an email" in client.post("/opt-out", data={"email": "nope"}).text
    finally:
        _clean()
