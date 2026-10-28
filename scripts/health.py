"""Nightly site check and repair (cron, deploy/cron/np-health, midnight US Eastern; production). Owner, 2026-10-23: "checks and
repairs all the core parts of the site, reporting in email any errors, what they were and if they were fixed".

1. Check every core part: the app, the public pages (status, speed, title and the forms and buttons each must
   contain), nginx's fallback pages, the database, disk space, the TLS certificate, the leaderboards, the daily
   insights pool, the daily email, the nightly loads, the sitemap, the cron files and the dev server.
2. Repair what failed, with fixed, known-safe steps only, matched to the kind of failure (owner, 2026-10-28:
   "restart is not a repair for a missing element or a slow query"):
   - process (the app down, 5xx, the server out of memory): restart the app. Only these get a restart.
   - content or speed (a page missing a form or section, a slow page): no restart; reported for a code or data fix.
   - data loads (a nightly loader failed, or a folder or file it needs is missing): create the missing folders and
     log files, retry the load once, and only then escalate.
   - the rest: re-render the fallback pages, rebuild a missing leaderboard or the insights pool, renew the
     certificate, reinstall a cron file, rebuild a missing key index.
   It never edits code, deletes data or deploys.
3. Check everything again, so a repair that broke something else shows up too.
4. Email the report: each problem, what it was, what was tried, and whether it is fixed now. A check failing three
   nights in a row is STUCK: it leads the report and the subject ("1 STUCK"), with the date it was first seen
   (history in STATE).

Usage: .venv/bin/python scripts/health.py [--dry-run] [--no-email] [--no-repair]
  --dry-run   check everything and print what each repair would do; repairs, emails and history are left alone
"""

from __future__ import annotations

import datetime as dt
import filecmp
import html
import json
import os
import re
import shutil
import ssl
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SITE = os.environ.get("HEALTH_SITE", "https://furp.org")     # HEALTH_SITE=https://dev.furp.org to try it on dev
LOCAL = "http://127.0.0.1:8000"
DEV = "https://dev.furp.org"
LOGS = Path("/var/log/np-explorer")
SLOW = 5.0                      # seconds: slower than this is a failure
PY = str(ROOT / ".venv/bin/python")
STATE = LOGS / "health-state.json"     # each failing check: first seen, last seen, nights in a row
STUCK_NIGHTS = 3
MIN_MEMORY = 5                  # percent of memory available; less is a process failure
RETRY_TIMEOUT = 3 * 3600        # seconds: one retry of a failed load
NIGHTLY_MARK = "=== nightly run "   # scripts/nightly.sh writes it first: the latest run is what follows

# (path, title must contain, page must contain each of these). The page contents are the forms, buttons and
# sections each page must keep (CLAUDE.md: never lose a form or section silently).
PAGES = [
    # The approved minimal home page (2026-10-23) links "More ideas" and gives the signup form a second class.
    ("/", "furp.org", ['name="q"', 'id="ideas"', 'href="/today"', 'class="ideas-signup', 'action="/get-ideas"']),
    ("/about", "About", []),
    ("/data", "Data", []),
    ("/support", "Support FURP", ["<form", "<button"]),
    ("/privacy", "Privacy", []),
    ("/terms", "Terms", []),
    ("/search?q=smith", "Search: smith", ['name="q"', "<table"]),
    ("/search?q=hustle+fund", "Search", ["Hustle Fund"]),
    ("/boards", "Leaderboards", ["/boards/top-paid"]),
    ("/boards/top-paid", "", ["<table", "<tbody"]),
    ("/boards/sec-buyback-spenders", "", ["<tbody"]),
    ("/org/943242767", "", ["<h1"]),
    ("/person/49961934", "", ["<h1"]),
    ("/contractor/62137", "", ["<h1"]),
    ("/today", "", ["<li><a"]),
    ("/about/daily", "", ["/today/"]),
    ("/get-ideas", "", ["<form", 'name="email"']),
    ("/contact", "", ["<form"]),
    ("/federal-spending", "", ["<h1"]),
    ("/corporate", "", ["<h1"]),
    ("/corporate/company/12927", "", ['id="buybacks"']),
    ("/corporate/fund/805-9257018350", "", ["<svg"]),
    ("/politics", "", ["<h1"]),
    ("/lobbying", "", ["<h1"]),
    ("/recalls", "", ["<h1"]),
    ("/student-loans", "", ["<h1"]),
    ("/schools/pay", "", ["<h1"]),
    # What the nightly loaders feed (a load that fails quietly shows up as an empty section or board here).
    ("/boards/patents-universities", "", ["<tbody"]),
    ("/boards/pension-commitments", "", ["<tbody"]),
    ("/boards/sec-formd-unregistered-managers", "", ["<tbody"]),
    ("/business", "", ["<h1"]),
    ("/robots.txt", None, ["Sitemap"]),
    ("/sitemap.xml", None, ["<sitemapindex"]),
    ("/static/furp-logo.png", None, []),
]
# nginx serves these when the app is down: they must keep their content too.
KEY_INDEXES = [("person_clusters", "id"), ("person_cluster_members", "person_id"), ("organizations", "ein"),
               ("filings", "id"), ("people", "id"), ("sec_formd", "accession"), ("sec_insider_filings", "accession")]
