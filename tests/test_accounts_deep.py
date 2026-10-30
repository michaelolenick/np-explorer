"""Accounts, the allow-list and Deep Query plans and estimates (owner, 2026-10-29). No model calls, no logins."""

from starlette.testclient import TestClient

from app import accounts, deep


def test_safe_next_stays_on_site():
    assert accounts._safe_next("/deep/q/3") == "/deep/q/3"
    for bad in ("//evil.example", "https://evil.example", "/\\evil", "", None):
        assert accounts._safe_next(bad) == "/deep"


def test_emails():
    assert accounts.normalize_email(" MFolenick@Gmail.com ") == "mfolenick@gmail.com"
    assert accounts.normalize_email("not an email") is None


def test_csrf_is_tied_to_the_session():
    a, b = {"session_hash": "a" * 64}, {"session_hash": "b" * 64}
    assert accounts.csrf_ok(a, {"csrf": accounts.csrf(a)})
    assert not accounts.csrf_ok(a, {"csrf": accounts.csrf(b)})
    assert not accounts.csrf_ok(None, {"csrf": ""})


def test_allow_list_file_is_read_again_when_it_changes(tmp_path, monkeypatch):
    f = tmp_path / "allow.txt"
    f.write_text("# comment\nOwner@Example.com\n")
    monkeypatch.setattr(deep, "DEEP_ALLOWLIST_FILE", str(f))
    deep._allow_cache.clear()
    user = {"email": "owner@example.com", "status": "active"}
    assert deep.deep_allowed(user)
    assert not deep.deep_allowed({**user, "email": "someone@example.com"})
    assert not deep.deep_allowed({**user, "status": "new"})        # signup not finished
    import os
    import time
    f.write_text("someone@example.com\n")
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert deep.deep_allowed({**user, "email": "someone@example.com"}) and not deep.deep_allowed(user)


def test_allow_list_default_without_the_file(monkeypatch):
    monkeypatch.setattr(deep, "DEEP_ALLOWLIST_FILE", "/nonexistent/allow.txt")
    assert {"mfolenick@gmail.com", "mfolenick@vstrat.ai"} <= deep.allow_list()


def test_plan_validation():
    p = deep.validate({"recipe": "topic", "title": "x", "terms": "re:astro.*", "state": "texas", "check": "Is it?"})
    assert p["terms"] == "astro.*" and p["state"] is None and p["check_limit"] == 300 and not p["unsupported"]
    assert deep.validate({"recipe": "person", "title": "x"})["unsupported"]
    assert deep.validate({"recipe": "drop tables", "title": "x"})["unsupported"]
    assert deep.validate({"recipe": "funders", "title": "x"})["unsupported"]


def test_plain_estimate():
    e = {"tokens": 40400, "dollars": 0.1512, "seconds": 30}
    assert deep.plain(e) == "about 40K tokens, roughly $0.15, 30 seconds"
    assert deep.plain({"tokens": 900, "dollars": 0.004, "seconds": 300}) == "about 900 tokens, roughly $0.00, 5 minutes"


def test_costs():
    assert round(deep.cost("claude-haiku-5-5", 1_000_000, 100_000), 2) == 0.15
    assert round(deep.cost("claude-sonnet-5-5", 1_000_000, 100_000), 2) == 3.0


def _client():
    from app import db
    from app.main import app
    db.pool.open(wait=False)          # as tests/test_attribution.py: no `with`, its lifespan closes the shared pool
    return TestClient(app)


def test_logged_out_pages():
    c = _client()
    r = c.get("/deep")
    assert r.status_code == 200 and "Deep queries need a login." in r.text and r.headers["cache-control"] == "no-store"
    assert c.get("/signup", follow_redirects=False).status_code == 303
    assert c.post("/deep/estimate", content="question=hello+world+test", follow_redirects=False).headers["location"] == "/deep"
    r = c.get("/auth/google/callback?code=x&state=y", follow_redirects=False)
    assert r.headers["location"] == "/login?error=google"          # no state cookie: refused
    assert "expired" in c.get("/auth/magic?t=not-a-real-token").text


def test_beta_label_and_menu_link():
    html = _client().get("/about").text
    assert "beta-tag" in html and "FURP is in beta. Data may have gaps or errors." in html
    assert 'href="/deep"' in html and ">Deep queries</a>" in html and "login required" not in html.lower()
    nav = html[html.index('<nav class="site-nav"'):html.index("</nav>")]
    assert nav.count('href="/deep"') == 1                          # under Browse Data only (owner, 2026-10-30)
    page = _client().get("/deep").text                             # logged out: what it is, then the login
    assert page.index("What is a deep query?") < page.index("Deep queries need a login.")
    assert 'href="/deep"' in _client().get("/more").text
