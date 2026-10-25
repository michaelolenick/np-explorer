"""USPTO patents on the site (loader/patents.py): patent pages, inventor and assignee pages, patent sections on
company, nonprofit, university and person pages, and patent numbers, assignees and inventors in site search.

Links to other records carry EXACT or FUZZY and a confidence (ip_links, built by loader/patents.links); every
table row shows its source (USPTO bulk product ID and file date).
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db

router = APIRouter()
log = logging.getLogger("np.patents")
SOURCE = ("USPTO bulk data: PatentsView granted patents, disambiguated (PVGPATDIS) for patents, assignees, "
          "inventors, places and CPC categories; the USPTO Patent Assignment Dataset (ECORSEXC) for assignments and "
          "security interests. Patents filed in the last 20 years. No claims or full text.")
TYPE_LABEL = {1: "Unassigned", 2: "US company or organization", 3: "Foreign company or organization",
              4: "US individual", 5: "Foreign individual", 6: "US federal government", 7: "Foreign government",
              8: "US county government", 9: "US state government"}
CONVEY_LABEL = {"assignment": "Assignment", "employer": "Assignment from employee", "security": "Security interest",
                "release": "Release of security interest", "merger": "Merger", "namechg": "Name change",
                "license": "License", "govern": "Government interest", "correct": "Correction", "other": "Other"}
TARGET_LABEL = {"org": "Nonprofit", "college": "College or university", "formd": "Form D issuer",
                "biz": "State business registration", "sec": "SEC filer", "person": "Person",
                "adv": "Investment adviser (Form ADV)", "lda": "Federal lobbying client"}
SHOWN = 200


def _ready(conn, table: str = "pat_patents") -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (table,)).fetchone()["ok"]


def patent_number(v: str | None) -> str | None:
    from loader.patents import patent_number as pn
    return pn(v)


def google_url(patent_id: str, kind: str | None) -> str:
    return f"https://patents.google.com/patent/US{patent_id}{kind or ''}"


def uspto_pdf(patent_id: str) -> str:
    return f"https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{patent_id}"


def patent_center(application_id: str | None) -> str | None:
    d = re.sub(r"\D", "", application_id or "")
    return f"https://patentcenter.uspto.gov/applications/{d}" if len(d) == 8 else None


def type_label(t) -> str:
    try:
        t = int(t)
    except (TypeError, ValueError):
        return "Not reported"
    return TYPE_LABEL.get(t % 10, "Not reported") + (" (part interest)" if t >= 10 else "")


def convey_label(v: str | None) -> str:
    return CONVEY_LABEL.get(v or "", (v or "Not reported").capitalize())


def prov(product: str | None, date) -> str:
    return f"{product or 'USPTO'}, file of {date}" if date else (product or "USPTO")


def target_url(kind: str, key: str) -> str | None:
    return {"org": f"/org/{key}", "college": f"/institution/{key}", "person": f"/person/{key}",
            "sec": f"/corporate/company/{key}", "lda": f"/lobbying/client/{key}",
            "adv": f"https://adviserinfo.sec.gov/firm/summary/{key}"}.get(kind) or (
        "/business/" + key.replace(":", "/", 1) if kind == "biz" else None)


def link_rows(conn, src_kind: str, src_key: str) -> list[dict]:
    """Records elsewhere on the site linked to an assignee, inventor or trademark owner, with names and URLs."""
    out = []
    for l in conn.execute("SELECT * FROM ip_links WHERE src_kind = %s AND src_key = %s ORDER BY match, confidence",
                          (src_kind, src_key)).fetchall():
        name, url = l["target_key"], target_url(l["target_kind"], l["target_key"])
        k = l["target_kind"]
        if k == "org":
            r = conn.execute("SELECT name FROM organizations WHERE ein = %s", (l["target_key"],)).fetchone()
        elif k == "college":
            r = conn.execute("SELECT name FROM colleges WHERE unitid = %s::int", (l["target_key"],)).fetchone() \
                if l["target_key"].isdigit() else None
        elif k == "person":
            # The id compared as a number: id::text = ... can't use the key and scans every person (2.6 s, 2026-10-25).
            r = conn.execute("SELECT display_name AS name FROM person_clusters WHERE id = %s::bigint",
                             (l["target_key"],)).fetchone() if l["target_key"].isdigit() else None
        elif k == "formd":
            r = conn.execute("""SELECT issuer_name AS name, latest_accession FROM sec_formd_offerings WHERE cik = %s
                                ORDER BY latest_date DESC LIMIT 1""", (l["target_key"],)).fetchone()
            url = f"/corporate/form-d/{r['latest_accession']}" if r else None
        elif k == "biz":
            st, eid = l["target_key"].split(":", 1)
            r = conn.execute("SELECT name FROM biz_entities WHERE state = %s AND entity_id = %s", (st, eid)).fetchone()
        elif k == "sec":
            r = conn.execute("SELECT name FROM sec_fin_subs WHERE cik::text = %s ORDER BY filed DESC LIMIT 1",
                             (l["target_key"],)).fetchone()
        elif k == "adv":
            r = conn.execute("""SELECT coalesce(business_name, legal_name) AS name FROM adv_filings WHERE crd = %s
                                ORDER BY submitted DESC NULLS LAST LIMIT 1""", (l["target_key"],)).fetchone()
        elif k == "lda":
            r = conn.execute("""SELECT client_name AS name FROM lda_filings WHERE client_id = %s::int
                                ORDER BY dt_posted DESC NULLS LAST LIMIT 1""", (l["target_key"],)).fetchone() \
                if l["target_key"].isdigit() else None
        else:
            r = None
        out.append({**l, "label": TARGET_LABEL.get(k, k), "name": (r or {}).get("name") or name, "url": url})
    return out


# --- data for pages ----------------------------------------------------------------------------------------------

def patent(patent_id: str) -> dict | None:
    with db.conn() as conn:
        if not _ready(conn):
            return None
        p = conn.execute("SELECT * FROM pat_patents WHERE patent_id = %s", (patent_id,)).fetchone()
        if not p:
            return None
        assignees = conn.execute("""SELECT a.*, o.n_patents FROM pat_assignees a
                                    LEFT JOIN pat_assignee_orgs o USING (assignee_id)
                                    WHERE a.patent_id = %s ORDER BY a.seq""", (patent_id,)).fetchall()
        for a in assignees:
            a["links"] = link_rows(conn, "assignee", a["assignee_id"]) if a["assignee_id"] else []
        inventors = conn.execute("""SELECT i.*, ip.n_patents,
                                           (SELECT l.target_key FROM ip_links l WHERE l.src_kind = 'inventor'
                                            AND l.src_key = i.inventor_id LIMIT 1) AS person_id,
                                           (SELECT l.confidence FROM ip_links l WHERE l.src_kind = 'inventor'
                                            AND l.src_key = i.inventor_id LIMIT 1) AS person_conf
                                    FROM pat_inventors i LEFT JOIN pat_inventor_people ip USING (inventor_id)
                                    WHERE i.patent_id = %s ORDER BY i.seq""", (patent_id,)).fetchall()
        cpc = conn.execute("""SELECT c.*, t.title, t.class_title FROM pat_cpc c LEFT JOIN pat_cpc_titles t USING (subclass)
                              WHERE c.patent_id = %s ORDER BY c.seq NULLS LAST, c.subclass""", (patent_id,)).fetchall()
        history = assignments_for(conn, patent_id)
    return {"p": p, "assignees": assignees, "inventors": inventors, "cpc": cpc, "history": history}


def assignments_for(conn, patent_id: str) -> list[dict]:
    rows = conn.execute("""SELECT x.* FROM pat_assignment_docs d JOIN pat_assignments x USING (rf_id)
                           WHERE d.patent_id = %s ORDER BY x.record_date DESC NULLS LAST, x.rf_id DESC LIMIT 100""",
                        (patent_id,)).fetchall()
    if rows:
        parties = conn.execute("""SELECT * FROM pat_assignment_parties WHERE rf_id = ANY(%s) ORDER BY rf_id, role, seq""",
                               ([r["rf_id"] for r in rows],)).fetchall()
        for r in rows:
            r["assignors"] = [p for p in parties if p["rf_id"] == r["rf_id"] and p["role"] == "assignor"]
            r["assignees"] = [p for p in parties if p["rf_id"] == r["rf_id"] and p["role"] == "assignee"]
    return rows


def inventor(inventor_id: str) -> dict | None:
    with db.conn() as conn:
        if not _ready(conn, "pat_inventor_people"):
            return None
        i = conn.execute("SELECT * FROM pat_inventor_people WHERE inventor_id = %s", (inventor_id,)).fetchone()
        if not i:
            return None
        pats = conn.execute(f"""SELECT p.patent_id, p.title, p.granted, p.kind, p.src_product, p.src_date,
                                       (SELECT string_agg(a.name, '; ' ORDER BY a.seq) FROM pat_assignees a
                                        WHERE a.patent_id = p.patent_id) AS assignees
                                FROM pat_inventors x JOIN pat_patents p USING (patent_id)
                                WHERE x.inventor_id = %s ORDER BY p.granted DESC, p.patent_id DESC LIMIT {SHOWN}""",
                             (inventor_id,)).fetchall()
        links = link_rows(conn, "inventor", inventor_id)
    return {"i": i, "patents": pats, "links": links}


def assignee(assignee_id: str) -> dict | None:
    with db.conn() as conn:
        if not _ready(conn, "pat_assignee_orgs"):
            return None
        a = conn.execute("SELECT * FROM pat_assignee_orgs WHERE assignee_id = %s", (assignee_id,)).fetchone()
        if not a:
            return None
        pats = conn.execute(f"""SELECT p.patent_id, p.title, p.granted, p.kind, p.src_product, p.src_date
                                FROM pat_assignees x JOIN pat_patents p USING (patent_id)
                                WHERE x.assignee_id = %s ORDER BY p.granted DESC, p.patent_id DESC LIMIT {SHOWN}""",
                             (assignee_id,)).fetchall()
        security = conn.execute("""SELECT x.rf_id, x.record_date, x.convey_text, x.src_product, x.src_date,
                                          count(DISTINCT d.patent_id) AS patents,
                                          (SELECT string_agg(DISTINCT pp.name, '; ') FROM pat_assignment_parties pp
                                           WHERE pp.rf_id = x.rf_id AND pp.role = 'assignee') AS secured_party
                                   FROM pat_assignees a JOIN pat_assignment_docs d ON d.patent_id = a.patent_id
                                   JOIN pat_assignments x ON x.rf_id = d.rf_id AND x.is_security
                                   WHERE a.assignee_id = %s
                                   GROUP BY 1, 2, 3, 4, 5 ORDER BY x.record_date DESC NULLS LAST LIMIT 50""",
                                (assignee_id,)).fetchall()
        inventors = conn.execute("""SELECT ip.inventor_id, ip.name, count(*) AS n FROM pat_assignees a
                                    JOIN pat_inventors i USING (patent_id) JOIN pat_inventor_people ip USING (inventor_id)
                                    WHERE a.assignee_id = %s GROUP BY 1, 2 ORDER BY 3 DESC, 2 LIMIT 25""",
                                 (assignee_id,)).fetchall()
        links = link_rows(conn, "assignee", assignee_id)
    return {"a": a, "patents": pats, "security": security, "inventors": inventors, "links": links}


def for_record(kind: str, key: str | None) -> dict | None:
    """Patents of the assignees linked to a nonprofit (org), college, Form D issuer (formd), registry entity (biz,
    "STATE:ID") or SEC filer (sec), for that page's patent section."""
    if not key:
        return None
    try:
        with db.conn() as conn:
            if not _ready(conn, "ip_links"):
                return None
            conn.execute("SET LOCAL statement_timeout = '3s'")
            owners = conn.execute("""SELECT o.*, l.match, l.confidence, l.how FROM ip_links l
                                     JOIN pat_assignee_orgs o ON o.assignee_id = l.src_key
                                     WHERE l.src_kind = 'assignee' AND l.target_kind = %s AND l.target_key = %s
                                     ORDER BY o.n_patents DESC LIMIT 20""", (kind, str(key))).fetchall()
            if not owners:
                return None
            recent = conn.execute("""SELECT p.patent_id, p.title, p.granted, p.kind, p.src_product, p.src_date
                                     FROM pat_assignees a JOIN pat_patents p USING (patent_id)
                                     WHERE a.assignee_id = ANY(%s) ORDER BY p.granted DESC, p.patent_id DESC LIMIT 10""",
                                  ([o["assignee_id"] for o in owners],)).fetchall()
            return {"owners": owners, "recent": recent, "total": sum(o["n_patents"] or 0 for o in owners),
                    "security": sum(o["n_security"] or 0 for o in owners)}
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        log.exception("patents for %s %s", kind, key)
        return None


