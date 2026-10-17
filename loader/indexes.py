"""Secondary name indexes on people that are dropped during big backfills.

No live query needs them (search uses person_clusters), but they make ad-hoc
name queries fast. Inserting into a 30M+ row table while maintaining them
dominates load time, so a backfill can drop them and ensure() rebuilds them,
concurrently so the site keeps working. Run only one ensure() at a time: two
concurrent index builds on the same table deadlock (load.py holds the loader lock).
"""

from __future__ import annotations

from loader import db

PEOPLE_NAME_INDEXES = {
    "people_name_norm": "ON people (name_norm)",
    "people_name_prefix": "ON people (name_norm text_pattern_ops)",
    "people_ein_name": "ON people (ein, name_norm)",
    "people_last_name": "ON people (np_last_name(name_norm))",
    "people_title_lower": "ON people (lower(title) text_pattern_ops)",
}


def ensure(status=None) -> list[str]:
    """Create any missing people name index. Returns the names created."""
    created = []
    with db.connect(autocommit=True) as conn:
        rows = conn.execute("""SELECT c.relname, x.indisvalid FROM pg_index x
                               JOIN pg_class c ON c.oid = x.indexrelid JOIN pg_class t ON t.oid = x.indrelid
                               WHERE t.relname = 'people'""").fetchall()
        valid = {name for name, ok in rows if ok}
        invalid = {name for name, ok in rows if not ok}
        for name, ddl in PEOPLE_NAME_INDEXES.items():
            if name in valid:
                continue
            if name in invalid:
                # A cancelled CREATE INDEX CONCURRENTLY leaves an invalid index behind.
                conn.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            if status:
                status.phase = f"index {name}"
            conn.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} {ddl}")
            created.append(name)
        if db.has_extension(conn, "pg_trgm"):
            conn.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS people_name_norm_trgm "
                         "ON people USING gin (name_norm gin_trgm_ops)")
    return created


def drop() -> None:
    with db.connect(autocommit=True) as conn:
        for name in PEOPLE_NAME_INDEXES:
            conn.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
