"""UK companies cross-referenced to the rest of FURP (owner, 2026-11-14), on the xref engine's rules: every link says how it was
made (`method`) and how sure it is (`confidence`); a name alone never links a UK company to a US one.

python -m loader.uk_companies_xref match      compute uk_companies.xmatch and psc_match (schema uk_companies only: invisible to prod)
python -m loader.uk_companies_xref publish    copy the matches into xlinks (linker 'ukco:<method>') and xref_counts; run after prod has the code
python -m loader.uk_companies_xref sample METHOD [--n 50]    a random sample of one method's matches, to judge precision
python -m loader.uk_companies_xref status

Methods
  charity_number     the company number on a Charity Commission register entry (uk.charity_main.company_number) equals the
                     company's number; no name needed (skipped when schema uk is absent)                                high
  biz_uk_home        a US state registry entity (biz_entities) with the same name core whose home jurisdiction is the UK
                     (England, Wales, Scotland, United Kingdom ...), at most three UK companies of that name     high
  biz_same_zip       a UK company whose registered office is in the US, and a US registry entity of the same name core in the
                     same ZIP code                                                                                           high
  biz_us_origin      a company registered in the UK whose country of origin is the United States, the same full name (legal form
                     included) as a US registry entity (not a Form 5500 sponsor row); at most 2 UK companies and 3 US entities of the name                                          medium
  sec_plc            an SEC filer whose name ends PLC / P.L.C. and a UK Public Limited Company of the same name core, each the
                     only one of its name                                                                                     high
  formd_uk           a Form D issuer located in the United Kingdom (state code X0) with the same name core as a UK company; high when
                     the issuer's city is also the company's registered town, else medium (at most 2 UK companies of the name)
  psc_person         a PSC who is an individual living in the US with the same full name (three or more parts) as the one
                     person page in FURP, in a state the person page lists: medium (FUZZY: a name and a state, not an identity)
SEC Exhibit 21 subsidiary lists are not loaded in FURP, so there is no subsidiary-list method yet.
"""

from __future__ import annotations

import argparse
import sys
import time

from loader import db

UKPAT = r"(united kingdom|england|great britain|scotland|wales|northern ireland|^u\.?k\.?$|^gb$)"

DDL = """
CREATE TABLE IF NOT EXISTS uk_companies.xmatch (
    company_number text NOT NULL, dst_kind text NOT NULL, dst_key text NOT NULL, dst_name text, dst_state text,
    method text NOT NULL, confidence text NOT NULL, evidence text,
    PRIMARY KEY (company_number, dst_kind, dst_key, method));
CREATE INDEX IF NOT EXISTS uk_xmatch_dst ON uk_companies.xmatch (dst_kind, dst_key);
CREATE TABLE IF NOT EXISTS uk_companies.psc_match (
    psc_id text NOT NULL, company_number text NOT NULL, cluster_id bigint NOT NULL, name text, state text, method text NOT NULL,
    confidence text NOT NULL, PRIMARY KEY (psc_id, company_number, cluster_id));
CREATE INDEX IF NOT EXISTS uk_psc_match_cluster ON uk_companies.psc_match (cluster_id);
"""


def _log(msg: str) -> None:
    from loader import uk_companies
    uk_companies._log("xref: " + msg)


def _run(conn, method: str, sql: str, params=None) -> int:
    t0 = time.time()
    conn.execute("DELETE FROM uk_companies.xmatch WHERE method = %s", (method,))
    n = conn.execute(sql, params or {}).rowcount
    conn.commit()
    _log(f"{method}: {n:,} matches in {time.time() - t0:.0f}s")
    return n


