"""UK company officers (loader/uk_officers.py) cross-referenced to the rest of FURP (owner, 2026-11-14), on the xref engine's rules:
every link says how it was made (`method`) and how sure it is (`confidence`); a name alone never links a UK officer to a US or UK-charity
person, there must be a shared organization or company as well.

python -m loader.uk_officers_xref match      compute uk_companies.officer_match (schema uk_companies only: invisible to prod)
python -m loader.uk_officers_xref publish    copy the matches into xlinks (linker 'ukoff:<method>') and xref_counts (low-confidence rows are not published)
python -m loader.uk_officers_xref sample METHOD [--n 50]
python -m loader.uk_officers_xref status
python -m loader.uk_officers_xref refresh    nightly: officer_stats, match, publish (publish only after the first manual publish)

Methods (an officer is an officer_id from the API: Companies House's own matching of one person's appointments)
  trustee_linked_charity  the officer of a company that is the registered company of a UK charity (uk.charity_main.company_number), and a
                          trustee of that same charity has the same full name (forenames and surname)                         high
  trustee_linked_charity_fl  same, but only the first forename and the surname agree (middle names differ or are missing)       medium
  us_insider_same_company the officer of a UK company that is matched to an SEC filer (ukco:sec_plc), and an SEC insider (Forms 3, 4, 5) of
                          that same issuer has the same full name                                                              high
  formd_party_same_issuer the officer of a UK company matched to a Form D issuer (ukco:formd_uk), and a person named on a Form D filing of
                          that issuer has the same full name                                                                   high
  us_unique_name          officer living in the United States whose full name (three or more parts) is the name of exactly one person page in
                          FURP: LOW, no shared organization; kept in officer_match for precision sampling, never published
"""

from __future__ import annotations

import argparse
import sys
import time

from loader import db

DDL = """
CREATE TABLE IF NOT EXISTS uk_companies.officer_match (
    officer_id text NOT NULL, company_number text NOT NULL, dst_kind text NOT NULL, dst_key text NOT NULL, dst_name text,
    method text NOT NULL, confidence text NOT NULL, evidence text, PRIMARY KEY (officer_id, dst_kind, dst_key, method));
CREATE INDEX IF NOT EXISTS uk_officer_match_dst ON uk_companies.officer_match (dst_kind, dst_key);
"""

HOW = {"trustee_linked_charity": "officer of a company that is the registered company of the charity this person is a trustee of, same name",
       "trustee_linked_charity_fl": "officer of a company that is the registered company of the charity this person is a trustee of, same first and last name",
       "us_insider_same_company": "same name, an SEC insider of the US filer matched to the company they direct",
       "formd_party_same_issuer": "same name, named on a Form D filing of the issuer matched to the company they direct"}


def _log(msg: str) -> None:
    from loader import uk_officers
    uk_officers._log("xref: " + msg)


def _run(conn, method: str, sql: str, params=None) -> int:
    t0 = time.time()
    conn.execute("DELETE FROM uk_companies.officer_match WHERE method = %s", (method,))
    n = conn.execute(sql, params or {}).rowcount
    conn.commit()
    _log(f"{method}: {n:,} matches in {time.time() - t0:.0f}s")
    return n


