"""Shared helpers for the unipay jobs. Reads DATABASE_URL from the environment (never printed)."""
import datetime as dt
import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

import psycopg

REPO = Path(os.path.expanduser("~/np-unipay"))
DATA = Path(os.path.expanduser("~/unipay-data"))
PROGRESS = REPO / "data" / "unipay-progress.json"
UA = "strategystudio.org university pay research (contact michael@strategystudio.org)"


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set (source ~/np-explorer/.env)")
    url = url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg.connect(url, application_name="unipay")
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = '30min'")
    return conn


def in_blackout(now=None):
    """True between 23:30 and 01:30 local (Chicago) time: no DB writes then."""
    now = now or dt.datetime.now()
    m = now.hour * 60 + now.minute
    return m >= 23 * 60 + 30 or m < 90


def wait_for_window():
    while in_blackout():
        print("in 23:30-01:30 blackout; sleeping 5 min", flush=True)
        time.sleep(300)


def load_progress():
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text())
    return {"catalog": False, "sources": {}}


def save_progress(p):
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(p, indent=1, sort_keys=True) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


import sys as _sys

_sys.path.insert(0, str(REPO))
from app.names import normalize_name as _site_normalize  # noqa: E402  same rules as public.people.name_norm


def name_norm(name):
    """Site normalizer: lowercase, no accents/punctuation, 'Last, First M' -> 'first m last'."""
    if not name:
        return None
    return _site_normalize(str(name)) or None


def join_name(first=None, middle=None, last=None, suffix=None):
    """Build 'Last, First M Suffix' as-published style from parts."""
    first = (first or "").strip()
    middle = (middle or "").strip()
    last = (last or "").strip()
    given = " ".join(x for x in (first, middle) if x)
    s = f"{last}, {given}" if last and given else (last or given)
    if suffix and str(suffix).strip():
        s += ", " + str(suffix).strip()
    return s or None


def to_num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("$", "").replace(",", "")
    if s in ("", "-", "NA", "N/A", "null", "None"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


# ---------------------------------------------------------------- polite HTTP
import urllib.parse
import urllib.robotparser

import httpx

_last_hit = {}
_robots = {}
DELAY = 2.0


def _robots_ok(url):
    u = urllib.parse.urlsplit(url)
    base = f"{u.scheme}://{u.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = httpx.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
            rp.parse(r.text.splitlines() if r.status_code == 200 and "html" not in r.headers.get("content-type", "") else [])
        except Exception:
            rp.parse([])
        _robots[base] = rp
        time.sleep(1)
    return _robots[base].can_fetch(UA, url)


def polite_get(url, params=None, dest=None, client=None, delay=DELAY, timeout=300, tries=6, check_robots=True):
    """GET with UA, one request at a time per host, delay, backoff on 429/5xx. Streams to dest if given."""
    if check_robots and not _robots_ok(url):
        raise PermissionError(f"robots.txt disallows {url}")
    host = urllib.parse.urlsplit(url).netloc
    wait = delay - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=timeout)
    try:
        for attempt in range(tries):
            _last_hit[host] = time.time()
            try:
                if dest:
                    with client.stream("GET", url, params=params) as r:
                        if r.status_code in (429, 500, 502, 503, 504):
                            raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                        r.raise_for_status()
                        tmp = Path(str(dest) + ".part")
                        with open(tmp, "wb") as f:
                            for chunk in r.iter_bytes(1 << 20):
                                f.write(chunk)
                        tmp.rename(dest)
                        return r
                r = client.get(url, params=params)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                r.raise_for_status()
                return r
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                if code and code not in (429, 500, 502, 503, 504):
                    raise
                back = min(600, 15 * 2 ** attempt)
                print(f"  retry {attempt+1} after {back}s ({code or type(e).__name__}) {url}", flush=True)
                time.sleep(back)
        raise RuntimeError(f"giving up on {url}")
    finally:
        if own:
            client.close()


def socrata_pages(base, params, page=50000, delay=1.5):
    """Yield pages of a SODA query using $limit/$offset (requires a stable $order)."""
    off = 0
    while True:
        q = dict(params)
        q["$limit"] = page
        q["$offset"] = off
        r = polite_get(base, params=q, delay=delay, timeout=600)
        rows = r.json()
        if not rows:
            return
        yield rows
        if len(rows) < page:
            return
        off += page
