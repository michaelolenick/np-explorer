"""A logged-in person with no folder can request one: one email to folder-requests@furp.org, once a day (owner, 2026-11-14)."""
import pytest
from starlette.testclient import TestClient

from app import accounts, db, mailer, space


@pytest.fixture
def client():
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def test_request_sends_one_email_and_is_kept_once_a_day(client, monkeypatch):
    who = "no-folder-test@example.com"
    sent = []
    monkeypatch.setattr(mailer, "send", lambda payload, timeout=20: sent.append(payload) or True)
    user = {"id": 0, "email": who, "name": "T", "session_hash": "x"}
    monkeypatch.setattr(accounts, "current_user", lambda request: user)
    monkeypatch.setattr(accounts, "csrf_ok", lambda u, f: True)
    monkeypatch.setattr(accounts, "csrf", lambda u: "t")
    try:
        for _ in range(2):
            r = client.post("/space/request-folder", data={"csrf": "t", "note": "research"}, follow_redirects=False)
            assert r.status_code == 303 and r.headers["location"] == "/space?msg=requested"
        assert len(sent) == 1 and sent[0]["To"] == "folder-requests@furp.org" and sent[0]["ReplyTo"] == who
        page = client.get("/space?msg=requested")
        assert "folder-requests@furp.org" in page.text
        assert "REQUEST A FOLDER" in client.get("/space").text
    finally:
        with db.conn() as conn:
            conn.execute("DELETE FROM space_log WHERE who = %s", (who,))
