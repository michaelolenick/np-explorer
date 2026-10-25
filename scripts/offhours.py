"""Off-hours bulk loads for the shared database (cron on the dev box, 07:00 UTC = 02:00 Central).

Prod reads the same Postgres, so heavy writes run one task at a time, in small committed batches with pauses
(loader/usaspending.py honours /tmp/load_pause), with ANALYZE after each table and the dataset's leaderboards rebuilt
when its load completes. A run goes on until everything is loaded, at any hour (owner, 2026-10-25: no run window);
if it is still going at the next night's start, the new run exits (file lock). Each night picks up where the last
stopped:

1. FEC: every cycle reloaded whenever the FEC posts a newer file (one HEAD request per cycle), then person links
   for the reloaded cycles, the summary tables and the campaign contribution boards.
2. Lobbying: the crawl (filings posted since the last run, new and amended, then the backfill of older years)
   is started first, detached, and runs at any time of day until caught up (API-bound, light on the database;
   an advisory lock keeps it to one crawler); then parse what has arrived, link and rebuild its boards.
3. USAspending: every fiscal year whose archive file is newer than the one loaded (the monthly archive, around the
   6th), then contract years that have not loaded (usa_runs), newest first; once every year is in, recipient links,
   summaries and the federal spending boards, rebuilt whenever new files have loaded since.
First each night: organizations' alternate names (loader/alt_names.py), and model suggestions for new large filers.

Usage: .venv/bin/python scripts/offhours.py   (logs to /var/log/np-explorer/offhours.log via cron)
"""

from __future__ import annotations

import datetime as dt
import fcntl
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loader import db  # noqa: E402

LOBBYING_HOURS: float | None = None      # owner, 2026-10-25: no time cap; the crawl runs until it has caught up
FIRST_FY = 2007
LOCK_FILE = Path("/tmp/np-offhours.lock")


def log(msg: str) -> None:
    print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} {msg}", flush=True)


def analyze(*tables: str) -> None:
    with db.connect(autocommit=True) as conn:
        for t in tables:
            conn.execute(f"ANALYZE {t}")


def refresh_group(group: str) -> None:
    from app import boards as B
    from loader import boards as LB
    with db.connect() as conn:
        for b in B.BOARDS:
            if b.group == group:
                log(f"board {b.slug}: {LB.refresh_board(conn, b)} rows")


def done(key: str) -> bool:
    with db.connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS offhours_done (key text PRIMARY KEY, at timestamptz DEFAULT now())")
        conn.commit()
        return conn.execute("SELECT 1 FROM offhours_done WHERE key = %s", (key,)).fetchone() is not None


def mark(key: str) -> None:
    with db.connect() as conn:
        conn.execute("INSERT INTO offhours_done (key) VALUES (%s) ON CONFLICT (key) DO UPDATE SET at = now()", (key,))
        conn.commit()


def marked_at(key: str):
    done(key)                                     # creates offhours_done the first time
    with db.connect() as conn:
        r = conn.execute("SELECT at FROM offhours_done WHERE key = %s", (key,)).fetchone()
    return r[0] if r else None


def usaspending() -> None:
    """Newer archive files for every fiscal year, contract years not loaded yet, then the summaries."""
    from loader import usaspending as U
    try:
        U.refresh(status=log)                     # new monthly archive: every fiscal year with a newer file
    except Exception as e:                        # noqa: BLE001 - the backfill below still gets its turn
        log(f"usaspending refresh failed: {e}")
    analyze("usa_awards", "usa_officers")
    today = dt.date.today()
    current = today.year + (1 if today.month >= 10 else 0)
    with db.connect() as conn:
        have = {r[0] for r in conn.execute("SELECT DISTINCT fiscal_year FROM usa_runs WHERE kind = 'contract'").fetchall()}
    for fy in range(current, FIRST_FY - 1, -1):
        if fy in have:
            continue
        log(f"usaspending: contracts FY{fy}")
        U.load([fy], kinds=("contract",), status=log)
        analyze("usa_awards", "usa_officers")
    with db.connect() as conn:
        newest = conn.execute("SELECT max(finished) FROM usa_runs").fetchone()[0]
    built = marked_at("usa-summaries")
    if built is None or (newest and newest > built):
        U.link_orgs(status=log)
        from app import fedspend
        fedspend.build_summaries(status=log)
        analyze("usa_awards", "usa_recipient_totals", "usa_person_links")
        refresh_group("fedspend")
        mark("usa-summaries")


