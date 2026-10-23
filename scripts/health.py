"""Nightly site check and repair (cron, deploy/cron/np-health; production). Owner, 2026-10-23: "checks and
repairs all the core parts of the site, reporting in email any errors, what they were and if they were fixed".

1. Check every core part: the app, the public pages (status, speed, title and the forms and buttons each must
   contain), nginx's fallback pages, the database, disk space, the TLS certificate, the leaderboards, the daily
   insights pool, the daily email, the nightly loads, the sitemap, the cron files and the dev server.
2. Repair what failed, with fixed, known-safe steps only (restart the app, re-render the fallback pages, rebuild a
   missing leaderboard, rebuild the insights pool, renew the certificate, reinstall a cron file). It never edits
   code, deletes data or deploys.
3. Check everything again, so a repair that broke something else shows up too.
4. Email the report: each problem, what it was, what was tried, and whether it is fixed now.

Usage: .venv/bin/python scripts/health.py [--no-email] [--no-repair]
"""

from __future__ import annotations

import datetime as dt
import filecmp
import html
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
SITE = "https://furp.org"
LOCAL = "http://127.0.0.1:8000"
DEV = "https://dev.furp.org"
LOGS = Path("/var/log/np-explorer")
SLOW = 5.0                      # seconds: slower than this is a failure
PY = str(ROOT / ".venv/bin/python")

# (path, title must contain, page must contain each of these). The page contents are the forms, buttons and
# sections each page must keep (CLAUDE.md: never lose a form or section silently).
PAGES = [
    ("/", "furp.org", ['name="q"', 'id="ideas"', "More insights", 'class="ideas-signup"']),
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
    ("/robots.txt", None, ["Sitemap"]),
    ("/sitemap.xml", None, ["<sitemapindex"]),
    ("/static/furp-logo.png", None, []),
]
# nginx serves these when the app is down: they must keep their content too.
FALLBACK = {"index.html": ['name="q"'], "about.html": ["<h1"], "data.html": ["<h1"], "privacy.html": ["<h1"],
            "terms.html": ["<h1"], "404.html": ["<h1"], "500.html": ["<h1"]}


class Check:
    def __init__(self, key: str, what: str, ok: bool, detail: str = "", repair: str | None = None, arg=None):
        self.key, self.what, self.ok, self.detail, self.repair, self.arg = key, what, ok, detail, repair, arg


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
    out.append(Check("app", "The app answers on the server", code == 200, f"HTTP {code}, {secs:.1f}s", "restart_app"))
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
        out.append(Check(f"page {path}", f"Page {path}", not problems,
                         "; ".join(problems) or f"{secs:.1f}s", "restart_app"))
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
            # Leaderboards: every visible board built.
            from app import boards
            built = {r[0] for r in conn.execute("SELECT slug FROM board_meta").fetchall()}
            missing = [b.slug for b in boards.visible() if b.slug not in built]
            out.append(Check("boards", "Every leaderboard is built", not missing,
                             ("not built: " + ", ".join(missing)) if missing else f"{len(built)} built", "refresh_boards", missing))
            # Daily insights pool.
            from app import ideas
            day = ideas.pool_date()
            n = conn.execute("SELECT count(*) FROM home_ideas WHERE pool = %s", (day,)).fetchone()[0]
            out.append(Check("ideas", f"Today's insights pool ({day})", n >= 20, f"{n} insights", "refresh_ideas"))
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
    nl = LOGS / "nightly.log"
    if nl.exists():
        age = (time.time() - nl.stat().st_mtime) / 3600
        tail = nl.read_text(errors="replace").splitlines()[-400:]
        bad = [line for line in tail if re.search(r"\bfailed\b|Traceback|Error:", line)]
        out.append(Check("nightly", "The nightly data loads", age < 30 and not bad,
                         "; ".join(([f"log not written for {age:.0f} hours"] if age >= 30 else []) + bad[-5:])))
    # LinkedIn: connected, and not about to expire (reconnecting needs the owner: the connect link).
    exp = int(os.environ.get("LINKEDIN_TOKEN_EXPIRES") or 0)
    left = (exp - time.time()) / 86400
    out.append(Check("linkedin", "LinkedIn connected for the daily post", bool(os.environ.get("LINKEDIN_ACCESS_TOKEN")) and left > 7,
                     "not connected" if not exp else f"expires in {left:.0f} days"))
    sm = Path("/data/sitemaps/sitemap.xml")
    age = (time.time() - sm.stat().st_mtime) / 86400 if sm.exists() else 99
    out.append(Check("sitemap", "Sitemap rebuilt in the last two days", age < 2.5, f"{age:.1f} days old"))
    return out


