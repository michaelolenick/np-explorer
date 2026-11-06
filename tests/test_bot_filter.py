"""Bots with a browser user agent (owner, 2026-11-06): spoofed referrers, scripts without Sec-Fetch headers, IPs that
never return the cookie; the report's definitions; the nightly closing line; the collector's lock retry."""

import time

from app import analytics, report

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
SAFARI_OLD = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 Version/14.0 Mobile/15E148 Safari/604.1"


def test_spoofed_referrer_and_missing_sec_fetch():
    assert analytics.spoofed_referrer({"sec-fetch-site": "none"}, "google.com")
    assert not analytics.spoofed_referrer({"sec-fetch-site": "cross-site"}, "google.com")
    assert not analytics.spoofed_referrer({}, "google.com")                 # no header: nothing to contradict
    assert not analytics.spoofed_referrer({"sec-fetch-site": "none"}, None)
    assert analytics.script_claiming_browser(CHROME, {})
    assert not analytics.script_claiming_browser(CHROME, {"sec-fetch-mode": "navigate"})
    assert not analytics.script_claiming_browser(SAFARI_OLD, {})            # older Safari sends none: still a person
    assert analytics.script_claiming_browser("Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0", {})
    assert not analytics.script_claiming_browser("Mozilla/5.0 (X11; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0", {})


def test_cookieless_ip_is_banned_after_the_limit_and_a_cookied_ip_is_not():
    analytics._ips.clear()
    t = time.time()
    hits = [analytics.cookieless_scraper("203.0.113.5", False, t + i) for i in range(analytics.COOKIELESS_LIMIT + 2)]
    assert hits[: analytics.COOKIELESS_LIMIT - 1] == [False] * (analytics.COOKIELESS_LIMIT - 1) and hits[-1]
    assert analytics.cookieless_scraper("203.0.113.5", True, t + 100)      # banned stays banned for the window
    assert not analytics.cookieless_scraper("203.0.113.5", False, t + analytics.COOKIELESS_BAN + 100)   # the ban lifts
    for i in range(analytics.COOKIELESS_LIMIT * 3):                        # an office: cookies come back
        assert not analytics.cookieless_scraper("198.51.100.9", i % 3 != 0, t + i)
    assert not analytics.cookieless_scraper(None, False)
    analytics._ips.clear()


def test_headless_requests_keep_no_visitor(monkeypatch):
    rows = [("event", {"ts": None, "ip": "203.0.113.5", "claimed": "headless", "visitor_id": "a" * 32, "name": "page",
                       "route": "org", "path": "/org/1", "status": 200, "ms": 1.0, "referrer": "google.com", "meta": None})]
    written = {}

    class Cur:
        def executemany(self, sql, rows):
            written[sql.split("INTO ")[1].split(" ")[0]] = rows

    class Conn:
        def cursor(self):
            return Cur()

        def transaction(self):
            import contextlib
            return contextlib.nullcontext()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Pool:
        def connection(self):
            return Conn()

    monkeypatch.setattr("app.db.pool", Pool())
    monkeypatch.setattr(analytics, "country", lambda ip: "SG")
    analytics.write(rows)
    assert written["events"][0][1] is None and written["events"][0][8] == "headless" and "visitors" not in written


def test_report_definitions_funnel_and_timeouts():
    assert "sponsor_clicks" in report.DEFINITIONS and "definitions" in report.SYSTEM
    assert report.FUNNEL[-1][0] == "opened the Support page"
    journal = ("2026-11-06T07:54:15-06:00 vm uvicorn[1]: psycopg.errors.QueryCanceled: canceling statement due to statement timeout\n"
               "2026-11-06T07:54:15-06:00 vm uvicorn[1]:     | psycopg.errors.QueryCanceled: canceling statement due to statement timeout\n"
               "2026-11-06T13:02:00-06:00 vm uvicorn[1]: psycopg.errors.QueryCanceled: canceling statement due to statement timeout\n"
               "2026-11-06T13:05:00-06:00 vm uvicorn[1]: INFO ok\n")
    assert report.timeouts_by_hour(journal) == {"count": 2, "by_hour": {"07:00": 1, "13:00": 1}}


