"""On-demand explanations of entity pages (owner, 2026-11-08): a short plain-English paragraph on who or what an
organization, person, contractor, company or committee is, written from that page's own data (app/explain.py does
the data gathering and the model call), generated the first time a real person opens the page, cached, and then
served to everyone in the server-rendered HTML.

Who triggers a generation: a browser that behaves like a person. The page's script waits for a real interaction
(a scroll, a pointer move, a key, a touch) at least ANTE_MS after load, then POSTs to /explain/auto with a header a
scraper would have to know. The server then requires a browser user agent that the analytics filter did not judge a
script (app/analytics.bot_reason), the visitor cookie set on the first page view, and rate limits per IP, per visitor
and site-wide. Bots and everyone else still see the cached text when there is one; they never cause a generation.

Cost: every generation is logged (explain_log: tokens, dollars, entity, time, IP bucket, visitor). Days are
America/Indianapolis. When a day's spend passes DAILY_CAP, generation stops at once (cached text keeps showing), the
owner gets an email saying why, with a signed one-click link to continue, and nothing resumes until that link is
clicked (or `python -m app.autoexplain resume`), not at midnight either.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import Counter
from zoneinfo import ZoneInfo

from app import db
from app.config import SITE_URL
from app.contact import HourlyLimit

log = logging.getLogger("np.autoexplain")

TZ = ZoneInfo("America/Indianapolis")
DAILY_CAP = float(os.environ.get("EXPLAIN_DAILY_CAP", "5"))
PRICES = {"claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50)}    # $ per million tokens in, out
ANTE_MS = 1500                            # the page must be open this long before the script asks
HEADER = "x-furp-explain"                 # the script's header; its value is the page path
PER_IP = HourlyLimit(12)                  # generations an IP may cause in an hour
PER_VISITOR = HourlyLimit(6)              # ... and one visitor cookie
SITEWIDE = HourlyLimit(120)               # ... and the whole site (a scraper farm cannot burn the day's cap in minutes)
BLOCK_LOG = HourlyLimit(20)               # blocked attempts logged per IP bucket per hour (the rest are counted in memory)
RECHECK_SECONDS = 6 * 3600                # a page's freshness (data hash) is checked at most this often per worker
ENTITY_PREFIXES = ("/org/", "/person/", "/contractor/", "/institution/", "/student-loans/trust/", "/politics/donor/",
                   "/politics/committee/", "/corporate/insider/", "/corporate/company/", "/corporate/form-d/",
                   "/federal-spending/recipient/", "/lobbying/client/", "/lobbying/firm/", "/lobbying/lobbyist/")

_checked: dict[str, float] = {}           # url -> when its freshness was last checked (per worker)
_blocked_mem: Counter = Counter()         # blocked attempts not written (per worker), by reason
_lock = threading.Lock()


def is_entity(path: str) -> bool:
    return path.startswith(ENTITY_PREFIXES)


def entity_kind(path: str) -> str:
    for p in ENTITY_PREFIXES:
        if path.startswith(p):
            return p.strip("/").split("/")[-1]
    return "other"


def today() -> dt.date:
    return dt.datetime.now(TZ).date()


def ip_bucket(ip: str | None) -> str:
    """An IPv4 /24 or an IPv6 /48: enough to see a cluster, not a person."""
    if not ip:
        return "unknown"
    if ":" in ip:
        return ":".join(ip.split(":")[:3]) + "::/48"
    return ip.rsplit(".", 1)[0] + ".0/24"


def cost_of(model: str, usage: dict) -> float:
    pin, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    tokens_in = int(usage.get("input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0) \
        + int(usage.get("cache_read_input_tokens") or 0)
    return round(tokens_in / 1e6 * pin + int(usage.get("output_tokens") or 0) / 1e6 * pout, 6)


# --- the cache, as the page renders ----------------------------------------------------------------

def cached_for(path: str) -> str:
    """The latest cached explanation for an entity page, for the server-rendered HTML ("" when none)."""
    if not is_entity(path):
        return ""
    try:
        with db.conn() as conn:
            row = conn.execute("SELECT html FROM nl_explain WHERE url = %s AND html <> '' ORDER BY created DESC LIMIT 1",
                               (path,)).fetchone()
        return row["html"] if row else ""
    except Exception:  # noqa: BLE001 - never breaks a page
        return ""


# --- the stop switch ----------------------------------------------------------------------------------

def state(conn) -> dict:
    row = conn.execute("SELECT value FROM explain_state WHERE key = 'stop'").fetchone()
    return row["value"] if row else {}


def set_state(conn, value: dict) -> None:
    conn.execute("""INSERT INTO explain_state (key, value) VALUES ('stop', %s::jsonb)
                    ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated = now()""", (json.dumps(value, default=str),))


def stopped(conn) -> bool:
    return bool(state(conn).get("stopped_at"))


def _secret() -> bytes:
    return (os.environ.get("SESSION_SECRET") or os.environ.get("CONTACT_FORM_SECRET") or "np-explorer-explain").encode()


def sign(nonce: str) -> str:
    return hmac.new(_secret(), nonce.encode(), hashlib.sha256).hexdigest()[:32]


def resume_link(nonce: str) -> str:
    return f"{SITE_URL}/explain/resume?t={nonce}.{sign(nonce)}"


def stop(conn, reason: str) -> str:
    """Stop generation and mint the one-click token; returns the resume link."""
    nonce = secrets.token_urlsafe(16)
    set_state(conn, {"stopped_at": dt.datetime.now(TZ).isoformat(timespec="seconds"), "day": today().isoformat(),
                     "reason": reason, "nonce": nonce})
    return resume_link(nonce)


def resume(conn, token: str | None = None, by: str = "link") -> bool:
    """Clear the stop. With a token (the emailed link) it must match the stored nonce and its signature; without one
    (the command line) it clears outright."""
    st = state(conn)
    if token is not None:
        nonce, _, sig = token.partition(".")
        if not st.get("nonce") or not hmac.compare_digest(sig, sign(nonce)) or not hmac.compare_digest(nonce, st["nonce"]):
            return False
    set_state(conn, {"resumed_at": dt.datetime.now(TZ).isoformat(timespec="seconds"), "resumed_by": by,
                     "previous": {k: v for k, v in st.items() if k != "nonce"}})
    return True


# --- the day's spend and the alert -----------------------------------------------------------------------

def day_window(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime.combine(day, dt.time(0), TZ)
    return start, start + dt.timedelta(days=1)


def spent(conn, day: dt.date | None = None) -> float:
    s, e = day_window(day or today())
    row = conn.execute("SELECT coalesce(sum(cost), 0) AS c FROM explain_log WHERE outcome = 'generated' AND ts >= %s AND ts < %s",
                       (s, e)).fetchone()
    return float(row["c"] or 0)


def day_report(conn, day: dt.date | None = None) -> dict:
    """What happened today: generations and cost, cost by hour, top entities, humans served vs bots blocked, and
    the IP buckets that look like a farm."""
    day = day or today()
    s, e = day_window(day)
    rows = conn.execute("""SELECT ts, url, outcome, cost, ip_bucket, visitor FROM explain_log
                           WHERE ts >= %s AND ts < %s ORDER BY ts""", (s, e)).fetchall()
    gen = [r for r in rows if r["outcome"] == "generated"]
    by_hour: Counter = Counter()
    for r in gen:
        by_hour[r["ts"].astimezone(TZ).strftime("%H:00")] += float(r["cost"] or 0)
    top = Counter()
    for r in gen:
        top[r["url"]] += float(r["cost"] or 0)
    buckets = Counter(r["ip_bucket"] for r in rows if r["outcome"] in ("generated", "blocked"))
    gen_buckets = Counter(r["ip_bucket"] for r in gen)
    visitors = Counter(r["visitor"] for r in gen if r["visitor"])
    abusive = [f"{b}: {n} generations" for b, n in gen_buckets.most_common(5) if n >= 8] \
        + [f"{v[:8]}…: {n} generations from one visitor" for v, n in visitors.most_common(5) if n >= 5] \
        + [f"{b}: {n} attempts (blocked and served)" for b, n in buckets.most_common(5) if n >= 50]
    return {"day": day.isoformat(), "generations": len(gen), "cost": round(sum(float(r["cost"] or 0) for r in gen), 4),
            "cost_by_hour": {h: round(c, 4) for h, c in sorted(by_hour.items())},
            "top_entities": [(u, round(c, 4)) for u, c in top.most_common(20)],
            "human_served": sum(1 for r in rows if r["outcome"] in ("generated", "cached")),
            "bots_blocked": sum(1 for r in rows if r["outcome"] == "blocked") + sum(_blocked_mem.values()),
            "blocked_reasons": dict(Counter(r["visitor"] for r in rows if r["outcome"] == "blocked").most_common(8)),
            "abusive": abusive or ["nothing unusual"]}


def alert_text(rep: dict, link: str) -> tuple[str, str]:
    lines = [f"Explanation generation stopped at ${rep['cost']:.2f} today ({rep['day']}, Indianapolis time), over the "
             f"${DAILY_CAP:.2f} daily cap. Cached explanations keep showing; nothing new is generated until you say so.",
             "",
             f"Generations today: {rep['generations']}, cost ${rep['cost']:.2f}.",
             "Cost by hour: " + (", ".join(f"{h} ${c:.2f}" for h, c in rep["cost_by_hour"].items()) or "none"),
             f"Humans served (generated or cached): {rep['human_served']}; bot or over-limit attempts blocked: {rep['bots_blocked']}"
             + (" (" + ", ".join(f"{k} {v}" for k, v in rep["blocked_reasons"].items()) + ")" if rep["blocked_reasons"] else ""),
             "Traffic that looks abusive: " + "; ".join(rep["abusive"]),
             "", "Top 20 entities by cost:"]
    lines += [f"  ${c:.3f}  {SITE_URL}{u}" for u, c in rep["top_entities"]]
    lines += ["", "Continue generating (one click, signed, works once):", link, "",
              "Do you want to continue? Click the link to resume; otherwise generation stays off (it does not resume at midnight)."]
    text = "\n".join(lines)
    html = "<pre style=\"font: 14px/1.5 monospace; white-space: pre-wrap\">" + text.replace("&", "&amp;").replace("<", "&lt;") \
        .replace(link, f'<a href="{link}">{link}</a>') + "</pre>"
    return text, html


def enforce_cap(conn) -> bool:
    """True when generation may proceed. Past the cap: stop, email once, refuse."""
    if stopped(conn):
        return False
    if spent(conn) < DAILY_CAP:
        return True
    link = stop(conn, f"daily cap ${DAILY_CAP:.2f} passed")
    conn.commit() if hasattr(conn, "commit") else None
    try:
        from app import report
        text, html = alert_text(day_report(conn), link)
        ok, info = report.send(f"FURP explanations stopped: ${DAILY_CAP:.0f} cap reached today", text, html)
        log.warning("autoexplain: stopped at the cap; email %s (%s)", "sent" if ok else "NOT sent", info)
    except Exception:  # noqa: BLE001
        log.exception("autoexplain: alert email")
    return False


# --- the generation, gated ----------------------------------------------------------------------------------

def _log(conn, outcome: str, path: str, ip: str | None, visitor: str | None, model: str = "", usage: dict | None = None,
         cost: float = 0.0, note: str | None = None) -> None:
    u = usage or {}
    conn.execute("""INSERT INTO explain_log (url, entity_kind, outcome, model, input_tokens, output_tokens, cost, ip_bucket, visitor)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                 (path[:500], entity_kind(path), outcome, model, int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
                  + int(u.get("cache_creation_input_tokens") or 0), int(u.get("output_tokens") or 0), cost, ip_bucket(ip),
                  (note or visitor or "")[:64]))


