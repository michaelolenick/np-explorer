"""Group people rows into person clusters, recording why rows were linked.

Rules (also in README.md):
  1. Rows with the same normalized name at the same organization (EIN) are the
     same person across years ("unit").
  2. At one organization, name variants that differ only by a middle name or
     initial ("john smith" / "john a smith") are the same person, provided the
     middles don't conflict.
  3. Across organizations, units with the same normalized name are linked only
     with evidence:
       - the organizations list each other on Schedule R (related orgs);
       - the organizations share a street address, or the person's own listed
         address (990-PF) matches;
       - co-board overlap: the two organizations share at least two *other*
         people's names.
  4. Institutions (banks, trust companies, firms; app/institutions.py) with
     the same name once role and legal suffixes are dropped ("Bank Of America
     N A Trustee" -> "bank of america") are one record, across every
     organization they serve.
  5. Otherwise rows stay separate. A cluster never holds two conflicting middle
     names, so a bare "john smith" can't chain "john a smith" to "john b smith".

A cluster's id is the smallest people.id in it, so ids stay stable as years
are added; ids that disappear in a merge resolve through person_cluster_members.
The new tables are built beside the live ones and swapped in one transaction.
"""

from __future__ import annotations

import json
from collections import defaultdict

from app.institutions import candidate_regex, care_of_candidate_regex, care_of_person, given_names_sql
from app.names import name_parts
from loader import db, search_table

COMMON_NAME_EINS = 50     # names at more EINs than this don't seed co-board pairs
ADDRESS_GROUP_MAX = 20    # an address shared by more orgs than this (e.g. a registered agent) isn't evidence

# Columns and indexes every rebuilt person_clusters table gets (mirrors migrations 0001-0003).
# Computed in the CREATE TABLE AS itself: adding them afterwards rewrote the table once per column.
CLUSTER_COLUMNS = [
    "to_tsvector('simple', l.name_norm) AS name_tsv",
    "np_first_name(l.name_norm) AS first_name",
    "np_last_name(l.name_norm) AS last_name",
    "to_tsvector('simple', np_soundex_tokens(l.name_norm)) AS sound_tsv",
    # Banks, trust companies and firms listed as officers (app/institutions.py).
    f"(l.name_norm ~ '{candidate_regex()}' AND np_institution(l.name_norm)) AS is_institution",
]
CLUSTER_INDEXES = [
    "USING gin (name_tsv)",
    "USING gin (sound_tsv)",
    "USING gin (states)",
    "(name_norm)",
    "(name_norm text_pattern_ops)",
    "(last_name, first_name)",
    "(first_name)",
    "(first_year, last_year)",
    "(max_comp)",
    "(n_filings DESC)",
    "(is_institution) WHERE is_institution",
]

# fl_key = "first last suffix" (middle names dropped), written as plain expressions so
# Postgres doesn't call a function per row: substring() takes the last non-suffix word.


class UnionFind:
    def __init__(self):
        self.parent: dict[int, int] = {}
        self.middles: dict[int, set] = {}

    def add(self, uid: int, middle: str) -> None:
        if uid not in self.parent:
            self.parent[uid] = uid
            self.middles[uid] = {middle} if middle else set()

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    @staticmethod
    def compatible(middles: set) -> bool:
        if len(middles) <= 1:
            return True
        initials = {m[0] for m in middles}
        full = {m for m in middles if len(m.replace(" ", "")) > 1}
        return len(initials) == 1 and len(full) <= 1

    def union(self, a: int, b: int, force: bool = False) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        merged = self.middles[ra] | self.middles[rb]
        if not force and not self.compatible(merged):
            return False
        if ra > rb:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.middles[ra] = merged
        del self.middles[rb]
        return True