def run_checks() -> list[Check]:
    with httpx.Client(headers={"User-Agent": "furp-health-check"}) as client:
        return check_pages(client) + check_fallback() + check_db() + check_server()


# --- repairs ------------------------------------------------------------------------------------------------

def _sh(cmd: list[str], timeout: int = 1800) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-300:]
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def repair(name: str, arg=None) -> tuple[bool, str]:
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
    if name == "clean_disk":
        _sh(["sudo", "journalctl", "--vacuum-time=14d"], 300)
        _sh(["sudo", "find", "/tmp", "-type", "f", "-mtime", "+7", "-delete"], 300)
        return True, "trimmed system logs over 14 days old and temporary files over 7 days old"
    return False, "no repair for this"


def rkey(c: Check) -> str:
    return f"{c.repair} {c.arg.name}" if isinstance(c.arg, Path) else str(c.repair)


# --- report -------------------------------------------------------------------------------------------------

def report(first: list[Check], repairs: dict, second: list[Check]) -> tuple[str, str]:
    after = {c.key: c for c in second}
    failed = [c for c in first if not c.ok]
    new = [c for c in second if not c.ok and c.key not in {f.key for f in failed}]
    still = [c for c in failed if not after.get(c.key, c).ok]
    if not failed and not new:
        subject = f"Site check, all {len(first)} checks passed"
    else:
        subject = (f"Site check, {len(failed)} problem{'s' if len(failed) != 1 else ''}, "
                   f"{len(failed) - len(still)} fixed, {len(still) + len(new)} still open")
    lines = [subject, ""]
    for c in failed:
        a = after.get(c.key, c)
        fix = repairs.get(rkey(c))
        lines.append(f"- {c.what}: {c.detail or 'failed'}")
        lines.append("  Repair: " + (("done: " if fix[0] else "tried, failed: ") + fix[1] if fix else
                                     "none available, needs a person" if not c.repair else "not attempted"))
        lines.append(f"  Now: {'FIXED' if a.ok else 'STILL FAILING: ' + (a.detail or 'failed')}")
    for c in new:
        lines.append(f"- NEW after repairs: {c.what}: {c.detail or 'failed'}")
    if failed or new:
        lines.append("")
    lines.append(f"Checked: {len(first)} items (app, {len(PAGES)} pages, fallback pages, database, leaderboards, "
                 f"insights pool, email, nightly loads, sitemap, disk, certificate, cron, dev server).")
    passed = [c.what for c in second if c.ok]
    lines.append(f"Passing now: {len(passed)} of {len(second)}.")
    return subject, "\n".join(lines) + "\n"


def main() -> int:
    from app import mailer
    from app.config import REPORT_FROM, REPORT_TO
    first = run_checks()
    repairs: dict[str, tuple[bool, str]] = {}
    if "--no-repair" not in sys.argv:
        for c in first:
            if not c.ok and c.repair and rkey(c) not in repairs:      # each repair once (one restart for many pages)
                repairs[rkey(c)] = repair(c.repair, c.arg)
        if repairs:
            time.sleep(20)
    second = run_checks() if repairs else first
    subject, text = report(first, repairs, second)
    print(text)
    if "--no-email" not in sys.argv:
        ok = mailer.send({"From": REPORT_FROM, "To": REPORT_TO, "Subject": mailer.report_subject(subject), "TextBody": text,
                          "MessageStream": "outbound"})
        print("emailed" if ok else "email failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
