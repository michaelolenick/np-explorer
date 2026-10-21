"""The daily usage report: metrics computed in code, a narrative written by Claude from those
metrics only, checked number by number, then saved and emailed.

Run by scripts/report.py (cron, 07:00 America/Chicago, production only).
"""

from __future__ import annotations

import gzip
import html
import json
import logging
import os
import re
import shutil
import statistics
import subprocess
from collections import Counter
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import psycopg
from psycopg.rows import dict_row

from app import analytics
from app.config import (DATABASE_URL, DATA_DIR, INFO_EMAIL, NL_REPORT_MODEL, REPORT_FROM, REPORT_SUBJECT, REPORT_TO,
                        ROOT, USAGE_RETENTION_DAYS)

log = logging.getLogger("np.report")

CHICAGO = ZoneInfo("America/Chicago")
LOW = 20                       # counts under this are marked * (low confidence)
TRAILING_DAYS = 7
NGINX = Path("/var/log/nginx")
REPORTS = ROOT / "reports"
MANUAL = ROOT / "manual_inputs.yml"
PRICE_IN = float(os.environ.get("NL_PRICE_IN", "1.00"))    # dollars per million tokens (as scripts/nl_cost.py)
PRICE_OUT = float(os.environ.get("NL_PRICE_OUT", "5.00"))
REMOVAL_TOPIC = "Correction or removal request"
CONSTANTS = {"low_confidence_under": LOW, "trailing_days": TRAILING_DAYS, "session_gap_minutes": 30,
             "percentiles": [50, 95], "form": 990, "top_n": 10, "retention_days": USAGE_RETENTION_DAYS}


def window(day: date, days: int = 1) -> tuple[datetime, datetime]:
    """[start, end) in UTC for `days` Chicago calendar days ending with `day`."""
    start = datetime.combine(day - timedelta(days=days - 1), dtime(0), CHICAGO)
    end = datetime.combine(day + timedelta(days=1), dtime(0), CHICAGO)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1)


def share(a, b):
    return round(100 * a / b, 1) if b else None


def connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, application_name="np-report")


# --- metrics from the database -----------------------------------------------------------

def traffic(conn, start, end) -> dict:
    rows = conn.execute("""SELECT visitor_id, ts, path, referrer, country FROM events
                           WHERE ts >= %s AND ts < %s AND ua_class = 'human' AND name = 'page'
                             AND visitor_id IS NOT NULL""", (start, end)).fetchall()
    ids = {r["visitor_id"] for r in rows}
    first = {r["id"]: r["first_seen"] for r in conn.execute(
        "SELECT id, first_seen FROM visitors WHERE id = ANY(%s)", (list(ids),)).fetchall()} if ids else {}
    new, returning = analytics.new_vs_returning(ids, first, start, end)
    sess = analytics.sessions([(r["visitor_id"], r["ts"], r["path"], r["referrer"]) for r in rows])
    by_visitor_country = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        by_visitor_country.setdefault(r["visitor_id"], r["country"] or "unknown")
    bots = {r["ua_class"]: r["n"] for r in conn.execute(
        "SELECT ua_class, count(*) AS n FROM events WHERE ts >= %s AND ts < %s AND ua_class <> 'human' "
        "GROUP BY ua_class", (start, end)).fetchall()}
    return {
        "human_visitors": len(ids), "new_visitors": new, "returning_visitors": returning,
        "sessions": len(sess), "page_views": len(rows),
        "pages_per_session": round(len(rows) / len(sess), 2) if sess else None,
        "top_referrers": Counter(s["referrer"] for s in sess if s["referrer"]).most_common(10),
        "top_landing_pages": Counter(s["landing"] for s in sess).most_common(10),
        "countries": Counter(by_visitor_country.values()).most_common(10),
        "bot_requests_by_class": dict(sorted(bots.items())),
    }


def _norm(q: str) -> str:
    return " ".join(q.lower().split())


def searches(conn, start, end) -> dict:
    rows = conn.execute("""SELECT q, search_type, nl_intent, results, zero, nl_fallback, fallback_reason, ms
                           FROM searches WHERE ts >= %s AND ts < %s AND ua_class = 'human'""", (start, end)).fetchall()
    nl = [r for r in rows if r["search_type"] in ("nl", "edit")]
    return {
        "searches": len(rows),
        "by_type": dict(Counter(r["search_type"] for r in rows).most_common()),
        "plain_searches": sum(1 for r in rows if r["search_type"] in ("plain", "name")),
        "nl_searches": len(nl),
        "nl_fallbacks": sum(1 for r in nl if r["nl_fallback"]),
        "nl_fallback_rate_pct": share(sum(1 for r in nl if r["nl_fallback"]), len(nl)),
        "nl_intents": dict(Counter(r["nl_intent"] for r in nl if r["nl_intent"] and not r["nl_fallback"]).most_common()),
        "nl_cap_hits": sum(1 for r in rows if r["fallback_reason"] == "cap"),
        "zero_result_searches": sum(1 for r in rows if r["zero"]),
        "top_searches": Counter(_norm(r["q"]) for r in rows).most_common(10),
        "top_zero_result_searches": Counter(_norm(r["q"]) for r in rows if r["zero"]).most_common(10),
        "search_p50_ms": pct([r["ms"] for r in rows], 50), "search_p95_ms": pct([r["ms"] for r in rows], 95),
    }


