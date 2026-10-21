"""Off-hours bulk loads for the shared database (cron on the dev box, 07:00 UTC = 02:00 Central).

Prod reads the same Postgres, so heavy writes run only in the window START_UTC..END_UTC, one task at a time, in
small committed batches with pauses (loader/usaspending.py honours /tmp/load_pause), with ANALYZE after each table
and the dataset's leaderboards rebuilt when its load completes. Each night picks up where the last stopped:

1. USAspending contract years that have not loaded (usa_runs), newest first; then recipient links, summaries
   and the federal spending boards.
2. FEC: person links, summary tables and the campaign contribution boards (once, after the cycles are in).
3. Lobbying: crawl for the rest of the window (API-bound, light), then parse, link and rebuild its boards.
First each night: organizations' alternate names (loader/alt_names.py), and model suggestions for new large filers.

Usage: .venv/bin/python scripts/offhours.py   (logs to /var/log/np-explorer/offhours.log via cron)
"""

from __future__ import annotations

import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loader import db  # noqa: E402

START_UTC, END_UTC = 7, 11
FIRST_FY = 2007


def log(msg: str) -> None:
    print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} {msg}", flush=True)


def in_window() -> bool:
    return START_UTC <= dt.datetime.now(dt.timezone.utc).hour < END_UTC


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
        conn.execute("INSERT INTO offhours_done (key) VALUES (%s) ON CONFLICT DO NOTHING", (key,))
        conn.commit()


def usaspending() -> bool:
    """True when every contract year is loaded and the summaries are built."""
    from loader import usaspending as U
    today = dt.date.today()
    current = today.year + (1 if today.month >= 10 else 0)
    with db.connect() as conn:
        have = {r[0] for r in conn.execute("SELECT DISTINCT fiscal_year FROM usa_runs WHERE kind = 'contract'").fetchall()}
    for fy in range(current, FIRST_FY - 1, -1):
        if fy in have:
            continue
        if not in_window():
            return False
        log(f"usaspending: contracts FY{fy}")
        U.load([fy], kinds=("contract",), status=log)
        analyze("usa_awards", "usa_officers")
    if not done("usa-summaries"):
        if not in_window():
            return False
        U.link_orgs(status=log)
        from app import fedspend
        fedspend.build_summaries(status=log)
        analyze("usa_awards", "usa_recipient_totals", "usa_person_links")
        refresh_group("fedspend")
        mark("usa-summaries")
    return True


def fec() -> bool:
    if done("fec-links"):
        return True
    if not in_window():
        return False
    from loader import fec_links
    fec_links.build_all(status=log)
    analyze("fec_person_links", "fec_committee_totals", "fec_donor_totals", "fec_org_committees")
    refresh_group("politics")
    mark("fec-links")
    return True


def lobbying() -> None:
    from loader import lda
    from app import lobbying as L
    hours = END_UTC - dt.datetime.now(dt.timezone.utc).hour - 0.5
    if hours > 0.25:
        lda.crawl(status=log, max_hours=hours)
    lda.parse(status=log)
    lda.link_orgs(status=log)
    L.build(status=log)
    analyze("lda_filings", "lda_activities", "lda_activity_lobbyists", "lda_client_years")
    refresh_group("lobbying")


def main() -> None:
    if not in_window():
        log("outside the off-hours window; nothing to do")
        return
    log("off-hours loads: start")
    if in_window():
        # Recipient pages (app/fedspend.recipient) need this index; built once, off-hours (60 GB table).
        with db.connect(autocommit=True) as conn:
            conn.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS usa_awards_uei ON usa_awards (recipient_uei) "
                         "WHERE recipient_uei IS NOT NULL")
        from loader import alt_names
        alt_names.build(status=log)                                   # short names, acronyms, DBAs (2 minutes)
        alt_names.llm_suggest(limit=50_000, status=log, max_minutes=20)   # new large filers only
    if usaspending() and fec() and in_window():
        lobbying()
    log("off-hours loads: done for tonight")


if __name__ == "__main__":
    main()
