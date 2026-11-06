"""Reclassify bot traffic that passed as human (owner, 2026-11-06), from nginx's access log.

The app's filter sees one request at a time; the log shows the pattern. Four rules, no model calls:
  1. An IP with a browser user agent that asks for PAGE_LIMIT or more pages in one day is a scraper (a reader opens
     a few pages, a scraper hundreds).
  2. Every IP in a /24 where NET_LIMIT or more IPs were flagged (the Alibaba Cloud Singapore cluster of 2026-11-05:
     430 IPs, 35-80 pages each, fake google.com referrers).
  3. A request whose Referer is exactly the bare origin ("https://furp.org", no slash): no browser sends that; the
     distributed scraper of 2026-10-25 to 2026-11-04 (hundreds of thousands of IPs, one request each) did, until
     nginx started refusing it on 2026-11-04.
  4. On a botnet day only (more than OWN_REF_BOTNET such IPs): an IP whose one to three requests all claim a
     furp.org page as referrer, though it never fetched one (the same scraper's other disguise: 206,931 IPs on
     2026-10-26 against 559 on a quiet day, so the rule stays off on quiet days).
Their page events are re-marked ua_class 'headless', their visitor ids dropped, and daily_stats recomputed, so the
report and its 7-day average count people.

Usage:  .venv/bin/python scripts/reclass_bots.py --days 14          # the last 14 Chicago days (yesterday back)
        .venv/bin/python scripts/reclass_bots.py --days 1 --dry-run  # what would change, no writes
Runs nightly for yesterday from scripts/nightly.sh. Needs the nginx logs on this host (prod)."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import analytics  # noqa: E402

NGINX = Path("/var/log/nginx")
CHICAGO = ZoneInfo("America/Chicago")
PAGE_LIMIT = 25          # browser-UA page requests from one IP in one day
NET_LIMIT = 8            # flagged IPs in one /24: the whole /24 is a scraper
OWN_REF_BOTNET = 5000    # IPs whose only requests claim an own-site referrer: above this, a botnet day
OWN_REF_MAX = 3          # ... and such an IP made at most this many requests
BARE_REFS = {"https://furp.org", "http://furp.org"}
OWN_REF = re.compile(r"^https?://(www\.)?furp\.org/")
LINE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "(?:GET|HEAD) ([^ "]+)[^"]*" (\d{3}) \S+ "([^"]*)" "([^"]*)"')
STATIC = re.compile(r"^/static/|\.(png|css|js|ico|txt|xml|csv|json)$")


def parse(line: str):
    m = LINE.match(line)
    if not m:
        return None
    ip, when, target, status, ref, ua = m.groups()
    path = target.split("?", 1)[0]
    if STATIC.search(path):
        return None
    try:
        ts = datetime.strptime(when, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    return {"ip": ip, "ts": ts, "path": path[:300], "status": int(status), "ua": ua, "ref": ref}


def log_files(days: int):
    """Every access log that could hold the window (by modification time)."""
    cutoff = (datetime.now(CHICAGO) - timedelta(days=days + 1)).timestamp()
    return sorted(p for p in NGINX.glob("access.log*") if p.stat().st_mtime >= cutoff)


def read(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        yield from f


def scan(days: int, today: date | None = None) -> dict[date, dict]:
    """Per Chicago day in the window: per_ip (browser-UA page requests), own_only (IPs whose requests all claim an
    own-site referrer, with their counts), and lines (ip, ts, path, bare referrer?)."""
    today = today or datetime.now(CHICAGO).date()
    first, last = today - timedelta(days=days), today - timedelta(days=1)
    out: dict[date, dict] = defaultdict(lambda: {"per_ip": Counter(), "own": Counter(), "lines": []})
    for f in log_files(days):
        for raw in read(f):
            r = parse(raw)
            if not r or r["status"] >= 400 or analytics.classify_ua(r["ua"]) != "human":
                continue
            d = r["ts"].astimezone(CHICAGO).date()
            if not first <= d <= last:
                continue
            day = out[d]
            day["per_ip"][r["ip"]] += 1
            if OWN_REF.match(r["ref"]):
                day["own"][r["ip"]] += 1
            day["lines"].append((r["ip"], r["ts"], r["path"], r["ref"] in BARE_REFS))
    return out


def flagged_ips(per_ip: Counter, own: Counter | None = None) -> tuple[set[str], set[str], int]:
    """(flagged IPs, /24 networks with NET_LIMIT or more of them, IPs flagged by the own-referrer rule)."""
    ips = {ip for ip, n in per_ip.items() if n >= PAGE_LIMIT}
    nets = Counter(ip.rsplit(".", 1)[0] for ip in ips if ip.count(".") == 3)
    bad_nets = {net for net, n in nets.items() if n >= NET_LIMIT}
    ips |= {ip for ip in per_ip if ip.count(".") == 3 and ip.rsplit(".", 1)[0] in bad_nets}
    own_only = {ip for ip, n in (own or {}).items() if n == per_ip[ip] and n <= OWN_REF_MAX}
    n_own = 0
    if len(own_only) > OWN_REF_BOTNET:
        n_own = len(own_only - ips)
        ips |= own_only
    return ips, bad_nets, n_own


def reclassify(conn, day: date, lines, ips: set[str], dry_run: bool) -> int:
    """Mark the day's events from the flagged IPs and the bare-referrer requests: matched by second and path (the
    app records the request's end, nginx logs it a moment later), ua_class 'headless', no visitor id. Returns the
    rows changed (the rows to change, on a dry run)."""
    rows = [(ts, path) for ip, ts, path, bare in lines if bare or ip in ips]
    if not rows or dry_run:
        return len(rows)
    with conn.transaction():
        conn.execute("CREATE TEMP TABLE bot_hits (t timestamptz, path text) ON COMMIT DROP")
        with conn.cursor().copy("COPY bot_hits (t, path) FROM STDIN") as cp:
            for ts, path in rows:
                cp.write_row((ts, path))
        conn.execute("CREATE INDEX ON bot_hits (path, t)")
        n = conn.execute("""
            UPDATE events e SET ua_class = 'headless', visitor_id = NULL
            FROM bot_hits b
            WHERE e.ua_class = 'human' AND e.path = b.path AND e.ts >= b.t - interval '1 second'
              AND e.ts < b.t + interval '2 seconds' AND e.ts >= %s AND e.ts < %s""",
            (datetime.combine(day, datetime.min.time(), CHICAGO), datetime.combine(day + timedelta(days=1), datetime.min.time(), CHICAGO))).rowcount
    return n


def recompute_daily(conn, day: date) -> dict | None:
    """daily_stats for the day: the core numbers recomputed from the reclassified events (the full metrics stay)."""
    from app import report
    core = report.compute(conn, day, light=True)["core"]
    r = conn.execute("SELECT metrics FROM daily_stats WHERE day = %s", (day,)).fetchone()
    if r:
        metrics = {**r["metrics"], "core": core, "reclassified_at": datetime.now(CHICAGO).isoformat(timespec="minutes")}
        conn.execute("UPDATE daily_stats SET metrics = %s, computed_at = now() WHERE day = %s",
                     (json.dumps(metrics, default=str), day))
        conn.commit()
    return core


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not NGINX.exists():
        print("no nginx logs here; run on the server that serves the site")
        return 2
    from app import report
    days = scan(args.days)
    with report.connect() as conn:
        for day in sorted(days):
            d = days[day]
            ips, nets, n_own = flagged_ips(d["per_ip"], d["own"])
            bare = sum(1 for _, _, _, b in d["lines"] if b)
            n = reclassify(conn, day, d["lines"], ips, args.dry_run)
            line = (f"{day}: {len(d['per_ip']):,} browser IPs; flagged {len(ips):,} IPs ({len(nets)} /24 networks, "
                    f"{n_own:,} by the own-referrer rule) and {bare:,} bare-referrer requests; "
                    f"{n:,} events {'would be ' if args.dry_run else ''}re-marked")
            if not args.dry_run and n:
                core = recompute_daily(conn, day)
                line += f"; human visitors now {core['human_visitors']:,}" if core else ""
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
