"""UK companies (loader/uk_companies.py): Companies House's free company data product and PSC snapshot. /uk/companies (index, search),
/uk/company/<number> (profile, previous names, SIC codes, officers, people with significant control, linked UK charity, linked US entities),
/uk/officer/<id> (one officer's appointments in the companies fetched so far), and the "UK company" rows xlinks gives the US pages.
Shown unless UK_COMPANIES_PUBLIC=0; pages answer 404 while the tables are missing.

Source and licence: Companies House, Open Government Licence v3.0. The attribution below goes on every page that shows the data and on
/data#uk-companies. Officers and the extra profile fields come from the Companies House REST API (loader/uk_officers.py, a free key kept in
.env), fetched continuously in priority order, so a company shows officers only once it has been fetched. Officers' names, roles, dates,
nationality, country of residence, occupation and birth month and year are shown; day of birth and home addresses are never kept.
"""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("UK_COMPANIES_PUBLIC", "1") == "1"
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Source: Companies House.")
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
CH_URL = "https://find-and-update.company-information.service.gov.uk/company/{}"
CH_OFFICER_URL = "https://find-and-update.company-information.service.gov.uk/officers/{}/appointments"
DOWNLOAD_URL = "https://download.companieshouse.gov.uk/en_output.html"
SOURCE = ("Companies House, Free Company Data Product (every live company on the UK register, a monthly snapshot) and the People with "
          "Significant Control snapshot. Dissolved companies are not in the free product. " + ATTRIBUTION)
LIMIT = 100
_NUM = re.compile(r"^[A-Za-z]{0,2}\d{1,8}$")

NATURES = {
    "ownership-of-shares-25-to-50-percent": "owns 25 to 50% of the shares",
    "ownership-of-shares-50-to-75-percent": "owns 50 to 75% of the shares",
    "ownership-of-shares-75-to-100-percent": "owns 75 to 100% of the shares",
    "voting-rights-25-to-50-percent": "holds 25 to 50% of the voting rights",
    "voting-rights-50-to-75-percent": "holds 50 to 75% of the voting rights",
    "voting-rights-75-to-100-percent": "holds 75 to 100% of the voting rights",
    "right-to-appoint-and-remove-directors": "can appoint and remove directors",
    "significant-influence-or-control": "has significant influence or control",
}


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render
    return render(request, template, ukco=sys.modules[__name__], **ctx)


_SMALL = {"of", "and", "the", "for", "in", "on", "at", "to", "a", "an", "by", "with"}
_KEEP = {"UK", "USA", "LTD", "PLC", "LLP", "LP", "CIC", "CIO", "II", "III", "IV", "NHS", "BBC", "IT", "HR", "SW", "NE", "NW", "SE"}


def title_case(s: str | None) -> str:
    """Names are mostly upper case on the register: Title Case for display (mixed-case names are left alone)."""
    if not s or not s.isupper():
        return s or ""
    out = []
    for i, w in enumerate(s.split(" ")):
        core_w = w.strip("().,&")
        if i and w.lower() in _SMALL:
            out.append(w.lower())
        elif core_w in _KEEP:
            out.append(w)
        else:
            out.append(re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), w.lower()))
    return " ".join(out)


def nature(n: str) -> str:
    return NATURES.get(n, n.replace("-", " "))


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('uk_companies.company') AS t").fetchone()["t"] is not None


def ready() -> bool:
    if not PUBLIC:
        return False
    try:
        with db.conn() as conn:
            return _ok(conn)
    except Exception:  # noqa: BLE001
        return False


def _core(q: str) -> str:
    from loader.recalls import core
    words = core(q).split()
    while words and words[-1] in ("plc", "llp", "lp", "cic", "cio", "ltd", "limited", "unlimited", "partnership"):
        words.pop()
    return " ".join(words)


def norm_number(q: str) -> str | None:
    q = (q or "").strip().upper().replace(" ", "")
    if not _NUM.match(q):
        return None
    m = re.match(r"^([A-Z]{0,2})(\d+)$", q)
    return m.group(1) + m.group(2).zfill(8 - len(m.group(1)))


COLS = "company_number, name, status, category, incorporated, region, town, postcode"