def run(status) -> None:
    status.phase = "cluster"
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("DROP TABLE IF EXISTS cl_units, cl_links, cl_map")
        # 0. People listed care of a bank ("Kristin Cupillari Co Wells Fargo") go by their own name.
        status.phase = "cluster: care-of names"
        renames = _care_of_renames(conn)
        if renames:
            with conn.cursor() as cur:
                cur.execute("CREATE TEMP TABLE co_names (old text PRIMARY KEY, new text) ON COMMIT DROP")
                db.copy_rows(cur, "co_names", ["old", "new"], ((o, n) for o, (n, _) in renames.items()))
                cur.execute("UPDATE people p SET name_norm = c.new FROM co_names c WHERE p.name_norm = c.old")
            conn.commit()
            status.emit(f"cluster: {len(renames):,} care-of names now go by the person's name")
        status.phase = "cluster: units"
        # 1. Units: one row per (normalized name, EIN).
        conn.execute("""
            CREATE UNLOGGED TABLE cl_units AS
            SELECT row_number() OVER (ORDER BY min(id)) AS uid, name_norm, ein,
                   min(tax_year) AS y0, max(tax_year) AS y1, count(*) AS n, min(id) AS min_pid,
                   split_part(name_norm, ' ', 1) || ' '
                       || substring(name_norm from '(\\S+)(?: (?:jr|sr|ii|iii|iv|v))?$') || ' '
                       || coalesce(substring(name_norm from ' (jr|sr|ii|iii|iv|v)$'), '') AS fl_key
            FROM people GROUP BY name_norm, ein
        """)
        conn.execute("CREATE INDEX ON cl_units (name_norm, ein)")
        conn.execute("CREATE INDEX ON cl_units (ein, fl_key)")
        conn.execute("CREATE INDEX ON cl_units (ein)")
        conn.execute("ANALYZE cl_units")
        conn.commit()

        uf = UnionFind()
        links: dict[int, list] = defaultdict(list)   # uid -> evidence entries
        org_names: dict[str, str] = {}

        def middle(name_norm: str) -> str:
            return name_parts(name_norm)[1]

        def link(u1, n1, u2, n2, ev):
            uf.add(u1, middle(n1))
            uf.add(u2, middle(n2))
            if uf.union(u1, u2):
                links[u1].append(ev)
                links[u2].append(ev)

        status.phase = "cluster: name variants"
        # 2. Name variants within one organization.
        rows = conn.execute("""
            SELECT a.uid, a.name_norm, b.uid, b.name_norm, a.ein
            FROM cl_units a JOIN cl_units b ON a.ein = b.ein AND a.fl_key = b.fl_key AND a.uid < b.uid
            WHERE a.fl_key NOT LIKE ' %%'
        """).fetchall()
        for u1, n1, u2, n2, ein in rows:
            link(u1, n1, u2, n2, {"r": "variant", "ein": ein, "names": [n1, n2]})

        status.phase = "cluster: related orgs"
        # 3a. Schedule R related organizations.
        rows = conn.execute("""
            WITH pairs AS (SELECT DISTINCT least(ein, related_ein) AS e1, greatest(ein, related_ein) AS e2
                           FROM related_orgs WHERE ein <> related_ein)
            SELECT a.uid, a.name_norm, b.uid, b.name_norm, p.e1, p.e2
            FROM pairs p JOIN cl_units a ON a.ein = p.e1 JOIN cl_units b ON b.ein = p.e2 AND b.name_norm = a.name_norm
        """).fetchall()
        for u1, n1, u2, n2, e1, e2 in rows:
            link(u1, n1, u2, n2, {"r": "related_org", "eins": [e1, e2]})

        status.phase = "cluster: addresses"
        # 3b. Shared organization address, or the same personal address on 990-PF rows.
        # Grouped by (address, name) and linked as a star, which stays linear even
        # when one trustee bank appears at the same address on thousands of filings.
        conn.execute(f"""
            CREATE TEMP TABLE addr_members AS
            WITH addr AS (
                SELECT ein, lower(regexp_replace(street, '[^A-Za-z0-9]+', '', 'g')) || ':' || left(zip, 5) AS k
                FROM organizations WHERE street IS NOT NULL AND zip IS NOT NULL
            ), grp AS (
                SELECT k FROM addr GROUP BY k HAVING count(*) BETWEEN 2 AND {ADDRESS_GROUP_MAX}
            )
            SELECT addr.k, addr.ein FROM addr JOIN grp USING (k)
        """)
        conn.execute("ANALYZE addr_members")
        rows = conn.execute("""
            SELECT u.name_norm, array_agg(u.uid ORDER BY u.ein), array_agg(u.ein ORDER BY u.ein), 'org'
            FROM addr_members m JOIN cl_units u ON u.ein = m.ein
            GROUP BY m.k, u.name_norm HAVING count(*) >= 2
            UNION ALL
            SELECT p.name_norm, array_agg(u.uid ORDER BY u.ein), array_agg(u.ein ORDER BY u.ein), 'person'
            FROM (SELECT DISTINCT name_norm, ein,
                         lower(regexp_replace(street, '[^A-Za-z0-9]+', '', 'g')) || ':' || left(zip, 5) AS k
                  FROM people WHERE street IS NOT NULL AND zip IS NOT NULL) p
            JOIN cl_units u ON u.name_norm = p.name_norm AND u.ein = p.ein
            GROUP BY p.k, p.name_norm HAVING count(*) >= 2
        """).fetchall()
        for name, uids, eins, kind in rows:
            for u2, e2 in zip(uids[1:], eins[1:]):
                link(uids[0], name, u2, name, {"r": "address", "kind": kind, "eins": [eins[0], e2]})

        status.phase = "cluster: co-board"
        # 3c. Co-board overlap: org pairs seeded by uncommon shared names, then
        # every name they share counts. A shared name links when 2+ others are shared too.
        conn.execute(f"""
            CREATE TEMP TABLE seed AS
            WITH grp AS (SELECT name_norm, array_agg(ein) AS eins FROM cl_units GROUP BY name_norm
                         HAVING count(*) BETWEEN 2 AND {COMMON_NAME_EINS})
            SELECT a.e AS e1, b.e AS e2 FROM grp, unnest(eins) a(e), unnest(eins) b(e)
            WHERE a.e < b.e GROUP BY 1, 2 HAVING count(*) >= 2
        """)
        conn.execute("ANALYZE seed")
        conn.execute("""CREATE TEMP TABLE seed_names AS
                        SELECT s.e1, s.e2, a.name_norm FROM seed s JOIN cl_units a ON a.ein = s.e1""")
        conn.execute("ANALYZE seed_names")
        rows = conn.execute("""
            SELECT s.e1, s.e2, array_agg(s.name_norm ORDER BY s.name_norm)
            FROM seed_names s JOIN cl_units b ON b.name_norm = s.name_norm AND b.ein = s.e2
            GROUP BY s.e1, s.e2 HAVING count(*) >= 3
        """).fetchall()
        pair_names = [(e1, e2, names) for e1, e2, names in rows]
        need = {(n, e) for e1, e2, names in pair_names for n in names for e in (e1, e2)}
        uid_of = {}
        if need:
            cur = conn.cursor()
            cur.execute("CREATE TEMP TABLE need (name_norm text, ein text)")
            db.copy_rows(cur, "need", ["name_norm", "ein"], need)
            for uid, n, e in conn.execute("SELECT u.uid, u.name_norm, u.ein FROM cl_units u JOIN need USING (name_norm, ein)"):
                uid_of[(n, e)] = uid
        for e1, e2, names in pair_names:
            for n in names:
                others = [x for x in names if x != n][:4]
                link(uid_of[(n, e1)], n, uid_of[(n, e2)], n,
                     {"r": "co_board", "eins": [e1, e2], "with": others, "n_shared": len(names) - 1})

        status.phase = "cluster: institutions"
        # 3d. One record per institution: same key once role/legal suffixes are dropped.
        rows = conn.execute(f"""
            SELECT np_institution_key(name_norm) AS k, array_agg(uid ORDER BY uid), array_agg(DISTINCT name_norm)
            FROM cl_units WHERE name_norm ~ '{candidate_regex()}' AND np_institution(name_norm)
            GROUP BY 1 HAVING count(*) > 1
        """).fetchall()
        for key, uids, names in rows:
            ev = {"r": "same_institution", "key": key, "n": len(uids), "names": sorted(names)[:12]}
            for u in uids:
                uf.add(u, "")
            for u in uids[1:]:
                uf.union(uids[0], u, force=True)
            # One evidence entry per institution, not one per member.
            links[uids[0]].append(ev)

        # Write uid -> root and evidence.
        cur = conn.cursor()
        cur.execute("CREATE UNLOGGED TABLE cl_map (uid bigint PRIMARY KEY, root bigint, links jsonb)")
        db.copy_rows(cur, "cl_map", ["uid", "root", "links"],
                     ((uid, uf.find(uid), json.dumps(links.get(uid) or [])) for uid in uf.parent))
        conn.commit()
        status.emit(f"cluster: {len(uf.parent):,} linked units, {len(uf.middles):,} merged groups")

        status.phase = "cluster: building tables"
        # Refresh the given-name list the institution rule consults (from the current clusters).
        conn.execute(given_names_sql())
        conn.commit()

        # 4. Build the new tables beside the live ones.
        conn.execute("DROP TABLE IF EXISTS person_cluster_members_new, person_clusters_new")
        conn.execute("""
            CREATE TABLE cl_cluster AS
            SELECT u.uid, coalesce(r.cluster_id, u.min_pid) AS cluster_id, u.name_norm, u.ein, u.y0, u.y1, u.n,
                   m.links
            FROM cl_units u
            LEFT JOIN cl_map m ON m.uid = u.uid
            LEFT JOIN (SELECT m2.root, min(u2.min_pid) AS cluster_id FROM cl_map m2
                       JOIN cl_units u2 ON u2.uid = m2.uid GROUP BY m2.root) r ON r.root = m.root
        """)
        conn.execute("CREATE INDEX ON cl_cluster (name_norm, ein)")
        # Members only: the evidence lives on the cluster. Stored in cluster order, so a
        # person page reads its rows from adjacent pages.
        conn.execute("""
            CREATE TABLE person_cluster_members_new AS
            SELECT p.id AS person_id, c.cluster_id
            FROM people p JOIN cl_cluster c ON c.name_norm = p.name_norm AND c.ein = p.ein
            ORDER BY c.cluster_id, p.id
        """)
        conn.execute("ALTER TABLE person_cluster_members_new ADD PRIMARY KEY (person_id)")
        conn.execute("CREATE INDEX ON person_cluster_members_new (cluster_id)")
        conn.commit()
        conn.execute("CREATE TABLE person_clusters_new AS " + summary_sql(
            "person_cluster_members_new",
            f"""(SELECT cluster_id, jsonb_agg(DISTINCT e) AS evidence FROM (
                    SELECT c.cluster_id, e FROM cl_cluster c, jsonb_array_elements(c.links) e
                    WHERE c.links IS NOT NULL
                    UNION ALL
                    {_CARE_OF_EVIDENCE}
                ) x GROUP BY cluster_id)"""))
        for ddl in CLUSTER_INDEXES:
            conn.execute(f"CREATE INDEX ON person_clusters_new {ddl}")
        if db.has_extension(conn, "pg_trgm"):
            conn.execute("CREATE INDEX ON person_clusters_new USING gin (name_norm gin_trgm_ops)")
            conn.execute("CREATE INDEX ON person_clusters_new USING gin (last_name gin_trgm_ops)")
        conn.execute("ANALYZE person_clusters_new")
        conn.execute("ANALYZE person_cluster_members_new")
        conn.commit()

        status.phase = "cluster: swap"
        # 5. Swap.
        conn.execute("SET lock_timeout = '30s'")
        conn.execute("ALTER TABLE person_clusters RENAME TO person_clusters_old")
        conn.execute("ALTER TABLE person_cluster_members RENAME TO person_cluster_members_old")
        conn.execute("ALTER TABLE person_clusters_new RENAME TO person_clusters")
        conn.execute("ALTER TABLE person_cluster_members_new RENAME TO person_cluster_members")
        conn.commit()
        # CASCADE: leaderboard views built on the old tables go too; boards.refresh() (run right after
        # every re-cluster) rebuilds any board whose view is missing.
        conn.execute("DROP TABLE person_clusters_old, person_cluster_members_old, cl_units, cl_map, cl_cluster CASCADE")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM person_clusters").fetchone()[0]
        db.progress(conn, "cluster", "done", kind="cluster", rows=n)
        conn.commit()
    status.emit(f"cluster: {n:,} person clusters live")
    search_table.build(status)

