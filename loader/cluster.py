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
  4. Otherwise rows stay separate. A cluster never holds two conflicting middle
     names, so a bare "john smith" can't chain "john a smith" to "john b smith".

A cluster's id is the smallest people.id in it, so ids stay stable as years
are added; ids that disappear in a merge resolve through person_cluster_members.
The new tables are built beside the live ones and swapped in one transaction.
"""

from __future__ import annotations

import json
from collections import defaultdict

from app.names import name_parts
from loader import db

COMMON_NAME_EINS = 50     # names at more EINs than this don't seed co-board pairs
ADDRESS_GROUP_MAX = 20    # an address shared by more orgs than this (e.g. a registered agent) isn't evidence

FL_KEY_SQL = """
    CREATE OR REPLACE FUNCTION pg_temp.fl_key(n text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
        WITH a AS (SELECT string_to_array(n, ' ') AS t),
             b AS (SELECT CASE WHEN array_length(t, 1) > 1 AND t[array_length(t, 1)] IN ('jr','sr','ii','iii','iv','v')
                               THEN t[1:array_length(t, 1) - 1] ELSE t END AS core,
                          CASE WHEN array_length(t, 1) > 1 AND t[array_length(t, 1)] IN ('jr','sr','ii','iii','iv','v')
                               THEN t[array_length(t, 1)] ELSE '' END AS suf FROM a)
        SELECT core[1] || ' ' || core[array_length(core, 1)] || ' ' || suf FROM b
    $$;
"""


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

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        merged = self.middles[ra] | self.middles[rb]
        if not self.compatible(merged):
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
        conn.execute(FL_KEY_SQL)
        conn.execute("DROP TABLE IF EXISTS cl_units, cl_links, cl_map")
        # 1. Units: one row per (normalized name, EIN).
        conn.execute("""
            CREATE UNLOGGED TABLE cl_units AS
            SELECT row_number() OVER (ORDER BY min(id)) AS uid, name_norm, ein,
                   min(tax_year) AS y0, max(tax_year) AS y1, count(*) AS n, min(id) AS min_pid,
                   pg_temp.fl_key(name_norm) AS fl_key
            FROM people GROUP BY name_norm, ein
        """)
        conn.execute("CREATE INDEX ON cl_units (name_norm, ein)")
        conn.execute("CREATE INDEX ON cl_units (ein, fl_key)")
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

        # 2. Name variants within one organization.
        rows = conn.execute("""
            SELECT a.uid, a.name_norm, b.uid, b.name_norm, a.ein
            FROM cl_units a JOIN cl_units b ON a.ein = b.ein AND a.fl_key = b.fl_key AND a.uid < b.uid
            WHERE a.fl_key NOT LIKE ' %%'
        """).fetchall()
        for u1, n1, u2, n2, ein in rows:
            link(u1, n1, u2, n2, {"r": "variant", "ein": ein, "names": [n1, n2]})

        # 3a. Schedule R related organizations.
        rows = conn.execute("""
            WITH pairs AS (SELECT DISTINCT least(ein, related_ein) AS e1, greatest(ein, related_ein) AS e2
                           FROM related_orgs WHERE ein <> related_ein)
            SELECT a.uid, a.name_norm, b.uid, b.name_norm, p.e1, p.e2
            FROM pairs p JOIN cl_units a ON a.ein = p.e1 JOIN cl_units b ON b.ein = p.e2 AND b.name_norm = a.name_norm
        """).fetchall()
        for u1, n1, u2, n2, e1, e2 in rows:
            link(u1, n1, u2, n2, {"r": "related_org", "eins": [e1, e2]})

        # 3b. Shared organization address, or the same personal address on 990-PF rows.
        rows = conn.execute(f"""
            WITH addr AS (
                SELECT ein, lower(regexp_replace(street, '[^A-Za-z0-9]+', '', 'g')) || ':' || left(zip, 5) AS k
                FROM organizations WHERE street IS NOT NULL AND zip IS NOT NULL
            ), grp AS (
                SELECT k FROM addr GROUP BY k HAVING count(*) BETWEEN 2 AND {ADDRESS_GROUP_MAX}
            ), pairs AS (
                SELECT DISTINCT a.ein AS e1, b.ein AS e2 FROM addr a JOIN grp USING (k)
                JOIN addr b ON b.k = a.k AND a.ein < b.ein
            )
            SELECT a.uid, a.name_norm, b.uid, b.name_norm, p.e1, p.e2, 'org'
            FROM pairs p JOIN cl_units a ON a.ein = p.e1 JOIN cl_units b ON b.ein = p.e2 AND b.name_norm = a.name_norm
            UNION ALL
            SELECT DISTINCT ua.uid, ua.name_norm, ub.uid, ub.name_norm, pa.ein, pb.ein, 'person'
            FROM people pa JOIN people pb
              ON pa.name_norm = pb.name_norm AND pa.ein < pb.ein
             AND left(pa.zip, 5) = left(pb.zip, 5)
             AND lower(regexp_replace(pa.street, '[^A-Za-z0-9]+', '', 'g'))
               = lower(regexp_replace(pb.street, '[^A-Za-z0-9]+', '', 'g'))
            JOIN cl_units ua ON ua.name_norm = pa.name_norm AND ua.ein = pa.ein
            JOIN cl_units ub ON ub.name_norm = pb.name_norm AND ub.ein = pb.ein
            WHERE pa.street IS NOT NULL AND pb.street IS NOT NULL AND pa.zip IS NOT NULL
        """).fetchall()
        for u1, n1, u2, n2, e1, e2, kind in rows:
            link(u1, n1, u2, n2, {"r": "address", "kind": kind, "eins": [e1, e2]})

        # 3c. Co-board overlap: org pairs seeded by uncommon shared names, then
        # every name they share counts. A shared name links when 2+ others are shared too.
        rows = conn.execute(f"""
            WITH pe AS (SELECT ein, name_norm FROM cl_units),
                 rare AS (SELECT name_norm FROM pe GROUP BY name_norm
                          HAVING count(*) BETWEEN 2 AND {COMMON_NAME_EINS}),
                 seed AS (SELECT a.ein AS e1, b.ein AS e2
                          FROM pe a JOIN rare USING (name_norm)
                          JOIN pe b ON b.name_norm = a.name_norm AND a.ein < b.ein
                          GROUP BY 1, 2 HAVING count(*) >= 2),
                 shared AS (SELECT s.e1, s.e2, a.name_norm
                            FROM seed s JOIN pe a ON a.ein = s.e1
                            JOIN pe b ON b.ein = s.e2 AND b.name_norm = a.name_norm)
            SELECT e1, e2, array_agg(name_norm ORDER BY name_norm) FROM shared
            GROUP BY e1, e2 HAVING count(*) >= 3
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

        # Write uid -> root and evidence.
        cur = conn.cursor()
        cur.execute("CREATE UNLOGGED TABLE cl_map (uid bigint PRIMARY KEY, root bigint, links jsonb)")
        db.copy_rows(cur, "cl_map", ["uid", "root", "links"],
                     ((uid, uf.find(uid), json.dumps(links.get(uid) or [])) for uid in uf.parent))
        conn.commit()
        status.emit(f"cluster: {len(uf.parent):,} linked units, {len(uf.middles):,} merged groups")

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
        conn.execute("""
            CREATE TABLE person_cluster_members_new AS
            SELECT p.id AS person_id, c.cluster_id,
                   jsonb_strip_nulls(jsonb_build_object(
                       'ein', c.ein, 'years', jsonb_build_array(c.y0, c.y1), 'n', c.n,
                       'links', CASE WHEN jsonb_array_length(coalesce(c.links, '[]')) > 0 THEN c.links END
                   )) AS evidence
            FROM people p JOIN cl_cluster c ON c.name_norm = p.name_norm AND c.ein = p.ein
        """)
        conn.execute("ALTER TABLE person_cluster_members_new ADD PRIMARY KEY (person_id)")
        conn.execute("CREATE INDEX ON person_cluster_members_new (cluster_id)")
        conn.commit()
        conn.execute("""
            CREATE TABLE person_clusters_new AS
            WITH rows AS (
                SELECT m.cluster_id, p.id, p.ein, p.tax_year, p.title, p.name_raw, p.name_norm, f.state,
                       f.org_name, p.filing_id, f.superseded,
                       coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total
                FROM person_cluster_members_new m JOIN people p ON p.id = m.person_id
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
                   o.orgs, l.title AS latest_title,
                   (SELECT jsonb_agg(DISTINCT e) FROM cl_cluster c, jsonb_array_elements(c.links) e
                     WHERE c.cluster_id = a.cluster_id AND c.links IS NOT NULL
                       AND jsonb_array_length(c.links) > 0) AS evidence
            FROM agg a JOIN latest l USING (cluster_id) JOIN orgs o USING (cluster_id)
        """)
        conn.execute("""ALTER TABLE person_clusters_new ADD COLUMN name_tsv tsvector
                        GENERATED ALWAYS AS (to_tsvector('simple', name_norm)) STORED""")
        conn.execute("ALTER TABLE person_clusters_new ADD PRIMARY KEY (id)")
        conn.execute("CREATE INDEX ON person_clusters_new USING gin (name_tsv)")
        conn.execute("CREATE INDEX ON person_clusters_new (name_norm)")
        if db.has_extension(conn, "pg_trgm"):
            conn.execute("CREATE INDEX ON person_clusters_new USING gin (name_norm gin_trgm_ops)")
        conn.execute("ANALYZE person_clusters_new")
        conn.execute("ANALYZE person_cluster_members_new")
        conn.commit()

        # 5. Swap.
        conn.execute("SET lock_timeout = '30s'")
        conn.execute("ALTER TABLE person_clusters RENAME TO person_clusters_old")
        conn.execute("ALTER TABLE person_cluster_members RENAME TO person_cluster_members_old")
        conn.execute("ALTER TABLE person_clusters_new RENAME TO person_clusters")
        conn.execute("ALTER TABLE person_cluster_members_new RENAME TO person_cluster_members")
        conn.commit()
        conn.execute("DROP TABLE person_clusters_old, person_cluster_members_old, cl_units, cl_map, cl_cluster")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM person_clusters").fetchone()[0]
    status.emit(f"cluster: {n:,} person clusters live")
