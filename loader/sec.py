"""SEC EDGAR downloads for the student loan ABS loader: polite, throttled, cached.

Every request sends the User-Agent the SEC asks for and waits so that this process
makes at most RATE requests per second (the SEC allows 10; we stay well under).
Raw responses are cached gzipped under SLA_DATA (default ~/sla-data, not in git),
keyed by URL path, so re-running a parse never re-downloads.
"""

from __future__ import annotations

import gzip
import os
import threading
import time
from pathlib import Path

import httpx

USER_AGENT = "strategystudio.org research michael@strategystudio.org"
RATE = float(os.environ.get("SEC_RATE", "4"))   # requests per second, at most (the weekly refresh uses 2)
CACHE = Path(os.environ.get("SLA_DATA", Path.home() / "sla-data"))
WWW = "https://www.sec.gov"
DATA = "https://data.sec.gov"

_lock = threading.Lock()
_last = [0.0]
_client: httpx.Client | None = None


class NotFound(Exception):
    pass


_client_lock = threading.Lock()


def _http() -> httpx.Client:
    """One shared client (thread-safe), made on first use."""
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
                                   timeout=60, follow_redirects=True)
    return _client


def _wait() -> None:
    with _lock:
        gap = 1.0 / RATE - (time.monotonic() - _last[0])
        if gap > 0:
            time.sleep(gap)
        _last[0] = time.monotonic()


def cache_path(url: str) -> Path:
    path = url.split("://", 1)[1].split("/", 1)[1]
    host = "data" if url.startswith(DATA) else "www"
    return CACHE / "raw" / host / (path.rstrip("/") + ".gz")


def fetch(url: str, refresh: bool = False, retries: int = 4) -> bytes:
    """The body at url, from the cache when we have it. Raises NotFound on 404."""
    p = cache_path(url)
    missing = p.with_suffix(".404")
    if not refresh:
        if p.exists():
            return gzip.decompress(p.read_bytes())
        if missing.exists():
            raise NotFound(url)
    for attempt in range(retries):
        _wait()
        try:
            r = _http().get(url)
        except httpx.HTTPError:
            time.sleep(2 ** attempt * 2)
            continue
        if r.status_code == 404:
            missing.parent.mkdir(parents=True, exist_ok=True)
            missing.touch()
            raise NotFound(url)
        if r.status_code in (429, 403, 500, 502, 503, 504):
            time.sleep(2 ** attempt * 5)     # the SEC's throttle answers 403/429: back off hard
            continue
        r.raise_for_status()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_bytes(gzip.compress(r.content, 6))
        tmp.rename(p)
        return r.content
    raise RuntimeError(f"gave up on {url}")


def fetch_path(url: str) -> Path:
    """Make sure url is in the cache (without keeping the body around) and return the cache file,
    which holds the body gzipped. Raises NotFound on 404."""
    p = cache_path(url)
    if not p.exists():
        fetch(url)
    return p


def cached(url: str) -> bool:
    return cache_path(url).exists()
