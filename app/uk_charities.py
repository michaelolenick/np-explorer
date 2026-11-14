"""UK charities (loader/uk_charities.py): the Charity Commission for England and Wales register. /uk (index, search), one page per
charity (/uk/charity/<number>), one page per trustee (/uk/trustee/<id>), the UK to US matches (loader/uk_xref.py) and the "Also in the
UK" block on US organization pages. Shown unless UK_CHARITIES_PUBLIC=0; the pages answer 404 while the tables are missing.

Source and licence: Charity Commission for England and Wales, register of charities data extract, under the Open Government
Licence v3.0. The attribution below goes on every page that shows the data and on /data#uk-charities.
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
PUBLIC = os.environ.get("UK_CHARITIES_PUBLIC", "1") == "1"
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Source: Charity Commission for England and Wales.")
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
REGISTER_URL = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/{}"
DOWNLOAD_URL = "https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download"
SOURCE = ("Charity Commission for England and Wales, register of charities: the daily data extract of registered, removed and "
          "linked charities in England and Wales (Scotland and Northern Ireland keep their own registers, not loaded here). "
          + ATTRIBUTION)
SCOPE_NOTE = ("The register has no pay for individuals: it records, per charity, the income and spending reported to the Commission, "
              "the number of staff paid over £60,000 (in bands) and whether trustees were paid.")
LIMIT = 100
_NUM = re.compile(r"^\d{1,8}$")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, ukc=sys.modules[__name__], **ctx)


def gbp(v) -> str:
    """£12,345 (the register reports pounds)."""
    if v is None or v == "":
        return "Not reported"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    return ("-" if n < 0 else "") + "£" + format(abs(round(n)), ",")


def short_gbp(v) -> str:
    if v is None or v == "":
        return "Not reported"
    n = float(v)
    a = abs(n)
    for div, suffix in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if a >= div:
            return ("-" if n < 0 else "") + "£" + f"{a / div:.1f}".rstrip("0").rstrip(".") + suffix
    return gbp(n)


_SMALL = {"of", "and", "the", "for", "in", "on", "at", "to", "a", "an", "by", "with", "de", "la"}
_KEEP = {"UK", "USA", "NHS", "BBC", "CIC", "CIO", "UCL", "UCLH", "RSPCA", "RSPB", "NSPCC", "YMCA", "YWCA", "PTA", "SOS", "HIV", "AIDS", "II", "III", "IV"}


def title_case(s: str | None) -> str:
    """Names are upper case on the register: Title Case for display (acronyms in _KEEP stay upper; mixed-case names are left alone)."""
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


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('uk.charity_main') AS t").fetchone()["t"] is not None


def _matches_ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('uk.us_match') AS t").fetchone()["t"] is not None


def ready() -> bool:
    if not PUBLIC:
        return False
    try:
        with db.conn() as conn:
            return _ok(conn)
    except Exception:  # noqa: BLE001
        return False


def web_url(w: str | None) -> str | None:
    w = (w or "").strip()
    if not w or "." not in w or " " in w:
        return None
    return w if re.match(r"^https?://", w, re.I) else "http://" + w


def overview() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        totals = conn.execute("""
            SELECT count(*) AS total, count(*) FILTER (WHERE status = 'Registered') AS registered,
                   count(*) FILTER (WHERE status = 'Removed') AS removed,
                   sum(income) FILTER (WHERE status = 'Registered') AS income,
                   (SELECT count(*) FROM uk.trustee WHERE kind = 'P') AS trustees,
                   (SELECT count(DISTINCT trustee_id) FROM uk.trustee WHERE kind = 'P') AS trustee_people,
                   (SELECT count(*) FROM uk.return_history) AS returns,
                   (SELECT loaded FROM uk.meta WHERE key = 'summary') AS loaded,
                   (SELECT max(last_modified) FROM uk.meta WHERE key LIKE 'file:%%') AS extract
            FROM uk.charity_main""").fetchone()
        matches = None
        if _matches_ok(conn):
            matches = conn.execute("""SELECT count(DISTINCT uk_reg) FILTER (WHERE relation = 'same' AND confidence IN ('high', 'medium')) AS charities,
                                             count(*) FILTER (WHERE relation = 'same' AND confidence IN ('high', 'medium')) AS links,
                                             (SELECT count(DISTINCT uk_reg) FROM uk.us_grant) AS grant_charities,
                                             (SELECT count(*) FROM uk.person_match) AS people
                                      FROM uk.us_match""").fetchone()
        regions = conn.execute("""SELECT coalesce(region, 'No postcode') AS region, count(*) AS charities, sum(income) AS income
                                  FROM uk.charity_main WHERE status = 'Registered' GROUP BY 1 ORDER BY 3 DESC NULLS LAST""").fetchall()
        biggest = conn.execute("""SELECT reg_number, name, income, region FROM uk.charity_main WHERE status = 'Registered' AND income IS NOT NULL
                                  ORDER BY income DESC LIMIT 15""").fetchall()
        newest = conn.execute("""SELECT reg_number, name, registered, region, income FROM uk.charity_main WHERE status = 'Registered'
                                 AND registered IS NOT NULL ORDER BY registered DESC, reg_number DESC LIMIT 10""").fetchall()
        types = conn.execute("""SELECT coalesce(charity_type, 'Not stated') AS charity_type, count(*) AS n FROM uk.charity_main
                                WHERE status = 'Registered' GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    return {"totals": totals, "matches": matches, "regions": regions, "biggest": biggest, "newest": newest, "types": types}