def test_nightly_ends_with_its_own_mark():
    sh = open("scripts/nightly.sh").read()
    assert sh.rstrip().endswith('exit "$rc"') and "=== nightly done" in sh and "reclass_bots.py --days 1" in sh
    src = open("app/report.py").read()
    assert 'last_line.startswith("=== nightly done")' in src
    cron = open("deploy/cron/np-explorer").read()
    assert '= 07 ]' in cron and "nightly.sh" in cron


def test_reclass_flags_heavy_ips_and_their_network():
    import importlib.util
    spec = importlib.util.spec_from_file_location("reclass_bots", "scripts/reclass_bots.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    from collections import Counter
    per_ip = Counter({f"47.79.201.{i}": 30 for i in range(10)} | {"47.79.201.250": 2, "198.51.100.7": 3, "203.0.113.1": 40})
    ips, nets, n_own = rb.flagged_ips(per_ip)
    assert "203.0.113.1" in ips and "198.51.100.7" not in ips and n_own == 0
    assert nets == {"47.79.201"} and "47.79.201.250" in ips         # the whole /24 once 8 of its IPs are flagged
    # The own-referrer rule: IPs whose one to three requests all claim a furp.org page; only on a botnet day.
    quiet = Counter({f"10.0.{i // 256}.{i % 256}": 1 for i in range(500)})
    assert rb.flagged_ips(quiet, Counter(quiet))[2] == 0
    botnet = Counter({f"10.{i // 65536}.{(i // 256) % 256}.{i % 256}": 1 for i in range(rb.OWN_REF_BOTNET + 1)})
    ips, _, n_own = rb.flagged_ips(botnet, Counter(botnet))
    assert n_own == rb.OWN_REF_BOTNET + 1 and len(ips) == rb.OWN_REF_BOTNET + 1
    heavy = Counter(botnet); heavy["10.9.9.9"] = 10
    assert "10.9.9.9" not in rb.flagged_ips(heavy, Counter(heavy))[0]   # ten requests: a session, not this rule
    assert rb.OWN_REF.match("https://furp.org/org/1") and not rb.OWN_REF.match("https://furp.org") and "https://furp.org" in rb.BARE_REFS
    line = ('47.79.218.108 - - [05/Nov/2026:10:00:01 -0600] "GET /person/john-smith-12?x=1 HTTP/1.1" 200 5000 '
            '"https://www.google.com/" "' + CHROME + '"')
    r = rb.parse(line)
    assert r["ip"] == "47.79.218.108" and r["path"] == "/person/john-smith-12" and r["status"] == 200
    assert rb.parse('1.2.3.4 - - [05/Nov/2026:10:00:01 -0600] "GET /static/site.js HTTP/1.1" 200 1 "-" "x"') is None


def test_collector_retries_lock_errors_with_backoff():
    import psycopg
    from loader import categorize
    calls, slept = [], []

    class Conn:
        def rollback(self):
            calls.append("rollback")

    attempts = iter([psycopg.errors.DeadlockDetected("d"), psycopg.errors.LockNotAvailable("l"), "ok"])

    def fn():
        x = next(attempts)
        if isinstance(x, Exception):
            raise x
        return x
    assert categorize.with_lock_retry(Conn(), "t", fn, waits=(1, 2, 4), sleep=slept.append) == "ok"
    assert slept == [1, 2] and calls == ["rollback", "rollback"]
    always = iter([psycopg.errors.DeadlockDetected("d")] * 5)

    def bad():
        raise next(always)
    try:
        categorize.with_lock_retry(Conn(), "t", bad, waits=(1, 1), sleep=slept.append)
        raise AssertionError("should have raised")
    except psycopg.errors.DeadlockDetected:
        pass
    assert categorize.CATEGORY_LOCK == 778101


def test_offpeak_window(monkeypatch):
    import datetime as dt
    from loader import offpeak
    noon = dt.datetime(2026, 11, 6, 13, 0, tzinfo=offpeak.CHICAGO)
    night = dt.datetime(2026, 11, 6, 23, 30, tzinfo=offpeak.CHICAGO)
    assert not offpeak.is_quiet(noon) and offpeak.is_quiet(night) and offpeak.is_quiet(night.replace(hour=3))
    assert offpeak.seconds_until_quiet(noon) == 9 * 3600 and offpeak.seconds_until_quiet(night) == 0
    monkeypatch.setenv("NP_NOW", "1")
    assert offpeak.wait("x", status=lambda m: None, sleep=lambda s: (_ for _ in ()).throw(AssertionError("slept"))) is False
