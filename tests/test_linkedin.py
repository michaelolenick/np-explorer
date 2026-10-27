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
    # The post: INTRO, items as plain text, no links at all. The comment: the FURP link on top, then the item links.
    assert text.startswith(linkedin.INTRO + "\n\nWhat public records said this week\n\n- The Smithsonian")
    assert not linkedin.LINKISH.search(text) and "FURP," in text
    assert text.rstrip().split("\n")[-1].startswith("#PublicRecords #OpenData")
    first, *rest = comment.split("\n")
    assert first.startswith(linkedin.SITE_URL + "/?utm_source=linkedin") and len(rest) == 3
    assert rest[0].startswith("1. Who funds the Smithsonian? " + linkedin.SITE_URL + "/ask?intent=funders_of")
    assert "utm_source=linkedin&utm_medium=social&utm_campaign=daily" in rest[0]
    assert linkedin.little_text("Line two (with parens) #1 @x") == "Line two \\(with parens\\) \\#1 \\@x"


def test_compose_posts_exactly_three_and_drops_unchecked_numbers(monkeypatch):
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
        return R(listed[:3])            # three ranked per call: the first call yields 2 good ones
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(linkedin.httpx, "post", post)
    monkeypatch.setattr(linkedin, "recently_named", lambda days=7: [])
    hooked = []
    monkeypatch.setattr(linkedin, "_hook", lambda lines: hooked.append(lines) or "What three donors gave")
    d = linkedin.compose(cands)
    assert [x["id"] for x in d["items"]] == [1, 2, 4] and len(calls) == 2      # always exactly three
    assert hooked == [[x["line"] for x in d["items"]]] and d["hook"] == "What three donors gave"   # hook fits the final three
    monkeypatch.setattr(linkedin.httpx, "post", lambda *a, **k: R([1, 2]))
    assert linkedin.compose(cands) is None                     # fewer than three: no post


def test_an_organization_named_this_week_is_not_named_again(monkeypatch):
    # Owner, 2026-10-27: no charity or firm twice within a week; a line that names one is replaced by another pick.
    assert linkedin.name_key("The Ford Foundation, Inc.") == "ford foundation"
    assert linkedin.names_repeat("x", ["Ford Foundation"], ["the Ford Foundation Inc"])
    assert linkedin.names_repeat("The Ford Foundation gave $5 million", [], ["Ford Foundation"])   # left off its list
    assert not linkedin.names_repeat("Fordham gave $5 million", ["Fordham University"], ["Ford Foundation"])
    cands = [{"id": i, "question": f"Q{i}", "url": f"/q{i}", "data": {"rows": [{"total": 1000000 * i}]}}
             for i in range(1, 7)]
    org = {1: "Ford Foundation", 2: "Acme LLC", 3: "Acme", 4: "Red Cross", 5: "Gates Foundation", 6: "Nike"}
    seen = []

    class R:
        status_code = 200
        def __init__(self, ids):
            self.ids = ids
        def json(self):
            import json as j
            return {"content": [{"type": "text", "text": j.dumps({"hook": "Who gave what", "items": [
                {"id": i, "line": f"{org[i]} gave ${i} million", "names": [org[i]]} for i in self.ids]})}]}

    def post(*a, **k):
        seen.append(k["json"]["messages"][0]["content"].split("\n")[0])
        return R([int(x.split(":")[0]) for x in k["json"]["messages"][0]["content"].split("id ")[1:]])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(linkedin.httpx, "post", post)
    monkeypatch.setattr(linkedin, "recently_named", lambda days=7: ["The Ford Foundation"])
    monkeypatch.setattr(linkedin, "_hook", lambda lines: "Who gave what")
    d = linkedin.compose(cands)
    # 1 was named this week; 3 (Acme) repeats 2 (Acme LLC) within the same post.
    assert [x["id"] for x in d["items"]] == [2, 4, 5] and d["items"][0]["names"] == ["Acme LLC"]
    assert seen[0] == "RECENTLY NAMED (don't name these again): The Ford Foundation"   # the model is told, too


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