def match() -> None:
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        conn.execute("SET statement_timeout = 0")
        has_uk = conn.execute("SELECT to_regclass('uk.charity_main') IS NOT NULL AND to_regclass('uk.trustee') IS NOT NULL").fetchone()[0]
        if has_uk:
            conn.execute("DROP TABLE IF EXISTS tr_link")
            conn.execute("""CREATE TEMP TABLE tr_link AS
                SELECT lpad(m.company_number, 8, '0') AS company_number, m.reg_number, m.name AS charity, t.trustee_id, t.name AS tname, t.name_norm,
                       split_part(t.name_norm, ' ', 1) AS first, (regexp_match(t.name_norm, '(\\S+)$'))[1] AS last
                FROM uk.charity_main m JOIN uk.trustee t ON t.reg_number = m.reg_number
                WHERE m.company_number ~ '^[A-Za-z0-9]{1,8}$' AND t.name_norm IS NOT NULL AND coalesce(t.kind, 'P') <> 'O'""")
            conn.execute("CREATE INDEX ON tr_link (company_number)")
            conn.commit()
            _run(conn, "trustee_linked_charity", """
                INSERT INTO uk_companies.officer_match
                SELECT DISTINCT ON (o.officer_id, t.trustee_id) o.officer_id, o.company_number, 'uk_trustee', t.trustee_id::text, t.tname,
                       'trustee_linked_charity', 'high',
                       'officer of company ' || o.company_number || ', the registered company of ' || t.charity || ' (charity ' || t.reg_number || '), of which ' || t.tname || ' is a trustee'
                FROM uk_companies.officer o JOIN tr_link t ON t.company_number = o.company_number AND t.name_norm = o.name_norm
                WHERE o.officer_id IS NOT NULL AND NOT o.corporate AND array_length(string_to_array(o.name_norm, ' '), 1) >= 2
                ON CONFLICT DO NOTHING""")
            _run(conn, "trustee_linked_charity_fl", """
                INSERT INTO uk_companies.officer_match
                SELECT DISTINCT ON (o.officer_id, t.trustee_id) o.officer_id, o.company_number, 'uk_trustee', t.trustee_id::text, t.tname,
                       'trustee_linked_charity_fl', 'medium',
                       'officer of company ' || o.company_number || ', the registered company of ' || t.charity || ' (charity ' || t.reg_number || '); first and last name match trustee ' || t.tname
                FROM uk_companies.officer o JOIN tr_link t ON t.company_number = o.company_number AND t.name_norm <> o.name_norm
                     AND t.first = split_part(o.name_norm, ' ', 1) AND t.last = (regexp_match(o.name_norm, '(\\S+)$'))[1]
                WHERE o.officer_id IS NOT NULL AND NOT o.corporate AND length(t.first) >= 2 AND length(t.last) >= 3
                ON CONFLICT DO NOTHING""")
        _run(conn, "us_insider_same_company", """
            INSERT INTO uk_companies.officer_match
            SELECT DISTINCT ON (o.officer_id, w.owner_cik) o.officer_id, o.company_number, 'sec_insider', w.owner_cik, w.owner_name,
                   'us_insider_same_company', 'high',
                   'officer of UK company ' || o.company_number || ' (SEC filer CIK ' || x.dst_key || ' ' || coalesce(x.dst_name, '') || '); the same name is an SEC insider of that issuer'
            FROM uk_companies.officer o
            JOIN uk_companies.xmatch x ON x.company_number = o.company_number AND x.dst_kind = 'sec'
            JOIN sec_insider_filings f ON f.issuer_cik = x.dst_key
            JOIN sec_insider_owners w ON w.accession = f.accession AND w.name_norm = o.name_norm
            WHERE o.officer_id IS NOT NULL AND NOT o.corporate AND array_length(string_to_array(o.name_norm, ' '), 1) >= 2
            ON CONFLICT DO NOTHING""")
        _run(conn, "formd_party_same_issuer", """
            INSERT INTO uk_companies.officer_match
            SELECT DISTINCT ON (o.officer_id, pp.party_id) o.officer_id, o.company_number, 'formd_party', pp.party_id::text, p.name,
                   'formd_party_same_issuer', 'high',
                   'officer of UK company ' || o.company_number || ' (Form D issuer CIK ' || x.dst_key || ' ' || coalesce(x.dst_name, '') || '); the same name is on a Form D filing of that issuer'
            FROM uk_companies.officer o
            JOIN uk_companies.xmatch x ON x.company_number = o.company_number AND x.dst_kind = 'formd'
            JOIN sec_formd fd ON fd.cik = x.dst_key
            JOIN sec_formd_people p ON p.accession = fd.accession AND p.name_norm = o.name_norm
            JOIN sec_formd_people_party pp ON pp.accession = p.accession AND pp.seq = p.seq
            WHERE o.officer_id IS NOT NULL AND NOT o.corporate AND array_length(string_to_array(o.name_norm, ' '), 1) >= 2
            ON CONFLICT DO NOTHING""")
        _run(conn, "us_unique_name", """
            INSERT INTO uk_companies.officer_match
            SELECT DISTINCT ON (o.officer_id) o.officer_id, o.company_number, 'person', pc.id::text, pc.display_name, 'us_unique_name', 'low',
                   'officer of UK company ' || o.company_number || ' living in the United States; the full name is that of the only matching person page'
            FROM uk_companies.officer o JOIN person_clusters pc ON pc.name_norm = o.name_norm
            WHERE o.officer_id IS NOT NULL AND NOT o.corporate AND o.residence ILIKE 'united states%%'
              AND array_length(string_to_array(o.name_norm, ' '), 1) >= 3 AND NOT coalesce(pc.is_institution, false)
              AND (SELECT count(*) FROM (SELECT 1 FROM person_clusters p2 WHERE p2.name_norm = o.name_norm LIMIT 2) z) = 1
            ON CONFLICT DO NOTHING""")
        conn.execute("""INSERT INTO uk_companies.meta (key, rows, loaded, checked, note)
                        VALUES ('officer_match', (SELECT count(*) FROM uk_companies.officer_match), now(), now(), 'matched')
                        ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""")
        conn.commit()