def match() -> None:
    from loader import offpeak
    offpeak.wait("uk companies cross-references", status=_log)
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        conn.execute("SET statement_timeout = 0")
        conn.execute("DROP TABLE IF EXISTS uk_cnt")
        conn.execute("""CREATE TEMP TABLE uk_cnt AS SELECT name_core, count(*) AS n FROM uk_companies.company
                        WHERE name_core IS NOT NULL AND length(name_core) >= 4 GROUP BY name_core""")
        conn.execute("CREATE UNIQUE INDEX ON uk_cnt (name_core)")
        conn.commit()
        has_uk = conn.execute("SELECT to_regclass('uk.charity_main') IS NOT NULL").fetchone()[0]
        if has_uk:
            _run(conn, "charity_number", """
                INSERT INTO uk_companies.xmatch
                SELECT c.company_number, 'uk_charity', m.reg_number::text, m.name, NULL, 'charity_number', 'high',
                       'company number ' || c.company_number || ' is on the Charity Commission register entry'
                FROM uk.charity_main m JOIN uk_companies.company c ON c.company_number = lpad(m.company_number, 8, '0')
                WHERE m.company_number ~ '^[A-Za-z0-9]{1,8}$'
                ON CONFLICT DO NOTHING""")
        _run(conn, "biz_uk_home", f"""
            INSERT INTO uk_companies.xmatch
            SELECT c.company_number, 'biz', b.state || ':' || b.entity_id, b.name, b.addr_state, 'biz_uk_home', 'high',
                   'same name; the ' || upper(b.state) || ' registry lists its home jurisdiction as ' || b.jurisdiction
            FROM biz_entities b JOIN uk_companies.company c ON c.name_core = b.name_core
            JOIN uk_cnt k ON k.name_core = c.name_core AND k.n <= 3
            WHERE b.jurisdiction ~* %(pat)s AND b.name_core IS NOT NULL AND length(b.name_core) >= 6
            ON CONFLICT DO NOTHING""", {"pat": UKPAT})
        _run(conn, "biz_same_zip", """
            INSERT INTO uk_companies.xmatch
            SELECT c.company_number, 'biz', b.state || ':' || b.entity_id, b.name, b.addr_state, 'biz_same_zip', 'high',
                   'same name and the same ZIP code, ' || left(b.zip, 5) || ', as the UK company''s registered office in the US'
            FROM uk_companies.company c JOIN biz_entities b ON b.name_core = c.name_core
            WHERE c.country ~* '(united states|^usa$|^us$|u\\.s\\.a|america)' AND c.postcode ~ '^\\d{5}'
              AND left(b.zip, 5) = left(c.postcode, 5) AND length(c.name_core) >= 4
            ON CONFLICT DO NOTHING""")
        _run(conn, "biz_us_origin", """
            INSERT INTO uk_companies.xmatch
            SELECT c.company_number, 'biz', b.state || ':' || b.entity_id, b.name, b.addr_state, 'biz_us_origin', 'medium',
                   'same full name, legal form included; the UK register lists the company''s country of origin as ' || c.country_of_origin
            FROM uk_companies.company c JOIN uk_cnt k ON k.name_core = c.name_core AND k.n <= 2
            JOIN biz_entities b ON b.name_core = c.name_core
            WHERE c.country_of_origin ~* '(united states|^usa$|^us$|america)' AND length(c.name_core) >= 8 AND b.source <> 'form5500'
              AND trim(regexp_replace(lower(b.name), '[^a-z0-9]+', ' ', 'g')) = trim(regexp_replace(lower(c.name), '[^a-z0-9]+', ' ', 'g'))
              AND (SELECT count(*) FROM (SELECT 1 FROM biz_entities b2 WHERE b2.name_core = c.name_core LIMIT 4) z) <= 3
            ON CONFLICT DO NOTHING""")
        _run(conn, "sec_plc", """
            INSERT INTO uk_companies.xmatch
            SELECT c.company_number, 'sec', x.key, x.name, NULL, 'sec_plc', 'high',
                   'same name; the SEC filer''s name ends PLC and the UK company is a Public Limited Company'
            FROM xref_names x JOIN uk_companies.company c ON c.name_core = x.core
            JOIN uk_cnt k ON k.name_core = c.name_core AND k.n <= 2
            WHERE x.kind = 'sec' AND x.name ~* '\\m(plc|p\\.l\\.c\\.)\\M\\W*$' AND c.category ILIKE 'public limited%%' AND c.status = 'Active'
              AND length(x.core) >= 5
              AND (SELECT count(*) FROM xref_names u WHERE u.kind = 'sec' AND u.core = x.core) = 1
            ON CONFLICT DO NOTHING""")
        _run(conn, "formd_uk", """
            INSERT INTO uk_companies.xmatch
            SELECT c.company_number, 'formd', x.key, x.name, NULL, 'formd_uk',
                   CASE WHEN upper(c.town) = upper(x.city) THEN 'high' ELSE 'medium' END,
                   'same name; Form D issuer located in the United Kingdom' ||
                   CASE WHEN upper(c.town) = upper(x.city) THEN ', in ' || x.city || ' like the company''s registered office' ELSE '' END
            FROM xref_names x JOIN uk_companies.company c ON c.name_core = x.core
            JOIN uk_cnt k ON k.name_core = c.name_core AND k.n <= 2
            WHERE x.kind = 'formd' AND length(x.core) >= 6
              AND EXISTS (SELECT 1 FROM sec_formd_offerings o WHERE o.cik = x.key AND o.state = 'X0')
              AND (SELECT count(*) FROM xref_names u WHERE u.kind = 'formd' AND u.core = x.core) <= 2
            ON CONFLICT DO NOTHING""")
        if conn.execute("SELECT to_regclass('uk_companies.psc_us_state') IS NOT NULL").fetchone()[0]:
            t0 = time.time()
            conn.execute("DELETE FROM uk_companies.psc_match")
            n = conn.execute("""
                INSERT INTO uk_companies.psc_match
                SELECT s.psc_id, s.company_number, p.id, p.display_name, s.state, 'psc_person', 'medium'
                FROM uk_companies.psc_us_state s JOIN person_clusters p ON p.name_norm = s.name_norm
                WHERE NOT coalesce(p.is_institution, false) AND array_length(string_to_array(s.name_norm, ' '), 1) >= 3
                  AND s.state = ANY(p.states)
                  AND (SELECT count(*) FROM (SELECT 1 FROM person_clusters p2 WHERE p2.name_norm = s.name_norm LIMIT 2) z) = 1
                ON CONFLICT DO NOTHING""").rowcount
            conn.commit()
            _log(f"psc_person: {n:,} matches in {time.time() - t0:.0f}s")
        conn.execute("""INSERT INTO uk_companies.meta (key, rows, loaded, checked, note)
                        VALUES ('xmatch', (SELECT count(*) FROM uk_companies.xmatch), now(), now(), 'matched')
                        ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""")
        conn.commit()