def blocked(reason: str, path: str, ip: str | None) -> dict:
    """Count a refused attempt (a few per IP bucket an hour reach the log; the rest stay in memory)."""
    with _lock:
        _blocked_mem[reason] += 1
    if BLOCK_LOG.allow(ip_bucket(ip)):
        try:
            with db.conn() as conn:
                _log(conn, "blocked", path, ip, None, note=reason)
        except Exception:  # noqa: BLE001
            pass
    return {"status": "blocked", "html": ""}


def human_request(request) -> str | None:
    """None when the request looks like a person's browser; else why not."""
    from app import analytics
    ua = request.headers.get("user-agent", "")
    if analytics.classify_ua(ua) != "human":
        return "user agent"
    if getattr(request.state, "bot_reason", None):
        return "headless"
    try:
        if analytics.bot_reason(request, has_cookie=bool(request.cookies.get(analytics.COOKIE))):
            return "headless"
    except Exception:  # noqa: BLE001
        pass
    vid = request.cookies.get(analytics.COOKIE) or ""
    if not analytics._VID.match(vid):
        return "no visitor cookie"
    if request.headers.get(HEADER) != request.query_params.get("u", "") or not request.headers.get("sec-fetch-mode"):
        return "no browser headers"
    return None


def generate(request, path: str) -> dict:
    """The explanation for an entity page, generating it when a person asks and the cache has no fresh one:
    {status: cached | generated | blocked | stopped | none, html}."""
    from app import analytics, explain
    ip = analytics._client_ip(request)
    vid = request.cookies.get(analytics.COOKIE) or ""
    why = human_request(request)
    if why:
        return blocked(why, path, ip)
    if not (PER_VISITOR.allow(vid) and PER_IP.allow(ip or "?") and SITEWIDE.allow("all")):
        return blocked("rate limit", path, ip)
    # Fresh in the cache? (the data hash is checked at most every RECHECK_SECONDS per page)
    now = time.monotonic()
    with _lock:
        recently = now - _checked.get(path, 0) < RECHECK_SECONDS
    have = cached_for(path)
    if have and recently:
        with db.conn() as conn:
            _log(conn, "cached", path, ip, vid)
        return {"status": "cached", "html": have}
    data, q = explain.page_data(path)
    if not data:
        return {"status": "none", "html": have}
    c = explain.compact(data)
    version = hashlib.sha256(json.dumps(c, sort_keys=True, default=str).encode()).hexdigest()[:16]
    key = hashlib.sha256(f"{path}|{version}|{explain.PROMPT_VERSION}".encode()).hexdigest()
    with db.conn() as conn:
        row = conn.execute("SELECT html FROM nl_explain WHERE key = %s AND html <> ''", (key,)).fetchone()
        if row:
            with _lock:
                _checked[path] = now
            _log(conn, "cached", path, ip, vid)
            return {"status": "cached", "html": row["html"]}
        if not enforce_cap(conn):
            _log(conn, "stopped", path, ip, vid)
            return {"status": "stopped", "html": have}
    reply, usage = _call(path, q, c)
    text = (reply or {}).get("explanation", "").strip() if reply else ""
    from app import answer
    out = ""
    if text and answer.numbers_ok(text, c):
        import html as html_mod
        out = f"<p>{html_mod.escape(answer.no_em_dash(text))}</p>"
        explain._log_flags(path, version, (reply or {}).get("flags") or [])
    cost = cost_of(explain.MODEL, usage)
    with db.conn() as conn:
        conn.execute("""INSERT INTO nl_explain (key, url, version, html) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (key) DO UPDATE SET html = excluded.html, created = now()""", (key, path[:2000], version, out))
        _log(conn, "generated", path, ip, vid, explain.MODEL, usage, cost)
        enforce_cap(conn)                 # this one may have crossed the line: stop and email now, not at the next ask
    with _lock:
        _checked[path] = now
    return {"status": "generated", "html": out}