def summary_sql(members: str, evidence: str) -> str:
    """SELECT producing person_clusters rows from a members table (person_id, cluster_id).

    `evidence` is a relation with (cluster_id, evidence jsonb). Shared by the full
    rebuild and merge_institutions(). Columns: CLUSTER_SELECT_COLUMNS.
    """
    columns = ", ".join(CLUSTER_COLUMNS)
    return f"""
            WITH rows AS (
                SELECT m.cluster_id, p.id, p.ein, p.tax_year, p.title, p.name_raw, p.name_norm, f.state,
                       f.org_name, p.filing_id, f.superseded,
                       coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total
                FROM {members} m JOIN people p ON p.id = m.person_id
                JOIN filings f ON f.id = p.filing_id
            ), per_org AS (
                SELECT cluster_id, ein, max(tax_year) AS last_year,
                       (array_agg(org_name ORDER BY tax_year DESC NULLS LAST))[1] AS org_name
                FROM rows GROUP BY cluster_id, ein
            ), orgs AS (
                SELECT cluster_id, (array_agg(org_name ORDER BY last_year DESC NULLS LAST, org_name))[1:5] AS orgs
                FROM per_org GROUP BY cluster_id
            ), latest AS (
                SELECT DISTINCT ON (cluster_id) cluster_id, name_raw, name_norm, title
                FROM rows ORDER BY cluster_id, tax_year DESC NULLS LAST, id DESC
            ), agg AS (
                SELECT cluster_id, count(DISTINCT filing_id) FILTER (WHERE NOT superseded) AS n_filings,
                       count(DISTINCT ein) AS n_orgs, min(tax_year) AS first_year, max(tax_year) AS last_year,
                       max(total) AS max_comp,
                       array_agg(DISTINCT state ORDER BY state) FILTER (WHERE state IS NOT NULL) AS states
                FROM rows GROUP BY cluster_id
            )
            SELECT a.cluster_id AS id,
                   CASE WHEN l.name_raw = upper(l.name_raw) THEN initcap(l.name_raw) ELSE l.name_raw END AS display_name,
                   l.name_norm, a.n_filings, a.n_orgs, a.first_year, a.last_year, a.max_comp, a.states,
                   o.orgs, l.title AS latest_title, ev.evidence, {columns}
            FROM agg a JOIN latest l USING (cluster_id) JOIN orgs o USING (cluster_id)
            LEFT JOIN {evidence} ev USING (cluster_id)
    """


