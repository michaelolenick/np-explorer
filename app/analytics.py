"""Usage stats for the daily report: page requests, searches and actions, recorded server-side.

Runs only when APP_ENV=prod (the dev box is never counted). Requests from INTERNAL_IPS,
loopback and the servers themselves are not recorded. Records go on an in-process queue;
a background thread classifies claimed search-engine crawlers by reverse DNS, looks up the
country, and writes them in batches, so a request never waits on the database. IP
addresses are used for that and then dropped; they are not stored.

What is collected is described on templates/privacy.html; keep the two in step.
"""

from __future__ import annotations

import functools
import ipaddress
import json
import logging
import re
import secrets
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from app.config import APP_ENV, DATA_DIR, INTERNAL_IPS, SITE_URL

log = logging.getLogger("np.analytics")

ENABLED = APP_ENV == "prod"
COOKIE = "ssv"
COOKIE_MAX_AGE = 365 * 24 * 3600
SESSION_GAP = timedelta(minutes=30)
FLUSH_EVERY = 5          # seconds
BEACON_EVENTS = {"copy_table", "copy_text", "sponsor_click"}
_VID = re.compile(r"^[0-9a-f]{32}$")
_SITE_HOST = urlsplit(SITE_URL).netloc.lower()

# VSTRAT, the owner's strategy software and FURP's sister site (owner, 2026-11-06): its segment tool calls
# /api/segments and opens /segments in a tab. Any VSTRAT environment is still VSTRAT: vstrat.ai and its bench and
# dev hosts (the nginx server_names on its three machines). A request is from VSTRAT when its Origin (API calls)
# or Referer (opened links) is one of these; the event is tagged source=vstrat, the headless filter never judges
# it, and the daily report has a VSTRAT row.
VSTRAT_HOSTS = {"vstrat.ai", "www.vstrat.ai", "bench.vstrat.ai", "b2.vstrat.ai", "dev.vstrat.ai"}


def _url_host(url: str | None) -> str:
    if not url:
        return ""
    return urlsplit(url).netloc.lower().split("@")[-1].split(":")[0]


def source_of(headers) -> str | None:
    """Which sister site a request came from, by its Origin or Referer: 'vstrat' for any VSTRAT host, else None."""
    hosts = {_url_host(headers.get("origin")), _url_host(headers.get("referer"))}
    return "vstrat" if hosts & VSTRAT_HOSTS else None

# --- who is asking -------------------------------------------------------------------

_SCRAPER = re.compile(r"curl|wget|python-requests|python-urllib|aiohttp|httpx|go-http-client|scrapy|java/|"
                      r"libwww|okhttp|axios|node-fetch|headless|phantomjs|puppeteer|playwright|selenium|"
                      r"chrome-lighthouse|electron|cypress|webdriver|jsdom|zgrab|masscan", re.I)
_CRAWLER = re.compile(r"bot\b|bot/|crawl|spider|slurp|facebookexternalhit|embedly|preview|monitor|uptime|"
                      r"feedfetcher|mediapartners|archiver|ia_archiver|petalbot|bytespider", re.I)


def classify_ua(ua: str | None) -> str:
    """User-agent class before verification: googlebot?, bingbot?, crawler, scraper or human."""
    ua = (ua or "").strip()
    if not ua:
        return "scraper"
    low = ua.lower()
    if "googlebot" in low or "google-inspectiontool" in low:
        return "googlebot?"
    if "bingbot" in low or "bingpreview" in low:
        return "bingbot?"
    if _SCRAPER.search(ua):
        return "scraper"
    if _CRAWLER.search(ua):
        return "crawler"
    if not low.startswith("mozilla/") and not low.startswith("opera/"):
        return "scraper"
    return "human"


BOT_DOMAINS = {
    "googlebot": (".googlebot.com", ".google.com", ".googleusercontent.com"),
    "bingbot": (".search.msn.com",),
}


# --- bots with a browser user agent (owner, 2026-11-06) --------------------------------------------------------
# On 2026-11-05, 9,819 "visitors" came from 430 Alibaba Cloud IPs in Singapore: Chrome user agents, a fake google.com
# referrer on every request, one page per "visit", never returning the cookie. Three checks, no model calls:
#   1. A referrer from another site on a request whose Sec-Fetch-Site says "none" (typed or scripted navigation,
#      which carries no referrer) is a spoofed referrer: a browser never sends that pair.
#   2. Chrome 80+ and Firefox 90+ always send Sec-Fetch-Mode; a request claiming them without it is a script.
#   3. An IP that keeps asking for pages without ever returning the visitor cookie: a reader's second page carries
#      it, a scraper's never does. After COOKIELESS_LIMIT such page requests in COOKIELESS_WINDOW with none cookied,
#      the IP is "headless" for COOKIELESS_BAN. Per worker, in memory, bounded.
# These are recorded as ua_class "headless", counted apart from humans and from declared crawlers.
_CHROMIUM = re.compile(r"(?:Chrome|CriOS)/(\d+)")
_FIREFOX = re.compile(r"Firefox/(\d+)")
COOKIELESS_LIMIT = 12
COOKIELESS_WINDOW = 24 * 3600
COOKIELESS_BAN = 24 * 3600
_IP_MAX = 50_000
_ips: dict[str, list] = {}        # ip -> [cookieless pages, cookied pages, window start, banned until]
_ips_lock = threading.Lock()


