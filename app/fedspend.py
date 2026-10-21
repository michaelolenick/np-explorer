"""Federal grants and contracts from USAspending: the hub page, the federal awards section on organization pages,
and officer pay on person pages. Data: loader/usaspending.py (usa_awards, usa_officers) and fedspend_links()
below (summary tables and links to people). Routes live on `router`, which app/main.py includes.

Shown only where FEDSPEND_PUBLIC=1 (dev while the load is checked; production once promoted). Every award links
to its page on usaspending.gov.
"""

from __future__ import annotations

import os
import sys

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("FEDSPEND_PUBLIC") == "1"
KIND_LABEL = {"assistance": "Grant or other assistance", "contract": "Contract"}
ASSISTANCE_TYPES = {"02": "Block grant", "03": "Formula grant", "04": "Project grant", "05": "Cooperative agreement",
                    "06": "Direct payment, specified use", "07": "Direct loan", "08": "Guaranteed or insured loan",
                    "09": "Insurance", "10": "Direct payment, unrestricted", "11": "Other"}


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS t", (table,)).fetchone()["t"] is not None


def org_awards(ein: str, limit: int = 200) -> dict | None:
    """Federal awards to this organization (linked by name and zip), largest first, with totals by year."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            totals = conn.execute("""
                SELECT fiscal_year, kind, sum(obligation) AS total, count(*) AS n FROM usa_awards
                WHERE recipient_ein = %s GROUP BY 1, 2 ORDER BY 1 DESC, 2""", (ein,)).fetchall()
            if not totals:
                return None
            rows = conn.execute("""
                SELECT award_key, kind, fiscal_year, obligation, agency, sub_agency, program_code, program_title,
                       award_type, description, permalink
                FROM usa_awards WHERE recipient_ein = %s AND obligation <> 0
                ORDER BY fiscal_year DESC, obligation DESC LIMIT %s""", (ein, limit)).fetchall()
            officers = conn.execute("""
                SELECT DISTINCT ON (o.name, a.fiscal_year) o.name, o.amount, a.fiscal_year, a.permalink
                FROM usa_officers o JOIN usa_awards a ON a.award_key = o.award_key AND a.fiscal_year = o.fiscal_year
                WHERE a.recipient_ein = %s AND o.amount > 0
                ORDER BY o.name, a.fiscal_year DESC, o.amount DESC""", (ein,)).fetchall()
    except Exception:  # noqa: BLE001 - tables not built
        return None
    years: dict = {}
    for t in totals:
        y = years.setdefault(t["fiscal_year"], {"fiscal_year": t["fiscal_year"], "assistance": 0, "contract": 0, "n": 0})
        y[t["kind"]] += t["total"] or 0
        y["n"] += t["n"]
    officers = sorted(officers, key=lambda o: (-o["fiscal_year"], -(o["amount"] or 0)))[:25]
    return {"years": list(years.values()), "rows": rows, "officers": officers,
            "total": sum((t["total"] or 0) for t in totals)}


def person_pay(cluster_id: int) -> list[dict]:
    """Officer pay this person's employers reported to USAspending (linked by name and organization)."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            return conn.execute("""
                SELECT DISTINCT ON (a.fiscal_year, a.recipient_name) a.fiscal_year, a.recipient_name, a.recipient_ein,
                       o.name, o.amount, a.permalink
                FROM usa_person_links l
                JOIN usa_officers o ON o.award_key = l.award_key AND o.fiscal_year = l.fiscal_year AND o.n = l.n
                JOIN usa_awards a ON a.award_key = l.award_key AND a.fiscal_year = l.fiscal_year
                WHERE l.cluster_id = %s
                ORDER BY a.fiscal_year DESC, a.recipient_name, o.amount DESC NULLS LAST""", (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


def overview() -> dict:
    with db.conn() as conn:
        if not _has(conn, "usa_recipient_totals"):
            return {"years": [], "runs": []}
        years = conn.execute("""SELECT fiscal_year, kind, sum(total) AS total, count(*) AS recipients,
                                       count(*) FILTER (WHERE nonprofit) AS nonprofits,
                                       sum(total) FILTER (WHERE nonprofit) AS to_nonprofits,
                                       count(*) FILTER (WHERE recipient_ein IS NOT NULL) AS linked
                                FROM usa_recipient_totals GROUP BY 1, 2 ORDER BY 1 DESC, 2""").fetchall()
        runs = conn.execute("SELECT max(finished) AS updated, sum(transactions) AS transactions FROM usa_runs").fetchone()
    return {"years": years, "runs": runs}


# --- summary tables and links (run after a load) -------------------------------------------------

def build_summaries(status=print) -> None:
    """usa_recipient_totals: per fiscal year, kind and recipient (name and zip5), the obligations and award count;
    usa_person_links: officers matched to people on the site (same normalized name, and the award's recipient is
    one of the person's organizations, by normalized name: fec_person_keys)."""
    from loader import db as ldb
    from loader.fec_links import ensure_function
    from app.names import normalize_name
    with ldb.connect() as conn:
        ensure_function(conn)
        conn.execute("SET work_mem = '1GB'")
        conn.execute("DROP TABLE IF EXISTS usa_recipient_totals_new")
        conn.execute("""
            CREATE TABLE usa_recipient_totals_new AS
            SELECT fiscal_year, kind, recipient_name, zip5, min(recipient_ein) AS recipient_ein,
                   bool_or(nonprofit) AS nonprofit, min(state) AS state, min(city) AS city,
                   sum(obligation) AS total, count(*) AS n_awards,
                   mode() WITHIN GROUP (ORDER BY agency) AS top_agency,
                   (array_agg(permalink ORDER BY obligation DESC NULLS LAST))[1] AS top_award_url
            FROM usa_awards WHERE recipient_name IS NOT NULL GROUP BY 1, 2, 3, 4""")
        conn.execute("CREATE INDEX ON usa_recipient_totals_new (recipient_ein)")
        ldb.swap_table(conn, "usa_recipient_totals")
        conn.commit()
        # Officer names to normalized form in Python (the same normalize_name as everywhere), then match in SQL.
        conn.execute("DROP TABLE IF EXISTS usa_officer_norm")
        conn.execute("CREATE TEMP TABLE usa_officer_norm (award_key text, fiscal_year smallint, n smallint, "
                     "name_norm text, core text)")
        rows = conn.execute("""SELECT o.award_key, o.fiscal_year, o.n, o.name, np_name_core(a.recipient_name)
                               FROM usa_officers o JOIN usa_awards a ON a.award_key = o.award_key
                                    AND a.fiscal_year = o.fiscal_year
                               WHERE o.name IS NOT NULL""").fetchall()
        with conn.cursor().copy("COPY usa_officer_norm FROM STDIN") as cp:
            for k, fy, n, name, core in rows:
                cp.write_row((k, fy, n, normalize_name(name), core))
        conn.execute("DROP TABLE IF EXISTS usa_person_links_new")
        conn.execute("""CREATE TABLE usa_person_links_new AS
                        SELECT o.award_key, o.fiscal_year, o.n, k.cluster_id FROM usa_officer_norm o
                        JOIN fec_person_keys k ON k.name_norm = o.name_norm AND k.core = o.core""")
        conn.execute("CREATE INDEX ON usa_person_links_new (cluster_id)")
        ldb.swap_table(conn, "usa_person_links")
        conn.commit()
        n = conn.execute("SELECT count(*), count(DISTINCT cluster_id) FROM usa_person_links").fetchone()
    status(f"fedspend: summaries built; {n[0]:,} officer records linked to {n[1]:,} people")


# --- routes -------------------------------------------------------------------------------------

def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, fs=sys.modules[__name__], **ctx)


@router.get("/federal-spending", response_class=HTMLResponse)
def hub_page(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    return _render(request, "fedspend.html", **overview())