def most_viewed(conn, start, end) -> dict:
    rows = conn.execute("""SELECT route, path, count(*) AS n FROM events
                           WHERE ts >= %s AND ts < %s AND ua_class = 'human' AND name = 'page'
                             AND route IN ('org', 'person') GROUP BY route, path ORDER BY n DESC""", (start, end)).fetchall()
    orgs = [(r["path"].split("/")[2], r["n"]) for r in rows if r["route"] == "org" and r["path"].count("/") == 2][:10]
    people = [(r["path"].split("/")[2], r["n"]) for r in rows if r["route"] == "person" and r["path"].count("/") == 2][:10]
    names = {}
    if orgs:
        names.update({("org", r["ein"]): r["name"] for r in conn.execute(
            "SELECT ein, name FROM organizations WHERE ein = ANY(%s)", ([e for e, _ in orgs],)).fetchall()})
    ids = [int(p) for p, _ in people if p.isdigit()]
    if ids:
        names.update({("person", str(r["id"])): r["display_name"] for r in conn.execute(
            "SELECT id, display_name FROM person_clusters WHERE id = ANY(%s)", (ids,)).fetchall()})
    return {"organizations": [(names.get(("org", e), e), n) for e, n in orgs],
            "people": [(names.get(("person", p), p), n) for p, n in people]}


FUNNEL = [
    ("landed", "SELECT DISTINCT visitor_id FROM events WHERE name = 'page'"),
    ("searched", "SELECT DISTINCT visitor_id FROM searches WHERE true"),
    ("opened an organization page", "SELECT DISTINCT visitor_id FROM events WHERE name = 'page' AND route = 'org'"),
    ("opened a person page", "SELECT DISTINCT visitor_id FROM events WHERE name = 'page' AND route = 'person'"),
    ("used year tabs or the popup", "SELECT DISTINCT visitor_id FROM events WHERE name IN ('year_tab', 'popup')"),
    ("copied or exported a table",
     "SELECT DISTINCT visitor_id FROM events WHERE name IN ('copy_table', 'copy_text', 'export')"),
    ("opened a leaderboard", "SELECT DISTINCT visitor_id FROM events WHERE name = 'page' AND route = 'boards'"),
    ("used a share card", "SELECT DISTINCT visitor_id FROM events WHERE name = 'share_card'"),
    ("contacted us", "SELECT DISTINCT visitor_id FROM events WHERE name = 'contact_submit'"),
    ("clicked Support FURP", "SELECT DISTINCT visitor_id FROM events WHERE name = 'page' AND route = 'support'"),
]


def funnel(conn, start, end) -> list[dict]:
    out, prev = [], None
    for label, sql in FUNNEL:
        n = conn.execute(f"SELECT count(*) AS n FROM ({sql} AND ts >= %s AND ts < %s AND ua_class = 'human' "
                         f"AND visitor_id IS NOT NULL) x", (start, end)).fetchone()["n"]
        out.append({"step": label, "visitors": n, "share_of_previous_pct": share(n, prev) if prev is not None else None})
        prev = n
    return out


def performance(conn, start, end) -> dict:
    rows = conn.execute("""SELECT route, ms, status FROM events WHERE ts >= %s AND ts < %s AND ms IS NOT NULL""",
                        (start, end)).fetchall()
    by_route = {}
    for r in rows:
        by_route.setdefault(r["route"], []).append(r["ms"])
    disk = {}
    for label, path in (("root", "/"), ("data", str(DATA_DIR))):
        try:
            u = shutil.disk_usage(path)
            disk[label] = {"used_pct": share(u.used, u.total), "free_gb": round(u.free / 2**30, 1)}
        except OSError:
            pass
    db_bytes = conn.execute("SELECT pg_database_size(current_database()) AS b").fetchone()["b"]
    return {
        "by_route": {k: {"requests": len(v), "p50_ms": pct(v, 50), "p95_ms": pct(v, 95)} for k, v in sorted(by_route.items())},
        "p95_ms_all": pct([r["ms"] for r in rows], 95),
        "server_5xx": sum(1 for r in rows if (r["status"] or 0) >= 500),
        "statement_timeouts": statement_timeouts(start, end),
        "visitor_429s": count_log_lines(NGINX / "np-limited.log", start, end, status=429),
        "database_gb": round(db_bytes / 2**30, 1),
        "disk": disk,
    }


def statement_timeouts(start, end):
    try:
        out = subprocess.run(["journalctl", "-u", "np-explorer", "-o", "cat", "--no-pager",
                              "--since", start.astimezone(CHICAGO).strftime("%Y-%m-%d %H:%M:%S"),
                              "--until", end.astimezone(CHICAGO).strftime("%Y-%m-%d %H:%M:%S")],
                             capture_output=True, text=True, timeout=120)
        return out.stdout.count("canceling statement due to statement timeout")
    except (OSError, subprocess.SubprocessError):
        return None


