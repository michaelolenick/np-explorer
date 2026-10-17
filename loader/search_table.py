"""Tables derived from person_clusters after every cluster change.

person_search: the columns name search reads, stored in name order.

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
    build_big_summaries(status)
    return n


# Same threshold as app/queries.py BIG_CLUSTER: records this big load one year at a time.
BIG_CLUSTER = 1000


def build_big_summaries(status=None) -> int:
    """person_big_summary: per-year pay totals and row counts for very large records (banks
    serving thousands of foundations), so their pages don't add up tens of thousands of rows
    on every view."""
    if status:
        status.phase = "big person summaries"
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("DROP TABLE IF EXISTS person_big_summary_new")
        conn.execute(f"""
            CREATE TABLE person_big_summary_new AS
            WITH big AS (SELECT id FROM person_clusters WHERE n_filings > {BIG_CLUSTER}),
            per_year AS (
                SELECT m.cluster_id, p.tax_year,
                       sum(coalesce(p.comp_org, 0)) FILTER (WHERE NOT f.superseded) AS comp_org,
                       sum(coalesce(p.comp_related, 0)) FILTER (WHERE NOT f.superseded) AS comp_related,
                       sum(coalesce(p.other_comp, 0)) FILTER (WHERE NOT f.superseded) AS other_comp,
                       sum(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0))
                           FILTER (WHERE NOT f.superseded) AS total,
                       count(*) FILTER (WHERE NOT f.superseded) AS n,
                       count(*) AS n_rows
                FROM big JOIN person_cluster_members m ON m.cluster_id = big.id
                JOIN people p ON p.id = m.person_id AND NOT p.is_duplicate JOIN filings f ON f.id = p.filing_id
                GROUP BY m.cluster_id, p.tax_year)
            SELECT cluster_id, sum(n_rows)::bigint AS n_rows,
                   jsonb_agg(jsonb_build_object('tax_year', tax_year, 'comp_org', comp_org,
                             'comp_related', comp_related, 'other_comp', other_comp, 'total', total, 'n', n,
                             'n_rows', n_rows) ORDER BY tax_year DESC NULLS LAST) AS years
            FROM per_year GROUP BY cluster_id""")
        conn.execute("ALTER TABLE person_big_summary_new ADD PRIMARY KEY (cluster_id)")
        conn.commit()
        conn.execute("SET lock_timeout = '30s'")
        conn.execute("DROP TABLE IF EXISTS person_big_summary")
        conn.execute("ALTER TABLE person_big_summary_new RENAME TO person_big_summary")
        conn.execute("ALTER INDEX IF EXISTS person_big_summary_new_pkey RENAME TO person_big_summary_pkey")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM person_big_summary").fetchone()[0]
    if status:
        status.emit(f"big person summaries: {n:,} records")
    return n
