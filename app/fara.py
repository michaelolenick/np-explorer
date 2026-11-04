"""Foreign agents (FARA registrations, loader/fara.py): the /fara hub, the registrant, foreign principal and
short-form registrant lists, one page per registrant, and the FARA rows on person and organization pages.
Shown unless FARA_PUBLIC=0 (the pages answer 404 while the tables are missing)."""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("FARA_PUBLIC", "1") == "1"
SOURCE = ("U.S. Department of Justice, FARA eFile bulk data (registrants, foreign principals and short-form "
          "registrants), updated daily by the Department; active and terminated registrations since the files begin.")
LIMIT = 200
KINDS = {"registrants": "Registrants", "principals": "Foreign principals", "people": "Short-form registrants"}
_STATE = re.compile(r"^[A-Za-z]{2}$")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, fara=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('fara_registrants') AS t").fetchone()["t"] is not None


def _like(q: str) -> str:
    from app.boards import norm
    return f"%{norm(q)}%"


def overview() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        totals = conn.execute("""
            SELECT (SELECT count(*) FROM fara_registrants) AS registrants,
                   (SELECT count(*) FROM fara_registrants WHERE termination_date IS NULL) AS registrants_active,
                   (SELECT count(*) FROM fara_principals) AS principals,
                   (SELECT count(*) FROM fara_principals WHERE termination_date IS NULL) AS principals_active,
                   (SELECT count(DISTINCT country) FROM fara_principals WHERE termination_date IS NULL) AS countries,
                   (SELECT count(*) FROM fara_short_forms) AS people,
                   (SELECT count(*) FROM fara_short_forms WHERE termination_date IS NULL) AS people_active,
                   (SELECT count(*) FROM fara_person_links) AS person_links,
                   (SELECT count(*) FROM fara_org_links) AS org_links,
                   (SELECT min(registration_date) FROM fara_registrants) AS first,
                   (SELECT max(loaded) FROM fara_registrants) AS loaded""").fetchone()
        countries = conn.execute("""SELECT country, count(*) AS n, count(DISTINCT reg_number) AS registrants
                                    FROM fara_principals WHERE termination_date IS NULL AND country IS NOT NULL
                                    GROUP BY 1 ORDER BY 2 DESC LIMIT 30""").fetchall()
        latest = conn.execute("""SELECT r.*, (SELECT string_agg(p.principal || coalesce(' (' || p.country || ')', ''), '; '
                                                     ORDER BY p.registration_date DESC)
                                              FROM (SELECT * FROM fara_principals WHERE reg_number = r.reg_number
                                                    ORDER BY registration_date DESC NULLS LAST LIMIT 3) p) AS principals
                                 FROM fara_registrants r ORDER BY r.registration_date DESC NULLS LAST, r.reg_number DESC
                                 LIMIT 25""").fetchall()
    return {"totals": totals, "countries": countries, "latest": latest}


def registrants(q: str = "", state: str | None = None, active: bool = True, limit: int = LIMIT) -> list[dict]:
    where, params = [], {"lim": limit}
    if q:
        where.append("(r.name_core LIKE %(q)s OR lower(r.business_name) LIKE %(q)s)")
        params["q"] = _like(q)
    if state:
        where.append("r.state = %(st)s")
        params["st"] = state
    if active:
        where.append("r.termination_date IS NULL")
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT r.* FROM fara_registrants r WHERE {" AND ".join(where) or "true"}
                                ORDER BY r.registration_date DESC NULLS LAST, r.reg_number DESC LIMIT %(lim)s""",
                            params).fetchall()


def principals(q: str = "", country: str | None = None, active: bool = True, limit: int = LIMIT) -> list[dict]:
    where, params = [], {"lim": limit}
    if q:
        where.append("(p.principal_core LIKE %(q)s OR lower(p.registrant_name) LIKE %(q)s)")
        params["q"] = _like(q)
    if country:
        where.append("upper(p.country) = %(c)s")
        params["c"] = country.upper()
    if active:
        where.append("p.termination_date IS NULL")
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT p.* FROM fara_principals p WHERE {" AND ".join(where) or "true"}
                                ORDER BY p.registration_date DESC NULLS LAST, p.id DESC LIMIT %(lim)s""", params).fetchall()