def search(q: str, limit: int = 10, offset: int = 0, region: str | None = None, full: bool = False) -> list[dict]:
    """By company number, exact name, name prefix and previous name; with full=True also any name containing the text (trigram)."""
    q = (q or "").strip()
    if not q:
        return []
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            num = norm_number(q) if re.search(r"\d", q) and not re.search(r"[A-Za-z]{3}", q) else None
            if num:
                return conn.execute(f"SELECT {COLS} FROM uk_companies.company WHERE company_number = %s", (num,)).fetchall()
            c = _core(q)
            if len(c) < 3:
                return []
            reg = " AND region = %(reg)s" if region else ""
            p = {"c": c, "pre": c.replace("%", "").replace("_", "") + "%", "lim": limit, "off": offset, "reg": region, "like": "%" + q.replace("%", "") + "%"}
            rows = conn.execute(f"""
                (SELECT {COLS}, 0 AS rk, NULL::text AS other_name FROM uk_companies.company WHERE name_core = %(c)s{reg})
                UNION ALL
                (SELECT {COLS}, 1, NULL FROM uk_companies.company WHERE name_core LIKE %(pre)s AND name_core <> %(c)s{reg}
                 ORDER BY incorporated DESC NULLS LAST LIMIT %(lim)s + %(off)s)
                ORDER BY rk, incorporated DESC NULLS LAST LIMIT %(lim)s OFFSET %(off)s""", p).fetchall()
            if full and len(rows) < limit:
                seen = {r["company_number"] for r in rows}
                more = conn.execute(f"SELECT {COLS}, 2 AS rk, NULL::text AS other_name FROM uk_companies.company WHERE name ILIKE %(like)s{reg} "
                                    "ORDER BY incorporated DESC NULLS LAST LIMIT %(lim)s", p).fetchall()
                rows += [r for r in more if r["company_number"] not in seen][:limit - len(rows)]
            if len(rows) < limit and not region and not offset:
                seen = {r["company_number"] for r in rows}
                prev = conn.execute(f"""SELECT c.company_number, c.name, c.status, c.category, c.incorporated, c.region, c.town, c.postcode, 3 AS rk,
                                               p.name AS other_name
                                        FROM uk_companies.previous_name p JOIN uk_companies.company c USING (company_number)
                                        WHERE p.name_core = %(c)s LIMIT %(lim)s""", p).fetchall()
                rows += [r for r in prev if r["company_number"] not in seen][:limit - len(rows)]
            return rows
    except Exception:  # noqa: BLE001
        return []


def overview() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        t = conn.execute("""SELECT (SELECT rows FROM uk_companies.meta WHERE key = 'table:company') AS companies,
                                   (SELECT rows FROM uk_companies.meta WHERE key = 'table:psc') AS psc,
                                   (SELECT rows FROM uk_companies.meta WHERE key = 'table:previous_name') AS previous,
                                   (SELECT name FROM uk_companies.meta WHERE key = 'file:basic') AS basic_file,
                                   (SELECT name FROM uk_companies.meta WHERE key = 'file:psc') AS psc_file""").fetchone()
        have = conn.execute("SELECT to_regclass('uk_companies.stats') IS NOT NULL AS t").fetchone()["t"]
        status = conn.execute("SELECT k AS status, n FROM uk_companies.stats WHERE kind = 'status' ORDER BY n DESC").fetchall() if have else []
        regions = conn.execute("SELECT k AS region, n, active, other FROM uk_companies.stats WHERE kind = 'region' ORDER BY n DESC").fetchall() if have else []
        cats = conn.execute("SELECT k AS category, n FROM uk_companies.stats WHERE kind = 'category' ORDER BY n DESC LIMIT 12").fetchall() if have else []
        sics = conn.execute("""SELECT s.code, s.descr, s.companies, coalesce(t.n, 0) AS new_year
                               FROM (SELECT * FROM uk_companies.sic ORDER BY companies DESC LIMIT 12) s
                               LEFT JOIN uk_companies.stats t ON t.kind = 'sic_new' AND t.k = s.code""").fetchall() \
            if have and conn.execute("SELECT to_regclass('uk_companies.sic') IS NOT NULL AS t").fetchone()["t"] else []
        newest = conn.execute("""SELECT company_number, name, incorporated, region, category FROM uk_companies.company
                                 WHERE incorporated IS NOT NULL ORDER BY incorporated DESC, company_number DESC LIMIT 10""").fetchall()
        links = None
        try:
            links = conn.execute("""SELECT count(DISTINCT src_key) FILTER (WHERE dst_kind = 'biz') AS biz,
                                           count(DISTINCT src_key) FILTER (WHERE dst_kind = 'sec') AS sec,
                                           count(DISTINCT src_key) FILTER (WHERE dst_kind = 'uk_charity') AS charity,
                                           count(DISTINCT src_key) FILTER (WHERE dst_kind = 'person') AS persons
                                    FROM xlinks WHERE src_kind IN ('uk_company', 'uk_psc') AND linker LIKE 'ukco:%%'""").fetchone()
        except Exception:  # noqa: BLE001
            conn.rollback()
    return {"totals": t, "status": status, "regions": regions, "cats": cats, "sics": sics, "newest": newest, "links": links}


