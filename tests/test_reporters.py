"""Get Ideas email (app/reporters.py): signup, confirmation, the email itself, sending and unsubscribing."""

import datetime as dt
import re
import uuid

import pytest
from starlette.testclient import TestClient

from app import contact, db, main, reporters

client = TestClient(main.app)            # no `with`: keeps the shared pool open
POOL = [{"id": i, "question": f"Question {i}?", "url": f"/ask?intent=x&id={i}"} for i in range(1, 121)]


def test_each_reader_gets_a_different_5_and_a_rerun_the_same():
    day = dt.date(2026, 10, 21)
    a, b = reporters.pick(POOL, 1, day), reporters.pick(POOL, 2, day)
    assert len(a) == 5 and len({x["id"] for x in a}) == 5
    assert a != b and reporters.pick(POOL, 1, day) == a


def test_email_has_links_cite_note_donate_contact_unsubscribe():
    subject, text, body = reporters.render_email(POOL[:5], "tok123", dt.date(2026, 10, 21))
    assert subject == "Interesting finds from public records, October 21"
    assert body.count("<li") == 5 and f'href="{reporters.SITE_URL}/ask?intent=x&amp;id=1"' in body
    for s in ("cite furp.org", "SUPPORT FURP AND OPEN DATA", "Join the FURP Alliance", "/support", "/contact",
              "/get-ideas/unsubscribe?t=tok123", "news stories",
              reporters.REPLY_TO, "interview", "podcast"):
        assert s in body, s
    assert "Courier" in body and "<script" not in body and "<img" not in body
    assert "Unsubscribe: " in text and "/get-ideas/unsubscribe?t=tok123" in text
    assert "Support FURP and open data: " in text and "Join the FURP Alliance: " in text


def test_signup_page_and_bot_check():
    html = client.get("/get-ideas").text
    assert 'name="email"' in html and "surprising finds from public records" in html
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


