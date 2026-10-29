"""Form D and Form ADV people in person search (owner, 2026-10-29).

Person search used to find only people on 990s; anyone whose only public role is at a private fund or an investment
adviser was invisible. Two tables fix that:

- adv_people: one row per person on Form ADV Schedules A and B (direct and indirect owners, executive officers),
  keyed like Form D people (sec_formd_parties): normalized name and the adviser's state, so the same name in two
  states stays two people. Stable ids (the page: /corporate/adviser-person/<slug>-<id>). Someone with a Form D page
  under the same key uses that page instead (formd_party_id), which already lists their ADV roles.
- fund_people: the search index. One row per Form D person (sec_formd_parties, kind person) and per ADV person
  without a Form D page: name, roles, the funds or advisers (newest first), first and last filing dates, the person
  on the site (cluster_id) when linked, and the name's words for search.

Rebuilt every night (scripts/nightly.sh) after the Form D and ADV loads: re-clustering can renumber the people on the
site they link to.

Usage: .venv/bin/python -m loader.fund_people
"""

from __future__ import annotations

import time

from loader import db

# Form ADV Schedule A/B ownership codes, in words.
OWNERSHIP = {"A": "owns under 5%", "B": "owns 5-10%", "C": "owns 10-25%", "D": "owns 25-50%", "E": "owns 50-75%",
             "F": "owns 75% or more"}


def display_name(raw: str) -> str:
    """ADV writes individuals "HSU, WILLIAM" or "SMITH, JOHN, A": show "William Hsu", "John A Smith"."""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if len(parts) >= 2:
        parts = parts[1:] + parts[:1]
    name = " ".join(" ".join(parts).split())
    return name.title() if name.isupper() or name.islower() else name