# Column order of summary_sql(), for INSERTs into the live table.
CLUSTER_SELECT_COLUMNS = ["id", "display_name", "name_norm", "n_filings", "n_orgs", "first_year", "last_year",
                          "max_comp", "states", "orgs", "latest_title", "evidence", "name_tsv", "first_name",
                          "last_name", "sound_tsv", "is_institution"]


def merge_institutions(status) -> int:
    """Merge institution clusters sharing a key on the live tables, in one transaction.

    For data clustered before the institution rule existed; run() applies the rule
    on every rebuild. Merged-away ids still resolve through person_cluster_members.
    """
    status.phase = "merge institutions"
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("""
            CREATE TEMP TABLE mg ON COMMIT DROP AS
            SELECT id AS old_id, min(id) OVER w AS new_id, np_institution_key(name_norm) AS key,
                   count(*) OVER w AS n, display_name
            FROM person_clusters WHERE is_institution
            WINDOW w AS (PARTITION BY np_institution_key(name_norm))
        """)
        conn.execute("DELETE FROM mg WHERE n = 1")
        n_groups = conn.execute("SELECT count(DISTINCT new_id) FROM mg").fetchone()[0]
        conn.execute("""
            CREATE TEMP TABLE mev ON COMMIT DROP AS
            SELECT g.new_id AS cluster_id,
                   coalesce((SELECT jsonb_agg(DISTINCT e) FROM mg g2 JOIN person_clusters c ON c.id = g2.old_id,
                                    jsonb_array_elements(c.evidence) e WHERE g2.new_id = g.new_id), '[]'::jsonb)
                   || jsonb_build_array(jsonb_build_object(
                          'r', 'same_institution', 'key', g.key, 'n', count(*),
                          'names', (array_agg(DISTINCT lower(g.display_name)))[1:12])) AS evidence
            FROM mg g GROUP BY g.new_id, g.key
        """)
        conn.execute("""UPDATE person_cluster_members m SET cluster_id = g.new_id
                        FROM mg g WHERE m.cluster_id = g.old_id AND g.old_id <> g.new_id""")
        conn.execute("""CREATE TEMP TABLE mm ON COMMIT DROP AS
                        SELECT m.person_id, m.cluster_id FROM person_cluster_members m
                        WHERE m.cluster_id IN (SELECT DISTINCT new_id FROM mg)""")
        conn.execute("DELETE FROM person_clusters WHERE id IN (SELECT old_id FROM mg)")
        cols = ", ".join(CLUSTER_SELECT_COLUMNS)
        conn.execute(f"INSERT INTO person_clusters ({cols}) SELECT {cols} FROM ("
                     + summary_sql("mm", "mev") + ") s")
        conn.commit()
        conn.execute("ANALYZE person_clusters")
        conn.commit()
    status.emit(f"merge institutions: {n_groups:,} institutions merged")
    search_table.build(status)
    return n_groups