def search(q: str, limit: int = 10, registered_only: bool = False, offset: int = 0, region: str | None = None) -> list[dict]:
    """Charities by name (any word order, previous and working names too) or by registered number."""
    q = (q or "").strip()
    if not PUBLIC or not q:
        return []
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            digits = re.sub(r"\D", "", q)
            extra, params = "", {"lim": limit, "off": offset}
            if registered_only:
                extra += " AND c.status = 'Registered'"
            if region:
                extra += " AND c.region = %(region)s"
                params["region"] = region
            if _NUM.match(q) and len(digits) >= 5:
                rows = conn.execute(f"""SELECT c.reg_number, c.name, c.status, c.income, c.region, c.charity_type, c.registered, c.removed,
                                               c.trustees, NULL::text AS other_name
                                        FROM uk.charity_main c WHERE c.reg_number = %(n)s {extra}""", {**params, "n": int(digits)}).fetchall()
                return [dict(r) for r in rows]
            words = [w for w in re.findall(r"[a-z0-9]+", q.lower().replace("'", "")) if len(w) >= 2][:6]
            if not words:
                return []
            cond = " AND ".join(f"(c.name_core LIKE %(w{i})s OR lower(c.name) LIKE %(w{i})s)" for i, _ in enumerate(words))
            for i, w in enumerate(words):
                params[f"w{i}"] = f"%{w}%"
            rows = conn.execute(f"""SELECT c.reg_number, c.name, c.status, c.income, c.region, c.charity_type, c.registered, c.removed,
                                           c.trustees, NULL::text AS other_name
                                    FROM uk.charity_main c WHERE {cond} {extra}
                                    ORDER BY (c.status = 'Registered') DESC, (c.name_core = %(exact)s) DESC, c.income DESC NULLS LAST, c.reg_number
                                    LIMIT %(lim)s OFFSET %(off)s""", {**params, "exact": " ".join(words)}).fetchall()
            out = [dict(r) for r in rows]
            if len(out) < limit and offset == 0:           # a previous or working name
                seen = {r["reg_number"] for r in out}
                cond2 = " AND ".join(f"o.name_core LIKE %(w{i})s" for i, _ in enumerate(words))
                more = conn.execute(f"""SELECT DISTINCT ON (c.reg_number) c.reg_number, c.name, c.status, c.income, c.region, c.charity_type,
                                               c.registered, c.removed, c.trustees, o.name AS other_name
                                        FROM uk.other_name o JOIN uk.charity_main c ON c.reg_number = o.reg_number
                                        WHERE {cond2} {extra} LIMIT %(lim)s""", params).fetchall()
                out += [dict(r) for r in more if r["reg_number"] not in seen][:limit - len(out)]
            return out
    except Exception:  # noqa: BLE001 - an extra group on the results page; never fail the search
        return []


def count_search(q: str) -> int:
    words = [w for w in re.findall(r"[a-z0-9]+", (q or "").lower().replace("'", "")) if len(w) >= 2][:6]
    if not PUBLIC or not words:
        return 0
    try:
        with db.conn() as conn:
            cond = " AND ".join(f"(c.name_core LIKE %s OR lower(c.name) LIKE %s)" for _ in words)
            params = [x for w in words for x in (f"%{w}%", f"%{w}%")]
            return conn.execute(f"SELECT count(*) AS n FROM uk.charity_main c WHERE {cond}", params).fetchone()["n"]
    except Exception:  # noqa: BLE001
        return 0