def build(status=print) -> dict:
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        conn.execute("""CREATE TABLE IF NOT EXISTS adv_people (
                            id bigserial PRIMARY KEY, key text UNIQUE NOT NULL, name text NOT NULL, name_norm text,
                            state text, crds text[], first_year int, last_year int, formd_party_id bigint,
                            cluster_id bigint)""")
        rows = conn.execute("""
            SELECT 'p:' || o.name_norm || '|' || coalesce(upper(left(f.state, 2)), '') AS key, o.name_norm,
                   upper(left(f.state, 2)) AS state,
                   (array_agg(o.name ORDER BY o.year DESC NULLS LAST))[1] AS raw,
                   array_agg(DISTINCT o.crd) FILTER (WHERE o.crd IS NOT NULL) AS crds,
                   min(o.year) AS first_year, max(o.year) AS last_year
            FROM adv_owners o JOIN adv_filings f USING (filing_id)
            WHERE o.entity_kind = 'I' AND coalesce(o.name_norm, '') <> ''
            GROUP BY 1, 2, 3""").fetchall()
        conn.execute("""CREATE TEMP TABLE ap (key text, name text, name_norm text, state text, crds text[],
                                              first_year int, last_year int)""")
        with conn.cursor() as cur, cur.copy("COPY ap FROM STDIN") as cp:
            for key, norm, st, raw, crds, fy, ly in rows:
                cp.write_row((key, display_name(raw)[:300], norm[:300], st, crds, fy, ly))
        conn.execute("""INSERT INTO adv_people (key, name, name_norm, state, crds, first_year, last_year)
                        SELECT key, name, name_norm, state, crds, first_year, last_year FROM ap
                        ON CONFLICT (key) DO UPDATE SET name = excluded.name, crds = excluded.crds,
                            first_year = excluded.first_year, last_year = excluded.last_year""")
        # The Form D page under the same key, and the person on the site (adv_person_links, by adviser and name).
        conn.execute("""UPDATE adv_people a SET formd_party_id = p.id FROM sec_formd_parties p
                        WHERE p.key = a.key AND a.formd_party_id IS DISTINCT FROM p.id""")
        conn.execute("""UPDATE adv_people a SET cluster_id = l.cluster_id
                        FROM (SELECT a.id, min(l.cluster_id) AS cluster_id FROM adv_people a
                              JOIN adv_person_links l ON l.name_norm = a.name_norm AND l.crd = ANY(a.crds)
                              GROUP BY a.id) l
                        WHERE l.id = a.id AND a.cluster_id IS DISTINCT FROM l.cluster_id""")
        conn.commit()

        # Form D people: roles, issuers newest first, dates; plus their ADV roles under the same key.
        conn.execute("""CREATE TEMP TABLE fd_roles AS
                        SELECT x.party_id, array_agg(DISTINCT trim(r)) FILTER (WHERE trim(r) <> '') AS roles
                        FROM sec_formd_people_party x JOIN sec_formd_people p USING (accession, seq),
                             unnest(string_to_array(p.relationships, ',')) r
                        GROUP BY 1""")
        conn.execute("""CREATE TEMP TABLE fd_orgs AS
                        SELECT party_id, (array_agg(issuer_name ORDER BY last DESC))[1:5] AS orgs, count(*) AS n_orgs,
                               min(first) AS first_date, max(last) AS last_date, sum(n) AS n_filings
                        FROM (SELECT x.party_id, d.issuer_name, min(d.filing_date) AS first, max(d.filing_date) AS last,
                                     count(*) AS n
                              FROM sec_formd_people_party x JOIN sec_formd d USING (accession)
                              GROUP BY 1, 2) s
                        GROUP BY 1""")
        # ADV people: per adviser, their titles, highest ownership band and latest year; advisers newest first.
        conn.execute("""CREATE TEMP TABLE adv_pc AS
                        SELECT a.id, o.crd, max(o.year) AS last,
                               array_agg(DISTINCT initcap(o.title)) FILTER (WHERE o.title IS NOT NULL) AS titles,
                               max(o.ownership_code) FILTER (WHERE o.ownership_code IN ('A', 'B', 'C', 'D', 'E', 'F')) AS own
                        FROM adv_people a JOIN adv_owners o ON o.name_norm = a.name_norm AND o.crd = ANY(a.crds)
                        GROUP BY 1, 2""")
        conn.execute("""CREATE TEMP TABLE adv_name AS
                        SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name) AS name FROM adv_filings
                        ORDER BY crd, submitted DESC NULLS LAST""")
        conn.execute("""CREATE TEMP TABLE adv_roles AS
                        SELECT id, (array_agg(DISTINCT t))[1:4] AS roles FROM adv_pc, unnest(titles) t GROUP BY id""")
        conn.execute(f"""CREATE TEMP TABLE adv_orgs AS
                         SELECT pc.id, (array_agg(n.name ORDER BY pc.last DESC NULLS LAST))[1:5] AS orgs, r.roles,
                                CASE max(pc.own) {" ".join(f"WHEN '{k}' THEN '{v}'" for k, v in OWNERSHIP.items())} END
                                    AS ownership
                         FROM adv_pc pc JOIN adv_name n USING (crd) LEFT JOIN adv_roles r USING (id)
                         GROUP BY pc.id, r.roles""")
        conn.execute("DROP TABLE IF EXISTS fund_people_new")
        conn.execute("""CREATE TABLE fund_people_new AS
            SELECT 'formd'::text AS kind, p.id AS ref_id, p.name, p.name_norm, p.state,
                   coalesce(p.cluster_id, (SELECT l.cluster_id FROM sec_formd_people_party x
                                           JOIN sec_person_links l ON l.source = 'formd'
                                                AND l.key = x.accession || ':' || x.seq
                                           WHERE x.party_id = p.id LIMIT 1), a.cluster_id) AS cluster_id,
                   r.roles AS formd_roles, o.orgs AS formd_orgs, ao.roles AS adv_roles, ao.ownership AS adv_ownership,
                   ao.orgs AS adv_orgs, o.first_date, greatest(o.last_date, make_date(a.last_year, 12, 31)) AS last_date,
                   a.first_year AS adv_first_year, a.last_year AS adv_last_year,
                   o.n_filings::int AS n_filings, o.n_orgs::int + coalesce(cardinality(a.crds), 0) AS n_orgs
            FROM sec_formd_parties p
            LEFT JOIN fd_roles r ON r.party_id = p.id LEFT JOIN fd_orgs o ON o.party_id = p.id
            LEFT JOIN adv_people a ON a.formd_party_id = p.id LEFT JOIN adv_orgs ao ON ao.id = a.id
            WHERE p.kind = 'person' AND coalesce(p.name_norm, '') <> ''
            UNION ALL
            SELECT 'adv', a.id, a.name, a.name_norm, a.state, a.cluster_id, NULL, NULL, ao.roles, ao.ownership,
                   ao.orgs, make_date(a.first_year, 1, 1), make_date(a.last_year, 12, 31), a.first_year, a.last_year,
                   0, cardinality(a.crds)
            FROM adv_people a LEFT JOIN adv_orgs ao ON ao.id = a.id
            WHERE a.formd_party_id IS NULL""")
        conn.execute("ALTER TABLE fund_people_new ADD COLUMN name_tsv tsvector")
        conn.execute("UPDATE fund_people_new SET name_tsv = to_tsvector('simple', name_norm)")
        conn.execute("ALTER TABLE fund_people_new ADD PRIMARY KEY (kind, ref_id)")
        conn.execute("CREATE INDEX ON fund_people_new USING gin (name_tsv)")
        conn.execute("CREATE INDEX ON fund_people_new USING gin (name_norm gin_trgm_ops)")
        conn.execute("CREATE INDEX ON fund_people_new (name_norm)")
        conn.execute("CREATE INDEX ON fund_people_new (cluster_id) WHERE cluster_id IS NOT NULL")
        db.swap_table(conn, "fund_people")
        conn.commit()
        conn.execute("ANALYZE fund_people")
        conn.execute("ANALYZE adv_people")
        conn.commit()
        n = conn.execute("""SELECT count(*) FILTER (WHERE kind = 'formd') AS formd, count(*) FILTER (WHERE kind = 'adv') AS adv,
                                   count(cluster_id) AS linked FROM fund_people""").fetchone()
    out = {"formd": n[0], "adv": n[1], "linked": n[2]}
    status(f"fund people: {n[0]:,} Form D people, {n[1]:,} ADV-only people, {n[2]:,} linked to a person on the site "
           f"({time.time() - t0:.0f}s)")
    return out


if __name__ == "__main__":
    build()