def _call(path: str, q: str, c: dict) -> tuple[dict | None, dict]:
    """app.explain's model call, with the usage kept for the cost log."""
    from app import ask, explain
    import httpx
    if not ask.enabled():
        return None, {}
    try:
        r = ask.post(timeout=45, payload={"model": explain.MODEL, "max_tokens": 4000, "thinking": {"type": "adaptive"},
                                          "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": explain.SCHEMA}},
                                          "system": explain.SYSTEM,
                                          "messages": [{"role": "user", "content": f"Page: {path}\nSearch typed: {q or '(none)'}\n\n"
                                                                                   f"DATA: {json.dumps(c, default=str)}"}]})
    except httpx.HTTPError as e:
        log.warning("autoexplain: call failed (%s)", type(e).__name__)
        return None, {}
    if r.status_code != 200:
        log.warning("autoexplain: model returned %s", r.status_code)
        return None, {}
    body = r.json()
    usage = body.get("usage") or {}
    ask._usage(calls=1, input_tokens=int(usage.get("input_tokens") or 0), output_tokens=int(usage.get("output_tokens") or 0))
    text = "".join(x.get("text", "") for x in body.get("content", []) if x.get("type") == "text").strip()
    try:
        return json.loads(text), usage
    except ValueError:
        return None, usage