FALLBACK = {"index.html": ['name="q"'], "about.html": ["<h1"], "data.html": ["<h1"], "privacy.html": ["<h1"],
            "terms.html": ["<h1"], "404.html": ["<h1"], "500.html": ["<h1"]}


# The nightly loads (scripts/nightly.sh): the line it writes when one fails, the command that retries it, and the
# folders and files it needs (created when missing: they are the first thing to check, not the third night).
USPTO_DATA = Path(os.environ.get("USPTO_DATA", Path.home() / "data" / "uspto"))
LOADS = [
    ("irs", "IRS 990 filings", r"irs nightly failed", [PY, "scripts/load.py", "nightly"], ["/data/xml", "/data/raw"]),
    ("irs_status", "IRS exempt status", r"irs status failed", [PY, "-m", "loader.irs_status"], []),
    ("adv", "SEC Form ADV", r"form adv failed", [PY, "-m", "loader.adv"], ["/bulk/adv"]),
    ("adv_monthly", "SEC Form ADV monthly reports", r"form adv monthly failed", [PY, "-m", "loader.adv", "--monthly"], []),
    ("sec_bulk", "SEC insider and Form D data", r"sec refresh failed", [PY, "-m", "loader.sec_bulk", "refresh"],
     ["/data/raw/sec_bulk"]),
    ("buybacks", "Share buybacks", r"buybacks failed", [PY, "-m", "loader.buybacks", "run"], ["/bulk/fsds", "/bulk/form345"]),
    ("registrations", "Securities registration", r"registrations failed", [PY, "-m", "loader.registrations"],
     ["/bulk/bd", "/bulk/iapd"]),
    ("business", "State business registries", r"business registry failed", [PY, "-m", "loader.business_registry"],
     ["/bulk/registry/fl"]),
    ("uspto", "USPTO patents and trademarks", r"uspto refresh failed|uspto [A-Z0-9]+ failed",
     [PY, "-m", "loader.uspto", "refresh"], [str(USPTO_DATA), str(USPTO_DATA / "api_calls.log")]),
    ("pensions", "Public pension reports", r"pensions failed", [PY, "-m", "loader.pensions"], []),
]
# Where a missing file may be created by a repair (never anywhere else).
CREATABLE = ("/data/", "/bulk/", str(Path.home()) + "/", str(LOGS) + "/")
RETRIED: dict[str, tuple[bool, str]] = {}      # load key -> the retry's result, read by the second round of checks


class Check:
    """kind: process (the app or server: the only kind a restart can fix), content, perf, data (a nightly load), or
    infra (the rest)."""

    def __init__(self, key: str, what: str, ok: bool, detail: str = "", repair: str | None = None, arg=None,
                 kind: str = "infra"):
        self.key, self.what, self.ok, self.detail, self.repair, self.arg = key, what, ok, detail, repair, arg
        self.kind = kind


