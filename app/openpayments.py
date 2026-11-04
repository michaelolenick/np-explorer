"""Open Payments (loader/openpayments.py): the /openpayments hub with totals by year and a search, one page per
recipient (physician, practitioner or teaching hospital) and per paying company, the Open Payments rows on person
and organization pages, and cross-links (app/xlinks.py)."""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("OPENPAYMENTS_PUBLIC", "1") == "1"
SOURCE = ("CMS Open Payments: payments and transfers of value that drug and medical device makers and group purchasing "
          "organizations report to Medicare, program years 2019 on, as published by CMS (general, research and ownership "
          "records; refreshed by CMS each June and January).")
KINDS = {"g": "General payment", "r": "Research payment", "o": "Ownership or investment interest"}
_STATE = re.compile(r"^[A-Za-z]{2}$")
_KEY = re.compile(r"^[phn][0-9a-f]{1,20}$")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, op=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('op_payer_years') AS t").fetchone()["t"] is not None


def overview() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        years = conn.execute("""SELECT program_year, kind, sum(n) AS n, sum(total) AS total FROM op_payer_years
                                GROUP BY 1, 2 ORDER BY 1 DESC, 2""").fetchall()
        totals = conn.execute("""SELECT (SELECT count(*) FROM op_recipients) AS recipients,
                                        (SELECT count(*) FROM op_recipients WHERE kind = 'Teaching hospital') AS hospitals,
                                        (SELECT count(*) FROM op_payers) AS payers,
                                        (SELECT count(*) FROM op_person_links) AS person_links,
                                        (SELECT count(*) FROM op_org_links) AS org_links,
                                        (SELECT max(loaded) FROM op_files) AS loaded""").fetchone()
        payers = conn.execute("SELECT * FROM op_payers ORDER BY total DESC NULLS LAST LIMIT 25").fetchall()
        hospitals = conn.execute("""SELECT * FROM op_recipients WHERE kind = 'Teaching hospital' ORDER BY total DESC NULLS LAST LIMIT 25""").fetchall()
        top = conn.execute("""SELECT * FROM op_recipients WHERE profile_id IS NOT NULL ORDER BY total DESC NULLS LAST LIMIT 25""").fetchall()
    return {"years": years, "totals": totals, "payers": payers, "hospitals": hospitals, "top": top}


def search(q: str, state: str | None, limit: int = 100) -> dict:
    from app.names import normalize_name
    from loader.recalls import core
    out = {"recipients": [], "payers": []}
    if not q:
        return out
    nn, c = normalize_name(q), core(q)
    with db.conn() as conn:
        if not _ok(conn):
            return out
        if nn and len(nn) >= 3:
            params = {"q": nn + "%", "lim": limit, "st": state}
            out["recipients"] = conn.execute(f"""SELECT r.*, l.cluster_id FROM op_recipients r
                                                 LEFT JOIN op_person_links l ON l.recipient_key = r.key
                                                 WHERE r.name_norm LIKE %(q)s {"AND r.state = %(st)s" if state else ""}
                                                 ORDER BY r.total DESC NULLS LAST LIMIT %(lim)s""", params).fetchall()
            # last name only: "smith" finds "john a smith" too
            if not out["recipients"] and " " not in nn:
                out["recipients"] = conn.execute(f"""SELECT r.*, l.cluster_id FROM op_recipients r
                                                     LEFT JOIN op_person_links l ON l.recipient_key = r.key
                                                     WHERE r.last IS NOT NULL AND lower(r.last) = %(ln)s {"AND r.state = %(st)s" if state else ""}
                                                     ORDER BY r.total DESC NULLS LAST LIMIT %(lim)s""",
                                                 {"ln": nn, "lim": limit, "st": state}).fetchall()
        if c and len(c) >= 3:
            out["payers"] = conn.execute("""SELECT * FROM op_payers WHERE lower(name) LIKE %s ORDER BY total DESC NULLS LAST LIMIT 50""",
                                         ("%" + c.split(" ")[0] + "%",)).fetchall()
            out["hospitals"] = conn.execute("""SELECT * FROM op_recipients WHERE profile_id IS NULL AND lower(name) LIKE %s
                                               ORDER BY total DESC NULLS LAST LIMIT 50""", ("%" + c.split(" ")[0] + "%",)).fetchall()
    return out