# Evidence for people whose filing listed them care of a bank (their raw name names the bank).
_CARE_OF_EVIDENCE = f"""
    SELECT m.cluster_id, jsonb_build_object(
               'r', 'care_of', 'bank', regexp_replace(substring(lower(p.name_raw) from '{care_of_candidate_regex()}'),
                                                      '(\\S)(bank|fargo|mellon|trust|stanley)', '\\1 \\2'),
               'listed_as', p.name_raw) AS e
    FROM people p JOIN person_cluster_members_new m ON m.person_id = p.id
    WHERE lower(p.name_raw) ~ '{care_of_candidate_regex()}' AND p.name_norm !~ '{care_of_candidate_regex()}'
"""


def _care_of_renames(conn) -> dict[str, tuple[str, str]]:
    """{current name_norm: (person name, bank)} for people listed care of a bank."""
    given = {r[0] for r in conn.execute("SELECT name FROM given_names")}
    rows = conn.execute(f"SELECT DISTINCT name_norm FROM people WHERE name_norm ~ '{care_of_candidate_regex()}'").fetchall()
    out = {}
    for (n,) in rows:
        hit = care_of_person(n, given)
        if hit and hit[0] != n:
            out[n] = hit
    return out


def split_care_of(status, conn=None) -> int:
    """Give people listed care of a bank ("Kristin Cupillari Co Wells Fargo") their own name
    and their own person record, on the live tables in one transaction.

    Each record moves to an existing person with the same name at the same EIN when
    there is one, otherwise to a new person; the bank keeps the rest. Run by
    load.py split-care-of and before every cluster rebuild (for name fixes only).
    """
    status.phase = "split care-of people"
    own = conn is None
    conn = conn or db.connect()
    try:
        renames = _care_of_renames(conn)
        if not renames:
            return 0
        cur = conn.cursor()
        cur.execute("CREATE TEMP TABLE co_names (old text PRIMARY KEY, new text, bank text) ON COMMIT DROP")
        db.copy_rows(cur, "co_names", ["old", "new", "bank"], ((o, n, b) for o, (n, b) in renames.items()))
        # The rows to move, with their current cluster.
        cur.execute("""CREATE TEMP TABLE co_rows ON COMMIT DROP AS
                       SELECT p.id, p.ein, p.name_raw, c.new, c.bank, m.cluster_id AS old_cluster
                       FROM people p JOIN co_names c ON c.old = p.name_norm
                       LEFT JOIN person_cluster_members m ON m.person_id = p.id""")
        cur.execute("UPDATE people p SET name_norm = c.new FROM co_names c WHERE p.name_norm = c.old")
        # Target: an existing person with the new name at the same EIN, else the smallest moved id.
        cur.execute("""CREATE TEMP TABLE co_target ON COMMIT DROP AS
                       SELECT r.id, coalesce(
                           (SELECT min(m.cluster_id) FROM people p JOIN person_cluster_members m ON m.person_id = p.id
                             WHERE p.name_norm = r.new AND p.ein = r.ein AND p.id NOT IN (SELECT id FROM co_rows)),
                           min(r.id) OVER (PARTITION BY r.new, r.ein)) AS new_cluster
                       FROM co_rows r""")
        # A cluster's id is its smallest member; when that member moves out, the rest get a new id.
        cur.execute("""CREATE TEMP TABLE co_renumber ON COMMIT DROP AS
                       SELECT r.old_cluster, (SELECT min(m.person_id) FROM person_cluster_members m
                                              WHERE m.cluster_id = r.old_cluster
                                                AND m.person_id NOT IN (SELECT id FROM co_rows)) AS new_id
                       FROM co_rows r WHERE r.id = r.old_cluster""")
        cur.execute("DELETE FROM co_renumber WHERE new_id IS NULL")
        cur.execute("""UPDATE person_cluster_members m SET cluster_id = n.new_id FROM co_renumber n
                       WHERE m.cluster_id = n.old_cluster AND m.person_id NOT IN (SELECT id FROM co_rows)""")
        touched = {x[0] for x in cur.execute(
            "SELECT old_cluster FROM co_rows WHERE old_cluster IS NOT NULL UNION SELECT new_cluster FROM co_target"
            " UNION SELECT new_id FROM co_renumber")}
        cur.execute("""UPDATE person_cluster_members m SET cluster_id = t.new_cluster
                       FROM co_target t WHERE m.person_id = t.id""")
        cur.execute("""INSERT INTO person_cluster_members (person_id, cluster_id)
                       SELECT t.id, t.new_cluster FROM co_target t
                       WHERE NOT EXISTS (SELECT 1 FROM person_cluster_members m WHERE m.person_id = t.id)""")
        # Evidence: keep each surviving cluster's, and record why the moved rows are individuals.
        cur.execute("""CREATE TEMP TABLE co_ev ON COMMIT DROP AS
                       SELECT x.cluster_id,
                              coalesce((SELECT evidence FROM person_clusters c
                                        WHERE c.id = coalesce((SELECT n.old_cluster FROM co_renumber n
                                                               WHERE n.new_id = x.cluster_id), x.cluster_id)),
                                       '[]'::jsonb)
                              || coalesce((SELECT jsonb_agg(DISTINCT jsonb_build_object('r', 'care_of', 'bank', r.bank,
                                                                 'listed_as', r.name_raw))
                                           FROM co_target t JOIN co_rows r USING (id) WHERE t.new_cluster = x.cluster_id),
                                          '[]'::jsonb) AS evidence
                       FROM unnest(%s::bigint[]) AS x(cluster_id)""", (list(touched),))
        cur.execute("""CREATE TEMP TABLE co_members ON COMMIT DROP AS
                       SELECT person_id, cluster_id FROM person_cluster_members WHERE cluster_id = ANY(%s)""",
                    (list(touched),))
        cur.execute("DELETE FROM person_clusters WHERE id = ANY(%s)", (list(touched),))
        cols = ", ".join(CLUSTER_SELECT_COLUMNS)
        cur.execute(f"INSERT INTO person_clusters ({cols}) SELECT {cols} FROM ("
                    + summary_sql("co_members", "co_ev") + ") s")
        # Display the person's name, not "... Co Wells Fargo".
        cur.execute(f"""UPDATE person_clusters SET display_name = initcap(name_norm)
                        WHERE id = ANY(%s) AND NOT is_institution
                          AND lower(display_name) ~ '{care_of_candidate_regex()}'""", (list(touched),))
        conn.commit()
        status.emit(f"split care-of people: {len(renames):,} names, {len(touched):,} person records updated")
        if own:
            search_table.build(status)
        return len(renames)
    finally:
        if own:
            conn.close()


