"""Secondary name indexes on people that are dropped during big backfills.

No live query needs them (search uses person_clusters), but they make ad-hoc
name queries fast. Inserting into a 30M+ row table while maintaining them
dominates load time, so a backfill can drop them and ensure() rebuilds them,
concurrently so the site keeps working.
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
        have = {r[0] for r in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'people'")}
        for name, ddl in PEOPLE_NAME_INDEXES.items():
            if name in have:
                continue
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