def charity(reg: int) -> dict | None:
    if not PUBLIC:
        return None
    with db.conn() as conn:
        if not _ok(conn):
            return None
        c = conn.execute("SELECT * FROM uk.charity_main WHERE reg_number = %s", (reg,)).fetchone()
        if not c:
            return None
        org = c["organisation_number"]
        full = conn.execute("SELECT * FROM uk.charity WHERE organisation_number = %s", (org,)).fetchone()
        linked = conn.execute("""SELECT organisation_number, linked_number, name, status, income FROM uk.charity
                                 WHERE reg_number = %s AND linked_number > 0 ORDER BY linked_number LIMIT 50""", (reg,)).fetchall()
        history = conn.execute("""SELECT fin_start, fin_end, income, expenditure, ar_received, accounts_received, qualified, suppressed
                                  FROM uk.return_history WHERE organisation_number = %s ORDER BY fin_end DESC""", (org,)).fetchall()
        parta = conn.execute("""SELECT * FROM uk.parta WHERE organisation_number = %s ORDER BY fin_end DESC""", (org,)).fetchall()
        partb = conn.execute("""SELECT * FROM uk.partb WHERE organisation_number = %s ORDER BY fin_end DESC""", (org,)).fetchall()
        trustees = conn.execute("""SELECT t.trustee_id, t.name, t.kind, t.is_chair, t.appointed,
                                          (SELECT count(DISTINCT t2.reg_number) FROM uk.trustee t2 WHERE t2.trustee_id = t.trustee_id) AS charities,
                                          (SELECT pm.cluster_id FROM uk.person_match pm WHERE pm.trustee_id = t.trustee_id LIMIT 1) AS us_person
                                   FROM uk.trustee t WHERE t.organisation_number = %s
                                   ORDER BY t.is_chair DESC NULLS LAST, t.appointed NULLS LAST, t.name""", (org,)).fetchall()
        classes = conn.execute("""SELECT kind, code, description FROM uk.classification WHERE organisation_number = %s
                                  ORDER BY kind, code""", (org,)).fetchall()
        areas = conn.execute("""SELECT area_type, area, parent_area FROM uk.area WHERE organisation_number = %s
                                ORDER BY area_type, area LIMIT 200""", (org,)).fetchall()
        names = conn.execute("""SELECT name_type, name FROM uk.other_name WHERE reg_number = %s AND linked_number = 0
                                ORDER BY name_type, name""", (reg,)).fetchall()
        gov = conn.execute("SELECT document, objects, area_of_benefit FROM uk.governing WHERE organisation_number = %s", (org,)).fetchone()
        policies = [r["policy"] for r in conn.execute("SELECT policy FROM uk.policy WHERE organisation_number = %s ORDER BY 1", (org,)).fetchall()]
        events = conn.execute("""SELECT event_order, event_type, event_date, reason, assoc_reg_number, assoc_name FROM uk.event
                                 WHERE organisation_number = %s ORDER BY event_order LIMIT 50""", (org,)).fetchall()
        regs = conn.execute("SELECT regulator, url FROM uk.regulator WHERE organisation_number = %s ORDER BY regulator_order", (org,)).fetchall()
        reports = conn.execute("SELECT report, location, published FROM uk.report WHERE organisation_number = %s ORDER BY published DESC", (org,)).fetchall()
        us = us_matches(conn, reg)
        grants = conn.execute("""SELECT g.grantor_ein, o.name, o.state, g.grants, g.total, g.first_year, g.last_year
                                 FROM uk.us_grant g JOIN organizations o ON o.ein = g.grantor_ein WHERE g.uk_reg = %s
                                 ORDER BY g.total DESC LIMIT 25""", (reg,)).fetchall() if _matches_ok(conn) else []
        peer = conn.execute("""SELECT reg_number, name, income FROM uk.charity_main WHERE postcode_area = %s AND status = 'Registered'
                               AND reg_number <> %s AND income IS NOT NULL ORDER BY income DESC LIMIT 5""", (c["postcode_area"], reg)).fetchall() \
            if c["postcode_area"] else []
    chart = [h for h in history if h["income"] is not None or h["expenditure"] is not None]
    return {"c": c, "full": full, "linked": linked, "history": history, "chart": list(reversed(chart[:15])), "parta": parta[0] if parta else None,
            "partb": partb, "trustees": trustees, "classes": classes, "areas": areas, "names": names, "gov": gov,
            "policies": policies, "events": events, "regs": regs, "reports": reports, "us": us["same"], "us_possible": us["possible"],
            "us_grants": grants, "peer": peer}


