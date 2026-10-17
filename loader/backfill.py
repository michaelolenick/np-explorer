"""Fill a newly mapped filing field from the stored XML, without a full reparse.

load.py backfill-fundraising reads every in-scope Form 990 (the leaderboard
scope in app/config.py; --all for every 990) whose fundraising_expenses is
still empty and writes the value. Resumable: rows already filled are skipped,
and rows whose return reports no figure are marked 0 only when the form has
the Part IX column (so they aren't read again).
"""

from __future__ import annotations

import gzip
import multiprocessing as mp

from app.config import BOARD_MIN_ASSETS, BOARD_MIN_REVENUE, XML_DIR
from loader import db
from loader.ingest import WORKERS
from loader.parser import parse

BATCH = 2000


def _read(item):
    fid, oid, path = item
    try:
        with gzip.open(XML_DIR / path) as f:
            filing = parse(f.read(), oid)
    except Exception:  # noqa: BLE001 - unreadable file: leave the row empty
        return fid, None, False
    if filing is None:
        return fid, None, False
    return fid, filing["filing"].get("fundraising_expenses"), True


def fundraising(status, everything: bool = False) -> int:
    status.phase = "backfill fundraising expenses"
    scope = "" if everything else \
        f"AND (total_revenue >= {BOARD_MIN_REVENUE} OR total_assets_eoy >= {BOARD_MIN_ASSETS})"
    with db.connect() as conn:
        rows = conn.execute(f"""SELECT id, object_id, xml_path FROM filings
                                WHERE form_type = '990' AND fundraising_expenses IS NULL
                                  AND xml_path IS NOT NULL {scope} ORDER BY id""").fetchall()
        status.begin_year("990s", len(rows), 0)
        status.emit(f"backfill fundraising: {len(rows):,} filings to read")
        done = 0
        with mp.get_context("fork").Pool(WORKERS, maxtasksperchild=2000) as pool, conn.cursor() as cur:
            buf = []
            for fid, value, ok in pool.imap_unordered(_read, rows, chunksize=64):
                if ok:
                    buf.append((fid, value if value is not None else 0))
                done += 1
                status.add(filings=1, errors=0 if ok else 1)
                if len(buf) >= BATCH:
                    _flush(cur, buf)
                    conn.commit()
                    buf.clear()
            _flush(cur, buf)
            conn.commit()
    status.emit(f"backfill fundraising: {done:,} filings read")
    return done


def _flush(cur, buf) -> None:
    if not buf:
        return
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS bf_vals (id bigint, v bigint)")
    cur.execute("TRUNCATE bf_vals")
    db.copy_rows(cur, "bf_vals", ["id", "v"], buf)
    cur.execute("UPDATE filings f SET fundraising_expenses = b.v FROM bf_vals b WHERE f.id = b.id")