# --- metrics from nginx logs -------------------------------------------------------------

_LINE = re.compile(r'^(\S+) \[([^\]]+)\] "([^"]*)" (\d{3})(?: (\S+))? "([^"]*)"')


def log_lines(base: Path):
    """Lines from base, base.1 and base.N.gz (logrotate), oldest first."""
    files = sorted(base.parent.glob(base.name + ".*.gz"), key=lambda p: -int(p.name.split(".")[-2])) \
        + [p for p in (base.with_name(base.name + ".1"), base) if p.exists()]
    for p in files:
        try:
            opener = gzip.open if p.suffix == ".gz" else open
            with opener(p, "rt", encoding="utf-8", errors="replace") as f:
                yield from f
        except OSError:
            continue


def parse_line(line: str):
    m = _LINE.match(line)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(2), "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    rt = m.group(5)
    return {"ip": m.group(1), "ts": ts, "request": m.group(3), "status": int(m.group(4)),
            "ms": round(float(rt) * 1000, 1) if rt and rt not in ("-",) and rt.replace(".", "", 1).isdigit() else None,
            "ua": m.group(6)}


def count_log_lines(base: Path, start, end, status: int | None = None):
    if not base.exists():
        return None
    n = 0
    for line in log_lines(base):
        r = parse_line(line)
        if r and start <= r["ts"] < end and (status is None or r["status"] == status):
            n += 1
    return n


def crawlers(start, end, verify=analytics.verify_bot) -> dict:
    """Googlebot and Bingbot from nginx's np-bots.log, verified by reverse DNS (claims that fail are fakes)."""
    base = NGINX / "np-bots.log"
    if not base.exists():
        return {"available": False, "reason": "no np-bots.log on this host"}
    out = {b: {"requests": 0, "4xx": 0, "5xx": 0, "429": 0, "ms": []} for b in ("googlebot", "bingbot")}
    fake = 0
    oldest = None
    for line in log_lines(base):
        r = parse_line(line)
        if r and (oldest is None or r["ts"] < oldest):
            oldest = r["ts"]
        if not r or not (start <= r["ts"] < end):
            continue
        claimed = analytics.classify_ua(r["ua"])
        if not claimed.endswith("?"):
            continue
        bot = claimed[:-1]
        if not verify(r["ip"], bot):
            fake += 1
            continue
        b = out[bot]
        b["requests"] += 1
        b["4xx"] += 400 <= r["status"] < 500
        b["5xx"] += r["status"] >= 500
        b["429"] += r["status"] == 429
        b["ms"].append(r["ms"])
    if oldest is None or oldest >= end:
        return {"available": False, "reason": "np-bots.log starts " + (oldest.astimezone(CHICAGO).isoformat(timespec="minutes")
                                                                        if oldest else "with no entries yet")}
    for b in out.values():
        ms = b.pop("ms")
        b["p50_ms"], b["p95_ms"] = pct(ms, 50), pct(ms, 95)
    return {"available": True, **out, "fake_claims": fake}


# --- other sources -------------------------------------------------------------------------

def nl_usage(conn, day: date) -> dict:
    r = conn.execute("SELECT * FROM nl_usage WHERE day = %s", (day,)).fetchone()
    if not r:
        return {"calls": 0, "cache_hits": 0, "fallbacks": 0, "input_tokens": 0, "output_tokens": 0, "est_cost_usd": 0.0}
    cost = r["input_tokens"] / 1e6 * PRICE_IN + r["output_tokens"] / 1e6 * PRICE_OUT
    return {"calls": r["calls"], "cache_hits": r["cache_hits"], "fallbacks": r["fallbacks"],
            "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"], "est_cost_usd": round(cost, 2)}


def data_loads(conn, start: datetime, until: datetime) -> dict:
    """Last night's loaders: loader_progress rows finished in [start, until), plus database totals."""
    rows = conn.execute("""SELECT kind, status, count(*) AS files, coalesce(sum(rows), 0) AS rows
                           FROM loader_progress WHERE finished >= %s AND finished < %s
                           GROUP BY kind, status ORDER BY kind, status""", (start, until)).fetchall()
    errors = conn.execute("""SELECT file, left(error, 200) AS error FROM loader_progress
                             WHERE finished >= %s AND finished < %s AND error IS NOT NULL LIMIT 10""",
                          (start, until)).fetchall()
    totals = {r["relname"]: int(r["n"]) for r in conn.execute(
        """SELECT c.relname, c.reltuples AS n FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace
           WHERE s.nspname = 'public' AND c.relname IN ('filings', 'organizations', 'person_clusters', 'people',
                                                       'contractors', 'grants')""").fetchall()}
    last_line, ok = None, None
    logp = Path("/var/log/np-explorer/nightly.log")
    if logp.exists() and start.timestamp() <= logp.stat().st_mtime < until.timestamp() + 6 * 3600:
        tail = logp.read_text(errors="replace").strip().splitlines()[-40:]
        last_line = tail[-1][:200] if tail else None
        ok = bool(last_line) and "| done |" in last_line and not any("Traceback" in t or "STOPPED" in t for t in tail)
    return {"loads": [dict(r) for r in rows], "errors": [dict(r) for r in errors], "totals_estimated": totals,
            "nightly_succeeded": ok, "nightly_last_line": last_line}


