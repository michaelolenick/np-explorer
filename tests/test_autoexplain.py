"""On-demand explanations (owner, 2026-11-08): who may trigger one, the cost log, the daily cap and its signed resume
link, the cached text in the HTML, the report numbers."""

import datetime as dt

import pytest

from app import autoexplain as ax


class Req:
    def __init__(self, ua="Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                 cookie="a" * 32, path="/org/123", header=True, sec_fetch=True, bot_reason=None):
        self.headers = {"user-agent": ua, "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin"} if sec_fetch else {"user-agent": ua}
        if header:
            self.headers[ax.HEADER] = path
        self.cookies = {"ssv": cookie} if cookie else {}
        self.query_params = {"u": path}
        self.state = type("S", (), {"bot_reason": bot_reason})()
        self.client = type("C", (), {"host": "203.0.113.9"})()


def test_entity_prefixes_and_buckets():
    assert ax.is_entity("/org/123") and ax.is_entity("/corporate/form-d/x") and not ax.is_entity("/search") and not ax.is_entity("/boards/x")
    assert ax.entity_kind("/person/9") == "person" and ax.entity_kind("/corporate/form-d/x") == "form-d"
    assert ax.ip_bucket("203.0.113.9") == "203.0.113.0/24" and ax.ip_bucket("2001:db8:1:2::5") == "2001:db8:1::/48" and ax.ip_bucket(None) == "unknown"
    assert ax.cost_of("claude-sonnet-5-5", {"input_tokens": 1_000_000, "output_tokens": 100_000}) == 3.0


def test_only_a_person_s_browser_passes(monkeypatch):
    from app import analytics
    monkeypatch.setattr(analytics, "bot_reason", lambda request, has_cookie: None)
    assert ax.human_request(Req()) is None
    assert ax.human_request(Req(ua="curl/8.0")) == "user agent"
    assert ax.human_request(Req(bot_reason="spoofed referrer")) == "headless"
    assert ax.human_request(Req(cookie=None)) == "no visitor cookie"
    assert ax.human_request(Req(header=False)) == "no browser headers"
    assert ax.human_request(Req(sec_fetch=False)) == "no browser headers"
    monkeypatch.setattr(analytics, "bot_reason", lambda request, has_cookie: "never returns the cookie")
    assert ax.human_request(Req()) == "headless"


def test_signed_resume_link_round_trip(monkeypatch):
    store = {}

    class Conn:
        def execute(self, sql, params=None):
            if sql.lstrip().startswith("SELECT value"):
                return type("R", (), {"fetchone": lambda s: {"value": store["stop"]} if "stop" in store else None})()
            if sql.lstrip().startswith("INSERT INTO explain_state"):
                import json
                store["stop"] = json.loads(params[0])
                return None
            raise AssertionError(sql)
    conn = Conn()
    link = ax.stop(conn, "test")
    assert link.startswith(ax.SITE_URL + "/explain/resume?t=") and ax.stopped(conn)
    token = link.split("t=")[1]
    assert not ax.resume(conn, "bogus.bogus") and ax.stopped(conn)
    assert not ax.resume(conn, token.split(".")[0] + "." + "0" * 32) and ax.stopped(conn)
    assert ax.resume(conn, token) and not ax.stopped(conn)
    assert not ax.resume(conn, token)                         # once only
    assert ax.resume(conn, None, by="command line") and not ax.stopped(conn)


def test_day_window_is_indianapolis():
    s, e = ax.day_window(dt.date(2026, 11, 8))
    assert s.tzinfo == ax.TZ and s.hour == 0 and (e - s).days == 1 and s.utcoffset() == dt.timedelta(hours=-5)


def test_alert_text_says_why_and_how_to_continue():
    rep = {"day": "2026-11-08", "generations": 140, "cost": 5.12, "cost_by_hour": {"09:00": 2.0, "10:00": 3.12},
           "top_entities": [("/org/1", 0.5)], "human_served": 300, "bots_blocked": 4000, "blocked_reasons": {"user agent": 3900},
           "abusive": ["203.0.113.0/24: 60 generations"]}
    text, html = ax.alert_text(rep, "https://furp.org/explain/resume?t=abc.def")
    for s in ("$5.12", "140", "09:00 $2.00", "Top 20 entities", "/org/1", "4000", "203.0.113.0/24", "resume?t=abc.def", "Do you want to continue?"):
        assert s in text
    assert '<a href="https://furp.org/explain/resume?t=abc.def">' in html


def test_page_has_the_cached_text_and_the_hook(monkeypatch):
    from starlette.testclient import TestClient
    from app import db, main
    try:
        db.pool.open(wait=False)
    except Exception:  # noqa: BLE001
        pass
    monkeypatch.setattr(ax, "cached_for", lambda path: "<p>A cached explanation.</p>" if path.startswith("/org/") else "")
    c = TestClient(main.app)
    r = c.get("/org/530196605")                                    # redirects to its readable address
    if r.status_code != 200:
        pytest.skip("no organization page on this database")
    path = r.url.path
    assert path.startswith("/org/") and f'<div class="explain" data-auto="{path}">' in r.text and "A cached explanation." in r.text
    assert "explain-btn" not in r.text[r.text.index('class="explain"'):r.text.index("</main>")]
    # the endpoint refuses anything that is not a person's browser, and non-entity paths
    assert c.post("/explain/auto?u=/search").status_code == 400
    j = c.post("/explain/auto?u=/org/530196605", headers={"user-agent": "curl/8"}).json()
    assert j == {"status": "blocked", "html": ""}
    assert c.get("/explain/resume?t=nope").status_code in (200, 400)


def test_report_definitions_and_script():
    from app import report
    assert "explanations" in report.DEFINITIONS
    js = open("static/site.js").read()
    assert '"/explain/auto?u="' in js and '"X-FURP-Explain": path' in js and "pointermove" in js and "1500" in js
    assert "nl_explain_url" in open("migrations/versions/0073_explain_log.py").read()
