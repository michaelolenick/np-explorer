"""Corporate and SEC data: insiders (Forms 3, 4, 5), companies, Form D private offerings and executive pay.
Data: loader/sec_bulk.py; links and summary tables: build() below. Routes live on `router` (app/main.py
includes it). Shown only where SEC_PUBLIC=1 (dev while the load is checked; production once promoted).

People on the site link to SEC records by name and state only (EDGAR gives no other identifier we share), so
every such link is marked Fuzzy and the person page says why. Every filing links to its index page on EDGAR.
"""

from __future__ import annotations

import logging
import os
import re
import sys

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
log = logging.getLogger("np.corporate")
PUBLIC = os.environ.get("SEC_PUBLIC") == "1"
CODES = {"P": "Open-market purchase", "S": "Open-market sale", "A": "Grant or award", "M": "Option exercise",
         "F": "Tax withholding", "G": "Gift", "D": "Sale back to the company", "C": "Conversion",
         "X": "Option exercise", "J": "Other", "I": "Discretionary", "W": "Inheritance", "Z": "Trust deposit"}


def filing_url(cik, accession: str) -> str:
    acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik or 0)}/{acc}/{accession}-index.htm"


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS t", (table,)).fetchone()["t"] is not None


# --- person and organization sections -------------------------------------------------------------

def person_sec(cluster_id: int) -> dict | None:
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            if not _has(conn, "sec_person_links"):
                return None
            links = conn.execute("SELECT source, key FROM sec_person_links WHERE cluster_id = %s", (cluster_id,)).fetchall()
            if not links:
                return None
            ciks = [l["key"] for l in links if l["source"] == "insider"]
            insider = conn.execute("""
                SELECT f.issuer_cik, f.issuer_name, f.ticker, min(f.filing_date) AS first, max(f.filing_date) AS last,
                       count(*) AS filings, string_agg(DISTINCT nullif(o.title, ''), '; ') AS titles,
                       string_agg(DISTINCT o.relationship, '; ') AS roles, min(o.owner_cik) AS owner_cik
                FROM sec_insider_owners o JOIN sec_insider_filings f ON f.accession = o.accession
                WHERE o.owner_cik = ANY(%s) GROUP BY 1, 2, 3 ORDER BY max(f.filing_date) DESC LIMIT 50""",
                                   (ciks,)).fetchall() if ciks else []
            accs = [l["key"] for l in links if l["source"] == "formd"]
            formd = conn.execute("""
                SELECT d.accession, d.cik, d.issuer_name, d.filing_date, d.industry, d.fund_type, d.amount_sold,
                       p.relationships, p.clarification
                FROM sec_formd_people p JOIN sec_formd d ON d.accession = p.accession
                WHERE p.accession || ':' || p.seq = ANY(%s) ORDER BY d.filing_date DESC LIMIT 50""",
                                 (accs,)).fetchall() if accs else []
    except Exception:  # noqa: BLE001
        return None
    if not insider and not formd:
        return None
    return {"insider": insider, "formd": formd, "owner_ciks": ciks}


