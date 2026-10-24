"""USPTO trademarks on the site (loader/trademarks.py): trademark pages, owner pages, trademark sections on company
and nonprofit pages, and marks, serial numbers and owners in site search. Owner links carry EXACT or FUZZY and a
confidence (ip_links); every row shows its source (USPTO bulk product ID and file date).
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
log = logging.getLogger("np.trademarks")
SOURCE = ("USPTO bulk data: the Trademark Case Files Dataset (TRCFECO2; the latest release, March 2024, runs "
          "through 2023) for marks, owners, classes and goods and services; the Trademark Assignment Dataset "
          "(TRASECO) for assignments. Marks filed in the last 20 years, plus older marks still registered.")
CONVEY_LABEL = {"assignment": "Assignment", "name change": "Name change", "security interest": "Security interest",
                "merger": "Merger", "release": "Release", "license": "License", "correction": "Correction",
                "other": "Other"}
SHOWN = 200


def _ready(conn, table: str = "tm_marks") -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (table,)).fetchone()["ok"]


def tsdr_url(serial: str) -> str:
    return f"https://tsdr.uspto.gov/#caseNumber={serial}&caseType=SERIAL_NO&searchType=statusSearch"


def status_label(m: dict) -> str:
    from loader.trademarks import status_label as sl
    return sl(m)


def owner_type_label(code: str | None) -> str:
    from loader.trademarks import owner_type_label as ol
    return ol(code)


def convey_label(v: str | None) -> str:
    return CONVEY_LABEL.get((v or "").lower(), (v or "Not reported").capitalize())


def mark(serial: str) -> dict | None:
    from app.patents import link_rows
    with db.conn() as conn:
        if not _ready(conn):
            return None
        m = conn.execute("SELECT * FROM tm_marks WHERE serial_no = %s", (serial,)).fetchone()
        if not m:
            return None
        owners = conn.execute("SELECT * FROM tm_owners WHERE serial_no = %s ORDER BY owner_type, seq", (serial,)).fetchall()
        for o in owners:
            o["links"] = link_rows(conn, "tm_owner", o["owner_key"]) if o["owner_key"] else []
        history = conn.execute("""SELECT x.* FROM tm_assignment_docs d JOIN tm_assignments x USING (rf_id)
                                  WHERE d.serial_no = %s ORDER BY x.record_date DESC NULLS LAST LIMIT 100""",
                               (serial,)).fetchall()
        if history:
            parties = conn.execute("SELECT * FROM tm_assignment_parties WHERE rf_id = ANY(%s) ORDER BY rf_id, role, seq",
                                   ([h["rf_id"] for h in history],)).fetchall()
            for h in history:
                h["assignors"] = [p for p in parties if p["rf_id"] == h["rf_id"] and p["role"] == "assignor"]
                h["assignees"] = [p for p in parties if p["rf_id"] == h["rf_id"] and p["role"] == "assignee"]
    return {"m": m, "owners": owners, "history": history, "status": status_label(m)}


def owner(key: str) -> dict | None:
    from app.patents import link_rows
    with db.conn() as conn:
        if not _ready(conn, "tm_owner_orgs"):
            return None
        o = conn.execute("SELECT * FROM tm_owner_orgs WHERE owner_key = %s", (key,)).fetchone()
        if not o:
            return None
        marks = conn.execute(f"""SELECT DISTINCT ON (m.live, m.filing_date, m.serial_no) m.*, ow.owner_type
                                 FROM tm_owners ow JOIN tm_marks m USING (serial_no) WHERE ow.owner_key = %s
                                 ORDER BY m.live DESC, m.filing_date DESC NULLS LAST, m.serial_no DESC
                                 LIMIT {SHOWN}""", (key,)).fetchall()
        for m in marks:
            m["status"] = status_label(m)
        links = link_rows(conn, "tm_owner", key)
    return {"o": o, "marks": marks, "links": links}


def for_record(kind: str, key: str | None) -> dict | None:
    """Marks of the trademark owners linked to a nonprofit, college, Form D issuer, registry entity or SEC filer."""
    if not key:
        return None
    try:
        with db.conn() as conn:
            if not _ready(conn, "tm_owner_orgs"):
                return None
            conn.execute("SET LOCAL statement_timeout = '3s'")
            owners = conn.execute("""SELECT o.*, l.match, l.confidence, l.how FROM ip_links l
                                     JOIN tm_owner_orgs o ON o.owner_key = l.src_key
                                     WHERE l.src_kind = 'tm_owner' AND l.target_kind = %s AND l.target_key = %s
                                     ORDER BY o.n_marks DESC LIMIT 20""", (kind, str(key))).fetchall()
            if not owners:
                return None
            marks = conn.execute("""SELECT DISTINCT ON (m.filing_date, m.serial_no) m.* FROM tm_owners ow
                                    JOIN tm_marks m USING (serial_no) WHERE ow.owner_key = ANY(%s)
                                    ORDER BY m.filing_date DESC NULLS LAST, m.serial_no DESC LIMIT 10""",
                                 ([o["owner_key"] for o in owners],)).fetchall()
            for m in marks:
                m["status"] = status_label(m)
            return {"owners": owners, "marks": marks, "total": sum(o["n_marks"] or 0 for o in owners),
                    "live": sum(o["n_live"] or 0 for o in owners)}
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        log.exception("trademarks for %s %s", kind, key)
        return None


def search(q: str) -> dict:
    """Site search: a serial number (8 digits) or registration number (7 digits or fewer) finds the mark; mark text
    finds marks (exact, then starting with), and owners by name (legal endings aside)."""
    out = {"marks": [], "owners": []}
    q = (q or "").strip()
    if len(q) < 2:
        return out
    try:
        with db.conn() as conn:
            if not _ready(conn, "tm_owner_orgs"):
                return out
            conn.execute("SET LOCAL statement_timeout = '3s'")
            d = re.sub(r"[\s,]", "", q)
            if re.fullmatch(r"\d{8}", d):
                out["marks"] = conn.execute("SELECT * FROM tm_marks WHERE serial_no = %s", (d,)).fetchall()
            elif re.fullmatch(r"\d{5,7}", d):
                out["marks"] = conn.execute("SELECT * FROM tm_marks WHERE registration_no = %s LIMIT 5",
                                            (d.lstrip("0"),)).fetchall()
            else:
                from loader.recalls import core
                from loader.trademarks import mark_norm
                mn = mark_norm(q)
                if mn and len(mn) >= 2:
                    out["marks"] = conn.execute("""SELECT * FROM tm_marks WHERE mark_norm = %s
                                                   ORDER BY live DESC, filing_date DESC NULLS LAST LIMIT 10""",
                                                (mn,)).fetchall()
                    if not out["marks"] and len(mn) >= 4:
                        out["marks"] = conn.execute("""SELECT * FROM tm_marks WHERE mark_norm LIKE %s
                                                       ORDER BY live DESC, filing_date DESC NULLS LAST LIMIT 10""",
                                                    (mn + " %",)).fetchall()
                c = core(q)
                if len(c) >= 3:
                    out["owners"] = conn.execute("""SELECT * FROM tm_owner_orgs WHERE name_core = %s
                                                    ORDER BY n_marks DESC LIMIT 5""", (c,)).fetchall()
            for m in out["marks"]:
                m["status"] = status_label(m)
    except Exception:  # noqa: BLE001 - an extra; never fail a search
        log.exception("trademark search %s", q)
    return out


def _render(request, template, **ctx):
    from app.main import render
    return render(request, template, **ctx)


@router.get("/trademark/{serial}", response_class=HTMLResponse)
def trademark_page(request: Request, serial: str):
    if not re.fullmatch(r"\d{8}", serial):
        raise HTTPException(404)
    data = mark(serial)
    if not data:
        raise HTTPException(404)
    return _render(request, "trademark.html", **data)


@router.get("/trademarks/owner/{key}", response_class=HTMLResponse)
def owner_page(request: Request, key: str):
    if not re.fullmatch(r"[0-9a-f]{12}", key):
        raise HTTPException(404)
    data = owner(key)
    if not data:
        raise HTTPException(404)
    return _render(request, "trademark_owner.html", **data)
