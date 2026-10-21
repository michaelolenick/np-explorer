"""FURP in the News (app/news.py): the page, the About-page list, and spotting news-site referrers."""

import datetime as dt

from starlette.testclient import TestClient

from app import main, news

client = TestClient(main.app)

LOG = (
    '1.2.3.4 - - [21/Oct/2026:10:00:00 -0500] "GET /org/131624086 HTTP/1.1" 200 5 '
    '"https://www.nytimes.com/2026/10/21/met.html" "Mozilla/5.0"\n'
    '1.2.3.5 - - [21/Oct/2026:10:01:00 -0500] "GET /org/131624086 HTTP/1.1" 200 5 "https://www.google.com/" "Mozilla/5.0"\n'
    '1.2.3.6 - - [21/Oct/2026:10:02:00 -0500] "GET / HTTP/1.1" 200 5 "https://www.nytimes.com/x" "Googlebot"\n')


def test_empty_page_says_nothing_yet():
    html = client.get("/about/news").text
    assert "FURP in the News" in html and "Nothing yet" in html


def test_articles_newest_first_and_about_shows_three(monkeypatch, tmp_path):
    f = tmp_path / "news.yml"
    f.write_text(
        '- {outlet: A, headline: Old story, date: 2026-11-01, url: "https://a.example/1"}\n'
        '- {outlet: B, headline: New story, date: 2026-12-01, url: "https://b.example/2"}\n'
        '- {outlet: C, headline: Mid story, date: 2026-11-15, url: "https://c.example/3"}\n'
        '- {outlet: D, headline: Oldest, date: 2026-10-25, url: "https://d.example/4"}\n')
    monkeypatch.setattr(news, "ARTICLES", f)
    assert [a["headline"] for a in news.articles()] == ["New story", "Mid story", "Old story", "Oldest"]
    html = client.get("/about").text
    assert "New story" in html and "Old story" in html and "Oldest" not in html


def test_news_hosts():
    assert news.is_news("www.nytimes.com") and news.is_news("dallasnews.com")
    assert not news.is_news("www.google.com") and not news.is_news("furp.org") and not news.is_news("t.co")


def test_referrals_from_the_nginx_log(monkeypatch, tmp_path):
    log = tmp_path / "access.log"
    log.write_text(LOG)
    monkeypatch.setattr(news, "NGINX_LOGS", [log])
    tz = dt.timezone(dt.timedelta(hours=-5))
    r = news.news_referrals(dt.datetime(2026, 10, 21, tzinfo=tz), dt.datetime(2026, 10, 22, tzinfo=tz))
    assert r["visits"] == 1 and r["pages"][0]["to"] == "/org/131624086" and "nytimes.com" in r["sites"]
