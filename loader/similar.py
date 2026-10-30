"""Tables for Nearby + Similar (app/nearby.py; owner, 2026-10-29).

- org_geo: every organization placed at its ZIP code's center (geo_zips, the Census ZCTA gazetteer), for "within N
  miles". Organizations without a ZIP in geo_zips are left out.
- sim_lexeme_df: for each word stem in research.org_text, how many organizations use it (document frequency), so a
  seed organization's most distinctive words can be weighted TF-IDF style.
- sim_grant_edges: one row per funder and recipient pair from the grants table where the recipient's EIN is filed
  (exact EIN links, no name matching), with the grant count, years and total.
- sim_grant_degree: how many recipients each funder has and how many funders each recipient has, so a donor-advised
  fund that gives to everyone counts for little.

Rebuilt every night (scripts/nightly.sh); about two minutes.

Usage: .venv/bin/python -m loader.similar
"""

from __future__ import annotations

import time

from loader import db


def build(status=print) -> dict:
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("DROP TABLE IF EXISTS org_geo_new")
        conn.execute("""CREATE TABLE org_geo_new AS
                        SELECT o.ein, g.zip5, g.lat, g.lon FROM organizations o JOIN geo_zips g ON g.zip5 = left(o.zip, 5)""")
        conn.execute("ALTER TABLE org_geo_new ADD PRIMARY KEY (ein)")
        conn.execute("CREATE INDEX ON org_geo_new (zip5)")
        conn.execute("CREATE INDEX ON org_geo_new (lat, lon)")
        db.swap_table(conn, "org_geo")
        conn.commit()

        if conn.execute("SELECT to_regclass('research.org_text') IS NOT NULL").fetchone()[0]:
            conn.execute("DROP TABLE IF EXISTS sim_lexeme_df_new")
            conn.execute("""CREATE TABLE sim_lexeme_df_new AS
                            SELECT word AS lexeme, ndoc AS df FROM ts_stat('SELECT tsv FROM research.org_text')""")
            conn.execute("ALTER TABLE sim_lexeme_df_new ADD PRIMARY KEY (lexeme)")
            db.swap_table(conn, "sim_lexeme_df")
            conn.commit()

        conn.execute("DROP TABLE IF EXISTS sim_grant_edges_new")
        conn.execute("""CREATE TABLE sim_grant_edges_new AS
                        SELECT ein AS funder, recipient_ein AS recipient, count(*) AS n_grants, min(tax_year) AS first_year,
                               max(tax_year) AS last_year,
                               sum(coalesce(cash_amount, 0) + coalesce(noncash_amount, 0)) AS amount
                        FROM grants WHERE recipient_ein ~ '^[0-9]{9}$' AND recipient_ein <> ein AND NOT is_summary
                        GROUP BY 1, 2""")
        conn.execute("CREATE INDEX ON sim_grant_edges_new (funder)")
        conn.execute("CREATE INDEX ON sim_grant_edges_new (recipient)")
        db.swap_table(conn, "sim_grant_edges")
        conn.commit()
        conn.execute("DROP TABLE IF EXISTS sim_grant_degree_new")
        conn.execute("""CREATE TABLE sim_grant_degree_new AS
                        SELECT ein, sum(n_out)::int AS n_out, sum(n_in)::int AS n_in FROM (
                            SELECT funder AS ein, count(*) AS n_out, 0 AS n_in FROM sim_grant_edges GROUP BY 1
                            UNION ALL SELECT recipient, 0, count(*) FROM sim_grant_edges GROUP BY 1) x
                        GROUP BY 1""")
        conn.execute("ALTER TABLE sim_grant_degree_new ADD PRIMARY KEY (ein)")
        db.swap_table(conn, "sim_grant_degree")
        conn.commit()
        for t in ("org_geo", "sim_lexeme_df", "sim_grant_edges", "sim_grant_degree"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
        n = conn.execute("""SELECT (SELECT count(*) FROM org_geo), (SELECT count(*) FROM sim_lexeme_df),
                                   (SELECT count(*) FROM sim_grant_edges)""").fetchone()
    out = {"org_geo": n[0], "lexemes": n[1], "grant_edges": n[2]}
    status(f"similar: {n[0]:,} organizations placed, {n[1]:,} word stems, {n[2]:,} funder-recipient links "
           f"({time.time() - t0:.0f}s)")
    return out


if __name__ == "__main__":
    build()