def us_matches(conn, reg: int) -> dict:
    """The charity's US counterparts: high and medium confidence matches first, then same-name-only ones as "possible"."""
    if not _matches_ok(conn):
        return {"same": [], "possible": []}
    rows = conn.execute("""SELECT m.us_kind, m.us_key, m.us_name, m.us_state, m.method, m.confidence, m.evidence,
                                  o.latest_total_revenue AS revenue, o.latest_filing_year AS year
                           FROM uk.us_match m LEFT JOIN organizations o ON m.us_kind = 'org' AND o.ein = m.us_key
                           WHERE m.uk_reg = %s AND m.relation = 'same'
                           ORDER BY CASE m.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, o.latest_total_revenue DESC NULLS LAST
                           LIMIT 40""", (reg,)).fetchall()
    out = {"same": [], "possible": []}
    seen = set()
    for r in rows:
        k = (r["us_kind"], r["us_key"])
        if k in seen:
            continue
        seen.add(k)
        r = dict(r, url=us_url(r["us_kind"], r["us_key"]))
        out["same" if r["confidence"] in ("high", "medium") else "possible"].append(r)
    return out


def us_url(kind: str, key: str) -> str:
    from app import xlinks
    ent = xlinks.TARGETS.get(kind)
    return ent[1](key, None) if ent else "#"


METHOD_TEXT = {"domain": "the same website", "american_friends": "an “American Friends of” name", "name": "the same name",
               "affix": "the same name apart from a country word", "fara_principal": "a foreign principal under FARA",
               "shared_trustee": "trustees in common"}


def trustee(tid: int) -> dict | None:
    if not PUBLIC:
        return None
    with db.conn() as conn:
        if not _ok(conn):
            return None
        rows = conn.execute("""SELECT t.reg_number, t.linked_number, t.name, t.is_chair, t.appointed, t.kind, c.name AS charity, c.status,
                                      c.income, c.region
                               FROM uk.trustee t JOIN uk.charity_main c ON c.reg_number = t.reg_number
                               WHERE t.trustee_id = %s ORDER BY (c.status = 'Registered') DESC, c.income DESC NULLS LAST""", (tid,)).fetchall()
        if not rows:
            return None
        names = {}
        for r in rows:
            names[r["name"]] = names.get(r["name"], 0) + 1
        us_people = conn.execute("""SELECT pm.cluster_id, p.display_name, pm.ein, o.name AS org, pm.uk_reg, c.name AS uk_charity,
                                           array_to_string(p.states, ', ') AS states, p.latest_title
                                    FROM uk.person_match pm JOIN person_clusters p ON p.id = pm.cluster_id
                                    LEFT JOIN organizations o ON o.ein = pm.ein JOIN uk.charity_main c ON c.reg_number = pm.uk_reg
                                    WHERE pm.trustee_id = %s""", (tid,)).fetchall() if _matches_ok(conn) else []
    return {"id": tid, "tname": max(names, key=names.get), "variants": [n for n in names if n != max(names, key=names.get)],
            "rows": rows, "registered": sum(1 for r in rows if r["status"] == "Registered"), "us_people": us_people,
            "individual": (rows[0]["kind"] or "P") != "O"}