def test_hashtags_become_linkedin_hashtags():
    c = linkedin.commentary("Line (one) #1 done\n\n#PublicRecords #OpenData")
    assert "\\(one\\)" in c and "\\#1" in c                         # escaped as text
    assert c.endswith("{hashtag|\\#|PublicRecords} {hashtag|\\#|OpenData}")


alerts: list[str] = []


def _posting(monkeypatch, row, sent_minutes_ago, last_run=False):
    calls, saved = [], {}
    alerts.clear()
    monkeypatch.setattr(linkedin, "_row", lambda day: row)
    monkeypatch.setattr(linkedin, "in_review", lambda day=None: True)
    monkeypatch.setattr(linkedin, "draft_sent_at", lambda day=None: None if sent_minutes_ago is None else
                        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=sent_minutes_ago))
    monkeypatch.setattr(linkedin, "env", lambda: {"LINKEDIN_ACCESS_TOKEN": "t", "LINKEDIN_PERSON_ID": "p",
                                                  "LINKEDIN_TOKEN_EXPIRES": "9999999999"})
    monkeypatch.setattr(linkedin, "_save", lambda day, **cols: saved.update(cols))
    monkeypatch.setattr(linkedin, "_email", lambda *a, **k: None)
    monkeypatch.setattr(linkedin, "_alert", lambda subject, text: alerts.append(subject) or True)
    monkeypatch.setattr(linkedin, "_last_run", lambda: last_run)

    class R:
        status_code, text, headers = 201, "", {"x-restli-id": "urn:li:share:1"}
    monkeypatch.setattr(linkedin, "_api_post", lambda url, token, body: calls.append(url) or R())
    return calls, saved


def test_review_week_draft_posts_once_the_email_has_been_out_30_minutes(monkeypatch):
    row = {"status": "draft", "text": "Hook\n\n- one", "comment": "links"}
    calls, saved = _posting(monkeypatch, row, sent_minutes_ago=45)
    linkedin.post(status=lambda m: None)
    assert calls and saved.get("status") == "posted"           # 2026-10-24: it logged "nothing to post" instead


def test_review_week_draft_waits_for_the_email_and_skips_stay_skipped(monkeypatch):
    calls, _ = _posting(monkeypatch, {"status": "draft", "text": "x", "comment": "y"}, sent_minutes_ago=10)
    linkedin.post(status=lambda m: None)
    calls2, _ = _posting(monkeypatch, {"status": "skipped", "text": "x", "comment": "y"}, sent_minutes_ago=90)
    linkedin.post(status=lambda m: None)
    assert not calls and not calls2


def test_comment_403_alerts_the_same_morning_and_the_day_stays_posted(monkeypatch):
    calls, saved = _posting(monkeypatch, {"status": "draft", "text": "x", "comment": "links"}, sent_minutes_ago=45)

    class Ok:
        status_code, text, headers = 201, "", {"x-restli-id": "urn:li:share:1"}

    class Denied:
        status_code, text, headers = 403, '{"status":403,"serviceErrorCode":100,"code":"ACCESS_DENIED"}', {}
    monkeypatch.setattr(linkedin, "_api_post", lambda url, token, body: Ok())
    monkeypatch.setattr(linkedin, "_comment", lambda urn, token, author, text: Denied())
    linkedin.post(status=lambda m: None)
    assert saved["status"] == "posted" and saved["post_urn"] == "urn:li:share:1"
    assert "403" in saved["error"] and alerts == ["LinkedIn post up, first comment failed"]


def test_comment_timeout_never_marks_a_live_post_failed(monkeypatch):
    calls, saved = _posting(monkeypatch, {"status": "draft", "text": "x", "comment": "links"}, sent_minutes_ago=45)

    class Ok:
        status_code, text, headers = 201, "", {"x-restli-id": "urn:li:share:1"}

    def slow(urn, token, author, text):
        raise linkedin.httpx.ReadTimeout("slow")
    monkeypatch.setattr(linkedin, "_api_post", lambda url, token, body: Ok())
    monkeypatch.setattr(linkedin, "_comment", slow)
    linkedin.post(status=lambda m: None)
    assert saved["status"] == "posted" and alerts == ["LinkedIn post up, first comment failed"]


