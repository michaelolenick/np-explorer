"""person_search: the columns name search reads, stored in name order.

person_clusters carries evidence JSON and full organization lists that search never
reads, and its rows are in id order, so a common name's candidates sit on thousands of
scattered pages; cold searches spend their time on random reads. This copy has only
what search needs and is sorted by name, so "john smith" candidates sit together on a
few dozen pages. Rebuilt beside the live one and swapped in after every cluster change
(load.py search-table to run it alone).
"""

from __future__ import annotations

from loader import db

COLUMNS = ("id, display_name, name_norm, n_filings, n_orgs, first_year, last_year, max_comp, states, "
           "orgs[1:5] AS orgs, latest_title, is_institution, name_tsv, sound_tsv")
INDEXES = [
    "ADD PRIMARY KEY (id)",
    "USING gin (name_tsv)",
    "USING gin (sound_tsv)",
    "(is_institution) WHERE is_institution",
]
TRGM_INDEX = "USING gin (name_norm gin_trgm_ops)"


def build(status=None) -> int:
    if status:
        status.phase = "search table: copy"
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("SET maintenance_work_mem = '1GB'")
        conn.execute("DROP TABLE IF EXISTS person_search_new")
        conn.execute(f"CREATE TABLE person_search_new WITH (fillfactor = 100) AS "
                     f"SELECT {COLUMNS} FROM person_clusters ORDER BY name_norm, id")
        conn.commit()
        for ddl in INDEXES + ([TRGM_INDEX] if db.has_extension(conn, "pg_trgm") else []):
            if status:
                status.phase = "search table: index " + ddl.split("(")[0].strip().lower() + " " + ddl.split("(")[1][:20]
            if ddl.startswith("ADD"):
                conn.execute(f"ALTER TABLE person_search_new {ddl}")
            else:
                conn.execute(f"CREATE INDEX ON person_search_new {ddl}")
            conn.commit()
        conn.execute("ANALYZE person_search_new")
        conn.commit()
        conn.execute("SET lock_timeout = '30s'")
        conn.execute("DROP TABLE IF EXISTS person_search")
        conn.execute("ALTER TABLE person_search_new RENAME TO person_search")
        for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'person_search'").fetchall():
            if "_new" in idx:
                conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{idx.replace("person_search_new", "person_search")}"')
        conn.commit()
        n = conn.execute("SELECT count(*) FROM person_search").fetchone()[0]
    if status:
        status.emit(f"search table: {n:,} rows live")
    return n
