"""Link FEC individual contributions to people already on the site (person_clusters from Form 990s).

A contribution links to a person when
  - the contributor's normalized name equals the person's (app.names.normalize_name on both sides), and
  - the contributor's employer, normalized like an organization name (np_name_core, the SQL twin of
    app.address.name_core), equals one of the organizations the person is listed at,
and exactly one person qualifies. Generic employers (retired, self-employed, none, ...) never link.

fec_person_keys holds (name_norm, org core, cluster_id) for every person and organization; it is rebuilt
from person_clusters before linking. Links are rebuilt per cycle in one transaction.
"""

from __future__ import annotations

import time

from loader import db

NAME_CORE_SQL = r"""
CREATE OR REPLACE FUNCTION np_name_core(t text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT nullif(btrim(regexp_replace(
           regexp_replace(
             regexp_replace(replace(lower(coalesce(t, '')), '&', ' and '), '[^a-z0-9]+', ' ', 'g'),
             '\m(the|inc|incorporated|llc|corp|corporation|co|company|ltd|limited|pc|pllc|lp|llp|a|an|dba)\M',
             ' ', 'g'),
           '\s+', ' ', 'g')), '')
$$"""

GENERIC = ["retired", "self employed", "self", "none", "n a", "na", "not employed", "unemployed", "homemaker",
           "information requested", "information requested per best efforts", "requested", "student",
           "self employed self", "disabled", "not applicable", "same", "refused", "employed", "volunteer"]


def ensure_function(conn) -> None:
    conn.execute(NAME_CORE_SQL)


def build_keys(status=print) -> int:
    t = time.time()
    with db.connect() as conn:
        ensure_function(conn)
        conn.execute("DROP TABLE IF EXISTS fec_person_keys_new")
        conn.execute("""
            CREATE TABLE fec_person_keys_new AS
            SELECT DISTINCT pc.name_norm, np_name_core(o) AS core, pc.id AS cluster_id
            FROM person_clusters pc, unnest(pc.orgs) o
            WHERE NOT pc.is_institution AND pc.name_norm ~ ' ' AND np_name_core(o) IS NOT NULL""")
        # A (name, organization) pair held by two people is ambiguous: neither links.
        conn.execute("""DELETE FROM fec_person_keys_new k USING (
                            SELECT name_norm, core FROM fec_person_keys_new GROUP BY 1, 2 HAVING count(*) > 1) d
                        WHERE k.name_norm = d.name_norm AND k.core = d.core""")
        conn.execute("CREATE UNIQUE INDEX fec_person_keys_new_k ON fec_person_keys_new (name_norm, core)")
        conn.execute("DROP TABLE IF EXISTS fec_person_keys")
        conn.execute("ALTER TABLE fec_person_keys_new RENAME TO fec_person_keys")
        conn.execute("ALTER INDEX fec_person_keys_new_k RENAME TO fec_person_keys_k")
        conn.commit()
        conn.execute("ANALYZE fec_person_keys")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM fec_person_keys").fetchone()[0]
    status(f"fec links: {n:,} person keys in {time.time() - t:.0f}s")
    return n


def link_cycle(cycle: int, status=print) -> int:
    t = time.time()
    with db.connect() as conn:
        ensure_function(conn)
        conn.execute("DELETE FROM fec_person_links WHERE cycle = %s", (cycle,))
        n = conn.execute(f"""
            INSERT INTO fec_person_links (cycle, sub_id, cluster_id)
            SELECT c.cycle, c.sub_id, k.cluster_id
            FROM fec_contributions c
            JOIN fec_person_keys k ON k.name_norm = c.name_norm AND k.core = np_name_core(c.employer)
            WHERE c.cycle = %s AND c.entity_type IS DISTINCT FROM 'ORG' AND c.employer IS NOT NULL
              AND np_name_core(c.employer) <> ALL(%s)
            ON CONFLICT DO NOTHING""", (cycle, GENERIC)).rowcount
        conn.commit()
    status(f"fec links {cycle}: {n:,} contributions linked to people in {time.time() - t:.0f}s")
    return n