def _get(client: httpx.Client, url: str):
    t = time.time()
    try:
        r = client.get(url, follow_redirects=True, timeout=30)
        return r.status_code, r.text if "text" in r.headers.get("content-type", "") or "xml" in r.headers.get("content-type", "") else "", time.time() - t
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}", time.time() - t


# --- checks -----------------------------------------------------------------------------------------------

def check_pages(client) -> list[Check]:
    out = []
    code, body, secs = _get(client, LOCAL + "/")
    out.append(Check("app", "The app answers on the server", code == 200, f"HTTP {code}, {secs:.1f}s", "restart_app",
                     kind="process"))
    for path, title, must in PAGES:
        code, body, secs = _get(client, SITE + path)
        problems = []
        if code != 200:
            problems.append(f"HTTP {code}")
        if code == 200 and secs > SLOW:
            problems.append(f"slow: {secs:.1f}s")
        if code == 200 and title:
            got = (re.search(r"<title>([^<]*)", body) or [None, ""])[1]
            if title not in got:
                problems.append(f"title is \"{html.unescape(got)[:60]}\"")
        missing = [m for m in must if code == 200 and m not in body]
        if missing:
            problems.append("missing " + ", ".join(missing))
        # Only a page that doesn't answer (5xx, no connection) is a process failure a restart can fix. A missing
        # element or a slow page is content or speed: restarting changes nothing (2026-10-25 to 28: three nights of
        # "restarted the app, still failing").
        if code == 0 or code >= 500:
            kind, fix = "process", "restart_app"
        else:
            kind, fix = ("perf" if problems and all(p.startswith("slow") for p in problems) else "content"), None
        out.append(Check(f"page {path}", f"Page {path}", not problems,
                         "; ".join(problems) or f"{secs:.1f}s", fix, kind=kind))
    code, body, secs = _get(client, DEV + "/")
    out.append(Check("dev", "Dev server (dev.furp.org)", code in (200, 401, 403), f"HTTP {code}", None))
    return out


def check_fallback() -> list[Check]:
    out = []
    for name, must in FALLBACK.items():
        p = ROOT / "public" / name
        if not p.exists():
            out.append(Check(f"fallback {name}", f"Fallback page {name}", False, "missing", "render_static"))
            continue
        text = p.read_text(errors="replace")
        missing = [m for m in must if m not in text]
        old = (time.time() - p.stat().st_mtime) / 86400
        problems = (["missing " + ", ".join(missing)] if missing else []) + ([f"{old:.0f} days old"] if old > 3 else [])
        out.append(Check(f"fallback {name}", f"Fallback page {name}", not problems, "; ".join(problems), "render_static"))
    return out