def people(q: str = "", active: bool = True, limit: int = LIMIT) -> list[dict]:
    where, params = [], {"lim": limit}
    if q:
        where.append("(s.name_norm LIKE %(q)s OR lower(s.registrant_name) LIKE %(q)s)")
        params["q"] = _like(q)
    if active:
        where.append("s.termination_date IS NULL")
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT s.*, l.cluster_id FROM fara_short_forms s
                                LEFT JOIN fara_person_links l ON l.short_form_id = s.id
                                WHERE {" AND ".join(where) or "true"}
                                ORDER BY s.form_date DESC NULLS LAST, s.id DESC LIMIT %(lim)s""", params).fetchall()


def countries() -> list[dict]:
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute("""SELECT country, count(*) AS n FROM fara_principals WHERE country IS NOT NULL
                               GROUP BY 1 ORDER BY 1""").fetchall()


def registrant(number: str) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        r = conn.execute("SELECT * FROM fara_registrants WHERE reg_number = %s", (number,)).fetchone()
        if not r:
            return None
        prins = conn.execute("""SELECT * FROM fara_principals WHERE reg_number = %s
                                ORDER BY termination_date IS NOT NULL, registration_date DESC NULLS LAST, principal""",
                             (number,)).fetchall()
        sf = conn.execute("""SELECT s.*, l.cluster_id FROM fara_short_forms s
                             LEFT JOIN fara_person_links l ON l.short_form_id = s.id
                             WHERE s.reg_number = %s
                             ORDER BY s.termination_date IS NOT NULL, s.form_date DESC NULLS LAST, s.last_name, s.first_name""",
                          (number,)).fetchall()
        links = []
        for l in conn.execute("SELECT kind, key, how FROM fara_org_links WHERE reg_number = %s", (number,)).fetchall():
            if l["kind"] == "org":
                o = conn.execute("SELECT name FROM organizations WHERE ein = %s", (l["key"],)).fetchone()
                links.append({"label": "Nonprofit", "name": o["name"] if o else l["key"], "url": f"/org/{l['key']}", "how": l["how"]})
            elif l["kind"] == "lda":
                o = conn.execute("""SELECT registrant_name FROM lda_filings WHERE registrant_id = %s
                                    ORDER BY dt_posted DESC NULLS LAST LIMIT 1""", (int(l["key"]),)).fetchone()
                links.append({"label": "Federal lobbying registrant", "name": o["registrant_name"] if o else l["key"],
                              "url": f"/lobbying/firm/{l['key']}", "how": l["how"]})
    return {"r": r, "principals": prins, "people": sf, "links": links}


def person_rows(cluster_id: int) -> list[dict]:
    """Short-form registrations linked to a person page (the FARA rows in the politics section)."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            return conn.execute("""SELECT s.*, l.how, r.name AS reg_name FROM fara_person_links l
                                   JOIN fara_short_forms s ON s.id = l.short_form_id
                                   JOIN fara_registrants r ON r.reg_number = s.reg_number
                                   WHERE l.cluster_id = %s ORDER BY s.form_date DESC NULLS LAST LIMIT 50""",
                                (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        return []


def org_rows(ein: str) -> list[dict]:
    """FARA registrants linked to a nonprofit (the organization page)."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            return conn.execute("""SELECT r.*, l.how FROM fara_org_links l JOIN fara_registrants r USING (reg_number)
                                   WHERE l.kind = 'org' AND l.key = %s ORDER BY r.registration_date DESC LIMIT 10""",
                                (ein,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/fara", response_class=HTMLResponse)
def hub_page(request: Request):
    _gate()
    data = overview()
    if data is None:
        raise HTTPException(404)
    return _render(request, "fara.html", **data)


@router.get("/fara/registrants", response_class=HTMLResponse)
def registrants_page(request: Request, q: str = Query("", max_length=100), state: str = Query("", max_length=2),
                     all: str = Query("", max_length=1)):
    _gate()
    st = state.upper() if _STATE.match(state) else None
    rows = registrants(q.strip(), st, active=all != "1")
    return _render(request, "fara_list.html", kind="registrants", q=q, state=st or "", all=all == "1", rows=rows, country="")


@router.get("/fara/principals", response_class=HTMLResponse)
def principals_page(request: Request, q: str = Query("", max_length=100), country: str = Query("", max_length=80),
                    all: str = Query("", max_length=1)):
    _gate()
    c = re.sub(r"[^A-Za-z ,.'()-]", "", country).strip()[:80]
    rows = principals(q.strip(), c or None, active=all != "1")
    return _render(request, "fara_list.html", kind="principals", q=q, country=c, all=all == "1", rows=rows, state="",
                   country_list=countries())


@router.get("/fara/people", response_class=HTMLResponse)
def people_page(request: Request, q: str = Query("", max_length=100), all: str = Query("", max_length=1)):
    _gate()
    rows = people(q.strip(), active=all != "1")
    return _render(request, "fara_list.html", kind="people", q=q, all=all == "1", rows=rows, state="", country="")


@router.get("/fara/registrant/{number}", response_class=HTMLResponse)
def registrant_page(request: Request, number: str):
    _gate()
    if not re.fullmatch(r"\d{1,8}", number):
        raise HTTPException(404)
    data = registrant(number)
    if not data:
        raise HTTPException(404)
    return _render(request, "fara_registrant.html", **data)
