"""Campaign contributions from the FEC: donor, committee and hub pages, and the political contributions
section on person pages. Data: loader/fec.py (contributions, committees, candidates), loader/fec_links.py
(links to people on the site). Routes live on `router`, which app/main.py includes.

Totals leave out memo entries (MEMO_CD = X): those restate money reported elsewhere (for example a conduit's
earmarked contributions), so counting them would double it. Each contribution links to the FEC's image of the
report page it came from.
"""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db
from app.names import normalize_name

router = APIRouter()

# Campaign contributions are shown only where POLITICS_PUBLIC=1 (dev while the FEC load is checked; production once
# it is promoted). When off: the routes 404, the person and organization sections and the boards are hidden.
PUBLIC = os.environ.get("POLITICS_PUBLIC") == "1"

SOURCE_URL = "https://docquery.fec.gov/cgi-bin/fecimg/?{}"
FEC_COMMITTEE_URL = "https://www.fec.gov/data/committee/{}/"
NOT_MEMO = "c.memo_cd IS DISTINCT FROM 'X'"
PAGE = 100
OFFICES = {"P": "President", "S": "Senate", "H": "House"}
CMTE_TYPES = {
    "C": "Communication cost", "D": "Delegate committee", "E": "Electioneering communication",
    "H": "House campaign", "I": "Independent expenditor (person or group)", "N": "PAC, nonqualified",
    "O": "Super PAC (independent expenditure only)", "P": "Presidential campaign", "Q": "PAC, qualified",
    "S": "Senate campaign", "U": "Single-candidate independent expenditure", "V": "Hybrid PAC, nonqualified",
    "W": "Hybrid PAC, qualified", "X": "Party, nonqualified", "Y": "Party, qualified",
    "Z": "National party nonfederal account"}
PARTIES = {"DEM": "Democratic", "REP": "Republican", "LIB": "Libertarian", "GRE": "Green", "IND": "Independent"}


def source_url(image_num: str | None) -> str | None:
    return SOURCE_URL.format(image_num) if image_num else None


def slug(name_norm: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name_norm or "").strip("-")


def donor_url(name_norm: str, zip5: str | None) -> str:
    return f"/politics/donor/{zip5 or '00000'}/{slug(name_norm)}"


def ready() -> bool:
    try:
        with db.conn() as conn:
            return bool(conn.execute("SELECT 1 FROM fec_runs WHERE status = 'done' LIMIT 1").fetchone())
    except Exception:  # noqa: BLE001 - tables not built
        return False


def coverage() -> dict:
    with db.conn() as conn:
        r = conn.execute("""SELECT min(cycle) AS first, max(cycle) AS last, max(finished) AS updated,
                                   sum(rows) AS rows
                            FROM (SELECT DISTINCT ON (cycle) cycle, finished, rows FROM fec_runs
                                  WHERE status = 'done' ORDER BY cycle, finished DESC) x""").fetchone()
    return r or {}


# --- person pages ------------------------------------------------------------------------------