def company(number: str) -> dict | None:
    num = norm_number(number)
    if not num:
        return None
    with db.conn() as conn:
        if not _ok(conn):
            return None
        c = conn.execute("SELECT * FROM uk_companies.company WHERE company_number = %s", (num,)).fetchone()
        if not c:
            return None
        prev = conn.execute("SELECT name, ceased FROM uk_companies.previous_name WHERE company_number = %s ORDER BY seq", (num,)).fetchall()
        psc, psc_n = [], None
        if conn.execute("SELECT to_regclass('uk_companies.psc') IS NOT NULL AS t").fetchone()["t"]:
            psc = conn.execute("""SELECT p.psc_id, p.kind, p.name, p.nationality, p.country_of_residence, p.birth_year, p.natures, p.notified_on, p.ceased_on,
                                         p.reg_number, p.reg_country, p.legal_form, p.addr_country, p.statement,
                                         (SELECT cc.company_number FROM uk_companies.company cc WHERE p.kind LIKE 'corporate%%' AND cc.company_number = p.reg_number) AS corp_company
                                  FROM uk_companies.psc p WHERE p.company_number = %s
                                  ORDER BY (p.ceased_on IS NOT NULL), p.notified_on DESC NULLS LAST, p.name LIMIT 200""", (num,)).fetchall()
            psc_n = conn.execute("SELECT count(*) AS n FROM uk_companies.psc WHERE company_number = %s", (num,)).fetchone()["n"]
        officers, officer_n, prof = [], None, None
        try:
            if conn.execute("SELECT to_regclass('uk_companies.officer') IS NOT NULL AS t").fetchone()["t"]:
                prof = conn.execute("SELECT * FROM uk_companies.profile WHERE company_number = %s", (num,)).fetchone()
                officers = conn.execute("""SELECT officer_id, name, role, corporate, appointed_on, resigned_on, nationality, residence, occupation,
                                            birth_year, birth_month FROM uk_companies.officer WHERE company_number = %s
                                     ORDER BY (resigned_on IS NOT NULL), corporate, appointed_on DESC NULLS LAST, name LIMIT 300""", (num,)).fetchall()
                officer_n = conn.execute("SELECT state FROM uk_companies.fetch_queue WHERE company_number = %s", (num,)).fetchone()
        except Exception:  # noqa: BLE001
            conn.rollback()
        charity = None
        try:
            charity = conn.execute("""SELECT reg_number, name, status, income FROM uk.charity_main
                                      WHERE company_number IS NOT NULL AND lpad(company_number, 8, '0') = %s ORDER BY (status = 'Registered') DESC LIMIT 3""", (num,)).fetchall()
        except Exception:  # noqa: BLE001
            conn.rollback()
        links, psc_links = [], {}
        try:
            from app import xlinks
            for r in conn.execute("""SELECT dst_kind, dst_key, dst_name, how FROM xlinks WHERE src_kind = 'uk_company' AND src_key = %s
                                     AND dst_kind <> 'uk_charity' ORDER BY dst_kind, dst_name LIMIT 60""", (num,)).fetchall():
                t = xlinks.TARGETS.get(r["dst_kind"])
                if t:
                    links.append({"label": t[0], "name": r["dst_name"] or r["dst_key"], "url": t[1](r["dst_key"], r["dst_name"]), "how": r["how"]})
            for r in conn.execute("""SELECT split_part(src_key, ':', 2) AS psc_id, dst_kind, dst_key, dst_name, how FROM xlinks
                                     WHERE src_kind = 'uk_psc' AND src_key LIKE %s LIMIT 100""", (num + ":%",)).fetchall():
                t = xlinks.TARGETS.get(r["dst_kind"])
                if t:
                    psc_links.setdefault(r["psc_id"], []).append({"label": t[0], "name": r["dst_name"] or r["dst_key"], "url": t[1](r["dst_key"], r["dst_name"]), "how": r["how"]})
        except Exception:  # noqa: BLE001
            conn.rollback()
    return {"c": c, "prev": prev, "psc": psc, "psc_n": psc_n, "charity": charity, "links": links, "psc_links": psc_links,
            "officers": officers, "officer_state": (officer_n or {}).get("state") if officer_n else None, "prof": prof,
            "sic": list(zip(c["sic"] or [], c["sic_text"] or []))}


_OID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def born(year, month) -> str:
    return (f"{_MONTHS[month]} {year}" if month and 1 <= month <= 12 else str(year)) if year else ""


