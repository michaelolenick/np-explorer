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
    assert "/today?utm_source=linkedin" in comment and "More of today's finds" in comment
    assert linkedin.little_text("Line two (with parens) #1 @x") == "Line two \\(with parens\\) \\#1 \\@x"


def test_compose_posts_exactly_five_and_drops_unchecked_numbers(monkeypatch):
    cands = [{"id": i, "question": f"Q{i}", "url": f"/q{i}", "data": {"rows": [{"total": 1000000 * i}]}}
             for i in range(1, 11)]
    calls = []

    class R:
        status_code = 200
        def __init__(self, ids):
            self.ids = ids
        def json(self):
            import json as j
            # "$99 million" isn't in candidate 3's data: dropped, and the next good one takes its place.
            return {"content": [{"type": "text", "text": j.dumps({"hook": "Who gave what", "items": [
                {"id": i, "line": f"Donor {chr(64 + i)} gave ${99 if i == 3 else i} million"} for i in self.ids]})}]}

    def post(*a, **k):
        listed = [int(x.split(":")[0]) for x in k["json"]["messages"][0]["content"].split("id ")[1:]]
        calls.append(listed)
        return R(listed[:4])            # four ranked per call: the first call yields 3 good ones
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(linkedin.httpx, "post", post)
    d = linkedin.compose(cands)
    assert [x["id"] for x in d["items"]] == [1, 2, 4, 5, 6] and len(calls) == 2      # always exactly five
    monkeypatch.setattr(linkedin.httpx, "post", lambda *a, **k: R([1, 2]))
    assert linkedin.compose(cands) is None                     # fewer than five: no post


def test_skip_needs_a_signed_link():
    assert client.get("/linkedin/skip?d=2026-10-22&t=bad").status_code == 404
    assert client.post("/linkedin/inbound?key=wrong", json={}).status_code == 404


def test_api_version_steps_back_when_retired(monkeypatch):
    import datetime as dt
    monkeypatch.setattr(linkedin, "today", lambda: dt.date(2026, 10, 23))
    monkeypatch.setattr(linkedin, "env", lambda: {})
    assert linkedin._versions()[:3] == ["202610", "202609", "202608"]
    seen = []

    class R:
        def __init__(self, code):
            self.status_code = code
    monkeypatch.setattr(linkedin.httpx, "post", lambda url, **k: seen.append(k["headers"]["LinkedIn-Version"]) or
                        R(426 if len(seen) < 3 else 201))
    assert linkedin._api_post("u", "t", {}).status_code == 201 and seen == ["202610", "202609", "202608"]


def test_no_repeat_key_ignores_ids_and_wording_case():
    a = linkedin.used_key("/ask?board=funding-loops&intent=leaderboard&q=Who+loops&id=7&utm_source=x", "Who loops?")
    b = linkedin.used_key("/ask?intent=leaderboard&board=funding-loops&q=Other+words&id=99", "WHO LOOPS")
    assert a[0] == b[0] and a[1] == b[1] == "who loops"