def publish() -> None:
    from loader import xref
    t0 = time.time()
    with db.connect() as conn:
        xref.ensure_schema(conn)
        if xref._rebuilding(conn):
            _log("publish: xlinks is being rebuilt, try again later")
            return
        conn.execute("DELETE FROM xlinks WHERE linker LIKE 'ukoff:%'")
        how = "CASE m.method " + " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in HOW.items()) + \
              " ELSE m.method END || ' (' || CASE m.confidence WHEN 'high' THEN 'EXACT' ELSE 'FUZZY' END || ')'"
        n = 0
        for fwd in (True, False):
            if fwd:
                sel = "'uk_officer', m.officer_id, o.name, NULL, m.dst_kind, m.dst_key, m.dst_name"
            else:
                sel = "m.dst_kind, m.dst_key, m.dst_name, NULL, 'uk_officer', m.officer_id, o.name"
            n += conn.execute(f"""
                INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
                SELECT {sel}, {how}, 'ukoff:' || m.method
                FROM uk_companies.officer_match m
                JOIN LATERAL (SELECT name FROM uk_companies.officer WHERE officer_id = m.officer_id LIMIT 1) o ON true
                WHERE m.confidence IN ('high', 'medium') ON CONFLICT DO NOTHING""").rowcount
        conn.execute("DELETE FROM xref_counts WHERE linker LIKE 'ukoff:%'")
        conn.execute("""INSERT INTO xref_counts (src_kind, dst_kind, linker, rule, n, sources, built)
                        SELECT src_kind, dst_kind, linker, min(how), count(*), count(DISTINCT src_key), now()
                        FROM xlinks WHERE linker LIKE 'ukoff:%' GROUP BY 1, 2, 3""")
        conn.execute("""INSERT INTO uk_companies.meta (key, rows, loaded, checked, note) VALUES ('officer_xlinks', %s, now(), now(), 'published')
                        ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""", (n,))
        conn.commit()
    _log(f"publish: {n:,} xlinks rows in {time.time() - t0:.0f}s")


def sample(method: str, n: int = 50) -> None:
    with db.connect() as conn:
        rows = conn.execute("""SELECT m.officer_id, (SELECT name FROM uk_companies.officer WHERE officer_id = m.officer_id LIMIT 1), m.dst_kind || ' ' || m.dst_key,
                                      m.dst_name, m.evidence
                               FROM uk_companies.officer_match m WHERE m.method = %s ORDER BY random() LIMIT %s""", (method, n)).fetchall()
    for r in rows:
        print(" | ".join(str(x) for x in r))


def refresh() -> None:
    """Nightly: officer_stats, new matches, and (once the first manual publish has happened, after the prod deploy) the xlinks."""
    from loader import uk_officers
    uk_officers.summarize()
    match()
    with db.connect() as conn:
        published = conn.execute("SELECT 1 FROM uk_companies.meta WHERE key = 'officer_xlinks'").fetchone()
    if published:
        publish()


def status() -> None:
    with db.connect() as conn:
        for r in conn.execute("SELECT method, confidence, count(*), count(DISTINCT officer_id) FROM uk_companies.officer_match GROUP BY 1, 2 ORDER BY 1, 2").fetchall():
            print("uk officers xref:", *r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["match", "publish", "sample", "status", "refresh"])
    ap.add_argument("method", nargs="?")
    ap.add_argument("--n", type=int, default=50)
    a = ap.parse_args(argv)
    if a.step == "match":
        match()
    elif a.step == "publish":
        publish()
    elif a.step == "refresh":
        refresh()
    elif a.step == "sample":
        sample(a.method, a.n)
    else:
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
