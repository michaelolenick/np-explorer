"""FURP in the News: articles that cite or use furp.org (content/in-the-news.yml), and the nightly check of the web
server's referrer log for visits from news sites (for the daily usage report).

Adding an article: append an entry to content/in-the-news.yml (outlet, headline, date YYYY-MM-DD, url) and deploy.
The /about/news page lists them newest first; the About page shows the three most recent once there are any.
"""

from __future__ import annotations

import datetime as dt
import gzip
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from app.config import ROOT

ARTICLES = ROOT / "content" / "in-the-news.yml"
NGINX_LOGS = [Path("/var/log/nginx/access.log"), Path("/var/log/nginx/access.log.1"),
              Path("/var/log/nginx/access.log.2.gz")]
OWN = ("furp.org", "strategystudio.org")

# Known news outlets, plus host words that mark most other news sites.
NEWS_DOMAINS = {
    "nytimes.com", "washingtonpost.com", "wsj.com", "usatoday.com", "latimes.com", "chicagotribune.com",
    "bostonglobe.com", "theguardian.com", "reuters.com", "apnews.com", "bloomberg.com", "axios.com", "politico.com",
    "propublica.org", "npr.org", "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com", "foxnews.com",
    "theatlantic.com", "newyorker.com", "vox.com", "slate.com", "salon.com", "thehill.com", "businessinsider.com",
    "insider.com", "forbes.com", "fortune.com", "cnbc.com", "marketwatch.com", "ft.com", "economist.com",
    "theintercept.com", "motherjones.com", "nationalreview.com", "washingtonexaminer.com", "huffpost.com",
    "chronicle.com", "insidehighered.com", "philanthropy.com", "nonprofitquarterly.org", "devex.com",
    "statnews.com", "kffhealthnews.org", "calmatters.org", "texastribune.org", "theverge.com", "wired.com",
    "arstechnica.com", "techcrunch.com", "semafor.com", "puck.news", "theinformation.com", "bbc.co.uk", "bbc.com",
    "nakedcapitalism.com", "substack.com", "medium.com", "news.google.com", "news.yahoo.com", "msn.com",
}
NEWS_WORDS = re.compile(r"(news|times|post|journal|tribune|herald|gazette|chronicle|press|courier|observer|"
                        r"dispatch|inquirer|sentinel|daily|weekly|reporter|examiner|ledger|globe|bee|magazine|radio)", re.I)
NOT_NEWS = re.compile(r"(google|bing|duckduckgo|yahoo\.com$|baidu|yandex|facebook|instagram|twitter|x\.com|t\.co|"
                      r"linkedin|reddit|chatgpt|openai|claude|perplexity|github|furp\.org|strategystudio)", re.I)

_LINE = re.compile(r'^\S+ \S+ \S+ \[(?P<ts>[^\]]+)\] "(?:GET|HEAD) (?P<path>\S+) [^"]*" (?P<status>\d{3}) \S+ '
                   r'"(?P<ref>[^"]*)" "(?P<ua>[^"]*)"')


def articles() -> list[dict]:
    """The articles in content/in-the-news.yml, newest first (entries missing a url or headline are skipped)."""
    try:
        items = yaml.safe_load(ARTICLES.read_text()) or []
    except (OSError, yaml.YAMLError):
        return []
    out = []
    for a in items if isinstance(items, list) else []:
        if not isinstance(a, dict) or not a.get("url") or not a.get("headline"):
            continue
        d = a.get("date")
        if isinstance(d, str):
            try:
                d = dt.date.fromisoformat(d)
            except ValueError:
                d = None
        out.append({"outlet": a.get("outlet") or urlsplit(a["url"]).hostname, "headline": a["headline"],
                    "date": d, "url": a["url"]})
    return sorted(out, key=lambda a: a["date"] or dt.date.min, reverse=True)


def is_news(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    if not host or host.endswith(OWN) or NOT_NEWS.search(host):
        return False
    base = ".".join(host.split(".")[-2:])
    return host in NEWS_DOMAINS or base in NEWS_DOMAINS or bool(NEWS_WORDS.search(host.split(".")[0] if
                                                                                   host.count(".") else host))


def news_referrals(start: dt.datetime, end: dt.datetime, top: int = 25) -> dict:
    """Visits in [start, end) whose referrer is a news site, from the nginx access log: each referring page with
    the furp.org page it linked to and how many visits. Bots are left out."""
    hits: Counter = Counter()
    hosts: Counter = Counter()
    read = []
    for p in NGINX_LOGS:
        if not p.exists():
            continue
        try:
            f = gzip.open(p, "rt", errors="replace") if p.suffix == ".gz" else open(p, errors="replace")
        except OSError:
            continue
        read.append(p.name)
        with f:
            for line in f:
                m = _LINE.match(line)
                if not m or m["status"][0] not in "23" or re.search(r"bot|crawl|spider|slurp", m["ua"], re.I):
                    continue
                ref = m["ref"]
                host = urlsplit(ref).hostname or ""
                if not is_news(host):
                    continue
                try:
                    ts = dt.datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z")
                except ValueError:
                    continue
                if start <= ts < end:
                    hits[(ref[:300], m["path"].split("?")[0][:200])] += 1
                    hosts[host.removeprefix("www.")] += 1
    return {"logs_read": read, "visits": sum(hits.values()), "sites": dict(hosts.most_common(15)),
            "pages": [{"from": r, "to": p, "visits": n} for (r, p), n in hits.most_common(top)]}
