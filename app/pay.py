"""State and city payroll (loader/gov_payroll.py): the /pay hub listing each government payroll source, a name
search across them, and one page per source with its top-paid staff by year. University payroll stays under
/schools/pay; rows of both reach person pages through payroll_person_links (loader/colleges.py)."""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("PAY_PUBLIC", "1") == "1"
LIMIT = 200
_STATE = re.compile(r"^[A-Za-z]{2}$")
_KEY = re.compile(r"^gov_[a-z_]{2,30}$")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, pay=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('payroll_sources') AS t").fetchone()["t"] is not None


def sources() -> list[dict]:
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute("""SELECT * FROM payroll_sources WHERE source_key LIKE 'gov\\_%' ORDER BY state, title""").fetchall()


def _attach_links(conn, rows: list[dict]) -> None:
    """Person pages (payroll_person_links) and cross-links (xlinks) for a list of payroll rows."""
    if not rows:
        return
    keys = list({(r["state"], r["label"], r["name_norm"]) for r in rows if r["name_norm"]})
    links = {}
    if keys:
        for st, label, nn, cid in conn.execute("""SELECT l.state, l.label, l.name_norm, l.cluster_id FROM payroll_person_links l
                                                  JOIN unnest(%s::text[], %s::text[], %s::text[]) AS k(state, label, name_norm)
                                                    ON k.state = l.state AND k.label = l.label AND k.name_norm = l.name_norm""",
                                               ([k[0] for k in keys], [k[1] for k in keys], [k[2] for k in keys])).fetchall():
            links[(st, label, nn)] = cid
    xl = {}
    if conn.execute("SELECT to_regclass('xlinks') AS t").fetchone()["t"]:
        xkeys = [f"{st}:{label}:{nn}" for st, label, nn in keys]
        for src_key, dst_kind, dst_key, dst_name in conn.execute("""SELECT src_key, dst_kind, dst_key, dst_name FROM xlinks
                                                                     WHERE src_kind = 'payroll_person' AND src_key = ANY(%s)
                                                                     AND dst_kind <> 'person'""", (xkeys,)).fetchall():
            xl.setdefault(src_key, []).append((dst_kind, dst_key, dst_name))
    from app import xlinks as xmod
    for r in rows:
        k = (r["state"], r["label"], r["name_norm"])
        r["cluster_id"] = links.get(k)
        r["xlinks"] = [{"label": xmod.TARGETS[dk][0], "url": xmod.TARGETS[dk][1](dkey, dn), "name": dn}
                       for dk, dkey, dn in xl.get(f"{r['state']}:{r['label']}:{r['name_norm']}", []) if dk in xmod.TARGETS]


def search(q: str, state: str | None, employer: str | None, limit: int = LIMIT) -> list[dict]:
    from app.names import normalize_name
    nn = normalize_name(q)
    if not nn or len(nn) < 3:
        return []
    params = {"q": nn + "%", "lim": limit, "st": state, "emp": employer}
    with db.conn() as conn:
        if not _ok(conn):
            return []
        rows = conn.execute(f"""SELECT p.*, s.title AS source_title, s.publisher, s.pay_basis, s.url AS source_home
                                FROM payroll_person_years p JOIN payroll_sources s ON s.source_key = p.source_key
                                WHERE p.name_norm LIKE %(q)s AND NOT p.withheld
                                      {"AND p.state = %(st)s" if state else ""} {"AND p.label = %(emp)s" if employer else ""}
                                ORDER BY p.name_norm, p.fiscal_year DESC NULLS LAST, p.total_pay DESC NULLS LAST LIMIT %(lim)s""",
                            params).fetchall()
        rows = [dict(r) for r in rows]
        _attach_links(conn, rows)
    return rows


def source(key: str, year: int | None, q: str, employer: str | None, limit: int = 100) -> dict | None:
    from app.names import normalize_name
    with db.conn() as conn:
        if not _ok(conn):
            return None
        s = conn.execute("SELECT * FROM payroll_sources WHERE source_key = %s", (key,)).fetchone()
        if not s:
            return None
        years = conn.execute("""SELECT fiscal_year, n, total, top FROM payroll_source_years WHERE source_key = %s
                                ORDER BY 1 DESC NULLS LAST""", (key,)).fetchall() \
            if conn.execute("SELECT to_regclass('payroll_source_years') AS t").fetchone()["t"] else []
        if year is None:
            year = next((y["fiscal_year"] for y in years if y["fiscal_year"] is not None), None)
        ypred = "fiscal_year = %(y)s" if year is not None else "fiscal_year IS NULL"     # an indexable test
        employers = conn.execute(f"""SELECT label, count(*) AS n, sum(total_pay) AS total FROM payroll_person_years
                                     WHERE source_key = %(k)s AND {ypred} GROUP BY 1 ORDER BY 2 DESC LIMIT 40""",
                                 {"k": key, "y": year}).fetchall()
        nn = normalize_name(q) if q else ""
        params = {"k": key, "y": year, "emp": employer, "q": (nn + "%") if nn else None, "lim": limit}
        rows = conn.execute(f"""SELECT p.*, s.title AS source_title, s.publisher, s.pay_basis, s.url AS source_home
                                FROM payroll_person_years p JOIN payroll_sources s ON s.source_key = p.source_key
                                WHERE p.source_key = %(k)s AND p.{ypred} AND NOT p.withheld
                                      {"AND p.label = %(emp)s" if employer else ""} {"AND p.name_norm LIKE %(q)s" if nn else ""}
                                ORDER BY p.total_pay DESC NULLS LAST, p.id LIMIT %(lim)s""", params).fetchall()
        rows = [dict(r) for r in rows]
        _attach_links(conn, rows)
    return {"s": s, "years": years, "year": year, "employers": employers, "rows": rows, "employer": employer, "q": q}


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/pay", response_class=HTMLResponse)
def hub_page(request: Request):
    _gate()
    return _render(request, "pay.html", sources=sources())


@router.get("/pay/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = Query("", max_length=100), state: str = Query("", max_length=2),
                employer: str = Query("", max_length=200)):
    _gate()
    st = state.upper() if _STATE.match(state) else None
    rows = search(q.strip(), st, employer.strip() or None) if q.strip() else []
    return _render(request, "pay_search.html", q=q, state=st or "", employer=employer, rows=rows)


@router.get("/pay/{key}", response_class=HTMLResponse)
def source_page(request: Request, key: str, year: str = Query("", max_length=4), q: str = Query("", max_length=100),
                employer: str = Query("", max_length=200)):
    _gate()
    if not _KEY.match(key):
        raise HTTPException(404)
    y = int(year) if year.isdigit() else None
    data = source(key, y, q.strip(), employer.strip() or None)
    if not data:
        raise HTTPException(404)
    return _render(request, "pay_source.html", **data)
