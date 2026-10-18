"""Usage stats and the daily report: bot classification, internal traffic, new vs returning,
sessions, and the check that every number in the narrative comes from the metrics."""

import socket
from datetime import date, datetime, timedelta, timezone

import pytest

from app import analytics, report

CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
BINGBOT = "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"


@pytest.mark.parametrize("ua, cls", [
    (CHROME, "human"),
    (GOOGLEBOT, "googlebot?"),
    (BINGBOT, "bingbot?"),
    ("Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)", "crawler"),
    ("Mozilla/5.0 (compatible; DuckDuckBot-Https/1.1)", "crawler"),
    ("curl/8.5.0", "scraper"),
    ("python-requests/2.32.3", "scraper"),
    ("Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/120.0 Safari/537.36", "scraper"),
    ("", "scraper"),
    (None, "scraper"),
    ("SomethingWeird/1.0", "scraper"),
])
def test_classify_ua(ua, cls):
    assert analytics.classify_ua(ua) == cls


def test_claimed_bots_need_verification():
    assert analytics.final_class("googlebot?", "66.249.66.1", verify=lambda ip, bot: True) == "googlebot"
    assert analytics.final_class("googlebot?", "203.0.113.9", verify=lambda ip, bot: False) == "scraper"
    assert analytics.final_class("bingbot?", None, verify=lambda ip, bot: True) == "scraper"
    assert analytics.final_class("human", "203.0.113.9", verify=lambda ip, bot: False) == "human"


def test_verify_bot_reverse_then_forward(monkeypatch):
    def fake(host_for_ip, ips_for_host):
        monkeypatch.setattr(socket, "gethostbyaddr", lambda ip: (host_for_ip, [], [ip]))
        monkeypatch.setattr(socket, "gethostbyname_ex", lambda h: (h, [], ips_for_host))
        monkeypatch.setattr(socket, "getaddrinfo", lambda h, p: [(0, 0, 0, "", (a, 0)) for a in ips_for_host])
        analytics.verify_bot.cache_clear()

    fake("crawl-66-249-66-1.googlebot.com", ["66.249.66.1"])
    assert analytics.verify_bot("66.249.66.1", "googlebot")
    fake("crawl-66-249-66-1.googlebot.com.evil.example", ["66.249.66.1"])
    assert not analytics.verify_bot("66.249.66.1", "googlebot")        # wrong domain
    fake("crawl-66-249-66-1.googlebot.com", ["66.249.66.2"])
    assert not analytics.verify_bot("66.249.66.1", "googlebot")        # forward lookup doesn't match
    fake("msnbot-40-77-167-1.search.msn.com", ["40.77.167.1"])
    assert analytics.verify_bot("40.77.167.1", "bingbot")
    assert not analytics.verify_bot("40.77.167.1", "googlebot")
    analytics.verify_bot.cache_clear()


def test_internal_traffic_excluded():
    nets = analytics._networks("45.20.197.127, 20.168.8.141 10.1.0.0/16 not-an-ip")
    assert analytics.is_internal("127.0.0.1", nets)
    assert analytics.is_internal("::1", nets)
    assert analytics.is_internal("45.20.197.127", nets)
    assert analytics.is_internal("10.1.0.5", nets)
    assert not analytics.is_internal("203.0.113.9", nets)
    assert analytics.is_internal(None, nets)                           # no client address: don't count it
    assert analytics.is_internal("garbage", nets)


def test_new_vs_returning():
    start = datetime(2026, 10, 17, 5, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    first_seen = {"a": start + timedelta(hours=2), "b": start - timedelta(days=3), "c": end + timedelta(hours=1)}
    assert analytics.new_vs_returning(["a", "a", "b", "c"], first_seen, start, end) == (1, 2)
    assert analytics.new_vs_returning([], first_seen, start, end) == (0, 0)


def test_sessions_split_after_30_idle_minutes():
    t = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
    rows = [("a", t + timedelta(minutes=29), "/about", None), ("a", t, "/", "news.example"),
            ("a", t + timedelta(minutes=70), "/boards", None), ("b", t, "/person/1", "google.com")]
    s = sorted(analytics.sessions(rows), key=lambda x: (x["visitor_id"], x["start"]))
    assert [(x["visitor_id"], x["landing"], x["pages"], x["referrer"]) for x in s] == [
        ("a", "/", 2, "news.example"), ("a", "/boards", 1, None), ("b", "/person/1", 1, "google.com")]


def test_referrer_domain_skips_own_site():
    assert analytics.referrer_domain("https://www.google.com/search?q=x") == "google.com"
    assert analytics.referrer_domain(analytics.SITE_URL + "/about") is None
    assert analytics.referrer_domain(None) is None


FACTS = {"metrics": {"traffic": {"human_visitors": 1234, "pages_per_session": 2.37},
                     "searches": {"nl_fallback_rate_pct": 41.7, "top_searches": [["jamie dimon", 12]]},
                     "window": {"last_day": "2026-10-17"}},
         "constants": {"trailing_days": 7, "low_confidence_under": 20}}


@pytest.mark.parametrize("text", [
    "1. Evidence: 1,234 human visitors over 7 days.",
    "Pages per session were 2.4 on 2026-10-17.",
    "The NL fallback rate was 42% (low confidence under 20).",
    "jamie dimon was searched 12 times.",
    "THE DAY IN FIVE LINES\nNo searches stood out.",
])
def test_validate_accepts_numbers_from_the_json(text):
    assert report.validate(text, FACTS) == []


@pytest.mark.parametrize("text, bad", [
    ("We had 1,500 visitors.", ["1,500"]),
    ("Fallbacks fell by 13%.", ["13%"]),
    ("Pages per session were 2.9.", ["2.9"]),
    ("2. Change: try 5 new examples.", ["5"]),
])
def test_validate_rejects_invented_numbers(text, bad):
    assert report.validate(text, FACTS) == bad


def test_narrative_falls_back_after_two_failures():
    calls = []

    def ask(msgs):
        calls.append(msgs)
        return "\n".join(report.SECTIONS) + "\nWe had 99999 visitors."
    text, status = report.narrative(FACTS, ask=ask)
    assert text is None and "twice" in status and len(calls) == 2


def test_narrative_accepted_when_numbers_check_out():
    good = "\n".join(f"{h}\n1,234 visitors." for h in report.SECTIONS)
    text, status = report.narrative(FACTS, ask=lambda msgs: good)
    assert status == "ok" and text == good


def test_window_is_a_chicago_calendar_day():
    start, end = report.window(date(2026, 10, 17))                     # CDT, UTC-5
    assert (start.hour, end - start) == (5, timedelta(days=1))
    start, end = report.window(date(2026, 11, 1))                      # DST ends: a 25-hour day
    assert end - start == timedelta(hours=25)


def test_low_counts_are_starred():
    assert report.star(19) == "19*" and report.star(20) == "20" and report.star(1234) == "1,234"
    assert report.star(2.5) == "2.5" and report.star(None) == "-"