def for_person(cluster_id: int) -> list[dict]:
    try:
        with db.conn() as conn:
            if not _ready(conn, "ip_links"):
                return []
            conn.execute("SET LOCAL statement_timeout = '3s'")
            return conn.execute("""SELECT ip.*, l.match, l.confidence, l.how FROM ip_links l
                                   JOIN pat_inventor_people ip ON ip.inventor_id = l.src_key
                                   WHERE l.src_kind = 'inventor' AND l.target_kind = 'person' AND l.target_key = %s
                                   ORDER BY ip.n_patents DESC LIMIT 10""", (str(cluster_id),)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("patents for person %s", cluster_id)
        return []


def search(q: str) -> dict:
    """Site search: a patent number goes straight to its page (search() in app/main.py redirects); otherwise
    assignees by name (legal endings aside, exact then starting with) and inventors by full name."""
    out = {"patent": None, "assignees": [], "inventors": []}
    q = (q or "").strip()
    if len(q) < 3:
        return out
    try:
        with db.conn() as conn:
            if not _ready(conn, "pat_assignee_orgs"):
                return out
            conn.execute("SET LOCAL statement_timeout = '3s'")
            pn = patent_number(q) if re.search(r"\d{5}", q) else None
            if pn:
                out["patent"] = conn.execute("SELECT patent_id, title, granted FROM pat_patents WHERE patent_id = %s",
                                             (pn,)).fetchone()
                return out
            from app.names import normalize_name
            from loader.recalls import core
            c = core(q)
            if len(c) >= 3:
                out["assignees"] = conn.execute("""SELECT * FROM pat_assignee_orgs WHERE name_core = %s
                                                   ORDER BY n_patents DESC LIMIT 5""", (c,)).fetchall() or \
                    conn.execute("""SELECT * FROM pat_assignee_orgs WHERE name_core LIKE %s
                                    ORDER BY n_patents DESC LIMIT 5""", (c + " %",)).fetchall()
            nn = normalize_name(q)
            if nn and " " in nn:
                out["inventors"] = conn.execute("""SELECT * FROM pat_inventor_people WHERE name_norm = %s
                                                   ORDER BY n_patents DESC LIMIT 10""", (nn,)).fetchall()
    except Exception:  # noqa: BLE001 - an extra; never fail a search
        log.exception("patent search %s", q)
    return out


# --- pages -------------------------------------------------------------------------------------------------------

def _render(request, template, **ctx):
    from app.main import render
    return render(request, template, **ctx)


@router.get("/patent/{number}", response_class=HTMLResponse)
def patent_page(request: Request, number: str):
    pid = patent_number(number)
    if not pid:
        raise HTTPException(404)
    if pid != number:
        return RedirectResponse(f"/patent/{pid}", status_code=301)
    data = patent(pid)
    if not data:
        raise HTTPException(404)
    return _render(request, "patent.html", **data)


@router.get("/inventor/{inventor_id}", response_class=HTMLResponse)
def inventor_page(request: Request, inventor_id: str):
    if len(inventor_id) > 64:
        raise HTTPException(404)
    data = inventor(inventor_id)
    if not data:
        raise HTTPException(404)
    return _render(request, "inventor.html", **data)


@router.get("/patents/assignee/{assignee_id}", response_class=HTMLResponse)
def assignee_page(request: Request, assignee_id: str):
    if len(assignee_id) > 64:
        raise HTTPException(404)
    data = assignee(assignee_id)
    if not data:
        raise HTTPException(404)
    return _render(request, "patent_assignee.html", **data)