def check_db() -> list[Check]:
    from loader import db
    out = []
    try:
        t = time.time()
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
            secs = time.time() - t
            out.append(Check("db", "Database connection", secs < 3, f"{secs:.2f}s"))
            long = conn.execute("""SELECT pid, now() - query_start AS age, left(regexp_replace(query, '\\s+', ' ', 'g'), 80)
                                   FROM pg_stat_activity WHERE state = 'active' AND pid <> pg_backend_pid()
                                     AND now() - query_start > interval '2 hours'""").fetchall()
            out.append(Check("db long", "No queries running over 2 hours", not long,
                             "; ".join(f"pid {p} for {a}: {q}" for p, a, q in long)))
            waiting = conn.execute("""SELECT count(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock'
                                      AND now() - query_start > interval '5 minutes'""").fetchone()[0]
            out.append(Check("db locks", "No queries stuck on locks over 5 minutes", waiting == 0, f"{waiting} waiting"))
            # The lookups every page depends on (2026-10-23: a re-cluster dropped person_clusters' key and person
            # pages scanned 15 million rows for hours).
            for table, col in KEY_INDEXES:
                ok = conn.execute("""SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid
                                     AND a.attnum = i.indkey[0] WHERE i.indrelid = %s::regclass AND i.indisunique
                                     AND i.indisvalid AND i.indnatts = 1 AND a.attname = %s""", (table, col)).fetchone()
                out.append(Check(f"index {table}", f"Unique index on {table} ({col})", bool(ok), "" if ok else "missing",
                                 "create_index", (table, col)))
            # Leaderboards: every visible board built.
            from app import boards
            built = {r[0] for r in conn.execute("SELECT slug FROM board_meta").fetchall()}
            missing = [b.slug for b in boards.visible() if b.slug not in built]
            out.append(Check("boards", "Every leaderboard is built", not missing,
                             ("not built: " + ", ".join(missing)) if missing else f"{len(built)} built", "refresh_boards", missing))
            # Daily insights pool.
            from app import ideas
            # Midnight Eastern is also when the next pool is built: the latest pool must be from today or yesterday.
            day, n = conn.execute("""SELECT pool, count(*) FROM home_ideas WHERE pool = (SELECT max(pool) FROM home_ideas)
                                     GROUP BY 1""").fetchone() or (None, 0)
            fresh = day is not None and (ideas.pool_date() - day).days <= 1
            out.append(Check("ideas", f"Daily insights pool ({day})", fresh and n >= 20, f"{n} insights", "refresh_ideas"))
    except Exception as e:  # noqa: BLE001
        out.append(Check("db", "Database connection", False, f"{type(e).__name__}: {e}"))
    return out