def report(cycle: int, k: int = 20) -> str:
    """Counts, a random sample of links, and near misses: same name as a person, employer similar to one of
    their organizations but not equal (pg_trgm similarity 0.5 or more), so not linked."""
    with db.connect() as conn:
        ensure_function(conn)
        total, linked, people = conn.execute("""
            SELECT (SELECT count(*) FROM fec_contributions WHERE cycle = %(c)s),
                   count(*), count(DISTINCT cluster_id) FROM fec_person_links WHERE cycle = %(c)s""",
                                             {"c": cycle}).fetchone()
        sample = conn.execute("""
            SELECT c.name, c.employer, c.city, c.state, pc.display_name, pc.orgs[1:3], c.amount
            FROM fec_person_links l TABLESAMPLE SYSTEM (1)
            JOIN fec_contributions c ON c.cycle = l.cycle AND c.sub_id = l.sub_id
            JOIN person_clusters pc ON pc.id = l.cluster_id WHERE l.cycle = %s LIMIT %s""", (cycle, k)).fetchall()
        near = conn.execute("""
            SELECT c.name, c.employer, pc.display_name, o, round(similarity(np_name_core(c.employer), np_name_core(o))::numeric, 2)
            FROM (SELECT * FROM fec_contributions TABLESAMPLE SYSTEM (2) WHERE cycle = %s AND employer IS NOT NULL) c
            JOIN person_clusters pc ON pc.name_norm = c.name_norm AND NOT pc.is_institution, unnest(pc.orgs) o
            WHERE np_name_core(c.employer) <> np_name_core(o)
              AND similarity(np_name_core(c.employer), np_name_core(o)) >= 0.5
            LIMIT %s""", (cycle, k)).fetchall()
    lines = [f"Cycle {cycle}: {linked:,} of {total:,} contributions linked ({100 * linked / max(total, 1):.2f}%), "
             f"{people:,} people", "", "Sample links (as filed -> person on the site):"]
    lines += [f"  {r[0]} | {r[1]} | {r[2]}, {r[3]} | ${r[6]}  ->  {r[4]} at {', '.join(r[5])}" for r in sample]
    lines += ["", "Near misses, not linked (same name; employer close to one of the person's organizations):"]
    lines += [f"  {r[4]}  {r[0]} | employer {r[1]}  vs  {r[2]} at {r[3]}" for r in near]
    return "\n".join(lines)


def build_totals(status=print) -> None:
    """fec_committee_totals: per cycle and committee, contributions from individuals (memo entries left out of
    the total, which would double count) and how many."""
    t = time.time()
    with db.connect() as conn:
        conn.execute("DROP TABLE IF EXISTS fec_committee_totals_new")
        conn.execute("""
            CREATE TABLE fec_committee_totals_new AS
            SELECT cycle, cmte_id, count(*) AS n, sum(amount) FILTER (WHERE memo_cd IS DISTINCT FROM 'X') AS total,
                   count(DISTINCT (name_norm, zip5)) AS donors
            FROM fec_contributions GROUP BY 1, 2""")
        conn.execute("CREATE UNIQUE INDEX fec_committee_totals_new_k ON fec_committee_totals_new (cmte_id, cycle)")
        conn.execute("DROP TABLE IF EXISTS fec_committee_totals")
        conn.execute("ALTER TABLE fec_committee_totals_new RENAME TO fec_committee_totals")
        conn.execute("ALTER INDEX fec_committee_totals_new_k RENAME TO fec_committee_totals_k")
        conn.commit()
    status(f"fec: committee totals in {time.time() - t:.0f}s")