def spoofed_referrer(headers, referrer: str | None) -> bool:
    return bool(referrer) and (headers.get("sec-fetch-site") or "").lower() == "none"


def script_claiming_browser(ua: str, headers) -> bool:
    if headers.get("sec-fetch-mode"):
        return False
    m = _CHROMIUM.search(ua)
    if m and int(m.group(1)) >= 80:
        return True
    m = _FIREFOX.search(ua)
    return bool(m and int(m.group(1)) >= 90)


def cookieless_scraper(ip: str | None, has_cookie: bool, now: float | None = None) -> bool:
    """Count this page request for the IP; True when the IP has earned (or already has) the ban."""
    if not ip:
        return False
    now = now or time.time()
    with _ips_lock:
        rec = _ips.get(ip)
        if rec is None:
            if len(_ips) >= _IP_MAX:                        # bounded: drop the oldest half
                for k in sorted(_ips, key=lambda k: _ips[k][2])[: _IP_MAX // 2]:
                    del _ips[k]
            rec = _ips[ip] = [0, 0, now, 0.0]
        if rec[3] > now:
            return True
        if now - rec[2] > COOKIELESS_WINDOW:
            rec[:3] = [0, 0, now]
        rec[1 if has_cookie else 0] += 1
        if rec[1] == 0 and rec[0] >= COOKIELESS_LIMIT:
            rec[3] = now + COOKIELESS_BAN
            return True
        return False


def bot_reason(request, has_cookie: bool) -> str | None:
    """Why a request with a browser user agent is not a person, or None."""
    h = request.headers
    ua = h.get("user-agent", "")
    ref = referrer_domain(h.get("referer"))
    if spoofed_referrer(h, ref):
        return "spoofed referrer"
    if script_claiming_browser(ua, h):
        return "no sec-fetch headers"
    if cookieless_scraper(_client_ip(request), has_cookie):
        return "never returns the cookie"
    return None


@functools.lru_cache(maxsize=4096)
def verify_bot(ip: str, bot: str) -> bool:
    """Reverse DNS must end in the engine's domain and resolve forward to the same IP."""
    try:
        host = socket.gethostbyaddr(ip)[0].lower().rstrip(".")
        if not host.endswith(BOT_DOMAINS[bot]):
            return False
        return ip in socket.gethostbyname_ex(host)[2] or ip in {a[4][0] for a in socket.getaddrinfo(host, None)}
    except (OSError, KeyError, UnicodeError):
        return False


def final_class(claimed: str, ip: str | None, verify=verify_bot) -> str:
    """A crawler claiming to be Googlebot or Bingbot is one only if its IP checks out; otherwise it's a scraper."""
    if claimed.endswith("?"):
        bot = claimed[:-1]
        return bot if ip and verify(ip, bot) else "scraper"
    return claimed


def _networks(spec: str) -> list:
    nets = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]
    for part in re.split(r"[,\s]+", spec or ""):
        if part:
            try:
                nets.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                log.warning("INTERNAL_IPS: ignoring %r", part)
    return nets


_INTERNAL = _networks(INTERNAL_IPS)


def is_internal(ip: str | None, nets=None) -> bool:
    if not ip:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return any(addr in n for n in (_INTERNAL if nets is None else nets))


def route_type(path: str) -> str:
    if path == "/":
        return "home"
    first = path.strip("/").split("/", 1)[0]
    if first == "org" and "/grants/" in path:
        return "grants"
    return {"search": "search", "ask": "ask", "person": "person", "org": "org", "contractor": "contractor",
            "contractors": "contractors", "filing": "filing", "boards": "boards", "api": "api", "about": "static",
            "data": "static", "privacy": "static", "support": "support", "contact": "contact"}.get(first, "other")


def referrer_domain(ref: str | None) -> str | None:
    if not ref:
        return None
    host = urlsplit(ref).netloc.lower().split("@")[-1].split(":")[0]
    if not host or host == _SITE_HOST or host.endswith("." + _SITE_HOST):
        return None
    return host.removeprefix("www.")