def check_server() -> list[Check]:
    out = []
    for mount in ("/", "/bulk"):
        if os.path.exists(mount):
            u = shutil.disk_usage(mount)
            pct = 100 * u.used / u.total
            out.append(Check(f"disk {mount}", f"Disk space on {mount}", pct < 90, f"{pct:.0f}% used", "clean_disk" if mount == "/" else None))
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection(("furp.org", 443), timeout=10) as s, ctx.wrap_socket(s, server_hostname="furp.org") as t:
            end = dt.datetime.strptime(t.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days = (end - dt.datetime.now(dt.UTC).replace(tzinfo=None)).days
        out.append(Check("tls", "TLS certificate", days > 14, f"expires in {days} days", "renew_cert"))
    except Exception as e:  # noqa: BLE001
        out.append(Check("tls", "TLS certificate", False, f"{type(e).__name__}: {e}", "renew_cert"))
    # Cron files: the installed ones match the repository's.
    for f in sorted((ROOT / "deploy/cron").iterdir()):
        live = Path("/etc/cron.d") / f.name
        same = live.exists() and filecmp.cmp(f, live, shallow=False)
        out.append(Check(f"cron {f.name}", f"Cron job {f.name} installed", same, "" if same else "differs from the repository",
                         "install_cron", f))
    # Logs of the night's jobs.
    today = dt.date.today()
    log = LOGS / "get-ideas.log"
    sent = log.exists() and any(f"for {today.isoformat()}" in line or f"for {(today - dt.timedelta(days=1)).isoformat()}" in line
                                for line in log.read_text(errors="replace").splitlines()[-20:])
    out.append(Check("email", "The daily insights email went out", bool(sent), "" if sent else "no send logged for today"))
    out += check_loads()
    # LinkedIn: connected, and not about to expire (reconnecting needs the owner: the connect link).
    exp = int(os.environ.get("LINKEDIN_TOKEN_EXPIRES") or 0)
    left = (exp - time.time()) / 86400
    out.append(Check("linkedin", "LinkedIn connected for the daily post", bool(os.environ.get("LINKEDIN_ACCESS_TOKEN")) and left > 7,
                     "not connected" if not exp else f"expires in {left:.0f} days"))
    sm = Path("/data/sitemaps/sitemap.xml")
    age = (time.time() - sm.stat().st_mtime) / 86400 if sm.exists() else 99
    out.append(Check("sitemap", "Sitemap rebuilt in the last two days", age < 2.5, f"{age:.1f} days old"))
    return out


def check_memory() -> list[Check]:
    try:
        info = {k: int(v.split()[0]) for k, v in (line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())}
        pct = 100 * info["MemAvailable"] / info["MemTotal"]
    except Exception:  # noqa: BLE001 - not Linux
        return []
    return [Check("memory", "Server memory", pct >= MIN_MEMORY, f"{pct:.0f}% available", "restart_app", kind="process")]


def last_run(lines: list[str]) -> list[str]:
    """The latest nightly run's lines: everything after its start mark (older runs' errors are not tonight's)."""
    starts = [i for i, line in enumerate(lines) if line.startswith(NIGHTLY_MARK)]
    return lines[starts[-1]:] if starts else lines[-400:]


def check_loads(log_path: Path | None = None) -> list[Check]:
    """Each nightly load: its folders and files exist, and the latest run didn't fail. Failures go to repair_load
    (create what's missing, retry once, then escalate)."""
    out = []
    for key, name, _, _, needs in LOADS:
        missing = [p for p in needs if not os.path.exists(p)]
        out.append(Check(f"files {key}", f"Folders and files for {name}", not missing,
                         ("missing " + ", ".join(missing)) if missing else "", "create_paths" if missing else None,
                         missing, kind="data"))
    nl = log_path or LOGS / "nightly.log"
    if not nl.exists():
        return out + [Check("nightly", "The nightly data loads", False, f"{nl} missing", kind="data")]
    age = (time.time() - nl.stat().st_mtime) / 3600
    out.append(Check("nightly", "The nightly data loads ran", age < 30, f"log not written for {age:.0f} hours"
                     if age >= 30 else f"last written {age:.0f} hours ago", kind="data"))
    run = last_run(nl.read_text(errors="replace").splitlines())
    claimed = set()
    for key, name, fail_re, cmd, _ in LOADS:
        bad = [line for line in run if re.search(fail_re, line)]
        claimed.update(bad)
        if key in RETRIED and RETRIED[key][0]:
            out.append(Check(f"load {key}", f"Nightly load: {name}", True, "failed in the nightly run; " + RETRIED[key][1],
                             kind="data"))
            continue
        missing = sorted({m for line in bad for m in re.findall(r"No such file or directory: '([^']+)'", line)})
        out.append(Check(f"load {key}", f"Nightly load: {name}", not bad, "; ".join(bad[-3:])[:600],
                         "retry_load" if bad else None, (key, cmd, missing), kind="data"))
    # Errors no load claims (a traceback with no "... failed" line): reported, not retried.
    other = [line for line in run if re.search(r"\bfailed\b|^Traceback|Error:", line) and line not in claimed
             and "render_static failed" not in line]
    out.append(Check("load other", "Nightly loads: other errors", not other, "; ".join(other[-3:])[:600], kind="data"))
    out.append(Check("render_static", "Nightly fallback page render", not any("render_static failed" in x for x in run),
                     "render_static failed", "render_static"))
    return out


def run_checks() -> list[Check]:
    with httpx.Client(headers={"User-Agent": "furp-health-check"}) as client:
        return check_pages(client) + check_memory() + check_fallback() + check_db() + check_server()


# --- repairs ------------------------------------------------------------------------------------------------

def _sh(cmd: list[str], timeout: int = 1800) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-300:]
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _creatable(p: str) -> bool:
    return os.path.abspath(p).startswith(CREATABLE)