def build_org_committees(status=print) -> int:
    """fec_org_committees: committees (usually PACs) whose connected organization is a filing organization,
    by normalized name and state, when exactly one organization in that state has the name."""
    with db.connect() as conn:
        ensure_function(conn)
        conn.execute("DROP TABLE IF EXISTS fec_org_committees_new")
        conn.execute("""
            CREATE TABLE fec_org_committees_new AS
            WITH cm AS (SELECT DISTINCT ON (cmte_id) cmte_id, np_name_core(connected_org) AS core, state
                        FROM fec_committees WHERE connected_org IS NOT NULL ORDER BY cmte_id, cycle DESC),
                 o AS (SELECT np_name_core(name) AS core, state, min(ein) AS ein, count(*) AS n
                       FROM organizations WHERE name IS NOT NULL GROUP BY 1, 2)
            SELECT cm.cmte_id, o.ein FROM cm JOIN o ON o.core = cm.core AND o.state = cm.state
            WHERE o.n = 1 AND cm.core IS NOT NULL AND cm.core NOT IN ('none', 'n a', 'na')""")
        conn.execute("CREATE INDEX fec_org_committees_new_ein ON fec_org_committees_new (ein)")
        conn.execute("CREATE INDEX fec_org_committees_new_cmte ON fec_org_committees_new (cmte_id)")
        conn.execute("DROP TABLE IF EXISTS fec_org_committees")
        conn.execute("ALTER TABLE fec_org_committees_new RENAME TO fec_org_committees")
        conn.execute("ALTER INDEX fec_org_committees_new_ein RENAME TO fec_org_committees_ein")
        conn.execute("ALTER INDEX fec_org_committees_new_cmte RENAME TO fec_org_committees_cmte")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM fec_org_committees").fetchone()[0]
    status(f"fec: {n:,} committees tied to filing organizations")
    return n


DONOR_FLOOR = 10_000      # fec_donor_totals keeps donors who gave at least this much in a cycle


def build_donor_totals(status=print) -> None:
    """fec_donor_totals: per cycle, each donor (normalized name and zip5) who gave at least DONOR_FLOOR in
    itemized contributions (memo entries left out), with the employer, occupation, city and state they
    reported most often. The leaderboards read this, not the contributions."""
    t = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("DROP TABLE IF EXISTS fec_donor_totals_new")
        conn.execute(f"""
            CREATE TABLE fec_donor_totals_new AS
            SELECT cycle, name_norm, zip5, sum(amount) AS total, count(*) AS n,
                   count(DISTINCT cmte_id) AS committees, min(name) AS name,
                   mode() WITHIN GROUP (ORDER BY employer) AS employer,
                   mode() WITHIN GROUP (ORDER BY occupation) AS occupation,
                   mode() WITHIN GROUP (ORDER BY city) AS city, mode() WITHIN GROUP (ORDER BY state) AS state
            FROM fec_contributions
            WHERE memo_cd IS DISTINCT FROM 'X' AND name_norm ~ ' ' AND entity_type IS DISTINCT FROM 'ORG'
              AND entity_type IS DISTINCT FROM 'PAC' AND entity_type IS DISTINCT FROM 'COM'
              AND entity_type IS DISTINCT FROM 'PTY' AND entity_type IS DISTINCT FROM 'CCM'
            GROUP BY 1, 2, 3 HAVING sum(amount) >= {DONOR_FLOOR}""")
        conn.execute("CREATE INDEX fec_donor_totals_new_k ON fec_donor_totals_new (name_norm, zip5)")
        conn.execute("DROP TABLE IF EXISTS fec_donor_totals")
        conn.execute("ALTER TABLE fec_donor_totals_new RENAME TO fec_donor_totals")
        conn.execute("ALTER INDEX fec_donor_totals_new_k RENAME TO fec_donor_totals_k")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM fec_donor_totals").fetchone()[0]
    status(f"fec: {n:,} donor-cycles of ${DONOR_FLOOR:,}+ in {time.time() - t:.0f}s")


def build_all(status=print, cycles: list[int] | None = None) -> None:
    """After a load: person keys, links for the given cycles (default all loaded), and the summary tables."""
    build_keys(status)
    with db.connect() as conn:
        loaded = [r[0] for r in conn.execute("""SELECT DISTINCT cycle FROM fec_runs WHERE status = 'done'
                                                ORDER BY 1""").fetchall()]
    for c in cycles or loaded:
        link_cycle(c, status)
    build_totals(status)
    build_org_committees(status)
    build_donor_totals(status)