def test_post_refused_alerts(monkeypatch):
    calls, saved = _posting(monkeypatch, {"status": "draft", "text": "x", "comment": "y"}, sent_minutes_ago=45)

    class Bad:
        status_code, text, headers = 422, "bad", {}
    monkeypatch.setattr(linkedin, "_api_post", lambda url, token, body: Bad())
    linkedin.post(status=lambda m: None)
    assert saved["status"] == "failed" and alerts == ["LinkedIn post failed today"]


def test_draft_still_unposted_at_the_last_run_alerts(monkeypatch):
    monkeypatch.setattr(linkedin, "_not_posted", lambda day, why: alerts.append("not posted: " + why))
    calls, _ = _posting(monkeypatch, {"status": "draft", "text": "x", "comment": "y"}, sent_minutes_ago=None)
    linkedin.post(status=lambda m: None)
    assert not calls and not alerts                               # 08:30-10:30: wait quietly
    calls, _ = _posting(monkeypatch, {"status": "draft", "text": "x", "comment": "y"}, sent_minutes_ago=None,
                        last_run=True)
    linkedin.post(status=lambda m: None)
    assert not calls and len(alerts) == 1 and "never went out" in alerts[0]


def test_no_draft_at_the_last_run_alerts_but_skipped_does_not(monkeypatch):
    monkeypatch.setattr(linkedin, "_not_posted", lambda day, why: alerts.append("not posted"))
    _posting(monkeypatch, None, sent_minutes_ago=None, last_run=True)
    linkedin.post(status=lambda m: None)
    assert alerts == ["not posted"]
    _posting(monkeypatch, {"status": "skipped", "text": "x", "comment": "y"}, sent_minutes_ago=None, last_run=True)
    linkedin.post(status=lambda m: None)
    assert alerts == []


def test_draft_crash_in_candidates_is_saved_and_alerted(monkeypatch):
    saved = {}
    monkeypatch.setattr(linkedin, "check_token", lambda status=print: None)
    monkeypatch.setattr(linkedin, "_row", lambda day: None)
    monkeypatch.setattr(linkedin, "_save", lambda day, **cols: saved.update(cols))
    monkeypatch.setattr(linkedin, "_alert", lambda subject, text: alerts.append(subject) or True)
    alerts.clear()

    def boom():
        raise RuntimeError("pool missing")
    monkeypatch.setattr(linkedin, "candidates", boom)
    assert linkedin.draft(status=lambda m: None) is None
    assert saved["status"] == "failed" and "pool missing" in saved["error"]
    assert alerts == ["LinkedIn post not drafted today"]


def test_alert_sends_the_batch_now(monkeypatch):
    sent = []
    monkeypatch.setattr(linkedin.mailer, "notify_owner", lambda *a, **k: True)
    monkeypatch.setattr(linkedin.mailer, "send_digest", lambda status=print: sent.append(1) or True)
    assert linkedin._alert("LinkedIn post failed today", "x") and sent == [1]


def test_a_live_post_emails_its_link_and_text(monkeypatch):
    calls, saved = _posting(monkeypatch, {"status": "draft", "text": "Hook\n\n- one", "comment": "links"},
                            sent_minutes_ago=45)
    texts = []
    monkeypatch.setattr(linkedin, "_alert", lambda subject, text: alerts.append(subject) or texts.append(text) or True)

    class Ok:
        status_code, text, headers = 201, "", {"x-restli-id": "urn:li:comment:9"}
    monkeypatch.setattr(linkedin, "_comment", lambda urn, token, author, text: Ok())
    linkedin.post(status=lambda m: None)
    assert saved["status"] == "posted" and alerts and alerts[0].startswith("LinkedIn post is up:")
    assert "https://www.linkedin.com/feed/update/urn:li:share:1/" in texts[0] and "Hook" in texts[0]
    assert "links" in texts[0] and "/recent-activity/all/" in texts[0]
