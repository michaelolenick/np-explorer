"""Form D related persons, sorted into people and organizations (owner, 2026-10-23).

Form D lists "related persons" with a first, middle and last name. Entities (a fund's general partner, a
management company) are entered with "n/a" as the first name, or blank, and come out as "n/a Inspired Capital
Partners GP I, LLC". Each related person is classified:

- entity: a first name of "n/a" (or none), or a name with a business word (LLC, LP, Inc, Partners, Fund, GP, ...);
  shown without the "n/a" and keyed by its normalized business name (loader.recalls.core), so the same GP across
  filings is one organization;
- person: everyone else, keyed by normalized name and state, so the same name in two states stays two people.

sec_formd_parties keeps one row per key with a stable id (its page: /corporate/entity/<slug>-<id> or
/corporate/fund-person/<slug>-<id>); sec_formd_people_party maps every related-person row to its party. Rebuilt after
each Form D load; ids never change for a key already seen.

Usage: .venv/bin/python -m loader.formd_parties
"""

from __future__ import annotations

import re
import time

from loader import db

NA = re.compile(r"^\s*(?:n/?a|none|null|-+)\s+|\s+(?:n/?a|none)\s*$", re.I)
ENTITY = re.compile(r"\b(?:l\.?l\.?c|l\.?l\.?p|l\.?p|inc|incorporated|corp|corporation|company|partners|"
                    r"partnership|fund|funds|gp|ltd|limited|holdings|trust|management|advisors|advisers|capital|"
                    r"ventures|group|lllp|plc|s\.?a|n\.?v|ag|gmbh|foundation)\b\.?", re.I)


def classify(raw: str) -> tuple[str, str]:
    """("entity" | "person", the name to show)."""
    raw = re.sub(r"\s+", " ", raw or "").strip()
    na = bool(NA.search(raw)) or raw.lower().startswith("n/a")
    name = NA.sub("", raw).strip(" ,")
    if na or ENTITY.search(name):
        return "entity", name
    return "person", name


def clean_text(s: str | None) -> str | None:
    """Relationship and clarification text: doubled quotes to single, stray quotes around the whole text dropped."""
    if not s:
        return s
    s = s.strip().replace('""', '"')
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].strip()
    if s.count('"') == 1:
        s = s.replace('"', "")
    return s


def build(status=print) -> dict:
    from app.names import normalize_name
    from loader.recalls import core
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '512MB'")
        rows = conn.execute("""SELECT p.accession, p.seq, p.name, p.state, d.filing_date
                               FROM sec_formd_people p JOIN sec_formd d USING (accession)""").fetchall()
        parties: dict[str, list] = {}
        mapping = []
        for acc, seq, raw, state, filed in rows:
            kind, name = classify(raw)
            if not name:
                continue
            if kind == "entity":
                c = core(name)
                if not c:
                    continue
                key, norm, st = "e:" + c, c, None
            else:
                n = normalize_name(name)
                if not n:
                    continue
                st = (state or "").upper()[:2] or None
                key, norm = f"p:{n}|{st or ''}", n
            p = parties.get(key)
            if p is None:
                parties[key] = p = [kind, name, st, norm, 0, filed]
            p[4] += 1
            if filed and (not p[5] or filed > p[5]):
                p[5], p[1] = filed, name             # the name as written on the latest filing
            mapping.append((acc, seq, key))
        conn.execute("CREATE TEMP TABLE np (kind text, key text, name text, state text, name_norm text, filings int, last_date date)")
        with conn.cursor() as cur, cur.copy("COPY np FROM STDIN") as cp:
            for key, (kind, name, st, norm, n, last) in parties.items():
                cp.write_row((kind, key, name[:300], st, norm[:300], n, last))
        conn.execute("""INSERT INTO sec_formd_parties (kind, key, name, state, name_norm, filings, last_date)
                        SELECT kind, key, name, state, name_norm, filings, last_date FROM np
                        ON CONFLICT (key) DO UPDATE SET name = excluded.name, filings = excluded.filings,
                            last_date = excluded.last_date""")
        conn.execute("CREATE TEMP TABLE nm (accession text, seq int, key text)")
        with conn.cursor() as cur, cur.copy("COPY nm FROM STDIN") as cp:
            for r in mapping:
                cp.write_row(r)
        conn.execute("DROP TABLE IF EXISTS sec_formd_people_party_new")
        conn.execute("""CREATE TABLE sec_formd_people_party_new AS
                        SELECT nm.accession, nm.seq, p.id AS party_id FROM nm JOIN sec_formd_parties p USING (key)""")
        conn.execute("ALTER TABLE sec_formd_people_party_new ADD PRIMARY KEY (accession, seq)")
        conn.execute("CREATE INDEX ON sec_formd_people_party_new (party_id)")
        db.swap_table(conn, "sec_formd_people_party")
        # A person's page on the site: the same full name (with a middle name, initial or particle, three parts or
        # more) held by exactly one person on the site, in any state. Two-part names link only filing by filing,
        # by name and state (sec_person_links).
        conn.execute("ALTER TABLE sec_formd_parties ADD COLUMN IF NOT EXISTS cluster_id bigint")
        conn.execute("""UPDATE sec_formd_parties p SET cluster_id = u.id
                        FROM (SELECT name_norm, min(id) AS id FROM person_clusters WHERE NOT is_institution
                              AND name_norm ~ '^\\S+ \\S+ \\S+' GROUP BY 1 HAVING count(*) = 1) u
                        WHERE p.kind = 'person' AND p.name_norm = u.name_norm
                          AND p.cluster_id IS DISTINCT FROM u.id""")
        conn.commit()
        for t in ("sec_formd_parties", "sec_formd_people_party"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
    n_e = sum(1 for v in parties.values() if v[0] == "entity")
    out = {"rows": len(mapping), "people": len(parties) - n_e, "entities": n_e}
    status(f"formd parties: {len(mapping):,} related-person rows; {out['people']:,} people, {n_e:,} organizations "
           f"({time.time() - t0:.0f}s)")
    return out


if __name__ == "__main__":
    build()