def slim_members(status) -> int:
    """Rewrite person_cluster_members as (person_id, cluster_id) only, in cluster order.

    The old per-member evidence JSON (about 12 GB) duplicated what the clusters and the
    rows already say. Built beside the live table and swapped in; run under the loader lock.
    """
    status.phase = "slim members: copy"
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("SET maintenance_work_mem = '1GB'")
        conn.execute("DROP TABLE IF EXISTS person_cluster_members_slim")
        conn.execute("""CREATE TABLE person_cluster_members_slim AS
                        SELECT person_id, cluster_id FROM person_cluster_members ORDER BY cluster_id, person_id""")
        conn.commit()
        status.phase = "slim members: indexes"
        conn.execute("ALTER TABLE person_cluster_members_slim ADD PRIMARY KEY (person_id)")
        conn.execute("CREATE INDEX ON person_cluster_members_slim (cluster_id)")
        conn.execute("ANALYZE person_cluster_members_slim")
        conn.commit()
        n_old = conn.execute("SELECT count(*) FROM person_cluster_members").fetchone()[0]
        n_new = conn.execute("SELECT count(*) FROM person_cluster_members_slim").fetchone()[0]
        if n_old != n_new:
            raise RuntimeError(f"slim members: row counts differ ({n_old:,} vs {n_new:,}); live table untouched")
        status.phase = "slim members: swap"
        conn.execute("SET lock_timeout = '30s'")
        conn.execute("ALTER TABLE person_cluster_members RENAME TO person_cluster_members_fat")
        conn.execute("ALTER TABLE person_cluster_members_slim RENAME TO person_cluster_members")
        conn.commit()
        # Leaderboard views compiled against the old table go with it; rebuild them after (load.py boards).
        conn.execute("DROP TABLE person_cluster_members_fat CASCADE")
        conn.commit()
    status.emit(f"slim members: {n_new:,} rows, evidence column dropped")
    return n_new