def person_contributions(cluster_id: int, limit: int = 300) -> dict | None:
    """The person's linked contributions, newest first, with totals by cycle; None when there are none."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            rows = conn.execute(f"""
                SELECT c.cycle, c.sub_id, c.tran_date, c.amount, c.name, c.employer, c.occupation, c.city, c.state,
                       c.cmte_id, cm.name AS committee, c.image_num, c.memo_cd, c.memo_text
                FROM fec_person_links l
                JOIN fec_contributions c ON c.cycle = l.cycle AND c.sub_id = l.sub_id
                LEFT JOIN fec_committees cm ON cm.cycle = c.cycle AND cm.cmte_id = c.cmte_id
                WHERE l.cluster_id = %s
                ORDER BY c.tran_date DESC NULLS LAST, c.sub_id DESC LIMIT %s""", (cluster_id, limit)).fetchall()
            if not rows:
                return None
            totals = conn.execute(f"""
                SELECT c.cycle, count(*) AS n, sum(c.amount) FILTER (WHERE {NOT_MEMO}) AS total
                FROM fec_person_links l JOIN fec_contributions c ON c.cycle = l.cycle AND c.sub_id = l.sub_id
                WHERE l.cluster_id = %s GROUP BY 1 ORDER BY 1 DESC""", (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001 - FEC tables not built
        return None
    return {"rows": rows, "totals": totals, "n": sum(t["n"] for t in totals),
            "total": sum(t["total"] or 0 for t in totals)}


# --- donors --------------------------------------------------------------------------------------

def donor(zip5: str, name_slug: str) -> dict | None:
    name_norm = name_slug.replace("-", " ")
    z = None if zip5 == "00000" else zip5
    with db.conn() as conn:
        rows = conn.execute(f"""
            SELECT c.cycle, c.sub_id, c.tran_date, c.amount, c.name, c.employer, c.occupation, c.city, c.state,
                   c.zip5, c.cmte_id, cm.name AS committee, c.image_num, c.memo_cd, c.memo_text, l.cluster_id
            FROM fec_contributions c
            LEFT JOIN fec_committees cm ON cm.cycle = c.cycle AND cm.cmte_id = c.cmte_id
            LEFT JOIN fec_person_links l ON l.cycle = c.cycle AND l.sub_id = c.sub_id
            WHERE c.name_norm = %s AND c.zip5 IS NOT DISTINCT FROM %s
            ORDER BY c.tran_date DESC NULLS LAST, c.sub_id DESC LIMIT 2000""", (name_norm, z)).fetchall()
        if not rows:
            return None
        people = conn.execute("""SELECT id, display_name FROM person_clusters WHERE id = ANY(%s)""",
                              ([r["cluster_id"] for r in rows if r["cluster_id"]],)).fetchall()
    totals: dict = {}
    for r in rows:
        t = totals.setdefault(r["cycle"], {"cycle": r["cycle"], "n": 0, "total": 0})
        t["n"] += 1
        if r["memo_cd"] != "X":
            t["total"] += r["amount"] or 0
    return {"donor_name": rows[0]["name"], "name_norm": name_norm, "zip5": z, "rows": rows, "people": people,
            "totals": sorted(totals.values(), key=lambda t: -t["cycle"]),
            "total": sum(t["total"] for t in totals.values()), "capped": len(rows) == 2000}


def search_donors(q: str, state: str | None = None, limit: int = 50) -> list[dict]:
    """Donors by name: each (name, zip) once, with totals. Exact normalized name, or every name that starts
    with it when the query is a single word plus a partial."""
    n = normalize_name(q)
    if not n or " " not in n:
        return []
    with db.conn() as conn:
        conn.execute("SET LOCAL statement_timeout = '8s'")
        return conn.execute(f"""
            SELECT c.name_norm, c.zip5, min(c.name) AS name, min(c.city) AS city, min(c.state) AS state,
                   mode() WITHIN GROUP (ORDER BY c.employer) AS employer, count(*) AS n,
                   sum(c.amount) FILTER (WHERE {NOT_MEMO}) AS total, min(c.cycle) AS first, max(c.cycle) AS last
            FROM fec_contributions c
            WHERE c.name_norm = %s {"AND c.state = %s" if state else ""}
            GROUP BY 1, 2 ORDER BY total DESC NULLS LAST LIMIT %s""",
                            (n, state, limit) if state else (n, limit)).fetchall()


# --- committees ----------------------------------------------------------------------------------

def committee(cmte_id: str) -> dict | None:
    with db.conn() as conn:
        cms = conn.execute("SELECT * FROM fec_committees WHERE cmte_id = %s ORDER BY cycle DESC", (cmte_id,)).fetchall()
        if not cms:
            return None
        cm = cms[0]
        cand = conn.execute("SELECT * FROM fec_candidates WHERE cand_id = %s ORDER BY cycle DESC LIMIT 1",
                            (cm["cand_id"],)).fetchone() if cm["cand_id"] else None
        totals = conn.execute("SELECT * FROM fec_committee_totals WHERE cmte_id = %s ORDER BY cycle DESC",
                              (cmte_id,)).fetchall() if _has(conn, "fec_committee_totals") else []
        top, top_cycle, top_note = [], None, None
        if totals:
            top_cycle = totals[0]["cycle"]
            try:
                conn.execute("SET LOCAL statement_timeout = '6s'")
                top = conn.execute(f"""
                    SELECT c.name_norm, c.zip5, min(c.name) AS name, min(c.city) AS city, min(c.state) AS state,
                           mode() WITHIN GROUP (ORDER BY c.employer) AS employer, count(*) AS n,
                           sum(c.amount) AS total
                    FROM fec_contributions c
                    WHERE c.cycle = %s AND c.cmte_id = %s AND {NOT_MEMO} AND c.name_norm IS NOT NULL
                    GROUP BY 1, 2 ORDER BY total DESC NULLS LAST LIMIT 50""", (top_cycle, cmte_id)).fetchall()
            except Exception:  # noqa: BLE001 - too many rows to rank on the fly
                conn.rollback()
                top_note = "This committee has too many contributions to rank on the fly; the totals above are complete."
        orgs = conn.execute("""SELECT o.ein, o.name FROM fec_org_committees x JOIN organizations o ON o.ein = x.ein
                               WHERE x.cmte_id = %s""", (cmte_id,)).fetchall() if _has(conn, "fec_org_committees") else []
    return {"cm": cm, "history": cms, "cand": cand, "totals": totals, "top": top, "top_cycle": top_cycle,
            "top_note": top_note, "orgs": orgs}


def org_committees(ein: str) -> list[dict]:
    """Political committees whose filings name this organization as their connected organization."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            return conn.execute("""
                SELECT DISTINCT ON (x.cmte_id) x.cmte_id, cm.name, cm.cmte_type, cm.cycle,
                       (SELECT sum(t.total) FROM fec_committee_totals t WHERE t.cmte_id = x.cmte_id) AS raised
                FROM fec_org_committees x JOIN fec_committees cm ON cm.cmte_id = x.cmte_id
                WHERE x.ein = %s ORDER BY x.cmte_id, cm.cycle DESC""", (ein,)).fetchall()
    except Exception:  # noqa: BLE001 - FEC tables not built
        return []


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS t", (table,)).fetchone()["t"] is not None


def overview() -> dict:
    with db.conn() as conn:
        cycles = conn.execute("""SELECT cycle, sum(n) AS n, sum(total) AS total, count(*) AS committees
                                 FROM fec_committee_totals GROUP BY 1 ORDER BY 1 DESC""").fetchall() \
            if _has(conn, "fec_committee_totals") else []
        links = conn.execute("SELECT count(*) AS n, count(DISTINCT cluster_id) AS people FROM fec_person_links").fetchone()
    return {"cycles": cycles, "links": links, "coverage": coverage()}


# --- routes -------------------------------------------------------------------------------------

def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, pol=sys.modules[__name__], **ctx)


# The "More data" menu and hub page: one group per kind of source. Datasets add their links here.
MORE_GROUPS = [
    {"title": "For reporters", "links": [
        ("/get-ideas", "Get Ideas", "30 story leads from public records by email every morning")]},
]
POLITICS_GROUP = [
    {"title": "Politics and lobbying", "links": [
        ("/politics", "Campaign contributions", "FEC itemized contributions from individuals, 1980 to now"),
        ("/politics/donors", "Find a campaign donor", ""),
        ("/boards/politics-donors", "Biggest individual campaign donors", ""),
        ("/boards/politics-committees", "Committees raising the most from individuals", ""),
        ("/boards/politics-990-people", "Nonprofit leaders' campaign giving", "")]},
]


@router.get("/more", response_class=HTMLResponse)
def more_page(request: Request):
    from app import fedspend
    fed = [{"title": "Federal spending", "links": [
        ("/federal-spending", "Federal grants and contracts", "USAspending awards to organizations, fiscal 2007 to now"),
        ("/boards/fed-nonprofit-grants", "Nonprofits getting the most federal grants", ""),
        ("/boards/fed-nonprofit-contracts", "Nonprofits with the biggest federal contracts", ""),
        ("/boards/fed-top-recipients", "Biggest recipients of federal money", "")]}] if fedspend.PUBLIC else []
    from app import corporate
    sec = [{"title": "Corporate and SEC", "links": [
        ("/corporate", "Corporate insiders and private money", "Forms 3, 4, 5, Form D and proxy CEO pay from EDGAR"),
        ("/boards/sec-insider-sales", "Biggest insider stock sales", ""),
        ("/boards/sec-formd-raises", "Biggest private fundraisings", ""),
        ("/boards/sec-ceo-pay", "Highest-paid CEOs", ""),
        ("/boards/sec-990-insiders", "Nonprofit leaders who are corporate insiders", "")]}] if corporate.PUBLIC else []
    from app import lobbying
    lob = [("/lobbying", "Federal lobbying", "Lobbying Disclosure Act reports: clients, firms, lobbyists"),
           ("/boards/lobby-spenders", "Biggest spenders on federal lobbying", ""),
           ("/boards/lobby-nonprofits", "Nonprofits spending the most on lobbying", ""),
           ("/boards/lobby-firms", "Lobbying firms earning the most", "")] if lobbying.PUBLIC else []
    pol = [{"title": "Politics and lobbying", "links": (POLITICS_GROUP[0]["links"] if PUBLIC else []) + lob}] \
        if PUBLIC or lob else []
    return _render(request, "more.html", more_groups=pol + fed + sec + MORE_GROUPS)


@router.get("/politics", response_class=HTMLResponse)
def hub_page(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    return _render(request, "politics.html", **(overview() if ready() else {"cycles": [], "links": None,
                                                                            "coverage": {}}))


@router.get("/politics/donors", response_class=HTMLResponse)
def donors_page(request: Request, q: str = Query("", max_length=100), state: str = Query("", max_length=2)):
    if not PUBLIC:
        raise HTTPException(404)
    st = state.upper() if re.fullmatch(r"[A-Za-z]{2}", state or "") else None
    rows = search_donors(q, st) if q.strip() and ready() else []
    return _render(request, "politics_donors.html", q=q.strip(), state=st or "", rows=rows)


@router.get("/politics/donor/{zip5}/{name_slug}", response_class=HTMLResponse)
def donor_page(request: Request, zip5: str, name_slug: str):
    if not PUBLIC:
        raise HTTPException(404)
    if not re.fullmatch(r"\d{5}", zip5) or not re.fullmatch(r"[a-z0-9-]{3,120}", name_slug):
        raise HTTPException(404)
    data = donor(zip5, name_slug)
    if not data:
        raise HTTPException(404)
    return _render(request, "politics_donor.html", **data)


@router.get("/politics/committee/{key}", response_class=HTMLResponse)
def committee_page(request: Request, key: str):
    from app import slugs
    if not PUBLIC:
        raise HTTPException(404)
    cmte_id = slugs.parse("committee", key)
    data = committee(cmte_id) if cmte_id else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "committee", cmte_id, data["cm"]["name"])
    if moved:
        return moved
    return _render(request, "politics_committee.html", **data)