# --- recording -------------------------------------------------------------------------

_queue: list[tuple[str, dict]] = []
_lock = threading.Lock()
_thread: threading.Thread | None = None


def _enqueue(kind: str, rec: dict) -> None:
    global _thread
    with _lock:
        _queue.append((kind, rec))
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_flusher, name="analytics-flush", daemon=True)
            _thread.start()


def _client_ip(request) -> str | None:
    return request.client.host if request.client else None


def _base(request) -> dict | None:
    """Common fields, or None when this request isn't counted (dev box, internal traffic)."""
    if not ENABLED:
        return None
    ip = _client_ip(request)
    if is_internal(ip):
        return None
    ua = request.headers.get("user-agent", "")
    claimed = classify_ua(ua)
    if claimed == "human" and getattr(request.state, "bot_reason", None):
        claimed = "headless"
    return {"ts": datetime.now(timezone.utc), "ip": ip, "claimed": claimed,
            "visitor_id": getattr(request.state, "vid", None), "source": source_of(request.headers)}


def _meta(base: dict, meta: dict | None) -> dict | None:
    """The event's meta with the source (vstrat) added when there is one."""
    if base.get("source"):
        return {**(meta or {}), "source": base["source"]}
    return meta


async def middleware(request, call_next):
    """Assign the visitor id, time the request, record it, set the cookie on a new visitor's first page."""
    if not ENABLED or request.method not in ("GET", "HEAD") or request.url.path.startswith("/static/") \
            or request.url.path == "/e":
        return await call_next(request)
    vid = request.cookies.get(COOKIE)
    new_vid = None
    if not (vid and _VID.match(vid)):
        vid = None
    request.state.bot_reason = None
    request.state.source = source_of(request.headers)
    if classify_ua(request.headers.get("user-agent")) == "human":
        if not request.state.source:                 # a visit VSTRAT sent is a person (owner, 2026-11-06)
            try:
                request.state.bot_reason = bot_reason(request, has_cookie=vid is not None)
            except Exception:  # noqa: BLE001 - the filter must never break a page
                log.exception("analytics: bot check")
        if request.state.bot_reason:
            vid = None                                       # a bot keeps no visitor id, even one it replays
        elif vid is None:
            vid = new_vid = secrets.token_hex(16)
    request.state.vid = vid
    t0 = time.monotonic()
    response = await call_next(request)
    try:
        _record_page(request, response.status_code, (time.monotonic() - t0) * 1000)
        if new_vid and response.status_code < 400 and "text/html" in response.headers.get("content-type", ""):
            response.set_cookie(COOKIE, new_vid, max_age=COOKIE_MAX_AGE, path="/", secure=True, httponly=True,
                                samesite="lax")
    except Exception:  # noqa: BLE001 - stats must never break a page
        log.exception("analytics: recording a request")
    return response


def _record_page(request, status: int, ms: float) -> None:
    base = _base(request)
    if base is None:
        return
    path = request.url.path
    params = request.query_params
    route = route_type(path)
    name = "page"
    if path.endswith(".csv"):
        name = "export"
    elif path.startswith("/boards/") and path.endswith(".png"):
        name = "share_card"
    elif params.get("fragment") == "1":
        name = "popup" if route == "person" else "year_tab" if route == "grants" else "fragment"
    rec = {**base, "name": name, "route": route, "path": path[:300], "status": status, "ms": round(ms, 1),
           "referrer": referrer_domain(request.headers.get("referer")),
           # Campaign tags (utm_source=linkedin...) so the report can count clicks from posts.
           "meta": _meta(base, {k: params.get(k)[:60] for k in ("utm_source", "utm_medium", "utm_campaign") if params.get(k)} or None)}
    _enqueue("event", rec)
    if route == "person" and name == "page" and params.get("year"):
        _enqueue("event", {**rec, "name": "year_tab", "meta": {"year": params.get("year")[:4]}})


def event(request, name: str, meta: dict | None = None) -> None:
    """A server-side action (contact form sent) or a beacon (Copy table)."""
    try:
        base = _base(request)
        if base is None:
            return
        if base["visitor_id"] is None:
            vid = request.cookies.get(COOKIE)
            base["visitor_id"] = vid if vid and _VID.match(vid) else None
        _enqueue("event", {**base, "name": name, "route": route_type(request.url.path), "path": request.url.path[:300],
                           "status": None, "ms": None, "referrer": None, "meta": _meta(base, meta)})
    except Exception:  # noqa: BLE001
        log.exception("analytics: recording event %s", name)


