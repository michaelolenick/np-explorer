"""Corporate and SEC data: insiders (Forms 3, 4, 5), companies, Form D private offerings and executive pay.
Data: loader/sec_bulk.py; links and summary tables: build() below. Routes live on `router` (app/main.py
includes it). Shown only where SEC_PUBLIC=1 (dev while the load is checked; production once promoted).

People on the site link to SEC records by name and state only (EDGAR gives no other identifier we share), so
every such link is marked Fuzzy and the person page says why. Every filing links to its index page on EDGAR.
"""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
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
    return {"owner_cik": owner_cik, "owner_name": rows[0]["owner_name"], "rows": rows, "people": people}


def company(cik: str) -> dict | None:
    with db.conn() as conn:
        f = conn.execute("""SELECT issuer_name, ticker, count(*) AS n, min(filing_date) AS first, max(filing_date) AS last
                            FROM sec_insider_filings WHERE issuer_cik = %s GROUP BY 1, 2 ORDER BY max(filing_date) DESC
                            LIMIT 1""", (cik,)).fetchone()
        pay = conn.execute("SELECT * FROM sec_exec_pay WHERE cik = %s ORDER BY period_end DESC",
                           (str(int(cik)),)).fetchall()
        if not f and not pay:
            return None
        insiders = conn.execute("""
            SELECT o.owner_cik, min(o.owner_name) AS owner_name, string_agg(DISTINCT o.relationship, '; ') AS roles,
                   string_agg(DISTINCT nullif(o.title, ''), '; ') AS titles, max(fi.filing_date) AS last, count(*) AS n
            FROM sec_insider_filings fi JOIN sec_insider_owners o ON o.accession = fi.accession
            WHERE fi.issuer_cik = %s GROUP BY 1 ORDER BY max(fi.filing_date) DESC LIMIT 200""", (cik,)).fetchall()
    return {"cik": cik, "f": f, "pay": pay, "insiders": insiders,
            "company_name": (f or {}).get("issuer_name") or (pay[0]["entity_name"] if pay else cik)}


def formd(accession: str) -> dict | None:
    with db.conn() as conn:
        d = conn.execute("SELECT * FROM sec_formd WHERE accession = %s", (accession,)).fetchone()
        if not d:
            return None
        people = conn.execute("""SELECT p.*, l.cluster_id FROM sec_formd_people p
                                 LEFT JOIN sec_person_links l ON l.source = 'formd' AND l.key = p.accession || ':' || p.seq
                                 WHERE p.accession = %s ORDER BY p.seq""", (accession,)).fetchall()
        org = conn.execute("SELECT ein, name FROM organizations WHERE ein = %s", (d["issuer_ein"],)).fetchone() \
            if d["issuer_ein"] else None
    return {"d": d, "people": people, "org": org}


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


# --- routes ---------------------------------------------------------------------------------------

def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, sec=sys.modules[__name__], **ctx)


@router.get("/corporate", response_class=HTMLResponse)
def hub_page(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    return _render(request, "corporate.html", **overview())


@router.get("/corporate/insider/{owner_cik}", response_class=HTMLResponse)
def insider_page(request: Request, owner_cik: str):
    if not PUBLIC or not re.fullmatch(r"\d{1,10}", owner_cik):
        raise HTTPException(404)
    data = insider(owner_cik.zfill(10))
    if not data:
        raise HTTPException(404)
    return _render(request, "corporate_insider.html", **data)


@router.get("/corporate/company/{cik}", response_class=HTMLResponse)
def company_page(request: Request, cik: str):
    if not PUBLIC or not re.fullmatch(r"\d{1,10}", cik):
        raise HTTPException(404)
    data = company(cik.zfill(10))
    if not data:
        raise HTTPException(404)
    return _render(request, "corporate_company.html", **data)


@router.get("/corporate/form-d/{accession}", response_class=HTMLResponse)
def formd_page(request: Request, accession: str):
    if not PUBLIC or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        raise HTTPException(404)
    data = formd(accession)
    if not data:
        raise HTTPException(404)
    return _render(request, "corporate_formd.html", **data)
