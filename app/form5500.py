"""Form 5500 (loader/form5500.py): the /form5500 hub with a sponsor search, one page per plan sponsor (EIN) and one
per person named as a signer or preparer, each with its cross-links (app/xlinks.py). The sponsors also appear in
the business registry search and pages once loader/form5500.py supplement has run."""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("FORM5500_PUBLIC", "1") == "1"
SOURCE = ("Form 5500 and 5500-SF annual returns of employee benefit plans, from the Department of Labor's EFAST2 bulk "
          "datasets (plan years 2009 on, updated monthly): names, states and the record id only.")
PEOPLE_KINDS = ("preparer", "admin_signer", "sponsor_signer", "dfe_signer")
ROLES = {"preparer": "Preparer", "admin_signer": "Signed as plan administrator", "sponsor_signer": "Signed for the plan sponsor",
         "dfe_signer": "Signed for the direct filing entity", "preparer_firm": "Preparer's firm", "trust": "Fiduciary trust",
         "trustee": "Trustee or custodian", "sponsor_dba": "Sponsor's DBA", "sponsor_care_of": "Sponsor's care-of name",
         "admin_care_of": "Administrator's care-of name", "last_sponsor": "Previously reported sponsor"}
_STATE = re.compile(r"^[A-Za-z]{2}$")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, f5=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('form5500_sponsors') AS t").fetchone()["t"] is not None


def overview() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        totals = conn.execute("""SELECT (SELECT count(*) FROM form5500_sponsors) AS sponsors,
                                        (SELECT sum(filings) FROM form5500_sponsors) AS filings,
                                        (SELECT min(first_year) FROM form5500_sponsors) AS first,
                                        (SELECT max(last_year) FROM form5500_sponsors) AS last,
                                        (SELECT max(loaded) FROM form5500_files) AS loaded""").fetchone()
        files = conn.execute("SELECT year, form, rows FROM form5500_files ORDER BY year DESC, form").fetchall()
        states = conn.execute("""SELECT state, count(*) AS n, sum(filings) AS filings FROM form5500_sponsors
                                 WHERE state IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 60""").fetchall()
    return {"totals": totals, "files": files, "states": states}


def search(q: str, state: str | None, limit: int = 100) -> list[dict]:
    from loader.recalls import core
    where, params = [], {"lim": limit}
    digits = re.sub(r"\D", "", q)
    if len(digits) == 9:
        where.append("s.ein = %(ein)s")
        params["ein"] = digits
    elif q:
        c = core(q)
        if len(c) < 3:
            return []
        where.append("s.name_core LIKE %(q)s")
        params["q"] = c + "%"
    if state:
        where.append("s.state = %(st)s")
        params["st"] = state
    if not where:
        return []
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT s.* FROM form5500_sponsors s WHERE {" AND ".join(where)}
                                ORDER BY s.filings DESC, s.name LIMIT %(lim)s""", params).fetchall()


def sponsor(ein: str) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        s = conn.execute("SELECT * FROM form5500_sponsors WHERE ein = %s", (ein,)).fetchone()
        if not s:
            return None
        filings = conn.execute("""SELECT * FROM form5500_filings WHERE sponsor_ein = %s
                                  ORDER BY plan_year DESC NULLS LAST, date_received DESC NULLS LAST, plan_num LIMIT 300""", (ein,)).fetchall()
        names = conn.execute("""SELECT n.kind, n.name, n.name_norm, n.state, n.ein, count(*) AS n, min(f.plan_year) AS y0, max(f.plan_year) AS y1
                                FROM form5500_names n JOIN form5500_filings f ON f.ack_id = n.ack_id
                                WHERE f.sponsor_ein = %s GROUP BY 1, 2, 3, 4, 5 ORDER BY 1, 2 LIMIT 300""", (ein,)).fetchall()
        biz = conn.execute("SELECT state, entity_id FROM biz_entities WHERE ein = %s AND source = 'form5500' LIMIT 1", (ein,)).fetchone() \
            if conn.execute("SELECT to_regclass('biz_entities') AS t").fetchone()["t"] else None
        org = conn.execute("SELECT name FROM organizations WHERE ein = %s", (ein,)).fetchone()
    return {"s": s, "filings": filings, "names": names, "biz": biz, "org": org}


def person(state: str, name_norm: str) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        rows = conn.execute("""SELECT n.kind, n.name, f.ack_id, f.form, f.plan_year, f.plan_name, f.sponsor_name, f.sponsor_ein,
                                      f.sponsor_state, f.admin_name, f.date_received
                               FROM form5500_names n JOIN form5500_filings f ON f.ack_id = n.ack_id
                               WHERE n.name_norm = %s AND n.state = %s AND n.kind = ANY(%s)
                               ORDER BY f.plan_year DESC NULLS LAST, f.sponsor_name LIMIT 500""",
                            (name_norm, state, list(PEOPLE_KINDS))).fetchall()
    if not rows:
        return None
    return {"rows": rows, "person_name": rows[0]["name"], "state": state, "name_norm": name_norm}


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/form5500", response_class=HTMLResponse)
def hub_page(request: Request, q: str = Query("", max_length=120), state: str = Query("", max_length=2)):
    _gate()
    data = overview()
    if data is None:
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    found = search(q.strip(), st) if q.strip() or st else None
    return _render(request, "form5500.html", q=q, state=st or "", found=found, **data)


@router.get("/form5500/sponsor/{ein}", response_class=HTMLResponse)
def sponsor_page(request: Request, ein: str):
    _gate()
    if not re.fullmatch(r"\d{9}", ein):
        raise HTTPException(404)
    data = sponsor(ein)
    if not data:
        raise HTTPException(404)
    return _render(request, "form5500_sponsor.html", **data)


@router.get("/form5500/name/{key:path}", response_class=HTMLResponse)
def person_page(request: Request, key: str):
    _gate()
    state, _, name_norm = key.partition(":")
    if not _STATE.match(state) or not re.fullmatch(r"[a-z0-9 ]{3,120}", name_norm):
        raise HTTPException(404)
    data = person(state.upper(), name_norm)
    if not data:
        raise HTTPException(404)
    return _render(request, "form5500_name.html", **data)
