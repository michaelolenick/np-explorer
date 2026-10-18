"""Build event_classes: each itemized Schedule G Part II event (event1, event2) with its category,
"related to mission" flag and reason, from app/event_class.py (deterministic; no AI).

Built beside the live table and swapped in. Run by load.py event-classes, and by the nightly job
before the leaderboards refresh.
"""

from __future__ import annotations

from app import event_class
from loader import db

COLS = ["filing_id", "slot", "category", "related", "reason", "gala"]


def build(status) -> int:
    status.phase = "event classes"
    with db.connect() as conn:
        schema = conn.execute("SELECT current_schema()").fetchone()[0]
        conn.execute(f'DROP TABLE IF EXISTS "{schema}".event_classes__new')
        conn.execute("""CREATE TABLE event_classes__new (filing_id bigint, slot text, category text, related boolean,
                                                         reason text, gala boolean)""")
        rows = []
        with conn.cursor(name="event_classes_src") as cur:
            cur.itersize = 20000
            cur.execute("""SELECT v.filing_id, v.slot, v.name, o.name, o.ntee
                           FROM fundraising_events v JOIN filings f ON f.id = v.filing_id
                           LEFT JOIN organizations o ON o.ein = f.ein
                           WHERE v.slot IN ('event1', 'event2') AND v.name IS NOT NULL""")
            for fid, slot, desc, org, ntee in cur:
                cat, related, reason = event_class.classify(desc, org, ntee)
                rows.append((fid, slot, cat, related, reason, event_class.is_gala(desc)))
        with conn.cursor() as cur:
            db.copy_rows(cur, "event_classes__new", COLS, rows)
        conn.execute("CREATE INDEX ON event_classes__new (filing_id)")
        conn.execute("SET lock_timeout = '30s'")
        conn.execute(f'DROP TABLE IF EXISTS "{schema}".event_classes')
        conn.execute("ALTER TABLE event_classes__new RENAME TO event_classes")
        for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'event_classes'").fetchall():
            if "__new" in idx:
                conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{idx.replace("__new", "")}"')
        conn.execute("ANALYZE event_classes")
        conn.commit()
    status.emit(f"event classes: {len(rows):,} itemized events classified")
    return len(rows)