def recipient(key: str) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        r = conn.execute("SELECT * FROM op_recipients WHERE key = %s", (key,)).fetchone()
        if not r:
            return None
        link = conn.execute("SELECT cluster_id, how FROM op_person_links WHERE recipient_key = %s", (key,)).fetchone()
        years = conn.execute("""SELECT program_year, kind, count(*) AS n, sum(amount) AS total FROM op_payments
                                WHERE recipient_key = %s GROUP BY 1, 2 ORDER BY 1 DESC, 2""", (key,)).fetchall()
        natures = conn.execute("""SELECT nature, count(*) AS n, sum(amount) AS total FROM op_payments WHERE recipient_key = %s
                                  GROUP BY 1 ORDER BY 3 DESC NULLS LAST LIMIT 30""", (key,)).fetchall()
        payers = conn.execute("""SELECT p.payer_id, y.name, count(*) AS n, sum(p.amount) AS total, min(p.program_year) AS y0, max(p.program_year) AS y1
                                 FROM op_payments p LEFT JOIN op_payers y ON y.id = p.payer_id WHERE p.recipient_key = %s
                                 GROUP BY 1, 2 ORDER BY 4 DESC NULLS LAST LIMIT 50""", (key,)).fetchall()
        rows = conn.execute("""SELECT p.*, y.name AS payer_name FROM op_payments p LEFT JOIN op_payers y ON y.id = p.payer_id
                               WHERE p.recipient_key = %s ORDER BY p.date DESC NULLS LAST, p.amount DESC LIMIT 200""", (key,)).fetchall()
        pi_rows = conn.execute("""SELECT p.*, y.name AS payer_name, r.name AS recipient_name FROM op_payments p
                                  LEFT JOIN op_payers y ON y.id = p.payer_id LEFT JOIN op_recipients r ON r.key = p.recipient_key
                                  WHERE p.pi_key = %s ORDER BY p.date DESC NULLS LAST LIMIT 100""", (key,)).fetchall() if r["pi_payments"] else []
        orgs = _org_links(conn, "recipient", key)
    return {"r": r, "link": link, "years": years, "natures": natures, "payers": payers, "rows": rows, "pi_rows": pi_rows, "orgs": orgs}


def _org_links(conn, kind: str, key: str) -> list[dict]:
    out = []
    for l in conn.execute("SELECT target_kind, target_key, how FROM op_org_links WHERE kind = %s AND key = %s", (kind, key)).fetchall():
        if l["target_kind"] == "org":
            o = conn.execute("SELECT name FROM organizations WHERE ein = %s", (l["target_key"],)).fetchone()
            out.append({"label": "Nonprofit", "name": o["name"] if o else l["target_key"], "url": f"/org/{l['target_key']}", "how": l["how"]})
        elif l["target_kind"] == "biz":
            st, _, eid = l["target_key"].partition(":")
            o = conn.execute("SELECT name FROM biz_entities WHERE state = %s AND entity_id = %s", (st, eid)).fetchone()
            out.append({"label": "Business registration", "name": o["name"] if o else eid, "url": f"/business/{st}/{eid}", "how": l["how"]})
    return out


