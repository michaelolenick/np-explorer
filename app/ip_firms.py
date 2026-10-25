"""Firms derived from USPTO data in the business directory (loader/ip_firms.py): USPTO-only firm pages at
/business/USPTO/<firm_id> (app/business.entity_page hands them here), firms in the directory search, and the USPTO
source line on a matched registry entity's page. Registry data is never changed: a match only adds a line. Firms
whose names read as a person's (ip_firms.hidden) are left out of pages and search."""

from __future__ import annotations

import logging

from app import db

log = logging.getLogger("np.ip_firms")
NOTE = ("Derived from USPTO records only (patent assignees and trademark owners); FURP found no state registration, "
        "Form D, Form ADV, nonprofit, SEC or lobbying record with this name and place.")


def _ready(conn) -> bool:
    return conn.execute("SELECT to_regclass('ip_firms') IS NOT NULL AS ok").fetchone()["ok"]


def firm(firm_id: str) -> dict | None:
    from app.patents import link_rows
    with db.conn() as conn:
        if not _ready(conn):
            return None
        f = conn.execute("SELECT * FROM ip_firms WHERE firm_id = %s AND NOT hidden", (firm_id,)).fetchone()
        if not f:
            return None
        pats = conn.execute("""SELECT p.patent_id, p.title, p.granted, p.src_product, p.src_date
                               FROM pat_assignees a JOIN pat_patents p USING (patent_id)
                               WHERE a.assignee_id = ANY(%s) ORDER BY p.granted DESC, p.patent_id DESC LIMIT 25""",
                            (f["assignee_ids"] or [],)).fetchall()
        marks = conn.execute("""SELECT DISTINCT ON (m.filing_date, m.serial_no) m.* FROM tm_owners o
                                JOIN tm_marks m USING (serial_no) WHERE o.owner_key = ANY(%s)
                                ORDER BY m.filing_date DESC NULLS LAST, m.serial_no DESC LIMIT 25""",
                             (f["owner_keys"] or [],)).fetchall()
        from app.trademarks import status_label
        for m in marks:
            m["status"] = status_label(m)
        related = conn.execute("""SELECT r.*, x.n_patents, x.n_marks FROM ip_firm_related r
                                  LEFT JOIN ip_firms x ON r.kind = 'firm' AND x.firm_id = r.key
                                  WHERE r.firm_id = %s AND NOT coalesce(x.hidden, false)
                                  ORDER BY r.kind, r.name LIMIT 50""", (firm_id,)).fetchall()
        links = link_rows(conn, "firm", firm_id)
    return {"f": f, "patents": pats, "marks": marks, "related": related, "links": links}


def for_biz(state: str, entity_id: str) -> dict | None:
    """The USPTO source line for a registry entity a derived firm matched: patents, trademarks, state of
    organization."""
    try:
        with db.conn() as conn:
            if not _ready(conn):
                return None
            conn.execute("SET LOCAL statement_timeout = '3s'")
            return conn.execute("""SELECT * FROM ip_firms WHERE match_kind = 'biz' AND match_key = %s
                                   ORDER BY n_patents + n_marks DESC LIMIT 1""", (f"{state}:{entity_id}",)).fetchone()
    except Exception:  # noqa: BLE001 - an extra line; never fail the page
        log.exception("ip firm for %s %s", state, entity_id)
        return None


def search(q: str, limit: int = 20) -> list[dict]:
    """Directory search: USPTO-only firms named q (legal endings aside), exact first, then starting with it."""
    from loader.recalls import core
    c = core(q or "")
    if len(c) < 3:
        return []
    try:
        with db.conn() as conn:
            if not _ready(conn):
                return []
            conn.execute("SET LOCAL statement_timeout = '3s'")
            rows = conn.execute("""SELECT * FROM ip_firms WHERE name_core = %s AND match_kind IS NULL AND NOT hidden
                                   ORDER BY n_patents + n_marks DESC LIMIT %s""", (c, limit)).fetchall()
            return rows or conn.execute("""SELECT * FROM ip_firms WHERE name_core LIKE %s AND match_kind IS NULL
                                           AND NOT hidden ORDER BY n_patents + n_marks DESC LIMIT %s""", (c + " %", limit)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("ip firm search %s", q)
        return []


def place(f: dict) -> str:
    parts = [x for x in (f.get("city"), f.get("state")) if x]
    if f.get("country") and f.get("country") != "US":
        parts.append(f["country"])
    return ", ".join(parts) or "Not reported"


def org_place(f: dict) -> str:
    if f.get("org_state"):
        return f["org_state"]
    if f.get("org_country"):
        return f["org_country"]
    return "Not reported"
