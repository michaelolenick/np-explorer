"""Build event_classes: each itemized Schedule G Part II event (event1, event2) with its category,
"related to mission" flag and reason, from app/event_class.py (deterministic; no AI).

Built beside the live table, then copied into it in one transaction. Run by load.py event-classes, and by the nightly job
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
        # Refilled in place, not swapped: the event board views depend on this table.
        conn.execute("""CREATE TABLE IF NOT EXISTS event_classes (filing_id bigint, slot text, category text,
                                                                  related boolean, reason text, gala boolean)""")
        conn.execute("CREATE INDEX IF NOT EXISTS event_classes_filing_id_idx ON event_classes (filing_id)")
        conn.execute("SET lock_timeout = '30s'")
        conn.execute("TRUNCATE event_classes")
        conn.execute(f"INSERT INTO event_classes ({', '.join(COLS)}) SELECT {', '.join(COLS)} FROM event_classes__new")
        conn.execute("DROP TABLE event_classes__new")
        conn.execute("ANALYZE event_classes")
        conn.commit()
    status.emit(f"event classes: {len(rows):,} itemized events classified")
    return len(rows)