def create_paths(paths) -> tuple[bool, str]:
    """Missing folders, and missing log files (created empty): only under CREATABLE."""
    made, refused = [], []
    for p in paths:
        if os.path.exists(p):
            continue
        if not _creatable(p):
            refused.append(p)
            continue
        path = Path(p)
        if path.suffix in (".log", ".txt", ".json", ".csv"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        else:
            path.mkdir(parents=True, exist_ok=True)
        made.append(p)
    msg = (("created " + ", ".join(made)) if made else "nothing to create") + \
          (("; not allowed to create " + ", ".join(refused)) if refused else "")
    return not refused, msg


def repair_load(key: str, cmd: list[str], missing: list[str]) -> tuple[bool, str]:
    """A failed nightly load: create what it was missing, retry it once (output in health-retries.log)."""
    steps = []
    if missing:
        ok, msg = create_paths(missing)
        steps.append(msg)
    t = time.time()
    try:
        with open(LOGS / "health-retries.log", "a") as f:
            f.write(f"=== {dt.datetime.now():%Y-%m-%d %H:%M} retry {key}: {' '.join(cmd[1:])}\n")
            f.flush()
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            r = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=RETRY_TIMEOUT, env=env)
        ok = r.returncode == 0
        steps.append(f"retried the load: {'done' if ok else f'failed again (exit {r.returncode})'} in "
                     f"{(time.time() - t) / 60:.0f} min")
    except Exception as e:  # noqa: BLE001
        ok = False
        steps.append(f"retry failed: {type(e).__name__}: {e}")
    if not ok:
        steps.append("escalated: needs a person (see health-retries.log)")
    RETRIED[key] = (ok, "; ".join(steps))
    return ok, "; ".join(steps)


def describe(c: Check) -> str:
    """What the repair for this check would do (for --dry-run and the report)."""
    if not c.repair:
        if c.kind in ("content", "perf"):
            return (f"none: a {'speed' if c.kind == 'perf' else 'content'} problem; a restart would not fix it, "
                    "so it needs a code or data fix")
        return "none available, needs a person"
    if c.repair == "retry_load":
        key, cmd, missing = c.arg
        return (f"create {', '.join(missing)}, then " if missing else "") + \
            f"retry the load once ({' '.join(cmd[1:])}), then escalate if it fails again"
    arg = c.arg
    if c.repair == "refresh_boards":
        return f"rebuild boards {', '.join(arg or [])}"
    if c.repair == "install_cron":
        return f"reinstall /etc/cron.d/{arg.name}"
    if c.repair == "create_index":
        return f"build the unique index on {arg[0]} ({arg[1]})"
    if c.repair == "create_paths":
        return f"create {', '.join(arg or [])}"
    return {"restart_app": "restart the app (a process failure)", "render_static": "re-render the fallback pages",
            "refresh_ideas": "rebuild today's insights pool", "renew_cert": "renew the TLS certificate",
            "clean_disk": "trim old system logs and temporary files"}.get(c.repair, c.repair)