def messages(conn, start, end) -> dict:
    rows = conn.execute("""SELECT coalesce(meta->>'topic', 'unknown') AS topic, count(*) AS n FROM events
                           WHERE ts >= %s AND ts < %s AND name = 'contact_submit' GROUP BY 1 ORDER BY 2 DESC""",
                        (start, end)).fetchall()
    by_topic = {r["topic"]: r["n"] for r in rows}
    return {"contact_submissions": sum(by_topic.values()), "by_topic": by_topic,
            "removal_requests": by_topic.get(REMOVAL_TOPIC, 0),
            "removal_status": "not tracked (requests arrive by email; corrections and removals share one topic)"}


def azure_spend(day: date) -> dict:
    """np-explorer resource groups' cost yesterday and month to date, if the Azure CLI can read it."""
    def cost(first: date, last: date):
        out = subprocess.run(["az", "consumption", "usage", "list", "--start-date", first.isoformat(),
                              "--end-date", last.isoformat(), "-o", "json"], capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError((out.stderr or "az failed").strip().splitlines()[0][:200])
        items = json.loads(out.stdout or "[]")
        if not items:
            raise RuntimeError("Azure returned no usage records for this subscription (Sponsorship subscriptions "
                               "often don't expose cost data; check the Sponsorship portal)")
        mine = [i for i in items if "/resourcegroups/np-explorer" in (i.get("instanceId") or "").lower()]
        return round(sum(float(i.get("pretaxCost") or 0) for i in mine), 2)
    try:
        return {"available": True, "yesterday_usd": cost(day, day), "month_to_date_usd": cost(day.replace(day=1), day),
                "scope": "resource groups np-explorer*"}
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as e:
        return {"available": False, "reason": str(e)[:200]}


def manual_inputs(today: date) -> dict | None:
    """Search Console numbers typed into manual_inputs.yml, if updated in the last 14 days."""
    if not MANUAL.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(MANUAL.read_text()) or {}
    except Exception as e:  # noqa: BLE001
        return {"error": f"could not read manual_inputs.yml: {e}"[:200]}
    gsc = data.get("search_console") or {}
    d = gsc.get("date")
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            d = None
    if not isinstance(d, date) or (today - d).days > 14:
        return None
    return {"date": d.isoformat(), **{k: gsc.get(k) for k in ("pages_indexed", "clicks", "impressions")}}


# --- assembling --------------------------------------------------------------------------

def usage_since(conn) -> datetime | None:
    """When usage stats started (the oldest event kept)."""
    return conn.execute("SELECT min(ts) AS t FROM events").fetchone()["t"]


def compute(conn, day: date, days: int = 1, light: bool = False) -> dict:
    start, end = window(day, days)
    m = {"window": {"first_day": (day - timedelta(days=days - 1)).isoformat(), "last_day": day.isoformat(),
                    "days": days, "timezone": "America/Chicago"},
         "traffic": traffic(conn, start, end), "searches": searches(conn, start, end),
         "funnel": funnel(conn, start, end), "performance": performance(conn, start, end),
         "crawlers": crawlers(start, end), "messages": messages(conn, start, end)}
    m["nl_usage"] = nl_usage(conn, day) if days == 1 else None
    m["database"] = database_health(conn)
    try:
        from app import explain
        m["explainer_odd_numbers"] = explain.flag_summary(conn, start, end)
    except Exception:  # noqa: BLE001 - table not there yet
        if hasattr(conn, "rollback"):
            conn.rollback()
        m["explainer_odd_numbers"] = None
    try:
        from app import reporters
        m["get_ideas_email"] = reporters.counts(conn, start, end)
    except Exception:  # noqa: BLE001 - tables not there yet
        conn.rollback() if hasattr(conn, "rollback") else None
        m["get_ideas_email"] = None
    if not light:
        m["most_viewed"] = most_viewed(conn, start, end)
        until = min(datetime.now(timezone.utc), end + timedelta(hours=24))
        m["data"] = data_loads(conn, end, until)
        m["azure"] = azure_spend(day)
        m["search_console"] = manual_inputs(datetime.now(CHICAGO).date())
    since = usage_since(conn)
    m["usage_stats_since"] = since.astimezone(CHICAGO).isoformat(timespec="minutes") if since else None
    m["usage_stats_cover_window"] = bool(since) and since < end
    m["core"] = core(m)
    return m


def database_health(conn) -> dict | None:
    """Cache hit rate, database size, the largest tables and the slowest queries (pg_stat_statements: mean time,
    calls; query text trimmed). For the owner (2026-10-21): spot a cold cache or a slow query before visitors do."""
    try:
        hit = conn.execute("""SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2) AS pct
                              FROM pg_stat_database WHERE datname = current_database()""").fetchone()
        size = conn.execute("SELECT pg_database_size(current_database()) AS b").fetchone()
        tables = conn.execute("""SELECT c.relname AS table, pg_total_relation_size(c.oid) AS bytes
                                 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                                 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'm') AND NOT c.relispartition
                                 ORDER BY 2 DESC LIMIT 10""").fetchall()
        slow = conn.execute(r"""SELECT round(mean_exec_time::numeric) AS mean_ms, calls,
                                      left(regexp_replace(query, '\s+', ' ', 'g'), 160) AS query
                               FROM pg_stat_statements WHERE calls >= 5 AND query NOT ILIKE '%pg_prewarm%'
                               ORDER BY mean_exec_time DESC LIMIT 10""").fetchall()
    except Exception:  # noqa: BLE001 - the report must not fail on these
        if hasattr(conn, "rollback"):
            conn.rollback()
        return None
    return {"cache_hit_pct": float(hit["pct"] or 0), "size_gb": round(size["b"] / 1e9, 1),
            "largest_tables_gb": {t["table"]: round(t["bytes"] / 1e9, 1) for t in tables},
            "slowest_queries": [dict(r) for r in slow]}


USAGE_KEYS = ("human_visitors", "new_visitors", "returning_visitors", "sessions", "page_views", "pages_per_session",
              "searches", "nl_searches", "zero_result_searches", "nl_fallback_rate_pct", "visitors_opening_org_pages",
              "visitors_opening_person_pages", "server_5xx", "p95_ms_all", "contact_submissions")


def core(m: dict) -> dict:
    t, s, p, c = m["traffic"], m["searches"], m["performance"], m["crawlers"]
    g = c.get("googlebot", {}) if c.get("available") else {}
    f = {x["step"]: x["visitors"] for x in m["funnel"]}
    return {
        "human_visitors": t["human_visitors"], "new_visitors": t["new_visitors"],
        "returning_visitors": t["returning_visitors"], "sessions": t["sessions"], "page_views": t["page_views"],
        "pages_per_session": t["pages_per_session"], "searches": s["searches"], "nl_searches": s["nl_searches"],
        "zero_result_searches": s["zero_result_searches"], "nl_fallback_rate_pct": s["nl_fallback_rate_pct"],
        "visitors_opening_org_pages": f.get("opened an organization page"),
        "visitors_opening_person_pages": f.get("opened a person page"),
        "googlebot_requests": g.get("requests"), "googlebot_5xx": g.get("5xx"), "googlebot_p95_ms": g.get("p95_ms"),
        "server_5xx": p["server_5xx"], "visitor_429s": p["visitor_429s"], "p95_ms_all": p["p95_ms_all"],
        "nl_cost_usd": (m.get("nl_usage") or {}).get("est_cost_usd"),
        "contact_submissions": m["messages"]["contact_submissions"],
        **{f"get_ideas_{k}": v for k, v in (m.get("get_ideas_email") or {}).items()},
        "db_cache_hit_pct": (m.get("database") or {}).get("cache_hit_pct"),
        "db_size_gb": (m.get("database") or {}).get("size_gb"),
        "explainer_flagged_numbers": (m.get("explainer_odd_numbers") or {}).get("flagged_numbers"),
    } if m.get("usage_stats_cover_window", True) else _blank_usage(m)


def _blank_usage(m: dict) -> dict:
    """A window from before usage stats started: no usage numbers, rather than zeros."""
    m["usage_stats_cover_window"] = True
    c = core(m)
    m["usage_stats_cover_window"] = False
    return {k: (None if k in USAGE_KEYS else v) for k, v in c.items()}


def core_for(conn, day: date) -> dict:
    """A past day's core numbers: from daily_stats, or computed (raw data is kept USAGE_RETENTION_DAYS)."""
    r = conn.execute("SELECT metrics FROM daily_stats WHERE day = %s", (day,)).fetchone()
    if r and "core" in r["metrics"]:
        return r["metrics"]["core"]
    return compute(conn, day, light=True)["core"]


def comparisons(conn, day: date, days: int) -> dict:
    if days == 1:
        prev = core_for(conn, day - timedelta(days=1))
        trailing = [core_for(conn, day - timedelta(days=i)) for i in range(1, TRAILING_DAYS + 1)]
        avg = {}
        for k in prev:
            vals = [t[k] for t in trailing if isinstance(t.get(k), (int, float))]
            avg[k] = round(statistics.mean(vals), 1) if vals else None
        return {"previous_day": prev, "trailing_7_day_avg": avg}
    return {"previous_period": compute(conn, day - timedelta(days=days), days, light=True)["core"],
            "trailing_7_day_avg": None}


# --- the narrative ---------------------------------------------------------------------------

SECTIONS = ["THREE RECOMMENDATIONS", "THE DAY IN FIVE LINES", "WHAT CHANGED", "DID NOT CHANGE",
            "WERE LAST REPORT'S RECOMMENDATIONS ACTED ON", "WHERE USERS GET STUCK", "EXPERIMENTS", "QUESTIONS TO CHECK"]

SYSTEM = f"""You write the daily usage report for furp.org, a free public data explorer built on IRS Form 990 filings. You get a JSON of metrics computed in code.

Rules:
- Cite only numbers and search terms that appear in the JSON. Do not calculate new numbers (no new sums,
  differences or percentages). Rounding a number from the JSON is fine.
- Counts under {LOW} are low confidence: say so whenever you rely on one.
- Say how confident you are in each claim. If the data is thin, say that instead of guessing.
- Plain text only: no markdown, no bullets other than "- ", no bold.
- Output exactly these headings, in this order, each on its own line, with nothing before the first:
{chr(10).join(SECTIONS)}
- THREE RECOMMENDATIONS: exactly three, numbered "1." "2." "3.", each with three lines starting
  "Evidence:", "Change:" and "Next metric:".
- THE DAY IN FIVE LINES: exactly five lines.
- WERE LAST REPORT'S RECOMMENDATIONS ACTED ON: use "previous_report" and "commits_since_previous_report".
  If there is no previous report, say this is the first report.
- QUESTIONS TO CHECK: questions a human should look into, for example odd numbers or missing data.
"""


def _numbers_in(obj, out: set) -> set:
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        out.update(float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _numbers_in(k, out)
            _numbers_in(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers_in(v, out)
    return out


_NUM = re.compile(r"(?<![\w.])\$?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(%?)(?![\w])")


def validate(text: str, facts) -> list[str]:
    """Numbers in the narrative that don't appear in the facts (allowing rounding). Empty list: valid."""
    allowed = _numbers_in(facts, set())
    bad = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[123]\.\s", "", line)             # recommendation numbering
        for m in _NUM.finditer(line):
            whole, frac, is_pct = m.group(1).replace(",", ""), m.group(2), m.group(3)
            x = float(whole + ("." + frac if frac else ""))
            tol = 0.5 * 10 ** -(len(frac) if frac else 0)
            ok = any(abs(x - v) <= tol or (v and abs(x - v) / abs(v) <= 0.005) for v in allowed)
            if not ok and is_pct:
                ok = any(0 <= v <= 1 and abs(x - 100 * v) <= tol for v in allowed)
            if not ok:
                bad.append(m.group(0))
    return bad


def _anthropic(messages: list[dict]) -> str:
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
        "content-type": "application/json"},
        json={"model": NL_REPORT_MODEL, "max_tokens": 6000, "system": SYSTEM, "messages": messages})
    r.raise_for_status()
    body = r.json()
    if body.get("stop_reason") == "max_tokens":
        raise RuntimeError("the narrative hit the token limit and was cut off")
    return "".join(b.get("text", "") for b in body["content"] if b.get("type") == "text").strip()


def narrative(facts: dict, ask=_anthropic) -> tuple[str | None, str]:
    """(text, status): status is 'ok', or why the numbers-only report is used."""
    msgs = [{"role": "user", "content": "Metrics JSON:\n" + json.dumps(facts, default=str, indent=1)}]
    for attempt in (1, 2):
        try:
            text = ask(msgs)
        except Exception as e:  # noqa: BLE001
            log.warning("report: narrative attempt %d failed: %s", attempt, e)
            continue
        missing = [h for h in SECTIONS if h not in text]
        bad = validate(text, facts)
        if not bad and not missing:
            return text, "ok"
        log.warning("report: narrative attempt %d rejected: numbers %s, missing %s", attempt, bad[:10], missing)
        msgs += [{"role": "assistant", "content": text},
                 {"role": "user", "content": "Rewrite it. " + (f"These numbers are not in the JSON: {', '.join(bad[:20])}. "
                                                               if bad else "") +
                  (f"Missing headings: {', '.join(missing)}. " if missing else "") +
                  "Use only numbers from the JSON and every heading in order."}]
    return None, "narrative failed validation twice"


def section(text: str, name: str) -> str:
    i = text.find(name)
    if i < 0:
        return ""
    rest = text[i + len(name):]
    nxt = [rest.find(h) for h in SECTIONS if h != name and rest.find(h) >= 0]
    return rest[:min(nxt)].strip() if nxt else rest.strip()


# --- rendering ---------------------------------------------------------------------------------

def star(v):
    if isinstance(v, bool) or v is None:
        return "-" if v is None else str(v)
    if isinstance(v, int):
        return f"{v:,}*" if v < LOW else f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def table(rows: list[list], header: list[str]) -> str:
    rows = [[str(c) for c in r] for r in [header] + rows]
    w = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = ["  ".join(c.ljust(w[i]) if i == 0 else c.rjust(w[i]) for i, c in enumerate(r)) for r in rows]
    lines.insert(1, "  ".join("-" * x for x in w))
    return "\n".join(lines)


LABELS = {
    "human_visitors": "Human visitors", "new_visitors": "  new", "returning_visitors": "  returning",
    "sessions": "Sessions", "page_views": "Page views", "pages_per_session": "Pages per session",
    "searches": "Searches", "nl_searches": "  natural-language", "zero_result_searches": "  zero results",
    "nl_fallback_rate_pct": "NL fallback rate %", "visitors_opening_org_pages": "Visitors opening org pages",
    "visitors_opening_person_pages": "Visitors opening person pages", "googlebot_requests": "Googlebot requests",
    "googlebot_5xx": "Googlebot 5xx", "googlebot_p95_ms": "Googlebot p95 ms", "server_5xx": "Server 5xx",
    "visitor_429s": "Rate-limited (429) visitor requests", "p95_ms_all": "p95 response ms (all)",
    "nl_cost_usd": "NL search cost $", "contact_submissions": "Contact form submissions",
}


def numbers_table(cur: dict, comp: dict) -> str:
    prev = comp.get("previous_day") or comp.get("previous_period") or {}
    avg = comp.get("trailing_7_day_avg") or {}
    head = ["Metric", "Day", "Day before" if "previous_day" in comp else "Previous period", "7-day avg"]
    rows = [[LABELS.get(k, k), star(cur.get(k)), star(prev.get(k)), star(avg.get(k))] for k in LABELS]
    return table(rows, head) + f"\n* under {LOW}: low confidence."


def pairs(items, label="") -> str:
    if not items:
        return "  (none)"
    return "\n".join(f"  {star(n):>8}  {k}" for k, n in items)


def details(m: dict) -> str:
    t, s, p, c, d = m["traffic"], m["searches"], m["performance"], m["crawlers"], m.get("data") or {}
    out = ["TRAFFIC (humans)",
           f"  {star(t['human_visitors'])} visitors ({star(t['new_visitors'])} new, {star(t['returning_visitors'])} returning), "
           f"{star(t['sessions'])} sessions, {star(t['page_views'])} page views, {star(t['pages_per_session'])} pages per session",
           "Top referrers:", pairs(t["top_referrers"]), "Top landing pages:", pairs(t["top_landing_pages"]),
           "Countries (visitors):", pairs(t["countries"]),
           "", "BOTS AND CRAWLERS",
           "  App requests by class: " + (", ".join(f"{k} {star(v)}" for k, v in t["bot_requests_by_class"].items()) or "none")]
    if c.get("available"):
        for b in ("googlebot", "bingbot"):
            x = c[b]
            out.append(f"  {b} (reverse-DNS verified): {star(x['requests'])} requests, 4xx {star(x['4xx'])} "
                       f"(429 {star(x['429'])}), 5xx {star(x['5xx'])}, p50 {star(x['p50_ms'])} ms, p95 {star(x['p95_ms'])} ms")
        out.append(f"  Fake Googlebot/Bingbot claims: {star(c['fake_claims'])}")
    else:
        out.append(f"  Crawler log: not available ({c.get('reason')})")
    out += ["", "SEARCHES",
            f"  {star(s['searches'])} searches: {star(s['plain_searches'])} plain/name, {star(s['nl_searches'])} natural-language; "
            f"{star(s['zero_result_searches'])} with zero results; p50 {star(s['search_p50_ms'])} ms, p95 {star(s['search_p95_ms'])} ms",
            "  By type: " + (", ".join(f"{k} {star(v)}" for k, v in s["by_type"].items()) or "none"),
            f"  NL fallbacks {star(s['nl_fallbacks'])} ({star(s['nl_fallback_rate_pct'])}%), daily cap hits {star(s['nl_cap_hits'])}",
            "  NL intents: " + (", ".join(f"{k} {star(v)}" for k, v in s["nl_intents"].items()) or "none"),
            "Top searches:", pairs(s["top_searches"]), "Top zero-result searches:", pairs(s["top_zero_result_searches"])]
    mv = m.get("most_viewed") or {}
    out += ["", "MOST VIEWED", "Organizations:", pairs(mv.get("organizations")), "People:", pairs(mv.get("people"))]
    out += ["", "FUNNEL (visitors; share of the previous step)",
            table([[x["step"], star(x["visitors"]), "-" if x["share_of_previous_pct"] is None else f"{x['share_of_previous_pct']}%"]
                   for x in m["funnel"]], ["Step", "Visitors", "Share"])]
    out += ["", "PERFORMANCE",
            table([[k, star(v["requests"]), star(v["p50_ms"]), star(v["p95_ms"])] for k, v in p["by_route"].items()],
                  ["Route", "Requests", "p50 ms", "p95 ms"]) if p["by_route"] else "  (no requests recorded)",
            f"  5xx {star(p['server_5xx'])}, statement timeouts {star(p['statement_timeouts'])}, "
            f"rate-limited visitor requests (429) {star(p['visitor_429s'])}",
            f"  Database {p['database_gb']} GB; disk " + ", ".join(f"{k} {v['used_pct']}% used, {v['free_gb']} GB free"
                                                               for k, v in p["disk"].items())]
    nl = m.get("nl_usage")
    if nl:
        out += ["", "NATURAL-LANGUAGE SEARCH COST",
                f"  {star(nl['calls'])} model calls, {star(nl['cache_hits'])} cache hits, {star(nl['fallbacks'])} fallbacks; "
                f"{nl['input_tokens']:,} input and {nl['output_tokens']:,} output tokens; estimated ${nl['est_cost_usd']:.2f}"]
    if d:
        out += ["", "DATA (last night's loaders)",
                "  " + ("succeeded" if d["nightly_succeeded"] else "did not finish cleanly" if d["nightly_succeeded"] is False
                        else "no nightly run found in the window"),
                *(f"  {r['kind']} {r['status']}: {r['files']} files, {r['rows']:,} rows" for r in d["loads"]),
                *(f"  error in {e['file']}: {e['error']}" for e in d["errors"]),
                "  Totals (estimated): " + ", ".join(f"{k} {v:,}" for k, v in sorted(d["totals_estimated"].items()))]
    msg = m["messages"]
    out += ["", "MESSAGES",
            f"  Contact form: {star(msg['contact_submissions'])}" + (" (" + ", ".join(f"{k} {star(v)}" for k, v in msg['by_topic'].items()) + ")" if msg["by_topic"] else ""),
            f"  Removal requests (topic '{REMOVAL_TOPIC}'): {star(msg['removal_requests'])}; status {msg['removal_status']}"]
    az = m.get("azure") or {}
    out += ["", "AZURE SPEND", f"  Yesterday ${az['yesterday_usd']}, month to date ${az['month_to_date_usd']} ({az['scope']})"
            if az.get("available") else f"  Not available: {az.get('reason')}"]
    gsc = m.get("search_console")
    out += ["", "GOOGLE SEARCH CONSOLE (manual_inputs.yml)",
            f"  As of {gsc['date']}: pages indexed {gsc.get('pages_indexed')}, clicks {gsc.get('clicks')}, "
            f"impressions {gsc.get('impressions')}" if gsc and "error" not in gsc else
            f"  {gsc['error']}" if gsc else "  Not entered in the last 14 days."]
    return "\n".join(out)


def render(m: dict, comp: dict, text: str | None, status: str, notes: list[str]) -> str:
    w = m["window"]
    title = f"FURP.ORG DAILY: {w['last_day']}" if w["days"] == 1 else \
        f"FURP.ORG WEEKLY: {w['first_day']} to {w['last_day']}"
    if not m.get("usage_stats_cover_window"):
        notes = [f"Note: usage stats started {m.get('usage_stats_since') or 'after this window'}; this window "
                 "has no usage data, so traffic, search and funnel numbers are zero or blank.", *notes]
    head = [title, f"Window: {w['first_day']} to {w['last_day']} ({w['days']} day{'s' if w['days'] != 1 else ''}), "
                   f"America/Chicago. Compared with the {'day before and the trailing 7-day average' if w['days'] == 1 else 'previous period'}.",
            "Humans and bots are reported separately; internal traffic and the dev box are excluded.", *notes]
    numbers = "THE NUMBERS\n" + numbers_table(m["core"], comp) + "\n\n" + details(m)
    if text:
        q = text.find("QUESTIONS TO CHECK")
        body = text[:q].rstrip() + "\n\n" + numbers + "\n\n" + text[q:].strip() if q >= 0 else text + "\n\n" + numbers
    else:
        body = f"Numbers only: the narrative was not used ({status}).\n\n" + numbers
    return "\n".join(head) + "\n\n" + body + "\n"


def to_html(text: str) -> str:
    return ('<!doctype html><html><body style="margin:0;background:#fff;color:#000">'
            '<pre style="font-family:\'Courier New\',Courier,monospace;font-size:13px;line-height:1.45;'
            'white-space:pre-wrap;color:#000;background:#fff;padding:16px;max-width:900px">'
            + html.escape(text) + "</pre></body></html>")


def send(subject: str, text: str, html_body: str) -> tuple[bool, str]:
    """Postmark, retried once. A sender-signature error retries from INFO_EMAIL."""
    token = os.environ.get("POSTMARK_SERVER_TOKEN")
    if not token:
        return False, "POSTMARK_SERVER_TOKEN is not set"
    sender, err = REPORT_FROM, ""
    for attempt in (1, 2):
        try:
            r = httpx.post("https://api.postmarkapp.com/email", timeout=30, headers={
                "X-Postmark-Server-Token": token, "Accept": "application/json", "Content-Type": "application/json"},
                json={"From": sender, "To": REPORT_TO, "Subject": subject, "TextBody": text, "HtmlBody": html_body,
                      "MessageStream": "outbound"})
            if r.status_code == 200:
                return True, f"sent from {sender}"
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            err = f"HTTP {r.status_code} code {body.get('ErrorCode')}: {str(body.get('Message'))[:200]}"
            if "signature" in str(body.get("Message", "")).lower():
                from app import mailer
                sender = mailer.fallback({"From": sender})["From"] if sender.endswith("@" + mailer.SEND_DOMAIN) \
                    else INFO_EMAIL
        except httpx.HTTPError as e:
            err = f"{type(e).__name__}: {e}"[:200]
        log.warning("report: send attempt %d failed: %s", attempt, err)
    return False, err


def previous_report(conn, day: date) -> dict | None:
    r = conn.execute("""SELECT day, created_at, recommendations FROM report_history WHERE day < %s
                        ORDER BY day DESC LIMIT 1""", (day,)).fetchone()
    return dict(r) if r else None


def commits_since(when: datetime | None) -> list[str]:
    args = ["git", "-C", str(ROOT), "log", "--no-merges", "--format=%h %s"]
    args += [f"--since={when.isoformat()}"] if when else ["-20"]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30).stdout.strip().splitlines()[:60]
    except (OSError, subprocess.SubprocessError):
        return []
