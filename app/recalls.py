"""Food recalls (loader/recalls.py): the /recalls hub, one page per recalling firm, and the recalls section on
the pages of linked organizations (nonprofits, lobbying clients, SEC companies, federal award recipients).
Shown only where RECALLS_PUBLIC=1."""

from __future__ import annotations

import os
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("RECALLS_PUBLIC") == "1"
CLASSES = {"Class I": "Class I: could cause serious illness or death",
           "Class II": "Class II: could cause temporary or reversible harm",
           "Class III": "Class III: unlikely to cause harm (labeling, for example)"}
SOURCE = ("FDA food enforcement reports (openFDA), every report since June 2012. USDA FSIS meat, poultry and egg "
          "recalls are not included yet.")
ROW_COLS = """recall_number, event_id, status, classification, recalling_firm, firm_id, city, state,
              product_description, product_quantity, reason_for_recall, distribution_pattern, voluntary_mandated,
              recall_initiation_date, report_date, termination_date, source_url, data_url"""


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, rc=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('food_recall_firms') AS t").fetchone()["t"] is not None


def firm(fid: str) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        f = conn.execute("SELECT * FROM food_recall_firms WHERE firm_id = %s", (fid,)).fetchone()
        if not f:
            return None
        rows = conn.execute(f"""SELECT {ROW_COLS} FROM food_recalls WHERE firm_id = %s
                                ORDER BY recall_initiation_date DESC NULLS LAST, recall_number""", (fid,)).fetchall()
        links = conn.execute("SELECT kind, key, name FROM food_recall_links WHERE firm_id = %s ORDER BY kind, name",
                             (fid,)).fetchall()
    return {"f": f, "rows": rows, "links": links}


def for_entity(kind: str, key: str, limit: int = 50) -> dict | None:
    """The recalls section on a linked page: firms linked to this nonprofit (org), lobbying client (lobbying),
    SEC company (sec), federal recipient (fed), with their recalls, newest first."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return None
            firms = conn.execute("""SELECT f.* FROM food_recall_links l JOIN food_recall_firms f USING (firm_id)
                                    WHERE l.kind = %s AND l.key = %s ORDER BY f.recalls DESC""", (kind, key)).fetchall()
            if not firms:
                return None
            rows = conn.execute(f"""SELECT {ROW_COLS} FROM food_recalls WHERE firm_id = ANY(%s)
                                    ORDER BY recall_initiation_date DESC NULLS LAST LIMIT %s""",
                                ([f["firm_id"] for f in firms], limit)).fetchall()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        return None
    return {"firms": firms, "rows": rows, "total": sum(f["recalls"] for f in firms)}


def search(q: str = "", state: str | None = None, classification: str | None = None, year: int | None = None,
           reason: str | None = None, limit: int = 50) -> list[dict]:
    """Recalls by firm name, state, class, year of the recall and words in the reason; newest first."""
    from app.boards import norm
    where, params = [], {"lim": limit}
    if q:
        where.append("f.firm_key LIKE %(q)s")
        params["q"] = f"%{norm(q)}%"
    if state:
        where.append("r.state = %(st)s")
        params["st"] = state
    if classification:
        where.append("r.classification = %(cl)s")
        params["cl"] = classification
    if year:
        where.append("extract(year FROM r.recall_initiation_date) = %(yr)s")
        params["yr"] = year
    if reason:
        where.append("r.reason_for_recall ILIKE %(rs)s")
        params["rs"] = f"%{reason}%"
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT {", ".join("r." + c.strip() for c in ROW_COLS.split(","))}
                                FROM food_recalls r JOIN food_recall_firms f USING (firm_id)
                                WHERE {" AND ".join(where) or "true"}
                                ORDER BY r.recall_initiation_date DESC NULLS LAST, r.recall_number LIMIT %(lim)s""",
                            params).fetchall()


def hub() -> dict:
    with db.conn() as conn:
        if not _ok(conn):
            return {"totals": None, "recent": [], "reasons": []}
        totals = conn.execute("""SELECT count(*) AS n, count(DISTINCT firm_id) AS firms,
                                        count(*) FILTER (WHERE classification = 'Class I') AS c1,
                                        min(recall_initiation_date) AS first, max(report_date) AS last
                                 FROM food_recalls""").fetchone()
        reasons = conn.execute("""SELECT w AS word, count(*) AS n FROM food_recalls,
                                         unnest(ARRAY['listeria', 'salmonella', 'e. coli', 'undeclared', 'allergen',
                                                      'lead', 'foreign', 'botulism', 'mold']) AS w
                                  WHERE lower(reason_for_recall) LIKE '%%' || w || '%%'
                                  GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    return {"totals": totals, "recent": search(limit=25), "reasons": reasons}


@router.get("/recalls", response_class=HTMLResponse)
def hub_page(request: Request, q: str = Query("", max_length=100), state: str = Query("", max_length=2)):
    if not PUBLIC:
        raise HTTPException(404)
    st = state.upper() if len(state) == 2 and state.isalpha() else None
    found = search(q.strip(), st) if q.strip() or st else None
    return _render(request, "recalls.html", q=q, state=st or "", found=found, **hub())


@router.get("/recalls/firm/{key}", response_class=HTMLResponse)
def firm_page(request: Request, key: str):
    from app import slugs
    if not PUBLIC:
        raise HTTPException(404)
    fid = slugs.parse("recallfirm", key)
    data = firm(fid) if fid else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "recallfirm", fid, data["f"]["name"])
    if moved:
        return moved
    return _render(request, "recalls_firm.html", **data)


_fed_pages: list = []


def _recipient_pages() -> bool:
    """Federal recipient pages exist once their index is built (off-hours); until then, no link to them."""
    import time
    if not _fed_pages or time.time() - _fed_pages[0] > 600:
        try:
            with db.conn() as conn:
                ok = conn.execute("SELECT 1 AS x FROM pg_indexes WHERE indexname = 'usa_awards_uei'").fetchone()
        except Exception:  # noqa: BLE001
            ok = None
        _fed_pages[:] = [time.time(), bool(ok)]
    return _fed_pages[1]


def link_url(kind: str, key: str, name: str | None) -> str | None:
    if kind == "fed":
        return f"/federal-spending/recipient/{key}" if len(key) == 12 and key.isalnum() and _recipient_pages() else None
    return {"org": f"/org/{key}", "lobbying": f"/lobbying/client/{key}", "sec": f"/corporate/company/{key}",
            "pac": f"/politics/committee/{key}"}.get(kind)


LINK_LABEL = {"org": "Nonprofit filer", "lobbying": "Federal lobbying client", "sec": "SEC company",
              "fed": "Federal award recipient", "pac": "Sponsors a political committee"}
