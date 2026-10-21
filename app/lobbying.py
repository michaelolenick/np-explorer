"""Federal lobbying (Lobbying Disclosure Act): clients, lobbying firms and lobbyists, the lobbying section on
organization pages and lobbying roles on person pages. Data: loader/lda.py; links and summaries: build() below.
Routes live on `router` (app/main.py includes it). Shown only where LDA_PUBLIC=1.

Money: on a quarterly report (LD-2) a lobbying firm reports its income from the client, and an organization that
lobbies for itself reports its own lobbying expenses. A client's spending is the sum of both kinds across its
reports. Every filing links to its document on lda.gov.
"""

from __future__ import annotations

import os
import sys

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("LDA_PUBLIC") == "1"
SPEND = "coalesce(f.income, 0) + coalesce(f.expenses, 0)"


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS t", (table,)).fetchone()["t"] is not None


def org_lobbying(ein: str) -> dict | None:
    """As a client (lobbying bought) and as a registrant (a firm, or lobbying for itself), by year."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            years = conn.execute(f"""
                SELECT f.filing_year, sum({SPEND}) FILTER (WHERE f.client_ein = %(e)s) AS spent,
                       sum(f.income) FILTER (WHERE f.registrant_ein = %(e)s AND NOT f.self_filer) AS earned,
                       count(*) AS reports
                FROM lda_filings f WHERE f.client_ein = %(e)s OR f.registrant_ein = %(e)s
                GROUP BY 1 ORDER BY 1 DESC""", {"e": ein}).fetchall()
            if not years:
                return None
            firms = conn.execute(f"""
                SELECT f.registrant_id, f.registrant_name, sum({SPEND}) AS total, min(f.filing_year) AS first,
                       max(f.filing_year) AS last
                FROM lda_filings f WHERE f.client_ein = %s GROUP BY 1, 2 ORDER BY total DESC NULLS LAST LIMIT 30""",
                                 (ein,)).fetchall()
            issues = conn.execute("""
                SELECT a.issue, count(*) AS n FROM lda_filings f JOIN lda_activities a ON a.filing_uuid = f.filing_uuid
                WHERE f.client_ein = %s AND a.issue IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 12""", (ein,)).fetchall()
            recent = conn.execute(f"""
                SELECT f.filing_uuid, f.filing_year, f.filing_period, f.filing_type_display, f.registrant_name,
                       {SPEND} AS amount, f.document_url
                FROM lda_filings f WHERE f.client_ein = %(e)s OR f.registrant_ein = %(e)s
                ORDER BY f.dt_posted DESC NULLS LAST LIMIT 20""", {"e": ein}).fetchall()
    except Exception:  # noqa: BLE001
        return None
    return {"years": years, "firms": firms, "issues": issues, "recent": recent}


def person_lobbying(cluster_id: int) -> list[dict]:
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            if not _has(conn, "lda_person_links"):
                return []
            return conn.execute("""
                SELECT l.lobbyist_id, min(x.name) AS name, f.registrant_id, min(f.registrant_name) AS registrant,
                       count(DISTINCT f.client_id) AS clients, min(f.filing_year) AS first, max(f.filing_year) AS last,
                       string_agg(DISTINCT nullif(x.covered_position, ''), '; ') AS covered
                FROM lda_person_links l JOIN lda_activity_lobbyists x ON x.lobbyist_id = l.lobbyist_id
                JOIN lda_filings f ON f.filing_uuid = x.filing_uuid
                WHERE l.cluster_id = %s GROUP BY 1, 3 ORDER BY max(f.filing_year) DESC""", (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


def client(client_id: int) -> dict | None:
    with db.conn() as conn:
        rows = conn.execute(f"""
            SELECT f.filing_uuid, f.filing_year, f.filing_period, f.filing_type_display, f.registrant_id,
                   f.registrant_name, f.client_name, f.client_description, f.client_state, f.client_ein,
                   {SPEND} AS amount, f.document_url, f.self_filer
            FROM lda_filings f WHERE f.client_id = %s ORDER BY f.dt_posted DESC NULLS LAST LIMIT 1000""",
                            (client_id,)).fetchall()
        if not rows:
            return None
        issues = conn.execute("""SELECT a.issue, count(*) AS n FROM lda_filings f
                                 JOIN lda_activities a ON a.filing_uuid = f.filing_uuid WHERE f.client_id = %s
                                 AND a.issue IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 15""", (client_id,)).fetchall()
        org = conn.execute("SELECT ein, name FROM organizations WHERE ein = %s", (rows[0]["client_ein"],)).fetchone() \
            if rows[0]["client_ein"] else None
    years: dict = {}
    for r in rows:
        y = years.setdefault(r["filing_year"], {"year": r["filing_year"], "total": 0, "n": 0})
        y["total"] += r["amount"] or 0
        y["n"] += 1
    return {"client_id": client_id, "rows": rows, "issues": issues, "org": org,
            "years": sorted(years.values(), key=lambda y: -y["year"]), "client_name": rows[0]["client_name"]}


def registrant(registrant_id: int) -> dict | None:
    with db.conn() as conn:
        clients = conn.execute(f"""
            SELECT f.client_id, min(f.client_name) AS client_name, sum({SPEND}) AS total, count(*) AS n,
                   min(f.filing_year) AS first, max(f.filing_year) AS last
            FROM lda_filings f WHERE f.registrant_id = %s GROUP BY 1 ORDER BY total DESC NULLS LAST LIMIT 500""",
                               (registrant_id,)).fetchall()
        if not clients:
            return None
        head = conn.execute("""SELECT registrant_name, registrant_state, registrant_ein FROM lda_filings
                               WHERE registrant_id = %s ORDER BY dt_posted DESC NULLS LAST LIMIT 1""",
                            (registrant_id,)).fetchone()
        lobbyists = conn.execute("""
            SELECT x.lobbyist_id, min(x.name) AS name, max(f.filing_year) AS last,
                   string_agg(DISTINCT nullif(x.covered_position, ''), '; ') AS covered
            FROM lda_filings f JOIN lda_activity_lobbyists x ON x.filing_uuid = f.filing_uuid
            WHERE f.registrant_id = %s GROUP BY 1 ORDER BY max(f.filing_year) DESC, 2 LIMIT 300""",
                                 (registrant_id,)).fetchall()
    return {"registrant_id": registrant_id, "head": head, "clients": clients, "lobbyists": lobbyists}


def lobbyist(lobbyist_id: int) -> dict | None:
    with db.conn() as conn:
        rows = conn.execute(f"""
            SELECT f.filing_uuid, f.filing_year, f.filing_period, f.registrant_id, f.registrant_name, f.client_id,
                   f.client_name, a.issue, x.covered_position, x.name, f.document_url
            FROM lda_activity_lobbyists x JOIN lda_filings f ON f.filing_uuid = x.filing_uuid
            LEFT JOIN lda_activities a ON a.filing_uuid = x.filing_uuid AND a.n = x.n
            WHERE x.lobbyist_id = %s ORDER BY f.dt_posted DESC NULLS LAST LIMIT 1000""", (lobbyist_id,)).fetchall()
        if not rows:
            return None
        people = conn.execute("""SELECT pc.id, pc.display_name FROM lda_person_links l JOIN person_clusters pc
                                 ON pc.id = l.cluster_id WHERE l.lobbyist_id = %s""", (lobbyist_id,)).fetchall() \
            if _has(conn, "lda_person_links") else []
    covered = sorted({r["covered_position"] for r in rows if r["covered_position"]})
    return {"lobbyist_id": lobbyist_id, "lobbyist_name": rows[0]["name"], "rows": rows, "covered": covered,
            "people": people}


def overview() -> dict:
    with db.conn() as conn:
        years = conn.execute(f"""SELECT filing_year, count(*) AS n, sum({SPEND}) AS total,
                                        count(DISTINCT client_id) AS clients, count(DISTINCT registrant_id) AS firms,
                                        count(DISTINCT client_id) FILTER (WHERE client_ein IS NOT NULL) AS linked
                                 FROM lda_filings f GROUP BY 1 ORDER BY 1 DESC""").fetchall()
        crawl = conn.execute("SELECT max(updated) AS updated FROM lda_crawl").fetchone()
    return {"years": years, "crawl": crawl}


# --- links and summaries (after a parse) ------------------------------------------------------------

def build(status=print) -> None:
    """lda_person_links: lobbyists matched to people on the site (same normalized name, and the lobbyist's
    registrant or client is one of the person's organizations: fec_person_keys). lda_client_years: spending
    per client and year, for the boards."""
    from loader import db as ldb
    from loader.fec_links import ensure_function
    with ldb.connect() as conn:
        ensure_function(conn)
        conn.execute("DROP TABLE IF EXISTS lda_person_links_new")
        conn.execute("""
            CREATE TABLE lda_person_links_new AS
            SELECT DISTINCT x.lobbyist_id, k.cluster_id
            FROM lda_activity_lobbyists x JOIN lda_filings f ON f.filing_uuid = x.filing_uuid
            JOIN fec_person_keys k ON k.name_norm = x.name_norm
                 AND k.core IN (np_name_core(f.registrant_name), np_name_core(f.client_name))""")
        conn.execute("""DELETE FROM lda_person_links_new l USING (SELECT lobbyist_id FROM lda_person_links_new
                        GROUP BY 1 HAVING count(*) > 1) d WHERE l.lobbyist_id = d.lobbyist_id""")   # ambiguous
        conn.execute("CREATE INDEX ON lda_person_links_new (cluster_id)")
        conn.execute("CREATE INDEX ON lda_person_links_new (lobbyist_id)")
        ldb.swap_table(conn, "lda_person_links")
        conn.execute("DROP TABLE IF EXISTS lda_client_years_new")
        conn.execute(f"""
            CREATE TABLE lda_client_years_new AS
            SELECT f.filing_year AS year, f.client_id, min(f.client_name) AS client_name, min(f.client_state) AS state,
                   min(f.client_ein) AS client_ein, sum({SPEND}) AS spent, count(*) AS reports,
                   count(DISTINCT f.registrant_id) AS firms, (array_agg(f.document_url ORDER BY f.dt_posted DESC))[1] AS doc
            FROM lda_filings f WHERE f.filing_type NOT IN ('RR', 'RA') GROUP BY 1, 2""")
        ldb.swap_table(conn, "lda_client_years")
        conn.commit()
        n = conn.execute("SELECT count(*), count(DISTINCT cluster_id) FROM lda_person_links").fetchone()
    status(f"lda: {n[0]:,} lobbyists linked to {n[1]:,} people")


# --- routes ---------------------------------------------------------------------------------------

def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, lob=sys.modules[__name__], **ctx)


@router.get("/lobbying", response_class=HTMLResponse)
def hub_page(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    return _render(request, "lobbying.html", **overview())


@router.get("/lobbying/client/{key}", response_class=HTMLResponse)
def client_page(request: Request, key: str):
    from app import slugs
    i = slugs.parse("client", key)
    client_id = int(i) if i else 0
    data = client(client_id) if PUBLIC and i else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "client", client_id, data["client_name"])
    if moved:
        return moved
    return _render(request, "lobbying_client.html", **data)


@router.get("/lobbying/firm/{key}", response_class=HTMLResponse)
def firm_page(request: Request, key: str):
    from app import slugs
    i = slugs.parse("firm", key)
    registrant_id = int(i) if i else 0
    data = registrant(registrant_id) if PUBLIC and i else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "firm", registrant_id, (data["head"] or {}).get("registrant_name"))
    if moved:
        return moved
    return _render(request, "lobbying_firm.html", **data)


@router.get("/lobbying/lobbyist/{key}", response_class=HTMLResponse)
def lobbyist_page(request: Request, key: str):
    from app import slugs
    i = slugs.parse("lobbyist", key)
    lobbyist_id = int(i) if i else 0
    data = lobbyist(lobbyist_id) if PUBLIC and i else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "lobbyist", lobbyist_id, data["lobbyist_name"])
    if moved:
        return moved
    return _render(request, "lobbying_lobbyist.html", **data)
