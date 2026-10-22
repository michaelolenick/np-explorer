"""Daily LinkedIn posts (app/linkedin.py): the connect link is guarded, the post format, little-text escaping,
numbers checked against the data, and skipping."""

import datetime as dt

from starlette.testclient import TestClient

from app import linkedin, main

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def test_connect_needs_the_key_and_callback_explains():
    assert client.get("/linkedin/connect", follow_redirects=False).status_code == 403
    assert client.get("/linkedin/connect?key=wrong", follow_redirects=False).status_code == 403
    r = client.get("/linkedin/callback")
    assert r.status_code == 400 and "Missing code" in r.text
    r = client.get("/linkedin/callback?code=x&state=1.bad")
    assert r.status_code == 400 and "Link expired" in r.text


def test_post_format_and_escaping(monkeypatch):
    monkeypatch.setattr("app.ideas.pool_items", lambda day=None: (dt.date(2026, 10, 22), [{}] * 60))
    d = {"hook": "What public records said this week", "items": [
        {"id": 1, "question": "Who funds the Smithsonian?", "url": "/ask?intent=funders_of&org=Smithsonian",
         "line": "The Smithsonian's biggest funder gave $12.5 million"},
        {"id": 2, "question": "Q2", "url": "/today", "line": "Line two (with parens)"},
        {"id": 3, "question": "Q3", "url": "/ask?intent=x", "line": "Line three"}]}
    text, comment = linkedin.render_post(d)
    assert text.startswith("What public records said this week\n\n- The Smithsonian") and "http" not in text
    assert text.endswith(linkedin.CLOSER)
    assert "utm_source=linkedin&utm_medium=social&utm_campaign=daily" in comment
    assert "/today?utm_source=linkedin" in comment and "All 60 of today's finds" in comment
    assert linkedin.little_text("Line two (with parens) #1 @x") == "Line two \\(with parens\\) \\#1 \\@x"


def test_compose_drops_unchecked_numbers(monkeypatch):
    cands = [{"id": i, "question": f"Q{i}", "url": f"/q{i}", "data": {"rows": [{"total": 1000000 * i}]}}
             for i in range(1, 5)]
    lines = {1: "One gave $1 million", 2: "Two gave $2 million", 3: "Three gave $99 million", 4: "Four gave $4 million"}

    class R:
        status_code = 200
        def json(self):
            import json as j
            return {"content": [{"type": "text", "text": j.dumps({"hook": "Who gave what", "items": [
                {"id": i, "line": lines[i]} for i in (1, 2, 3, 4)]})}]}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(linkedin.httpx, "post", lambda *a, **k: R())
    d = linkedin.compose(cands)
    assert [x["id"] for x in d["items"]] == [1, 2, 4]          # "$99 million" isn't in its data: dropped


def test_skip_needs_a_signed_link():
    assert client.get("/linkedin/skip?d=2026-10-22&t=bad").status_code == 404
    assert client.post("/linkedin/inbound?key=wrong", json={}).status_code == 404
