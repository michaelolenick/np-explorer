"""Tell IndexNow (Bing, Yandex, Seznam, Naver and others) about new pages.

The key is public by design: search engines fetch {SITE_URL}/{key}.txt to check that we
own the host (static/<key>.txt, served at the root by nginx). Called by load.py nightly
with the URLs the sitemap rebuild found new. Never raises: a down endpoint must not fail
the nightly load.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from app.config import INDEXNOW_KEY, INDEXNOW_MAX, SITE_URL

ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000   # the protocol's limit per request
UA = "np-explorer/1.0 (+https://strategystudio.org; nonprofit people search)"


def _post(payload: dict) -> int:
    req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def submit(status, urls: list[str], key: str = INDEXNOW_KEY, limit: int = INDEXNOW_MAX, post=_post) -> int:
    """Send up to limit URLs in batches; return how many were accepted (HTTP 200 or 202)."""
    if not key:
        status.emit("indexnow: no INDEXNOW_KEY; skipped")
        return 0
    if not urls:
        status.emit("indexnow: no new pages")
        return 0
    host = urllib.parse.urlsplit(SITE_URL).netloc
    todo = urls[:limit]
    sent = 0
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        try:
            code = post({"host": host, "key": key, "keyLocation": f"{SITE_URL}/{key}.txt", "urlList": batch})
        except Exception as e:  # noqa: BLE001
            status.emit(f"indexnow: request failed ({e}); stopping")
            break
        if code not in (200, 202):
            status.emit(f"indexnow: HTTP {code} for a batch of {len(batch):,}; stopping")
            break
        sent += len(batch)
    skipped = len(urls) - len(todo)
    status.emit(f"indexnow: sent {sent:,} of {len(urls):,} new URLs" + (f" ({skipped:,} over the nightly cap)" if skipped else ""))
    return sent