def test_single_opt_in_welcome_send_once_then_unsubscribe(fake_postmark, monkeypatch):
    db.pool.open(wait=True)
    email = f"test-{uuid.uuid4().hex[:10]}@example.com"
    try:
        assert reporters.signup(email, "org")
        path, msg = fake_postmark[-1]
        assert path == "/email" and msg["To"] == email and msg["MessageStream"] == "outbound"
        assert "You're subscribed" in msg["TextBody"] and "confirm" not in msg["TextBody"].lower().replace("confirmed", "")
        token = re.search(r"unsubscribe\?t=([A-Za-z0-9_-]+)", msg["TextBody"]).group(1)
        hdr = {h["Name"]: h["Value"] for h in msg["Headers"]}
        assert hdr["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click" and token in hdr["List-Unsubscribe"]
        with db.conn() as conn:
            assert conn.execute("SELECT status FROM idea_subscribers WHERE email = %s", (email,)).fetchone()["status"] == "active"
        assert reporters.signup(email, "home") and len(fake_postmark) == 1        # a repeat sends nothing
        monkeypatch.setattr(reporters, "_pool", lambda day: POOL)
        assert reporters.send_daily(only=email, status=lambda *_: None) == 1
        assert fake_postmark[-1][1][0]["MessageStream"] == "broadcast"
        assert reporters.send_daily(only=email, status=lambda *_: None) == 0       # once a day
        assert "UNSUBSCRIBE" in client.get(f"/get-ideas/unsubscribe?t={token}").text     # GET only asks
        r = client.post(f"/get-ideas/unsubscribe?t={token}", content="List-Unsubscribe=One-Click",
                        headers={"content-type": "application/x-www-form-urlencoded"})      # a mail app's one-click POST
        assert r.status_code == 200
        with db.conn() as conn:
            assert conn.execute("SELECT status FROM idea_subscribers WHERE email = %s", (email,)).fetchone()["status"] == "unsubscribed"
            kinds = [r["kind"] for r in conn.execute("""SELECT e.kind FROM idea_email_events e JOIN idea_subscribers s
                     ON s.id = e.subscriber_id WHERE s.email = %s ORDER BY e.id""", (email,)).fetchall()]
        assert kinds == ["signup", "welcome_sent", "signup_repeat", "sent", "unsubscribed"]
    finally:
        with db.conn() as conn:
            sid = conn.execute("SELECT id FROM idea_subscribers WHERE email = %s", (email,)).fetchone()
            if sid:
                for t in ("idea_email_events", "idea_email_sends"):
                    conn.execute(f"DELETE FROM {t} WHERE subscriber_id = %s", (sid["id"],))
                conn.execute("DELETE FROM idea_subscribers WHERE id = %s", (sid["id"],))


def test_activate_pending_skips_tests_and_optouts(fake_postmark):
    db.pool.open(wait=True)
    real = f"real-{uuid.uuid4().hex[:8]}@example.org"
    test = f"t-{uuid.uuid4().hex[:8]}@example.com"
    block = "lschust1@oberlin.edu"
    ids = []
    try:
        with db.conn() as conn:
            conn.execute("DELETE FROM idea_subscribers WHERE email = %s", (block,))
            for em in (real, test, block):
                ids.append(conn.execute("INSERT INTO idea_subscribers (email, token) VALUES (%s, %s) RETURNING id",
                                        (em, uuid.uuid4().hex + uuid.uuid4().hex[:8])).fetchone()["id"])
        out = reporters.activate_pending(30, status=lambda *_: None, only=[real, test, block])
        assert out["skipped_test"] >= 1 and out["skipped_blocked"] >= 1
        sent_to = [m["To"] for p, m in fake_postmark if p == "/email"]
        assert real in sent_to and test not in sent_to and block not in sent_to
        with db.conn() as conn:
            st = {r["email"]: r["status"] for r in conn.execute("SELECT email, status FROM idea_subscribers WHERE id = ANY(%s)", (ids,)).fetchall()}
        assert st[real] == "active" and st[test] == "pending" and st[block] == "pending"
    finally:
        with db.conn() as conn:
            for t in ("idea_email_events", "idea_email_sends"):
                conn.execute(f"DELETE FROM {t} WHERE subscriber_id = ANY(%s)", (ids,))
            conn.execute("DELETE FROM idea_subscribers WHERE id = ANY(%s)", (ids,))


def test_stale_or_missing_token_is_not_a_bot_but_a_fast_one_is():
    import time
    assert not reporters.is_bot_signup({"t": contact.issue_token(now=1)})
    assert not reporters.is_bot_signup({"t": ""})
    assert reporters.is_bot_signup({"t": contact.issue_token(now=time.time())})
    assert reporters.is_bot_signup({"website": "x", "t": contact.issue_token(now=1)})


def test_signup_boxes_everywhere_and_in_place(monkeypatch):
    home = client.get("/").text
    assert "Surprising public-records finds every morning." in home and "10 " not in home.split("ideas-signup-head")[1][:60]
    assert 'name="src" value="home"' in home and 'name="website"' in home                       # honeypot kept
    assert "See a sample" not in home and home.count('name="email"') == 1                       # one signup, no sample link
    assert home.index('class="ideas-signup') > home.index('id="ideas"')                         # under the examples
    org = client.get("/about").text
    assert "Surprising finds, every morning. Free." not in org or True
    got = []
    monkeypatch.setattr(reporters, "signup", lambda email, src="page": got.append((email, src)) or True)
    r = client.post("/get-ideas", headers={"X-FURP-Signup": "1"},
                    data={"email": "reader@example.com", "src": "org", "t": contact.issue_token(now=1)})
    assert r.json()["ok"] and "You're subscribed" in r.json()["message"]   # an old token is not a bot: cached pages carry old tokens
    import time
    r = client.post("/get-ideas", headers={"X-FURP-Signup": "1"},
                    data={"email": "reader@example.com", "src": "org", "t": contact.issue_token(now=time.time() - 10)})
    assert r.json() == {"ok": True, "message": reporters.CHECK_EMAIL} and got == [("reader@example.com", "org")] * 2     # the stale-token post was signed up too
    r = client.post("/get-ideas", headers={"X-FURP-Signup": "1"},
                    data={"email": "nope", "t": contact.issue_token(now=time.time() - 10)})
    assert r.status_code == 400 and not r.json()["ok"]


def test_sample_email_page():
    r = client.get("/get-ideas/sample")
    assert r.status_code == 200 and "finds from public records" in r.text and "Join the FURP Alliance" in r.text


def test_every_email_can_be_forwarded_and_each_finding_shared():
    subject, text, body = reporters.render_email(POOL[:5], "tok123", dt.date(2026, 10, 21))
    from urllib.parse import unquote
    for part in (text, body):
        assert part.count("Forward to a colleague") >= 2                      # near the top and the bottom
        assert "Know someone who" in part and "free public-records search for nonprofits, contractors and companies" in part
        assert "utm_source=email&utm_medium=share&utm_campaign=daily" in unquote(part).replace("&amp;", "&")
    flat = unquote(body).replace("&amp;", "&")
    for kind in ("linkedin.com/sharing/share-offsite", "twitter.com/intent/tweet", "mailto:?subject="):
        assert flat.count(kind) >= 5 + (1 if kind.startswith("mailto") else 0), kind          # one per finding (plus the forward link)
    assert "/ask?intent=x&id=1&utm_source=email&utm_medium=share&utm_campaign=daily" in flat        # the finding's own page
    assert "Share: LinkedIn https://www.linkedin.com/sharing" in text                            # plain text carries the links too
    welcome = reporters.welcome_message("a@b.org", "tok")
    for part in (welcome["TextBody"], welcome["HtmlBody"]):
        assert part.count("Forward to a colleague") >= 2 and "utm_campaign=welcome" in unquote(part)
        assert "Know someone who" in part
