"""How many records FURP holds, for the home page (owner, 2026-11-13: "the total number of records and note all
cross referenced ... count them 4x a day and cache the result").

The count is the sum of the planner's row estimates (pg_class.reltuples) over every ordinary table outside the
system schemas: instant, and within a percent of exact. It is kept in the table site_counts, refreshed when
older than REFRESH_HOURS (on read, and by a cron every eight hours on prod: `python -m app.record_count refresh`),
and held in this process for a few minutes between reads.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from app import db

log = logging.getLogger("np.count")
REFRESH_HOURS = 8
KEY = "records"
_mem: dict = {"at": 0.0, "value": None}
_MEM_SECONDS = 600

SQL = """
CREATE TABLE IF NOT EXISTS site_counts (
    key text PRIMARY KEY, rows bigint NOT NULL, tables integer NOT NULL, detail jsonb, at timestamptz NOT NULL DEFAULT now());
"""
COUNT_SQL = """
SELECT n.nspname AS schema, sum(greatest(c.reltuples, 0))::bigint AS rows, count(*) AS tables
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
GROUP BY n.nspname ORDER BY 2 DESC"""


def refresh() -> dict:
    """Count now and store the result."""
    import json
    with db.conn(timeout="2min") as conn:
        conn.execute(SQL)
        parts = [dict(r) for r in conn.execute(COUNT_SQL).fetchall()]
        rows, tables = sum(p["rows"] for p in parts), sum(p["tables"] for p in parts)
        conn.execute("INSERT INTO site_counts (key, rows, tables, detail, at) VALUES (%s, %s, %s, %s, now()) "
                     "ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, tables = EXCLUDED.tables, "
                     "detail = EXCLUDED.detail, at = now()", (KEY, rows, tables, json.dumps(parts)))
    out = {"rows": rows, "tables": tables, "at": datetime.now(timezone.utc), "by_schema": parts}
    _mem.update(at=time.monotonic(), value=out)
    log.info("records counted: %s rows in %s tables", f"{rows:,}", tables)
    return out


def total() -> dict | None:
    """{"rows", "tables", "at"}: the stored count, refreshed when older than REFRESH_HOURS; None only when the
    database cannot be read (the home page then shows no figure rather than a wrong one)."""
    if _mem["value"] and time.monotonic() - _mem["at"] < _MEM_SECONDS:
        return _mem["value"]
    try:
        with db.conn(timeout="10s") as conn:
            if conn.execute("SELECT to_regclass('site_counts') AS t").fetchone()["t"]:
                row = conn.execute("SELECT rows, tables, at FROM site_counts WHERE key = %s", (KEY,)).fetchone()
            else:
                row = None
        if row and row["at"] > datetime.now(timezone.utc) - timedelta(hours=REFRESH_HOURS):
            out = {"rows": row["rows"], "tables": row["tables"], "at": row["at"]}
            _mem.update(at=time.monotonic(), value=out)
            return out
        return refresh()
    except Exception:  # noqa: BLE001 - never break the home page over a figure
        log.exception("records count")
        return _mem["value"]


def short(n: int | None) -> str:
    """1,502,149,857 -> "1.5 billion"."""
    if not n:
        return ""
    if n >= 1e9:
        return f"{n / 1e9:.1f} billion"
    if n >= 1e6:
        return f"{n / 1e6:.0f} million"
    return f"{n:,}"


if __name__ == "__main__":
    if sys.argv[1:] == ["refresh"]:
        r = refresh()
        print(f"{r['rows']:,} rows in {r['tables']} tables")
    else:
        print(total())