def officer(oid: str) -> dict | None:
    """One officer (Companies House's own officer id): every appointment of that id in the companies fetched so far."""
    if not _OID.match(oid or ""):
        return None
    with db.conn() as conn:
        if not _ok(conn) or not conn.execute("SELECT to_regclass('uk_companies.officer') IS NOT NULL AS t").fetchone()["t"]:
            return None
        rows = conn.execute("""SELECT o.company_number, o.name, o.role, o.appointed_on, o.resigned_on, o.nationality, o.residence, o.occupation,
                                      o.birth_year, o.birth_month, o.addr_country, c.name AS company, c.status, c.incorporated
                               FROM uk_companies.officer o LEFT JOIN uk_companies.company c USING (company_number)
                               WHERE o.officer_id = %s ORDER BY (o.resigned_on IS NOT NULL), o.appointed_on DESC NULLS LAST, c.name LIMIT 500""", (oid,)).fetchall()
        if not rows:
            return None
        pending = conn.execute("SELECT count(*) AS n FROM uk_companies.fetch_queue WHERE state = 'pending'").fetchone()["n"]
    first = rows[0]
    return {"oid": oid, "rows": rows, "oname": first["name"], "current": sum(1 for r in rows if not r["resigned_on"]),
            "born": born(first["birth_year"], first["birth_month"]), "nationalities": sorted({r["nationality"] for r in rows if r["nationality"]}),
            "occupations": sorted({r["occupation"] for r in rows if r["occupation"]}), "pending": pending}


def search_officers(q: str, limit: int = 25) -> list[dict]:
    """Officers by name: 'forename surname' (as people write it) or 'surname, forename' prefix; one row per officer id."""
    from loader.uk_officers import person_name
    q = (q or "").strip()
    if len(q) < 4:
        return []
    _, norm = person_name(q, False)
    if len(norm) < 4:
        return []
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('uk_companies.officer') IS NOT NULL AS t").fetchone()["t"]:
                return []
            return conn.execute("""SELECT officer_id, max(name) AS name, count(*) AS appointments, count(*) FILTER (WHERE resigned_on IS NULL) AS current,
                                          max(birth_year) AS birth_year, min(company_number) AS example_company
                                   FROM (SELECT * FROM uk_companies.officer WHERE name_norm LIKE %(p)s AND officer_id IS NOT NULL AND NOT corporate LIMIT 400) x
                                   GROUP BY officer_id ORDER BY count(*) DESC, max(name) LIMIT %(lim)s""",
                                {"p": norm.replace("%", "").replace("_", "") + "%", "lim": limit}).fetchall()
    except Exception:  # noqa: BLE001
        return []


def org_uk(ein: str) -> list[dict]:
    return []


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/uk/companies", response_class=HTMLResponse)
def hub_page(request: Request):
    _gate()
    data = overview()
    if data is None:
        raise HTTPException(404)
    return _render(request, "uk_companies.html", **data)


@router.get("/uk/companies/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = Query("", max_length=120), page: int = Query(1, ge=1, le=100), region: str = Query("", max_length=40)):
    _gate()
    q = q.strip()
    rows = search(q, LIMIT, offset=(page - 1) * LIMIT, region=region or None, full=True) if q else []
    if len(rows) == 1 and page == 1 and norm_number(q) and re.search(r"\d", q) and not re.search(r"[A-Za-z]{3}", q):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"/uk/company/{rows[0]['company_number']}", status_code=302)
    people = search_officers(q) if q and page == 1 and not region and not norm_number(q) else []
    return _render(request, "uk_companies_search.html", q=q, rows=rows, page=page, limit=LIMIT, region=region, people=people)


@router.get("/uk/officer/{oid}", response_class=HTMLResponse)
def officer_page(request: Request, oid: str):
    _gate()
    data = officer(oid)
    if not data:
        raise HTTPException(404)
    return _render(request, "uk_officer.html", **data)


@router.get("/uk/company/{number}", response_class=HTMLResponse)
def company_page(request: Request, number: str):
    _gate()
    data = company(number)
    if not data:
        raise HTTPException(404)
    return _render(request, "uk_company.html", **data)


_WORDS = re.compile(r"\b(?:(?:uk|u\.k\.|british|english|england|wales|scottish|united kingdom)\s+(?:limited\s+)?compan(?:y|ies)|companies house"
                    r"|uk\s+ltd|uk\s+plc|uk\s+psc|persons? with significant control)\b", re.I)
_FILLER = re.compile(r"\b(?:named|called|about|like|search(?:ing)? for|find|show me|show|list|all|the|with|that|which|are|is|in the|please|who|what|where|number|no\.?)\b", re.I)


def nl_route(raw: str) -> str | None:
    """A question about UK companies goes to /uk/companies/search (or /uk/companies)."""
    if not PUBLIC or not _WORDS.search(raw or ""):
        return None
    rest = _FILLER.sub(" ", _WORDS.sub(" ", raw))
    rest = re.sub(r"[^A-Za-z0-9&' -]", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip()
    return "/uk/companies/search?q=" + quote(rest) if len(rest) >= 2 else "/uk/companies"