def search(request, q: str, search_type: str, *, intent: str | None = None, results: int | None = None,
           fallback: bool = False, reason: str | None = None, ms: float | None = None) -> None:
    try:
        from app import space
        space.record_query(request, q, search_type, intent)   # the logged-in person's own history (2026-11-12)
    except Exception:  # noqa: BLE001
        log.exception("analytics: query history")
    try:
        base = _base(request)
        if base is None or not q:
            return
        _enqueue("search", {**base, "q": q[:300], "search_type": search_type, "nl_intent": intent,
                            "results": results, "zero": None if results is None else results == 0,
                            "nl_fallback": fallback, "fallback_reason": reason,
                            "ms": None if ms is None else round(ms, 1)})
    except Exception:  # noqa: BLE001
        log.exception("analytics: recording a search")


# --- writing ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _geo():
    path = DATA_DIR / "geo" / "dbip-country-lite.mmdb"
    if not path.exists():
        return None
    try:
        import maxminddb
        return maxminddb.open_database(str(path))
    except Exception:  # noqa: BLE001
        log.exception("analytics: opening %s", path)
        return None


def country(ip: str | None) -> str | None:
    reader = _geo()
    if not reader or not ip:
        return None
    try:
        rec = reader.get(ip) or {}
        return (rec.get("country") or {}).get("iso_code")
    except (ValueError, TypeError):
        return None


def _flusher() -> None:
    while True:
        time.sleep(FLUSH_EVERY)
        with _lock:
            batch = _queue[:]
            _queue.clear()
        if batch:
            try:
                write(batch)
            except Exception:  # noqa: BLE001 - best effort; a lost batch only lowers counts
                log.exception("analytics: writing %d records", len(batch))


def write(batch: list[tuple[str, dict]]) -> None:
    from app.db import pool
    events, searches, seen = [], [], {}
    for kind, r in batch:
        cls = final_class(r["claimed"], r["ip"])
        vid = r["visitor_id"] if cls == "human" else None     # headless and the rest keep no visitor
        if kind == "event":
            events.append((r["ts"], vid, r["name"], r["route"], r["path"], r["status"], r["ms"], r["referrer"], cls,
                           country(r["ip"]), json.dumps(r["meta"]) if r["meta"] else None))
        else:
            searches.append((r["ts"], vid, cls, r["q"], r["search_type"], r["nl_intent"], r["results"], r["zero"],
                             r["nl_fallback"], r["fallback_reason"], r["ms"]))
        if vid:
            first, last, n = seen.get(vid, (r["ts"], r["ts"], 0))
            seen[vid] = (min(first, r["ts"]), max(last, r["ts"]), n + (kind == "event" and r["name"] == "page"))
    with pool.connection() as conn, conn.transaction():
        if events:
            conn.cursor().executemany(
                "INSERT INTO events (ts, visitor_id, name, route, path, status, ms, referrer, ua_class, country, meta) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", events)
        if searches:
            conn.cursor().executemany(
                "INSERT INTO searches (ts, visitor_id, ua_class, q, search_type, nl_intent, results, zero, nl_fallback, "
                "fallback_reason, ms) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", searches)
        if seen:
            # In id order: workers flushing overlapping visitors in different orders deadlocked (2026-10-25 03:20).
            conn.cursor().executemany(
                "INSERT INTO visitors (id, first_seen, last_seen, requests) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET last_seen = greatest(visitors.last_seen, excluded.last_seen), "
                "requests = visitors.requests + excluded.requests",
                [(v, f, last, n) for v, (f, last, n) in sorted(seen.items())])


# --- counting helpers (used by app/report.py) ------------------------------------------

def sessions(rows) -> list[dict]:
    """Group (visitor_id, ts, path, referrer) rows, any order, into sessions: 30 minutes idle ends one."""
    out = []
    by_visitor: dict[str, list] = {}
    for vid, ts, path, ref in rows:
        by_visitor.setdefault(vid, []).append((ts, path, ref))
    for vid, hits in by_visitor.items():
        hits.sort(key=lambda h: h[0])
        cur = None
        for ts, path, ref in hits:
            if cur is None or ts - cur["last"] > SESSION_GAP:
                cur = {"visitor_id": vid, "start": ts, "last": ts, "landing": path, "referrer": ref, "pages": 0}
                out.append(cur)
            cur["last"] = ts
            cur["pages"] += 1
    return out


def new_vs_returning(active_ids, first_seen: dict, start: datetime, end: datetime) -> tuple[int, int]:
    """Of the visitors active in [start, end), how many were first seen in that window, and how many before."""
    new = sum(1 for v in set(active_ids) if v in first_seen and start <= first_seen[v] < end)
    return new, len(set(active_ids)) - new