def fec() -> None:
    """Reload every cycle the FEC has posted a newer file for, then relink every cycle loaded since the last link
    build (or all of them, the first time) and rebuild the summary tables and boards."""
    from loader import fec, fec_links
    try:
        fec.refresh(status=log)
    except Exception as e:                        # noqa: BLE001 - relink whatever did load; retried tomorrow
        log(f"fec refresh failed: {e}")
    built = marked_at("fec-links")
    with db.connect() as conn:
        newer = [r[0] for r in conn.execute("""SELECT DISTINCT cycle FROM fec_runs WHERE status = 'done'
                                               AND finished > %s ORDER BY 1""",
                                            (built or dt.datetime.min.replace(tzinfo=dt.timezone.utc),)).fetchall()]
    if built and not newer:
        return
    fec_links.build_all(status=log, cycles=newer if built else None)
    analyze("fec_person_links", "fec_committee_totals", "fec_donor_totals", "fec_org_committees")
    refresh_group("politics")
    mark("fec-links")


def start_lobbying_crawl() -> None:
    """Start the lobbying crawl as its own process, so it runs past the window until caught up; if one is still
    running from an earlier night it holds the advisory lock, and this one logs that and exits."""
    import subprocess
    args = [sys.executable, "-m", "loader.lda", "crawl"]
    if LOBBYING_HOURS:
        args += ["--max-hours", str(LOBBYING_HOURS)]
    # Writes to this script's output (the cron log), from its own session so it outlives this run.
    subprocess.Popen(args, cwd=Path(__file__).resolve().parent.parent, start_new_session=True)
    log("lobbying crawl started")


def lobbying() -> None:
    from loader import lda
    from app import lobbying as L
    lda.parse(status=log)
    lda.link_orgs(status=log)
    L.build(status=log)
    analyze("lda_filings", "lda_activities", "lda_activity_lobbyists", "lda_client_years")
    refresh_group("lobbying")


def main() -> None:
    start_lobbying_crawl()                        # any time of day
    # One run at a time: if last night's run is still going, this one leaves it to finish. Held until exit; the
    # lobbying crawl started above does not inherit it.
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log(f"an earlier off-hours run is still going (lock held on {LOCK_FILE}); exiting")
        return
    log("off-hours loads: start")
    # Recipient pages (app/fedspend.recipient) need this index; built once, off-hours (60 GB table).
    with db.connect(autocommit=True) as conn:
        conn.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS usa_awards_uei ON usa_awards (recipient_uei) "
                     "WHERE recipient_uei IS NOT NULL")
    from loader import alt_names
    alt_names.build(status=log)                                   # short names, acronyms, DBAs (2 minutes)
    alt_names.llm_suggest(limit=50_000, status=log)               # new large filers only
    from loader import recalls as food_recalls
    food_recalls.run(status=log)                                  # FDA food recalls, firms and links
    refresh_group("recalls")
    # Owner, 2026-10-22: leaderboards and ideas should draw from every dataset, so the campaign-money, lobbying and
    # federal-spending boards come first (federal spending from the years loaded so far, rebuilt in full once
    # every contract year is in); the remaining contract years load after.
    fec()
    lobbying()
    if not done("usa-summaries-partial"):
        from loader import usaspending as U
        from app import fedspend
        U.link_orgs(status=log)
        fedspend.build_summaries(status=log)
        analyze("usa_awards", "usa_recipient_totals", "usa_person_links")
        refresh_group("fedspend")
        mark("usa-summaries-partial")
    usaspending()
    log("off-hours loads: done for tonight")


if __name__ == "__main__":
    main()
