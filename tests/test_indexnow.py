"""loader/indexnow.py: batching, the nightly cap, and staying quiet without a key."""

import urllib.parse

from app.config import SITE_URL
from loader import indexnow


class Status:
    def __init__(self):
        self.lines = []

    def emit(self, m):
        self.lines.append(m)


def test_batches_and_cap():
    posts = []
    urls = [f"https://strategystudio.org/filing/{i}" for i in range(25000)]
    sent = indexnow.submit(Status(), urls, key="k" * 32, limit=22000, post=lambda p: posts.append(p) or 200)
    assert sent == 22000
    assert [len(p["urlList"]) for p in posts] == [10000, 10000, 2000]
    assert posts[0]["host"] == urllib.parse.urlsplit(SITE_URL).netloc
    assert posts[0]["keyLocation"].endswith("/" + "k" * 32 + ".txt")


def test_stops_on_error():
    posts = []
    sent = indexnow.submit(Status(), ["u"] * 15000, key="k", limit=50000, post=lambda p: posts.append(p) or 429)
    assert sent == 0 and len(posts) == 1


def test_no_key_or_no_urls_sends_nothing():
    calls = []
    assert indexnow.submit(Status(), ["u"], key="", post=calls.append) == 0
    assert indexnow.submit(Status(), [], key="k", post=calls.append) == 0
    assert calls == []