def org_formd(ein: str) -> list[dict]:
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            return conn.execute("""SELECT accession, cik, issuer_name, filing_date, industry, fund_type, amount_sold,
                                          offering_amount FROM sec_formd WHERE issuer_ein = %s
                                   ORDER BY filing_date DESC LIMIT 100""", (ein,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


# --- pages ------------------------------------------------------------------------------------------

def insider(owner_cik: str) -> dict | None:
    with db.conn() as conn:
        rows = conn.execute("""
            SELECT f.accession, f.filing_date, f.form, f.issuer_cik, f.issuer_name, f.ticker, o.owner_name,
                   o.relationship, o.title, o.city, o.state,
                   (SELECT sum(t.shares * t.price) FILTER (WHERE t.code = 'S') FROM sec_insider_trans t
                    WHERE t.accession = f.accession) AS sold,
                   (SELECT sum(t.shares * t.price) FILTER (WHERE t.code = 'P') FROM sec_insider_trans t
                    WHERE t.accession = f.accession) AS bought
            FROM sec_insider_owners o JOIN sec_insider_filings f ON f.accession = o.accession
            WHERE o.owner_cik = %s ORDER BY f.filing_date DESC LIMIT 500""", (owner_cik,)).fetchall()
        if not rows:
            return None
        people = conn.execute("""SELECT pc.id, pc.display_name FROM sec_person_links l JOIN person_clusters pc
                                 ON pc.id = l.cluster_id WHERE l.source = 'insider' AND l.key = %s""",
                              (owner_cik,)).fetchall() if _has(conn, "sec_person_links") else []
    from app import buybacks
    return {"owner_cik": owner_cik, "owner_name": rows[0]["owner_name"], "rows": rows, "people": people,
            "tr": buybacks.trades([owner_cik])}


def company(cik: str) -> dict | None:
    with db.conn() as conn:
        f = conn.execute("""SELECT issuer_name, ticker, count(*) AS n, min(filing_date) AS first, max(filing_date) AS last
                            FROM sec_insider_filings WHERE issuer_cik = %s GROUP BY 1, 2 ORDER BY max(filing_date) DESC
                            LIMIT 1""", (cik,)).fetchone()
        pay = conn.execute("SELECT * FROM sec_exec_pay WHERE cik = %s ORDER BY period_end DESC",
                           (str(int(cik)),)).fetchall()
        from app import buybacks
        bb = buybacks.company(cik)
        if not f and not pay and not bb:
            return None
        insiders = conn.execute("""
            SELECT o.owner_cik, min(o.owner_name) AS owner_name, string_agg(DISTINCT o.relationship, '; ') AS roles,
                   string_agg(DISTINCT nullif(o.title, ''), '; ') AS titles, max(fi.filing_date) AS last, count(*) AS n
            FROM sec_insider_filings fi JOIN sec_insider_owners o ON o.accession = fi.accession
            WHERE fi.issuer_cik = %s GROUP BY 1 ORDER BY max(fi.filing_date) DESC LIMIT 200""", (cik,)).fetchall()
    return {"cik": cik, "f": f, "pay": pay, "insiders": insiders, "bb": bb,
            "company_name": (f or {}).get("issuer_name") or (pay[0]["entity_name"] if pay else None)
                            or (bb or {}).get("name") or cik}


EXEMPTIONS = {
    "06b": "Private offering, no general advertising (Rule 506(b))",
    "06c": "Private offering, advertising allowed, accredited only (Rule 506(c))",
    "04": "Small offering, up to $10 million (Rule 504)",
    "04.1": "Small offering (Rule 504(b)(1)(i))", "04.2": "Small offering (Rule 504(b)(1)(ii))",
    "04.3": "Small offering (Rule 504(b)(1)(iii))",
    "06": "Private offering (Rule 506)",
    "3C": "Investment company exemption (3(c))",
    "3C.1": "Fund under 100 investors (3(c)(1))",
    "3C.7": "Qualified purchasers only (3(c)(7))",
    "4a5": "Offering to accredited investors only (Section 4(a)(5))",
}


def exemptions_plain(codes: str | None) -> str:
    """Form D exemption codes in plain English, each with its code ("06b" -> "Private offering, no general
    advertising (Rule 506(b))"; owner, 2026-10-23). A code with no translation is shown as written."""
    out = []
    for c in [x.strip() for x in (codes or "").split(",") if x.strip()]:
        plain = EXEMPTIONS.get(c)
        if not plain and c.startswith("3C."):
            plain = f"Investment company exemption (3(c)({c[3:]}))"
        out.append(plain or c)
    return "; ".join(out)


def formd(accession: str) -> dict | None:
    with db.conn() as conn:
        d = conn.execute("SELECT * FROM sec_formd WHERE accession = %s", (accession,)).fetchone()
        if not d:
            return None
        people = conn.execute("""SELECT p.*, coalesce(l.cluster_id, pt.cluster_id) AS cluster_id, pt.id AS party_id,
                                        pt.kind AS party_kind, pt.name AS party_name
                                 FROM sec_formd_people p
                                 LEFT JOIN sec_person_links l ON l.source = 'formd' AND l.key = p.accession || ':' || p.seq
                                 LEFT JOIN sec_formd_people_party x ON x.accession = p.accession AND x.seq = p.seq
                                 LEFT JOIN sec_formd_parties pt ON pt.id = x.party_id
                                 WHERE p.accession = %s ORDER BY p.seq""", (accession,)).fetchall()
        from app.formd_parties import clean_text
        for p in people:       # "n/a" first names on entities, doubled quotes (owner, 2026-10-23)
            p["relationships"], p["clarification"] = clean_text(p["relationships"]), clean_text(p["clarification"])
        org = conn.execute("SELECT ein, name FROM organizations WHERE ein = %s", (d["issuer_ein"],)).fetchone() \
            if d["issuer_ein"] else None
        company = conn.execute("SELECT 1 AS x FROM sec_insider_filings WHERE issuer_cik = %s LIMIT 1",
                               (d["cik"],)).fetchone() if d["cik"] else None
        others = conn.execute("""SELECT accession, form, filing_date, offering_amount, offering_indefinite, amount_sold,
                                        investors, issuer_name FROM sec_formd WHERE cik = %s
                                 ORDER BY filing_date DESC NULLS LAST, accession DESC LIMIT 100""",
                              (d["cik"],)).fetchall() if d["cik"] else []
    from app import adv
    silent = None
    if d["cik"] and not float(d["amount_sold"] or 0):
        with db.conn() as conn:
            offs = conn.execute("SELECT * FROM sec_formd_offerings WHERE cik = %s", (d["cik"],)).fetchall()
            adv.silent_values(conn, offs)
            silent = next((o["adv"] for o in offs if o.get("adv")), None)
    return {"d": d, "people": people, "org": org, "company_cik": d["cik"] if company else None, "others": others,
            "silent": silent,
            "adv_funds": adv.for_formd(d["cik"]), "adv_note": adv.NOTE}


def overview() -> dict:
    with db.conn() as conn:
        runs = conn.execute("""SELECT dataset, min(quarter) AS first, max(quarter) AS last, sum(rows) AS rows,
                                      max(finished) AS updated FROM sec_runs GROUP BY 1""").fetchall() \
            if _has(conn, "sec_runs") else []
        links = conn.execute("SELECT source, count(*) AS n, count(DISTINCT cluster_id) AS people FROM sec_person_links "
                             "GROUP BY 1").fetchall() if _has(conn, "sec_person_links") else []
    return {"runs": {r["dataset"]: r for r in runs}, "links": {r["source"]: r for r in links}}


# --- links and summaries (after a load) -------------------------------------------------------------

def build(status=print) -> None:
    """sec_person_links: insiders (by owner CIK) and Form D related persons matched to people on the site when the
    normalized name (first, middle initial and last) is held by exactly one person on the site, that person's
    states include the SEC record's state, and the name has at least three parts (a middle name or initial).
    sec_formd.issuer_ein: issuers that are filing organizations (normalized name and zip5, one EIN).
    sec_insider_sales: open-market sales and purchases by owner, issuer and year, for the boards."""
    from loader import db as ldb
    from loader.fec_links import ensure_function
    with ldb.connect() as conn:
        ensure_function(conn)
        conn.execute("SET work_mem = '1GB'")
        conn.execute("""CREATE TEMP TABLE uniq AS SELECT name_norm, min(id) AS id, min(states) AS states
                        FROM person_clusters WHERE NOT is_institution AND name_norm ~ '^\\S+ \\S+ \\S+'
                        GROUP BY 1 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON uniq (name_norm)")
        conn.execute("DROP TABLE IF EXISTS sec_person_links_new")
        conn.execute("""
            CREATE TABLE sec_person_links_new AS
            SELECT DISTINCT 'insider'::text AS source, o.owner_cik AS key, u.id AS cluster_id
            FROM sec_insider_owners o JOIN uniq u ON u.name_norm = o.name_norm AND o.state = ANY(u.states)
            WHERE o.owner_cik IS NOT NULL
            UNION ALL
            SELECT 'formd', p.accession || ':' || p.seq, u.id
            FROM sec_formd_people p JOIN uniq u ON u.name_norm = p.name_norm AND p.state = ANY(u.states)""")
        conn.execute("CREATE INDEX ON sec_person_links_new (cluster_id)")
        conn.execute("CREATE INDEX ON sec_person_links_new (source, key)")
        ldb.swap_table(conn, "sec_person_links")
        conn.commit()
        conn.execute("""CREATE TEMP TABLE org_keys AS
                        SELECT np_name_core(name) AS core, left(regexp_replace(zip, '\\D', '', 'g'), 5) AS z5, min(ein) AS ein
                        FROM organizations WHERE name IS NOT NULL AND zip IS NOT NULL GROUP BY 1, 2 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON org_keys (core, z5)")
        conn.execute("""UPDATE sec_formd d SET issuer_ein = k.ein FROM org_keys k
                        WHERE k.core = np_name_core(d.issuer_name) AND k.z5 = left(regexp_replace(d.zip, '\\D', '', 'g'), 5)
                          AND d.issuer_ein IS DISTINCT FROM k.ein""")
        conn.commit()
        conn.execute("DROP TABLE IF EXISTS sec_insider_sales_new")
        conn.execute("""
            CREATE TABLE sec_insider_sales_new AS
            SELECT extract(year FROM t.trans_date)::int AS year, o.owner_cik, min(o.owner_name) AS owner_name,
                   f.issuer_cik, min(f.issuer_name) AS issuer_name, min(f.ticker) AS ticker,
                   sum(t.shares * t.price) FILTER (WHERE t.code = 'S') AS sold,
                   sum(t.shares * t.price) FILTER (WHERE t.code = 'P') AS bought,
                   count(DISTINCT f.accession) AS filings, max(f.accession) AS last_accession,
                   string_agg(DISTINCT o.relationship, '; ') AS roles, min(o.state) AS state
            FROM sec_insider_trans t JOIN sec_insider_filings f ON f.accession = t.accession
            JOIN sec_insider_owners o ON o.accession = t.accession
            JOIN (SELECT accession FROM sec_insider_owners GROUP BY 1 HAVING count(*) = 1) one   -- one owner per filing,
                ON one.accession = t.accession                                                     -- so no double count
            WHERE t.code IN ('S', 'P') AND t.price > 0 AND t.shares > 0 AND t.trans_date >= '2003-01-01'
              AND t.price < 100000 AND t.shares * t.price < 5e9      -- larger values are filer typos (wrong units)
            GROUP BY 1, 2, 4""")
        ldb.swap_table(conn, "sec_insider_sales")
        conn.commit()
        r = conn.execute("""SELECT (SELECT count(*) FROM sec_person_links WHERE source = 'insider'),
                                   (SELECT count(*) FROM sec_person_links WHERE source = 'formd'),
                                   (SELECT count(DISTINCT cluster_id) FROM sec_person_links),
                                   (SELECT count(*) FROM sec_formd WHERE issuer_ein IS NOT NULL)""").fetchone()
    status(f"sec: {r[0]:,} insiders and {r[1]:,} Form D roles linked to {r[2]:,} people; {r[3]:,} Form D issuers "
           f"linked to filing organizations")
    build_offerings(status)


def build_offerings(status=print) -> int:
    """sec_formd_offerings: one row per offering, the original Form D and its amendments (D/A filings point back
    through previous_accession; an amendment whose original isn't in the data sets starts its own chain). The
    initial target is the original's total offering amount; the latest target and amount sold are the latest
    filing's (the subscription leaderboards compare those two). "Indefinite" targets are flagged. Coverage: the
    SEC's Form D Data Sets, 2014 onward (owner, 2026-10-22: no backfill of 2009 to 2013)."""
    from loader import db as ldb
    with ldb.connect() as conn:
        conn.execute("SET work_mem = '1GB'")
        conn.execute("DROP TABLE IF EXISTS sec_formd_offerings_new")
        # Chains in Python (one pass over the filings): each amendment's root is its predecessor's root.
        prev = {a: (p_ if amd else None) for a, p_, amd in conn.execute(
            "SELECT accession, previous_accession, is_amendment FROM sec_formd").fetchall()}
        root: dict[str, str] = {}

        def find(a: str) -> str:
            seen = []
            while a not in root:
                p_ = prev.get(a)
                if not p_ or p_ not in prev or p_ in seen or p_ == a:
                    root[a] = a
                    break
                seen.append(a)
                a = p_
            r_ = root[a]
            for x in seen:
                root[x] = r_
            return r_
        for a in prev:
            find(a)
        conn.execute("CREATE TEMP TABLE formd_chain (accession text PRIMARY KEY, root text)")
        with conn.cursor() as cur, cur.copy("COPY formd_chain FROM STDIN") as cp:
            for a, r_ in root.items():
                cp.write_row((a, r_))
        conn.execute("CREATE INDEX ON formd_chain (root)")
        conn.execute("ANALYZE formd_chain")
        conn.execute("""
            CREATE TABLE sec_formd_offerings_new AS
            WITH latest AS (
                SELECT DISTINCT ON (c.root) c.root, d.* FROM formd_chain c JOIN sec_formd d USING (accession)
                ORDER BY c.root, d.filing_date DESC NULLS LAST, d.accession DESC),
            n AS (SELECT root, count(*)::int AS filings FROM formd_chain GROUP BY 1)
            SELECT l.root AS root_accession, l.cik, l.issuer_name, l.industry, l.fund_type, l.entity_type, l.city,
                   l.state, r.filing_date AS first_date, l.accession AS latest_accession, l.filing_date AS latest_date,
                   n.filings, r.offering_amount AS initial_offering, r.amount_sold AS initial_sold,
                   r.offering_indefinite AS initial_indefinite,
                   l.offering_amount AS latest_offering,
                   l.amount_sold AS latest_sold, l.offering_indefinite AS indefinite,
                   CASE WHEN l.investors BETWEEN 0 AND 1000000 THEN l.investors::int END AS investors,  -- larger: typos
                   l.min_investment
            FROM latest l JOIN n USING (root) JOIN sec_formd r ON r.accession = l.root""")
        conn.execute("ALTER TABLE sec_formd_offerings_new ADD PRIMARY KEY (root_accession)")
        conn.execute("CREATE INDEX ON sec_formd_offerings_new (cik)")
        conn.execute("ALTER TABLE sec_formd_offerings_new ADD COLUMN is_spv boolean, ADD COLUMN family text, "
                     "ADD COLUMN spv_company text")
        rows = conn.execute("SELECT root_accession, issuer_name FROM sec_formd_offerings_new").fetchall()
        stems = {family_stem(n) for _, n in rows if n and not is_spv(n)} - {""}
        by_first: dict[str, list] = {}
        for s_ in stems:
            by_first.setdefault(s_.split()[0], []).append(s_)
        out = []
        for root, name in rows:
            spv = is_spv(name or "")
            fam, company = family_and_company(name or "", by_first) if spv else (family_stem(name or ""), None)
            out.append((root, spv, fam or None, company))
        conn.execute("CREATE TEMP TABLE spv_tags (root text, is_spv boolean, family text, spv_company text)")
        with conn.cursor() as cur, cur.copy("COPY spv_tags FROM STDIN") as cp:
            for r_ in out:
                cp.write_row(r_)
        conn.execute("""UPDATE sec_formd_offerings_new o SET is_spv = t.is_spv, family = t.family,
                        spv_company = t.spv_company FROM spv_tags t WHERE t.root = o.root_accession""")
        conn.execute("CREATE INDEX ON sec_formd_offerings_new USING gin (lower(issuer_name) gin_trgm_ops)")
        conn.execute("CREATE INDEX ON sec_formd_offerings_new (family)")
        ldb.swap_table(conn, "sec_formd_offerings")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM sec_formd_offerings").fetchone()[0]
    status(f"sec: {n:,} Form D offerings (original filings with their amendments)")
    return n


# --- main funds and deal-by-deal SPVs ------------------------------------------------------------------------

_SPV = re.compile(r"\bSPVs?\b|\ba series of\b|\bseries (?:of )?(?:llc|l\.l\.c\.)|\bseries [A-Z0-9-]+,? (?:llc|lp|l\.p\.)\b",
                  re.I)
_FUND_TAIL = re.compile(r"(?:[,\s]+(?:fund|funds|lp|l p|llc|l l c|ltd|inc|i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|"
                        r"\d+))+$")


def is_spv(name: str) -> bool:
    """An offering made for one deal: "SPV" in the name, "a series of" a series LLC, or a series-LLC shell."""
    return bool(_SPV.search(name or ""))


def family_stem(name: str) -> str:
    """The sponsor part of a name: "Geek Ventures Fund I, LP" -> "geek ventures" (fund words and legal endings
    off the end; at least one word kept)."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split()
    stem = _FUND_TAIL.sub("", " " + s).strip()
    return stem if stem else (words[0] if words else "")


def family_and_company(name: str, by_first: dict) -> tuple[str | None, str | None]:
    """For an SPV: the family (the longest main-fund stem its name starts with) and the company the deal appears to
    be for: "Geek Ventures Competera SPV, a series of Decile SPV, LLC" -> ("geek ventures", "Competera")."""
    head = re.split(r"\s*,?\s*\b(?:a series of|SPVs?)\b", name, maxsplit=1, flags=re.I)[0]
    low = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", head.lower())).strip()
    fam = None
    for stem in sorted(by_first.get(low.split()[0] if low else "", []), key=len, reverse=True):
        if low == stem or low.startswith(stem + " "):
            fam = stem
            break
    words = head.split()
    rest = " ".join(words[len(fam.split()):]) if fam else head
    rest = re.sub(r"\b[A-Z]{1,4}-\d{2,6}\b", "", rest)                     # deal codes: "SU-0709"
    rest = re.sub(r"\b(?:seed|series [a-z0-9]+|\d+|co-?invest(?:ment)?|deal|fund)\b", "", rest, flags=re.I)
    rest = re.sub(r"\b(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\b", "", rest)      # fund numbers
    rest = re.sub(r"\s+", " ", rest).strip(" ,-")
    return fam, (rest if len(rest) >= 3 and re.search(r"[A-Za-z]{2}", rest) else None)


def formd_families(q: str, main_limit: int = 60, spv_limit: int = 400, newest_first: bool = True) -> dict | None:
    """Form D offerings matching q, split into main funds (all of them, oldest first, with the growth of each raise)
    and deal-by-deal SPVs grouped by the series they belong to ("Hustle Fund Angel Squad, LP"), each SPV with the
    company it appears to be for. The exact phrase is tried first ("hustle fund" leaves out "Hustle&Trust ...
    Fund I"); every word anywhere only when the phrase finds nothing."""
    words = [w for w in re.findall(r"[a-z0-9]+", (q or "").lower()) if len(w) >= 2][:6]
    if not words or not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            cond, params = "lower(o.issuer_name) LIKE %s", ["%" + " ".join(words) + "%"]
            if len(words) > 1 and not conn.execute(f"SELECT 1 FROM sec_formd_offerings o WHERE {cond} LIMIT 1",
                                                   params).fetchone():
                cond, params = " AND ".join(["lower(o.issuer_name) LIKE %s"] * len(words)), [f"%{w}%" for w in words]
            mains = conn.execute(f"""SELECT o.* FROM sec_formd_offerings o WHERE NOT o.is_spv AND {cond}
                                     ORDER BY o.first_date NULLS LAST, o.issuer_name LIMIT %s""",
                                 params + [main_limit]).fetchall()
            series_sql = "coalesce(substring(o.issuer_name from '(?i)a series of (.*)$'), 'Other SPVs')"
            groups = conn.execute(f"""SELECT {series_sql} AS series, count(*) AS n, sum(o.latest_sold) AS raised,
                                             min(o.first_date) AS first, max(o.latest_date) AS last
                                      FROM sec_formd_offerings o WHERE o.is_spv AND {cond}
                                      GROUP BY 1 ORDER BY 2 DESC""", params).fetchall()
            spvs = conn.execute(f"""SELECT o.*, {series_sql} AS series FROM sec_formd_offerings o
                                    WHERE o.is_spv AND {cond} ORDER BY o.latest_date DESC NULLS LAST LIMIT %s""",
                                params + [spv_limit]).fetchall()
            if not mains and not spvs:
                return None
            from app import adv
            adv.silent_values(conn, mains)
            names = sorted({r["spv_company"] for r in spvs if r["spv_company"] and len(r["spv_company"]) >= 4})
            links = {}
            for n in names:
                core_ = re.sub(r"[^a-z0-9 ]+", " ", n.lower()).strip()
                # The whole name, then a word boundary: "Poolday AI Inc" is Poolday; "CTRL Therapeutics" is not CTR.
                hit = conn.execute("""SELECT latest_accession AS acc, issuer_name FROM sec_formd_offerings
                                      WHERE NOT is_spv AND (lower(issuer_name) LIKE %s OR lower(issuer_name) LIKE %s
                                                            OR lower(issuer_name) = %s)
                                      ORDER BY latest_date DESC NULLS LAST LIMIT 1""",
                                   (core_ + " %", core_ + ",%", core_)).fetchone()
                if hit:
                    links[n] = ("formd", hit["acc"], hit["issuer_name"])
            from app.funders import normalize_org
            rest = {normalize_org(n): n for n in names if n not in links}
            if rest:
                for o in conn.execute("""SELECT DISTINCT ON (name_norm) name_norm, ein FROM organizations
                                         WHERE name_norm = ANY(%s) ORDER BY name_norm, latest_total_revenue DESC NULLS LAST""",
                                      (list(rest),)).fetchall():
                    links[rest[o["name_norm"]]] = ("org", o["ein"], rest[o["name_norm"]])
    except Exception:  # noqa: BLE001 - an extra on the search page
        log.exception("formd families")
        return None
    by_series: dict[str, list] = {}
    for r in spvs:
        r["link"] = links.get(r["spv_company"])
        by_series.setdefault(r["series"], []).append(r)
    series = [{**g, "rows": by_series.get(g["series"], [])} for g in groups]
    return {"mains": mains, "series": series, "spv_count": sum(g["n"] for g in groups),
            "spv_total": sum(float(g["raised"] or 0) for g in groups), "spvs": spvs,
            "families": ordered_families(mains, spvs, newest_first)}


def ordered_families(mains: list[dict], spvs: list[dict], newest_first: bool = True) -> list[dict]:
    """Main funds and series grouped by fund family (loader/formd_order.py), in natural order (newest or highest
    first by default), each SPV under its parent fund in the same direction; a subtotal per family. SPVs whose
    parent isn't in the list go in an "Other SPVs" group at the end."""
    rows = {r["root_accession"]: r for r in mains + spvs}
    if not rows:
        return []
    try:
        with db.conn() as conn:
            order = {o["root_accession"]: o for o in conn.execute(
                "SELECT * FROM formd_order WHERE root_accession = ANY(%s)", (list(rows),)).fetchall()}
    except Exception:  # noqa: BLE001 - no order table yet: keep the old listing
        return []
    def o(r, k, default=None):
        return (order.get(r["root_accession"]) or {}).get(k, default)
    fams: dict[str, list] = {}
    for r in mains:
        fams.setdefault(o(r, "family_key") or family_stem(r["issuer_name"]), []).append(r)
    kids: dict[str, list] = {}
    orphans = []
    for v in spvs:
        p = o(v, "parent_root")
        (kids.setdefault(p, []) if p in rows and p not in {x["root_accession"] for x in spvs} else orphans).append(v)
    sgn = -1 if newest_first else 1
    def key(r):
        return (sgn * (o(r, "sort_order") or 0.0), sgn * (r["first_date"].toordinal() if r["first_date"] else 0))
    out = []
    for fam, members in fams.items():
        members.sort(key=key)
        lines, total = [], 0.0
        for m in members:
            lines.append({**m, "depth": 0, "kind": o(m, "fund_kind", "main_fund")})
            total += float(m["latest_sold"] or 0)
            for v in sorted(kids.get(m["root_accession"], []), key=key):
                lines.append({**v, "depth": 1, "kind": "spv"})
                total += float(v["latest_sold"] or 0)
        first = min((m["first_date"] for m in members if m["first_date"]), default=None)
        last = max((m["first_date"] for m in members if m["first_date"]), default=None)
        out.append({"family": members[0]["issuer_name"] if len(members) == 1 else _family_title(members),
                    "lines": lines, "total": total, "n": len(members), "first": first, "last": last})
    out.sort(key=lambda f: (f["last"] or __import__("datetime").date.min), reverse=newest_first)
    if orphans:
        orphans.sort(key=key)
        out.append({"family": "Other SPVs", "lines": [{**v, "depth": 0, "kind": "spv"} for v in orphans],
                    "total": sum(float(v["latest_sold"] or 0) for v in orphans), "n": len(orphans), "first": None,
                    "last": None})
    return out


def _family_title(members: list[dict]) -> str:
    """The family's display name: the words its members' names share at the start ("Capital Factory Ventures")."""
    names = [re.sub(r"[,.]?\s+(?:L\.?P\.?|LLC|Inc\.?|Ltd\.?)\b.*$", "", m["issuer_name"], flags=re.I) for m in members]
    words = [n.split() for n in names]
    common = []
    for col in zip(*words):
        if len({w.lower() for w in col}) == 1:
            common.append(col[0])
        else:
            break
    title = " ".join(common).rstrip(",-– ")
    return title or names[0]


def search_formd(q: str, limit: int = 10) -> list[dict]:
    """Form D issuers whose name has every word of q (trigram index), one row per issuer (CIK), its latest
    filing first."""
    words = [w for w in __import__("re").findall(r"[a-z0-9]+", (q or "").lower()) if len(w) >= 2][:6]
    if not words or not PUBLIC:
        return []
    cond = " AND ".join(["lower(d.issuer_name) LIKE %s"] * len(words))
    try:
        with db.conn() as conn:
            return conn.execute(f"""
                SELECT * FROM (
                    SELECT DISTINCT ON (d.cik) d.cik, d.issuer_name, d.city, d.state, d.accession, d.filing_date,
                           d.offering_amount, d.offering_indefinite, d.amount_sold, d.industry, d.fund_type,
                           count(*) OVER (PARTITION BY d.cik) AS filings
                    FROM sec_formd d WHERE {cond}
                    ORDER BY d.cik, d.filing_date DESC NULLS LAST, d.accession DESC) x
                ORDER BY x.filing_date DESC NULLS LAST LIMIT %s""",
                                [f"%{w}%" for w in words] + [limit]).fetchall()
    except Exception:  # noqa: BLE001 - an extra on the search page
        return []


def search_formd_people(q: str, limit: int = 10) -> list[dict]:
    """People named on Form D filings with this normalized name: the offerings, newest first."""
    from app.names import normalize_name
    n = normalize_name(q or "")
    if not n or " " not in n or not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            return conn.execute("""
                SELECT p.name, p.relationships, p.city, p.state, d.accession, d.issuer_name, d.filing_date
                FROM sec_formd_people p JOIN sec_formd d USING (accession)
                WHERE p.name_norm = %s ORDER BY d.filing_date DESC NULLS LAST LIMIT %s""", (n, limit)).fetchall()
    except Exception:  # noqa: BLE001
        return []


# --- routes ---------------------------------------------------------------------------------------

def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, sec=sys.modules[__name__], **ctx)


@router.get("/corporate", response_class=HTMLResponse)
def hub_page(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    return _render(request, "corporate.html", **overview())


@router.get("/corporate/insider/{key}", response_class=HTMLResponse)
def insider_page(request: Request, key: str):
    from app import slugs
    owner_cik = slugs.parse("insider", key)
    data = insider(owner_cik.zfill(10)) if PUBLIC and owner_cik else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "insider", owner_cik, data["owner_name"])
    if moved:
        return moved
    return _render(request, "corporate_insider.html", **data)


@router.get("/corporate/company/{key}", response_class=HTMLResponse)
def company_page(request: Request, key: str):
    from app import slugs
    cik = slugs.parse("company", key)
    data = company(cik.zfill(10)) if PUBLIC and cik else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "company", cik, data["company_name"])
    if moved:
        return moved
    return _render(request, "corporate_company.html", **data)


@router.get("/corporate/form-d/{key}", response_class=HTMLResponse)
def formd_page(request: Request, key: str):
    from app import slugs
    accession = slugs.parse("formd", key)
    data = formd(accession) if PUBLIC and accession else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "formd", accession, data["d"]["issuer_name"])
    if moved:
        return moved
    return _render(request, "corporate_formd.html", **data)