# --- the daily report's numbers -------------------------------------------------------------------------------

def report_numbers(conn, day: dt.date) -> dict:
    s, e = day_window(day)
    row = conn.execute("""SELECT count(*) FILTER (WHERE outcome = 'generated') AS generated,
                                 count(*) FILTER (WHERE outcome = 'cached') AS cached,
                                 count(*) FILTER (WHERE outcome = 'blocked') AS blocked,
                                 count(*) FILTER (WHERE outcome = 'stopped') AS stopped,
                                 coalesce(sum(cost) FILTER (WHERE outcome = 'generated'), 0) AS cost
                          FROM explain_log WHERE ts >= %s AND ts < %s""", (s, e)).fetchone()
    week = conn.execute("SELECT coalesce(sum(cost), 0) AS c FROM explain_log WHERE outcome = 'generated' AND ts >= %s AND ts < %s",
                        (s - dt.timedelta(days=6), e)).fetchone()["c"]
    human_views = row["generated"] + row["cached"]
    return {"generations": row["generated"], "cache_hits": row["cached"], "human_views": human_views,
            "cache_hit_rate_pct": round(100 * row["cached"] / human_views, 1) if human_views else None,
            "bots_blocked": row["blocked"], "refused_while_stopped": row["stopped"],
            "cost_today_usd": round(float(row["cost"]), 2), "cost_7_day_usd": round(float(week), 2),
            "stopped": bool(state(conn).get("stopped_at")), "daily_cap_usd": DAILY_CAP}


def main(argv=None) -> int:
    import sys
    cmd = (argv or sys.argv[1:] or ["status"])[0]
    with db.conn() as conn:
        if cmd == "resume":
            resume(conn, None, by="command line")
            print("resumed")
        elif cmd == "stop":
            print("stopped;", stop(conn, "by hand"))
        else:
            print(json.dumps({"state": state(conn), "today": report_numbers(conn, today())}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    from app import db as _db
    _db.pool.open(wait=False)
    raise SystemExit(main())
