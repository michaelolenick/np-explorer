"""The FURP space ingestion from the command line (owner, 2026-11-12); the logic is app/space_ingest.py.

    .venv/bin/python -m loader.space_ingest sweep            everything pending, new or stuck; failed ones retried once;
                                                             exposure re-synced with the current marks (cron, every 10 min on dev)
    .venv/bin/python -m loader.space_ingest file <id> [--force]   one file now (force: check and extract again)
    .venv/bin/python -m loader.space_ingest status           every file and what happened to it
"""

from __future__ import annotations

import argparse
import sys

from app import db


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("cmd", choices=["sweep", "file", "status"])
    ap.add_argument("file_id", nargs="?", type=int)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from app import space_ingest
    opened = db.pool.closed                  # the tests call this with the shared pool already open: leave it so
    if opened:
        db.pool.open(wait=True)
    try:
        if a.cmd == "sweep":
            space_ingest.sweep()
        elif a.cmd == "file":
            if a.file_id is None:
                ap.error("file needs an id")
            print(space_ingest.process_file(a.file_id, force=a.force, status=print))
        else:
            space_ingest.ensure()
            with db.conn() as conn:
                rows = conn.execute("""SELECT f.id, d.name AS folder, f.filename, f.size, f.visibility, f.removed_at, d.visibility AS folder_vis,
                                              f.public_token, s.status, s.kind, s.pages, s.messages, s.attachments, s.tables, s.entities,
                                              s.matched, s.exposure, s.error, s.attempts, s.progress
                                       FROM space_files f JOIN space_folders d ON d.id = f.folder_id
                                       LEFT JOIN space_docs s ON s.file_id = f.id ORDER BY f.id""").fetchall()
            for r in rows:
                what = r["status"] or ("private" if r["visibility"] == "private" or r["folder_vis"] == "private" else "not started")
                if r["removed_at"]:
                    what = "removed"
                detail = r["error"] or ""
                if r["status"] == "extracted":
                    detail = (f"{r['messages'] or 0:,} messages, {r['attachments'] or 0:,} attachments, " if r["kind"] == "pst" else f"{r['pages'] or 0} pages, ") \
                        + f"{r['tables'] or 0} tables, {r['entities'] or 0} entities ({r['matched'] or 0} matched); exposure {r['exposure']}"
                elif r["status"] == "checking" and r["progress"]:
                    detail = str(r["progress"])
                print(f"{r['id']:>5}  {r['folder']:<12} {r['filename'][:40]:<40} {r['size'] / 1048576:8.1f} MB  {r['visibility']:<7} {what:<10} {detail}")
    finally:
        if opened:
            db.pool.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
