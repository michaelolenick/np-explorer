"""Distinctive organization names, and every business contributor's link to an organization, precomputed.

A trigram match on a whole name is slow and loose on common words: "cottage two foundation inc" shares "foundation"
with 360,000 organizations. So the words that appear in at least GENERIC_SHARE of organization names (inc, of,
foundation, association, the, fund, trust, charitable, family...) are derived from the data, and each name is matched
on what is left ("the smith family foundation" -> "smith"), with its own trigram index. A name with nothing left is
matched exactly or not at all, and two organizations tying for the best match give no link.

build() rewrites name_generic_words and org_dname; links() rewrites donor_org_link (name and state of every business
contributor -> organization, method exact, distinctive or none), which org pages read first.

Usage: .venv/bin/python -m loader.org_dname [--links-only]
"""

from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from psycopg.rows import dict_row

from app.names import distinctive
from app.queries import DNAME_CANDIDATE, DNAME_MATCH_SQL, dname_pick
from loader import db

GENERIC_SHARE = 0.005


def build(status=print) -> int:
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        n = conn.execute("SELECT count(*) FROM organizations WHERE name_norm IS NOT NULL").fetchone()[0]
        words = conn.execute("""SELECT w, count(*)::real / %s FROM organizations, unnest(string_to_array(name_norm, ' ')) w
                                WHERE name_norm IS NOT NULL AND w <> '' GROUP BY w HAVING count(*) >= %s""",
                             (n, n * GENERIC_SHARE)).fetchall()
        generic = frozenset(w for w, _ in words)
        conn.execute("CREATE TEMP TABLE gw (word text, share real)")
        with conn.cursor() as cur, cur.copy("COPY gw FROM STDIN") as cp:
            for w, share in words:
                cp.write_row((w, share))
        conn.execute("DELETE FROM name_generic_words")
        conn.execute("INSERT INTO name_generic_words SELECT * FROM gw")
        # A fresh table swapped in, so pages keep reading the old one while this builds.
        conn.execute("DROP TABLE IF EXISTS org_dname_new")
        conn.execute("CREATE TABLE org_dname_new (ein text PRIMARY KEY, state text, dname text NOT NULL)")
        rows = 0
        with db.connect() as rconn, rconn.cursor(name="orgs") as rd, conn.cursor() as cur, \
                cur.copy("COPY org_dname_new (ein, state, dname) FROM STDIN") as cp:
            rd.itersize = 50_000
            rd.execute("SELECT ein, state, name_norm FROM organizations WHERE name_norm IS NOT NULL")
            for ein, state, norm in rd:
                d = distinctive(norm, generic)
                if d:
                    cp.write_row((ein, state, d))
                    rows += 1
        conn.execute("CREATE INDEX org_dname_new_trgm ON org_dname_new USING gin (dname gin_trgm_ops)")
        conn.execute("DROP TABLE IF EXISTS org_dname")
        conn.execute("ALTER TABLE org_dname_new RENAME TO org_dname")
        conn.execute("ALTER INDEX org_dname_new_trgm RENAME TO org_dname_trgm")
        conn.execute("ALTER INDEX org_dname_new_pkey RENAME TO org_dname_pkey")
        conn.commit()
    status(f"org dname: {len(generic)} generic words (in at least {GENERIC_SHARE:.1%} of {n:,} names); "
           f"{rows:,} organizations with a distinctive name ({time.time() - t0:.0f}s)")
    return rows


def links(status=print, workers: int = 4) -> dict:
    t0 = time.time()
    with db.connect() as conn:
        generic = frozenset(w for (w,) in conn.execute("SELECT word FROM name_generic_words").fetchall())
        pairs = conn.execute("""SELECT DISTINCT name_norm, state FROM donors
                                WHERE NOT is_person AND name_norm IS NOT NULL AND state IS NOT NULL""").fetchall()
        exact = {(r[0], r[1]): r[2:] for r in conn.execute("""
            SELECT DISTINCT ON (d.name_norm, d.state) d.name_norm, d.state, o.ein, o.name
            FROM (SELECT DISTINCT name_norm, state FROM donors WHERE NOT is_person AND name_norm IS NOT NULL
                  AND state IS NOT NULL) d
            JOIN organizations o ON o.name_norm = d.name_norm AND o.state = d.state
            ORDER BY d.name_norm, d.state, o.latest_total_revenue DESC NULLS LAST""").fetchall()}

    local, opened = threading.local(), []
    def fuzzy(pair):
        n, s = pair
        d = distinctive(n, generic)
        if not d:
            return n, s, None, None, None, "none"
        if not hasattr(local, "c"):                       # one connection per worker
            local.c = db.connect()
            local.c.autocommit = True
            local.c.execute(f"SET pg_trgm.similarity_threshold = {DNAME_CANDIDATE}")
            opened.append(local.c)
        cur = local.c.cursor(row_factory=dict_row)
        m = dname_pick(cur.execute(DNAME_MATCH_SQL, {"n": n, "d": d, "s": s}).fetchall())
        if not m:
            return n, s, None, None, None, "none"
        return n, s, m["ein"], m["name"], round(float(m["score"]), 2), "distinctive"

    out = [(n, s, e, nm, 1.0, "exact") for (n, s), (e, nm) in exact.items()]
    rest = [p for p in pairs if (p[0], p[1]) not in exact]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, row in enumerate(pool.map(fuzzy, rest), 1):
            out.append(row)
            if i % 10_000 == 0:
                status(f"org dname: {i:,} of {len(rest):,} fuzzy contributor names done")
    for c in opened:
        c.close()
    with db.connect() as conn:
        conn.execute("DROP TABLE IF EXISTS donor_org_link_new")
        conn.execute("CREATE TABLE donor_org_link_new (LIKE donor_org_link INCLUDING DEFAULTS)")
        with conn.cursor() as cur, cur.copy("""COPY donor_org_link_new (name_norm, state, ein, name, score, method)
                                               FROM STDIN""") as cp:
            for row in out:
                cp.write_row(row)
        conn.execute("ALTER TABLE donor_org_link_new ADD PRIMARY KEY (name_norm, state)")
        conn.execute("DROP TABLE donor_org_link")
        conn.execute("ALTER TABLE donor_org_link_new RENAME TO donor_org_link")
        conn.execute("ALTER INDEX donor_org_link_new_pkey RENAME TO donor_org_link_pkey")
        conn.commit()
    counts: dict = {}
    for row in out:
        counts[row[5]] = counts.get(row[5], 0) + 1
    status(f"org dname: {len(out):,} contributor names linked: {counts} ({time.time() - t0:.0f}s)")
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--links-only", action="store_true", help="keep the distinctive names, redo the contributor links")
    if not ap.parse_args().links_only:
        build()
    links()
