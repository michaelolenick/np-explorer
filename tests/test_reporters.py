"""Get Ideas email (app/reporters.py): signup, confirmation, the email itself, sending and unsubscribing."""

import datetime as dt
import re
import uuid

import pytest
from starlette.testclient import TestClient

from app import contact, db, main, reporters

client = TestClient(main.app)            # no `with`: keeps the shared pool open
POOL = [{"id": i, "question": f"Question {i}?", "url": f"/ask?intent=x&id={i}"} for i in range(1, 121)]


def test_each_reader_gets_a_different_30_and_a_rerun_the_same():
    day = dt.date(2026, 10, 21)
    a, b = reporters.pick(POOL, 1, day), reporters.pick(POOL, 2, day)
    assert len(a) == 30 and len({x["id"] for x in a}) == 30
    assert a != b and reporters.pick(POOL, 1, day) == a


def test_email_has_links_cite_note_donate_contact_unsubscribe():
    subject, text, body = reporters.render_email(POOL[:30], "tok123", dt.date(2026, 10, 21))
    assert "30 story leads" in subject
    assert body.count("<li") == 30 and f'href="{reporters.SITE_URL}/ask?intent=x&amp;id=1"' in body
    for s in ("cite strategystudio.org", "DONATE", "/support", "/contact", "/get-ideas/unsubscribe?t=tok123",
              reporters.REPLY_TO, "interview", "podcast"):
        assert s in body, s
    assert "Courier" in body and "<script" not in body and "<img" not in body
    assert "Unsubscribe: " in text and "/get-ideas/unsubscribe?t=tok123" in text


def test_signup_page_and_bot_check():
    html = client.get("/get-ideas").text
    assert 'name="email"' in html and "Daily story leads drawn from public records" in html
    r = client.post("/get-ideas", data={"email": "x@example.com", "website": "spam", "t": contact.issue_token()},
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/get-ideas?sent=1"


@pytest.fixture
def fake_postmark(monkeypatch):
    sent = []

    def post(path, payload):
        sent.append((path, payload))
        if path == "/email/batch":
            return 200, [{"ErrorCode": 0} for _ in payload]
        return 200, {"ErrorCode": 0}
    monkeypatch.setattr(reporters, "_postmark", post)
    return sent


def test_confirm_then_send_once_then_unsubscribe(fake_postmark, monkeypatch):
    db.pool.open(wait=True)
    email = f"test-{uuid.uuid4().hex[:10]}@example.com"
    try:
        assert reporters.signup(email)
        path, msg = fake_postmark[-1]
        assert path == "/email" and msg["To"] == email and msg["MessageStream"] == "outbound"
        token = re.search(r"confirm\?t=([A-Za-z0-9_-]+)", msg["TextBody"]).group(1)
        monkeypatch.setattr(reporters, "_pool", lambda day: POOL)
        assert reporters.send_daily(only=email, status=lambda *_: None) == 0       # not confirmed yet
        assert "on the list" in client.get(f"/get-ideas/confirm?t={token}").text
        assert reporters.send_daily(only=email, status=lambda *_: None) == 1
        assert fake_postmark[-1][1][0]["MessageStream"] == "broadcast"
        assert reporters.send_daily(only=email, status=lambda *_: None) == 0       # once a day
        assert "UNSUBSCRIBE" in client.get(f"/get-ideas/unsubscribe?t={token}").text     # GET only asks
        with db.conn() as conn:
            assert conn.execute("SELECT status FROM idea_subscribers WHERE email = %s", (email,)).fetchone()["status"] == "active"
        client.post("/get-ideas/unsubscribe", data={"t": token})
        with db.conn() as conn:
            assert conn.execute("SELECT status FROM idea_subscribers WHERE email = %s", (email,)).fetchone()["status"] == "unsubscribed"
            kinds = [r["kind"] for r in conn.execute("""SELECT e.kind FROM idea_email_events e JOIN idea_subscribers s
                     ON s.id = e.subscriber_id WHERE s.email = %s ORDER BY e.id""", (email,)).fetchall()]
        assert kinds == ["signup", "confirm_sent", "verified", "sent", "unsubscribed"]
    finally:
        with db.conn() as conn:
            sid = conn.execute("SELECT id FROM idea_subscribers WHERE email = %s", (email,)).fetchone()
            if sid:
                for t in ("idea_email_events", "idea_email_sends"):
                    conn.execute(f"DELETE FROM {t} WHERE subscriber_id = %s", (sid["id"],))
                conn.execute("DELETE FROM idea_subscribers WHERE id = %s", (sid["id"],))