def repair(name: str, arg=None) -> tuple[bool, str]:
    if name == "create_paths":
        return create_paths(arg or [])
    if name == "retry_load":
        return repair_load(*arg)
    if name == "restart_app":
        ok, out = _sh(["sudo", "systemctl", "restart", "np-explorer"], 120)
        for _ in range(12):
            time.sleep(5)
            try:
                if httpx.get(LOCAL + "/", timeout=10).status_code == 200:
                    return True, "restarted the app"
            except Exception:  # noqa: BLE001
                pass
        return False, "restarted the app, but it still doesn't answer: " + out
    if name == "render_static":
        ok, out = _sh(["sh", "-c", f"set -a; . ./.env; set +a; {PY} scripts/render_static.py"], 300)
        return ok, "re-rendered the fallback pages" if ok else out
    if name == "refresh_boards":
        from app.boards import BY_SLUG
        from loader import db
        from loader.boards import refresh_board
        done = []
        for slug in arg or []:
            with db.connect() as conn:
                refresh_board(conn, BY_SLUG[slug])
                conn.commit()
            done.append(slug)
        return True, "rebuilt " + ", ".join(done)
    if name == "refresh_ideas":
        ok, out = _sh([PY, "-m", "app.ideas", "refresh"], 1800)
        return ok, "rebuilt today's insights pool" if ok else out
    if name == "renew_cert":
        ok, out = _sh(["sudo", "certbot", "renew", "--quiet"], 600)
        if ok:
            _sh(["sudo", "systemctl", "reload", "nginx"], 60)
        return ok, "renewed the certificate" if ok else out
    if name == "install_cron":
        ok, out = _sh(["sudo", "install", "-m", "644", str(arg), f"/etc/cron.d/{arg.name}"], 60)
        return ok, f"reinstalled /etc/cron.d/{arg.name}" if ok else out
    if name == "create_index":
        import psycopg
        from app.config import DATABASE_URL
        table, col = arg
        try:
            with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
                conn.execute("SET maintenance_work_mem = '2GB'")
                conn.execute(f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {table}_{col}_key_repair ON {table} ({col})")
            return True, f"built the unique index on {table} ({col})"
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"
    if name == "clean_disk":
        _sh(["sudo", "journalctl", "--vacuum-time=14d"], 300)
        _sh(["sudo", "find", "/tmp", "-type", "f", "-mtime", "+7", "-delete"], 300)
        return True, "trimmed system logs over 14 days old and temporary files over 7 days old"
    return False, "no repair for this"


def rkey(c: Check) -> str:
    if isinstance(c.arg, Path):
        return f"{c.repair} {c.arg.name}"
    if c.repair == "retry_load":
        return f"retry_load {c.arg[0]}"
    if c.repair == "create_paths":
        return f"create_paths {','.join(c.arg)}"
    return f"{c.repair} {'.'.join(c.arg)}" if isinstance(c.arg, tuple) else str(c.repair)


# --- history: how many nights in a row each check has failed --------------------------------------------------------

def load_state(path: Path = STATE) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 - first run, or unreadable: start over
        return {}


def update_state(state: dict, failing: list[Check], today: dt.date) -> dict:
    """{check key: {first, last, nights, what}} for the checks failing now. A check failing again the next night adds
    a night; a gap of more than one night starts over; a second run on the same day changes nothing."""
    out = {}
    for c in failing:
        prev = state.get(c.key)
        last = dt.date.fromisoformat(prev["last"]) if prev else None
        if prev and last == today:
            out[c.key] = prev
        elif prev and (today - last).days == 1:
            out[c.key] = {**prev, "last": today.isoformat(), "nights": prev["nights"] + 1, "what": c.what}
        else:
            out[c.key] = {"first": today.isoformat(), "last": today.isoformat(), "nights": 1, "what": c.what}
    return out


def seed_state(failing: list[Check], today: dt.date) -> dict:
    """No history yet: rebuild it from the nightly site-check notices already sent (owner_notices), so problems that
    were failing before the history existed count their nights from when they started."""
    try:
        import psycopg
        from app.config import DATABASE_URL
        with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
            rows = conn.execute("""SELECT created::date, body FROM owner_notices WHERE topic = 'Site check'
                                   AND created > now() - interval '30 days' ORDER BY created DESC""").fetchall()
    except Exception:  # noqa: BLE001
        return {}
    by_day: dict[dt.date, str] = {}
    for day, body in rows:
        by_day.setdefault(day, "")
        by_day[day] += body
    out = {}
    for c in failing:
        nights, day = 0, today - dt.timedelta(days=1)
        while f"- {c.what}:" in by_day.get(day, "") or f"- NEW after repairs: {c.what}:" in by_day.get(day, ""):
            nights, day = nights + 1, day - dt.timedelta(days=1)
        if nights:
            first = today - dt.timedelta(days=nights)
            out[c.key] = {"first": first.isoformat(), "last": (today - dt.timedelta(days=1)).isoformat(),
                          "nights": nights, "what": c.what}
    return out


def save_state(state: dict, path: Path = STATE) -> None:
    try:
        path.write_text(json.dumps(state, indent=1, sort_keys=True))
    except OSError:
        print(f"could not write {path}")


# --- report -------------------------------------------------------------------------------------------------

def report(first: list[Check], repairs: dict, second: list[Check], history: dict | None = None,
           dry_run: bool = False) -> tuple[str, str]:
    history = history or {}
    after = {c.key: c for c in second}
    failed = [c for c in first if not c.ok]
    new = [c for c in second if not c.ok and c.key not in {f.key for f in failed}]
    still = [c for c in failed if not after.get(c.key, c).ok]
    stuck = [c for c in still + new if history.get(c.key, {}).get("nights", 0) >= STUCK_NIGHTS]
    # STUCK first, oldest first, then the rest in check order.
    failed.sort(key=lambda c: (c not in stuck, history.get(c.key, {}).get("first", "9999")))
    if not failed and not new:
        subject = f"Site check, all {len(first)} checks passed"
    else:
        subject = (f"Site check, {len(failed)} problem{'s' if len(failed) != 1 else ''}, "
                   + (f"{len(plan(failed))} repairs planned (dry run)" if dry_run else
                      f"{len(failed) - len(still)} fixed, {len(still) + len(new)} still open"))
    if stuck:
        since = min(history[c.key]["first"] for c in stuck)
        subject = f"{len(stuck)} STUCK since {since}, " + subject
    lines = [("DRY RUN: nothing repaired, emailed or recorded. " if dry_run else "") + subject, ""]
    for c in failed:
        a = after.get(c.key, c)
        fix = repairs.get(rkey(c))
        h = history.get(c.key)
        tag = (f"STUCK, failing {h['nights']} nights in a row since {h['first']}: " if c in stuck else
               f"(failing {h['nights']} nights in a row since {h['first']}) " if h and h["nights"] > 1 else "")
        lines.append(f"- {tag}{c.what}: {c.detail or 'failed'}  [{c.kind}]")
        if dry_run:
            lines.append("  Would repair: " + describe(c))
            continue
        lines.append("  Repair: " + (("done: " if fix[0] else "tried, failed: ") + fix[1] if fix else describe(c)
                                     if not c.repair else "not attempted"))
        lines.append(f"  Now: {'FIXED' if a.ok else 'STILL FAILING: ' + (a.detail or 'failed')}")
    for c in new:
        lines.append(f"- NEW after repairs: {c.what}: {c.detail or 'failed'}")
    if failed or new:
        lines.append("")
    lines.append(f"Checked: {len(first)} items (app, {len(PAGES)} pages, memory, fallback pages, database, leaderboards, "
                 f"insights pool, email, {len(LOADS)} nightly loads and their files, sitemap, disk, certificate, cron, "
                 f"dev server).")
    passed = [c.what for c in second if c.ok]
    lines.append(f"Passing now: {len(passed)} of {len(second)}.")
    return subject, "\n".join(lines) + "\n"


def plan(checks: list[Check]) -> list[Check]:
    """The failing checks to repair, each repair once (one restart for many pages). A restart only for process
    failures, whatever repair a check names."""
    out, seen = [], set()
    for c in checks:
        if c.ok or not c.repair or rkey(c) in seen:
            continue
        if c.repair == "restart_app" and c.kind != "process":
            continue
        seen.add(rkey(c))
        out.append(c)
    return out


def main() -> int:
    from app import mailer
    from app.config import REPORT_FROM, REPORT_TO
    dry = "--dry-run" in sys.argv
    today = dt.date.today()
    first = run_checks()
    repairs: dict[str, tuple[bool, str]] = {}
    if not dry and "--no-repair" not in sys.argv:
        for c in plan(first):
            repairs[rkey(c)] = repair(c.repair, c.arg)
        if repairs:
            time.sleep(20)
    second = run_checks() if repairs else first
    state = load_state()
    failing = [c for c in second if not c.ok]
    history = update_state(state or seed_state(failing, today), failing, today)
    subject, text = report(first, repairs, second, history, dry_run=dry)
    print(text)
    if dry:
        return 0
    save_state(history)
    if "--no-email" not in sys.argv:
        ok = mailer.notify_owner("Site check", subject, text) or mailer.send({"From": REPORT_FROM, "To": REPORT_TO, "Subject": mailer.report_subject(subject), "TextBody": text,
                          "MessageStream": "outbound"})
        print("emailed" if ok else "email failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