def company(pid: int) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        p = conn.execute("SELECT * FROM op_payers WHERE id = %s", (pid,)).fetchone()
        if not p:
            return None
        years = conn.execute("""SELECT program_year, kind, n, total, recipients FROM op_payer_years
                                WHERE payer_id = %s ORDER BY 1 DESC, 2""", (pid,)).fetchall()
        natures = conn.execute("""SELECT nature, n, total FROM op_payer_natures WHERE payer_id = %s
                                  ORDER BY total DESC NULLS LAST LIMIT 30""", (pid,)).fetchall()
        recipients = conn.execute("""SELECT t.recipient_key, r.name, r.kind, r.state, r.specialty, t.n, t.total
                                     FROM op_payer_top t JOIN op_recipients r ON r.key = t.recipient_key
                                     WHERE t.payer_id = %s ORDER BY t.rk""", (pid,)).fetchall()
        products = conn.execute("""SELECT product, product_type, category, n, total FROM op_payer_products
                                   WHERE payer_id = %s ORDER BY rk""", (pid,)).fetchall()
        orgs = _org_links(conn, "payer", str(pid))
    return {"p": p, "years": years, "natures": natures, "recipients": recipients, "products": products, "orgs": orgs}


def person_rows(cluster_id: int) -> dict | None:
    """The Open Payments section of a person page: the linked recipient(s) with totals by year and top payers."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return None
            recs = conn.execute("""SELECT r.*, l.how FROM op_person_links l JOIN op_recipients r ON r.key = l.recipient_key
                                   WHERE l.cluster_id = %s ORDER BY r.total DESC""", (cluster_id,)).fetchall()
            if not recs:
                return None
            keys = [r["key"] for r in recs]
            years = conn.execute("""SELECT program_year, count(*) AS n, sum(amount) AS total FROM op_payments
                                    WHERE recipient_key = ANY(%s) GROUP BY 1 ORDER BY 1 DESC""", (keys,)).fetchall()
            payers = conn.execute("""SELECT p.payer_id, y.name, count(*) AS n, sum(p.amount) AS total
                                     FROM op_payments p LEFT JOIN op_payers y ON y.id = p.payer_id WHERE p.recipient_key = ANY(%s)
                                     GROUP BY 1, 2 ORDER BY 4 DESC NULLS LAST LIMIT 10""", (keys,)).fetchall()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        return None
    return {"recipients": recs, "years": years, "payers": payers}


def org_rows(ein: str) -> list[dict]:
    """Open Payments recipients (teaching hospitals) or payers linked to a nonprofit."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            out = []
            for l in conn.execute("SELECT kind, key, how FROM op_org_links WHERE target_kind = 'org' AND target_key = %s", (ein,)).fetchall():
                if l["kind"] == "recipient":
                    r = conn.execute("SELECT * FROM op_recipients WHERE key = %s", (l["key"],)).fetchone()
                    if r:
                        out.append({"label": "Teaching hospital receiving payments", "name": r["name"], "url": f"/openpayments/recipient/{r['key']}",
                                    "total": r["total"], "n": r["payments"], "years": (r["first_year"], r["last_year"]), "how": l["how"]})
                else:
                    p = conn.execute("SELECT * FROM op_payers WHERE id = %s", (int(l["key"]),)).fetchone()
                    if p:
                        out.append({"label": "Company reporting payments", "name": p["name"], "url": f"/openpayments/company/{p['id']}",
                                    "total": p["total"], "n": p["payments"], "years": (p["first_year"], p["last_year"]), "how": l["how"]})
            return out
    except Exception:  # noqa: BLE001
        return []


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/openpayments", response_class=HTMLResponse)
def hub_page(request: Request, q: str = Query("", max_length=100), state: str = Query("", max_length=2)):
    _gate()
    data = overview()
    if data is None:
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    found = search(q.strip(), st) if q.strip() else None
    return _render(request, "openpayments.html", q=q, state=st or "", found=found, **data)


@router.get("/openpayments/recipient/{key}", response_class=HTMLResponse)
def recipient_page(request: Request, key: str):
    _gate()
    if not _KEY.match(key):
        raise HTTPException(404)
    data = recipient(key)
    if not data:
        raise HTTPException(404)
    return _render(request, "openpayments_recipient.html", **data)


@router.get("/openpayments/company/{pid}", response_class=HTMLResponse)
def company_page(request: Request, pid: int):
    _gate()
    data = company(pid)
    if not data:
        raise HTTPException(404)
    return _render(request, "openpayments_company.html", **data)