HOW = {"charity_number": "the company number on the Charity Commission register", "biz_uk_home": "same name, home jurisdiction the UK",
       "biz_same_zip": "same name and ZIP code", "biz_us_origin": "same name, country of origin the United States",
       "sec_plc": "same name, an SEC filer that is a PLC", "formd_uk": "same name, a Form D issuer in the UK"}


def publish() -> None:
    from loader import xref
    t0 = time.time()
    with db.connect() as conn:
        xref.ensure_schema(conn)
        if xref._rebuilding(conn):
            _log("publish: xlinks is being rebuilt, try again later")
            return
        conn.execute("DELETE FROM xlinks WHERE linker LIKE 'ukco:%'")
        how = "CASE m.method " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in HOW.items()) + \
              " ELSE m.method END || ' (' || CASE m.confidence WHEN 'high' THEN 'EXACT' ELSE 'FUZZY' END || ')'"
        n = 0
        for fwd in (True, False):
            if fwd:
                sel = "'uk_company', m.company_number, c.name, NULL, m.dst_kind, m.dst_key, m.dst_name"
            else:
                sel = "m.dst_kind, m.dst_key, m.dst_name, m.dst_state, 'uk_company', m.company_number, c.name"
            n += conn.execute(f"""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT {sel}, {how}, 'ukco:' || m.method
                FROM uk_companies.xmatch m JOIN uk_companies.company c USING (company_number)
                WHERE m.confidence IN ('high', 'medium') ON CONFLICT DO NOTHING""").rowcount
        if conn.execute("SELECT to_regclass('uk_companies.psc_match') IS NOT NULL").fetchone()[0]:
            for fwd in (True, False):
                if fwd:
                    sel = "'uk_psc', m.company_number || ':' || m.psc_id, m.name, m.state, 'person', m.cluster_id::text, m.name"
                else:
                    sel = "'person', m.cluster_id::text, m.name, m.state, 'uk_psc', m.company_number || ':' || m.psc_id, m.name"
                n += conn.execute(f"""
                    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                    SELECT {sel}, 'a person with significant control of UK company ' || m.company_number || ', living in the US: the same full name in ' || m.state || ' (FUZZY)', 'ukco:psc_person'
                    FROM uk_companies.psc_match m ON CONFLICT DO NOTHING""").rowcount
        conn.execute("DELETE FROM xref_counts WHERE linker LIKE 'ukco:%'")
        conn.execute("""INSERT INTO xref_counts (src_kind, dst_kind, linker, rule, n, sources, built)
                        SELECT src_kind, dst_kind, linker, min(how), count(*), count(DISTINCT src_key), now()
                        FROM xlinks WHERE linker LIKE 'ukco:%' GROUP BY 1, 2, 3""")
        conn.execute("""INSERT INTO uk_companies.meta (key, rows, loaded, checked, note) VALUES ('xlinks', %s, now(), now(), 'published')
                        ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""", (n,))
        conn.commit()
    _log(f"publish: {n:,} xlinks rows in {time.time() - t0:.0f}s")


def sample(method: str, n: int = 50) -> None:
    with db.connect() as conn:
        if method == "psc_person":
            rows = conn.execute("""SELECT m.company_number, c.name, m.name, m.state FROM uk_companies.psc_match m JOIN uk_companies.company c USING (company_number)
                                   ORDER BY random() LIMIT %s""", (n,)).fetchall()
        else:
            rows = conn.execute("""SELECT m.company_number, c.name, m.dst_kind || ' ' || m.dst_key || ' ' || coalesce(m.dst_name, ''), m.evidence
                                   FROM uk_companies.xmatch m JOIN uk_companies.company c USING (company_number)
                                   WHERE m.method = %s ORDER BY random() LIMIT %s""", (method, n)).fetchall()
    for r in rows:
        print(" | ".join(str(x) for x in r))


def status() -> None:
    with db.connect() as conn:
        for r in conn.execute("SELECT method, confidence, count(*), count(DISTINCT company_number) FROM uk_companies.xmatch GROUP BY 1, 2 ORDER BY 1, 2").fetchall():
            print("uk companies xref:", *r)
        if conn.execute("SELECT to_regclass('uk_companies.psc_match') IS NOT NULL").fetchone()[0]:
            print("uk companies xref: psc_person", conn.execute("SELECT count(*) FROM uk_companies.psc_match").fetchone()[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["match", "publish", "sample", "status"])
    ap.add_argument("method", nargs="?")
    ap.add_argument("--n", type=int, default=50)
    a = ap.parse_args(argv)
    if a.step == "match":
        match()
    elif a.step == "publish":
        publish()
    elif a.step == "sample":
        sample(a.method, a.n)
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
