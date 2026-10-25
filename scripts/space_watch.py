"""Hourly space check (owner, 2026-10-25: "watch diskspace in both the DB and raw disk").

Logs one line per run, and alerts the owner the same hour (queued notice, then the daily email is sent at once)
when the database (data + WAL, against DB_STORAGE_GB, the Azure plan's 512 GiB with auto-grow off) or a local disk
passes WARN_PCT, again at CRIT_PCT. One alert per level per day per item.

Usage: .venv/bin/python scripts/space_watch.py [--db]   (--db on one machine only: the dev box checks the database)
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WARN_PCT, CRIT_PCT = 85, 92
DB_STORAGE_GB = float(os.environ.get("DB_STORAGE_GB", "512"))
MOUNTS = ("/", "/bulk", "/data")
MARKS = Path(os.environ.get("HOME", "/tmp")) / ".space-watch"


def db_used_gb() -> float:
    import psycopg
    from app.config import DATABASE_URL
    with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
        data = conn.execute("SELECT sum(pg_database_size(datname)) FROM pg_database").fetchone()[0]
        try:
            wal = conn.execute("SELECT coalesce(sum(size), 0) FROM pg_ls_waldir()").fetchone()[0]
        except Exception:  # noqa: BLE001 - no permission: data only
            wal = 0
    return float(data + wal) / 2**30


def items(check_db: bool) -> list[tuple[str, float, float]]:
    """(name, used GB, total GB)."""
    out, seen = [], set()
    for m in MOUNTS:
        if os.path.exists(m) and os.stat(m).st_dev not in seen:
            seen.add(os.stat(m).st_dev)
            u = shutil.disk_usage(m)
            out.append((f"disk {m} on {socket.gethostname()}", u.used / 2**30, u.total / 2**30))
    if check_db:
        out.append(("database (data + WAL)", db_used_gb(), DB_STORAGE_GB))
    return out


def alert(name: str, level: str, line: str) -> None:
    MARKS.mkdir(exist_ok=True)
    mark = MARKS / f"{dt.date.today()}-{level}-{name.replace('/', '_').replace(' ', '_')}"
    if mark.exists():
        return
    from app import mailer
    subject = f"{'CRITICAL' if level == 'crit' else 'Warning'}: {name} is {line}"
    body = (f"{name}: {line}.\n\nBig loads keep adding data; at 100% the database stops accepting writes "
            f"(disk: loads and logs fail). Free space or raise the limit.")
    if mailer.notify_owner("Site check", subject, body):
        try:
            mailer.send_digest(status=lambda m: None)
        except Exception:  # noqa: BLE001 - stays queued for the daily email
            pass
        mark.touch()


def main() -> None:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = []
    for name, used, total in items("--db" in sys.argv):
        pct = 100 * used / total
        line = f"{pct:.0f}% used ({used:,.0f} of {total:,.0f} GiB)"
        parts.append(f"{name} {line}")
        if pct >= CRIT_PCT:
            alert(name, "crit", line)
        elif pct >= WARN_PCT:
            alert(name, "warn", line)
    print(f"{now} " + " | ".join(parts), flush=True)


if __name__ == "__main__":
    main()