def org_uk(ein: str) -> dict | None:
    """For a US organization page: the UK charities matched to it ("Also in the UK") and the UK charities it has granted to."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            if not _ok(conn) or not _matches_ok(conn):
                return None
            same = conn.execute("""SELECT m.uk_reg, c.name, c.income, c.region, c.status, m.method, m.confidence, m.evidence
                                   FROM uk.us_match m JOIN uk.charity_main c ON c.reg_number = m.uk_reg
                                   WHERE m.us_kind = 'org' AND m.us_key = %s AND m.relation = 'same'
                                   ORDER BY CASE m.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, c.income DESC NULLS LAST
                                   LIMIT 10""", (ein,)).fetchall()
            grants = conn.execute("""SELECT g.uk_reg, c.name, c.region, g.grants, g.total, g.first_year, g.last_year FROM uk.us_grant g
                                     JOIN uk.charity_main c ON c.reg_number = g.uk_reg WHERE g.grantor_ein = %s ORDER BY g.total DESC LIMIT 15""",
                                  (ein,)).fetchall()
            n_grants = conn.execute("SELECT count(*) AS n, sum(total) AS total FROM uk.us_grant WHERE grantor_ein = %s", (ein,)).fetchone()
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        return None
    if not same and not grants:
        return None
    seen, rows = set(), []
    for r in same:
        if r["uk_reg"] not in seen:
            seen.add(r["uk_reg"])
            rows.append(r)
    return {"same": [r for r in rows if r["confidence"] in ("high", "medium")], "possible": [r for r in rows if r["confidence"] not in ("high", "medium")],
            "grants": grants, "n_grants": n_grants["n"], "grants_total": n_grants["total"]}


def person_uk(cluster_id: int) -> list[dict]:
    """For a US person page: UK trustee pages with the same name at a matched organization."""
    if not PUBLIC:
        return []
    try:
        with db.conn() as conn:
            if not _ok(conn) or not _matches_ok(conn):
                return []
            return conn.execute("""SELECT pm.trustee_id, pm.uk_name, pm.uk_reg, c.name AS charity, o.name AS org, pm.ein,
                                          (SELECT count(DISTINCT t.reg_number) FROM uk.trustee t WHERE t.trustee_id = pm.trustee_id) AS charities
                                   FROM uk.person_match pm JOIN uk.charity_main c ON c.reg_number = pm.uk_reg
                                   LEFT JOIN organizations o ON o.ein = pm.ein WHERE pm.cluster_id = %s LIMIT 10""", (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/uk", response_class=HTMLResponse)
def hub_page(request: Request):
    _gate()
    data = overview()
    if data is None:
        raise HTTPException(404)
    return _render(request, "uk.html", **data)


@router.get("/uk/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = Query("", max_length=120), page: int = Query(1, ge=1, le=500),
                region: str = Query("", max_length=40)):
    _gate()
    q = q.strip()
    rows = search(q, LIMIT, offset=(page - 1) * LIMIT, region=region or None) if q or region else []
    total = count_search(q) if q and not _NUM.match(q) else len(rows)
    if len(rows) == 1 and page == 1 and _NUM.match(q):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(f"/uk/charity/{rows[0]['reg_number']}", status_code=302)
    return _render(request, "uk_search.html", q=q, rows=rows, page=page, total=total, limit=LIMIT, region=region)


@router.get("/uk/charity/{number}", response_class=HTMLResponse)
def charity_page(request: Request, number: str):
    _gate()
    if not _NUM.match(number):
        raise HTTPException(404)
    data = charity(int(number))
    if not data:
        raise HTTPException(404)
    return _render(request, "uk_charity.html", **data)


@router.get("/uk/trustee/{tid}", response_class=HTMLResponse)
def trustee_page(request: Request, tid: str):
    _gate()
    if not _NUM.match(tid):
        raise HTTPException(404)
    data = trustee(int(tid))
    if not data:
        raise HTTPException(404)
    return _render(request, "uk_trustee.html", **data)


# --- natural-language shortcut (the plain-text box: "UK charities named Oxfam", "charity commission 202918") -------------

_UK_WORDS = re.compile(r"\b(?:(?:uk|u\.k\.|british|english|welsh|england|wales|england and wales|united kingdom)\s+(?:registered\s+)?charit(?:y|ies)"
                       r"|charity commission|registered charity(?: number| no\.?)?|uk 990s?|uk nonprofits?)\b", re.I)
_FILLER = re.compile(r"\b(?:named|called|about|like|search(?:ing)? for|find|show me|show|list|all|the|with|that|which|are|is|"
                     r"in the|please|who|what|where|trustees? of|number|no\.?)\b", re.I)


def nl_route(raw: str) -> str | None:
    """A question about UK charities goes to /uk/search (or /uk): the plain-text planner has no UK intent."""
    if not PUBLIC or not _UK_WORDS.search(raw or ""):
        return None
    rest = _FILLER.sub(" ", _UK_WORDS.sub(" ", raw))
    rest = re.sub(r"[^A-Za-z0-9&' -]", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip()
    return "/uk/search?q=" + quote(rest) if len(rest) >= 2 else "/uk"
