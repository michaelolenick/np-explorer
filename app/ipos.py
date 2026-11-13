"""IPO registrations (SEC Forms S-1 and F-1, loader/s1.py): the /ipos hub, the filings and companies lists (by
year, state, industry, name), one page per registrant with its FURP ties, the rows on other pages, and the search
and API lookups. Shown unless IPOS_PUBLIC=0 (the pages answer 404 while the tables are missing)."""

from __future__ import annotations

import os
import re
import sys

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db

router = APIRouter()
PUBLIC = os.environ.get("IPOS_PUBLIC", "1") == "1"
SOURCE = ("Data: SEC EDGAR. The quarterly full index (every S-1, S-1/A, F-1 and F-1/A since 1993, with the pricing "
          "prospectus, notice of effectiveness and withdrawal request of each registrant) and the company submissions "
          "data (SIC, state of incorporation, address, EIN, tickers, former names).")
LIMIT = 200
FORMS = {"S-1": "S-1 (registration)", "S-1/A": "S-1/A (amendment)", "F-1": "F-1 (foreign registration)",
         "F-1/A": "F-1/A (amendment)", "424B4": "424B4 (final prospectus)", "424B1": "424B1 (final prospectus)",
         "EFFECT": "EFFECT (declared effective)", "S-1MEF": "S-1MEF (added securities)", "F-1MEF": "F-1MEF (added securities)",
         "RW": "RW (withdrawal request)"}
BY = {"year": "By year", "state": "By state", "industry": "By industry", "incorporation": "By state of incorporation"}
_STATE = re.compile(r"^[A-Za-z]{2}$")


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, ipos=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('ipo_companies') AS t").fetchone()["t"] is not None


def _like(q: str) -> str:
    from loader.recalls import core
    return f"%{core(q)}%"


def cik_of(key: str) -> str | None:
    """The CIK in a page key: digits, or a name slug ending in -digits."""
    m = re.fullmatch(r"(?:[a-z0-9-]*-)?0*(\d{1,10})", key or "")
    return m.group(1) if m else None


def path(cik: str, name: str | None) -> str:
    from app import slugs
    s = slugs.slug(name) if name else ""
    return f"/ipos/{s}-{int(cik)}" if s else f"/ipos/{int(cik)}"


def overview() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        totals = conn.execute("""
            SELECT (SELECT count(*) FROM ipo_companies) AS companies,
                   (SELECT count(*) FROM ipo_companies WHERE kind LIKE '%%F-1%%') AS foreign_companies,
                   (SELECT count(*) FROM ipo_filings) AS filings,
                   (SELECT count(*) FROM ipo_filings WHERE form IN ('S-1', 'F-1')) AS registrations,
                   (SELECT count(*) FROM ipo_companies WHERE priced IS NOT NULL) AS priced,
                   (SELECT count(*) FROM ipo_companies WHERE withdrawn IS NOT NULL) AS withdrawn,
                   (SELECT count(*) FROM ipo_companies WHERE tickers IS NOT NULL) AS with_ticker,
                   (SELECT count(DISTINCT cik) FROM ipo_links) AS linked,
                   (SELECT count(*) FROM ipo_links) AS links,
                   (SELECT min(filed) FROM ipo_filings) AS first,
                   (SELECT max(filed) FROM ipo_filings) AS last,
                   (SELECT max(loaded) FROM ipo_companies) AS loaded""").fetchone()
        years = conn.execute("""SELECT year, count(*) FILTER (WHERE form = 'S-1') AS s1, count(*) FILTER (WHERE form = 'F-1') AS f1,
                                       count(*) FILTER (WHERE form IN ('S-1/A', 'F-1/A')) AS amendments,
                                       count(*) FILTER (WHERE form IN ('424B4', '424B1')) AS priced,
                                       count(*) FILTER (WHERE form = 'RW') AS withdrawn
                                FROM ipo_filings GROUP BY 1 ORDER BY 1 DESC""").fetchall()
        latest = conn.execute("""SELECT f.*, c.name AS company, c.state, c.sic_desc, c.tickers FROM ipo_filings f
                                 JOIN ipo_companies c USING (cik) WHERE f.form IN ('S-1', 'F-1')
                                 ORDER BY f.filed DESC, f.accession DESC LIMIT 25""").fetchall()
        link_counts = conn.execute("SELECT dst_kind, count(*) AS n, count(DISTINCT cik) AS companies FROM ipo_links GROUP BY 1 ORDER BY 2 DESC").fetchall()
    return {"totals": totals, "years": years, "latest": latest, "link_counts": link_counts}


def filings(q: str = "", year: int | None = None, form: str | None = None, state: str | None = None, limit: int = LIMIT) -> list[dict]:
    where, params = [], {"lim": limit}
    if q:
        where.append("(c.name_core LIKE %(q)s OR lower(f.company_name) LIKE %(q)s)")
        params["q"] = _like(q)
    if year:
        where.append("f.year = %(y)s")
        params["y"] = year
    if form:
        where.append("f.form = %(f)s")
        params["f"] = form
    if state:
        where.append("c.state = %(st)s")
        params["st"] = state
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT f.*, c.name AS company, c.state, c.sic_desc, c.tickers FROM ipo_filings f
                                JOIN ipo_companies c USING (cik) WHERE {" AND ".join(where) or "true"}
                                ORDER BY f.filed DESC, f.accession DESC LIMIT %(lim)s""", params).fetchall()


def companies(q: str = "", year: int | None = None, state: str | None = None, sic: str | None = None,
              state_inc: str | None = None, kind: str | None = None, limit: int = LIMIT) -> list[dict]:
    where, params = [], {"lim": limit}
    if q:
        where.append("(c.name_core LIKE %(q)s OR lower(c.index_name) LIKE %(q)s OR lower(c.tickers) LIKE %(q)s)")
        params["q"] = _like(q)
    if year:
        where.append("extract(year FROM c.first_filed) = %(y)s")
        params["y"] = year
    if state:
        where.append("c.state = %(st)s")
        params["st"] = state
    if state_inc:
        where.append("c.state_inc = %(si)s")
        params["si"] = state_inc
    if sic:
        where.append("c.sic = %(sic)s")
        params["sic"] = sic
    if kind:
        where.append("c.kind LIKE %(k)s")
        params["k"] = f"%{kind}%"
    with db.conn() as conn:
        if not _ok(conn):
            return []
        return conn.execute(f"""SELECT c.*, (SELECT count(*) FROM ipo_links l WHERE l.cik = c.cik) AS n_links
                                FROM ipo_companies c WHERE {" AND ".join(where) or "true"}
                                ORDER BY c.first_filed DESC, c.cik DESC LIMIT %(lim)s""", params).fetchall()


def groups(by: str) -> list[dict]:
    """Companies counted by year of first registration, business-address state, SIC industry or state of
    incorporation."""
    col = {"year": "extract(year FROM first_filed)::int", "state": "state", "industry": "sic", "incorporation": "state_inc"}[by]
    with db.conn() as conn:
        if not _ok(conn):
            return []
        if by == "industry":
            return conn.execute("""SELECT sic AS key, min(sic_desc) AS label, count(*) AS n,
                                          count(*) FILTER (WHERE priced IS NOT NULL) AS priced, max(first_filed) AS latest
                                   FROM ipo_companies WHERE sic IS NOT NULL GROUP BY 1 ORDER BY 3 DESC""").fetchall()
        return conn.execute(f"""SELECT {col} AS key, {col}::text AS label, count(*) AS n,
                                       count(*) FILTER (WHERE priced IS NOT NULL) AS priced, max(first_filed) AS latest
                                FROM ipo_companies WHERE {col} IS NOT NULL GROUP BY 1
                                ORDER BY {"1 DESC" if by == "year" else "3 DESC"}""").fetchall()


def company(cik: str) -> dict | None:
    with db.conn() as conn:
        if not _ok(conn):
            return None
        c = conn.execute("SELECT * FROM ipo_companies WHERE cik = %s", (str(int(cik)),)).fetchone()
        if not c:
            return None
        rows = conn.execute("SELECT * FROM ipo_filings WHERE cik = %s ORDER BY filed, accession", (c["cik"],)).fetchall()
        links = conn.execute("""SELECT dst_kind, dst_key, dst_name, how FROM ipo_links WHERE cik = %s
                                ORDER BY dst_kind = 'person', dst_kind, how NOT LIKE '%%EXACT%%', dst_name""",
                             (c["cik"],)).fetchall()
        has = lambda t: conn.execute("SELECT to_regclass(%s) AS t", (t,)).fetchone()["t"] is not None  # noqa: E731
        insiders = conn.execute("""
            SELECT o.owner_cik, min(o.owner_name) AS owner_name, string_agg(DISTINCT nullif(o.relationship, ''), '; ') AS roles,
                   string_agg(DISTINCT nullif(o.title, ''), '; ') AS titles, min(fi.filing_date) AS first, max(fi.filing_date) AS last,
                   count(*) AS n, min(l.cluster_id) AS cluster_id
            FROM sec_insider_filings fi JOIN sec_insider_owners o ON o.accession = fi.accession
            LEFT JOIN sec_person_links l ON l.source = 'insider' AND l.key = o.owner_cik
            WHERE fi.issuer_cik ~ '^\\d+$' AND fi.issuer_cik::bigint = %s GROUP BY 1 ORDER BY min(fi.filing_date), 2 LIMIT 100""",
            (int(c["cik"]),)).fetchall() if has("sec_insider_filings") and has("sec_person_links") else []
        formd = conn.execute("""SELECT * FROM sec_formd_offerings WHERE cik ~ '^\\d+$' AND cik::bigint = %s
                                ORDER BY first_date DESC LIMIT 20""", (int(c["cik"]),)).fetchall() if has("sec_formd_offerings") else []
    from app import xlinks
    out_links = []
    for l in links:
        label, url = xlinks.TARGETS.get(l["dst_kind"], (l["dst_kind"], lambda k, n: "#"))
        u = url(l["dst_key"], l["dst_name"])
        if l["dst_kind"] == "formd":        # the issuer's latest Form D (the page is per filing), as app/xlinks.for_source does
            o = next((d for d in formd if d["cik"] == l["dst_key"]), None)
            if not o:
                continue
            u = f"/corporate/form-d/{o['latest_accession']}"
        out_links.append({"label": label, "name": l["dst_name"] or l["dst_key"], "url": u, "how": l["how"],
                          "exact": "EXACT" in l["how"], "external": u.startswith("http"), "kind": l["dst_kind"]})
    return {"c": c, "rows": rows, "links": out_links, "insiders": insiders, "formd": formd,
            "sec_company": any(l["dst_kind"] == "sec" for l in links)}


def search(q: str, limit: int = 10) -> list[dict]:
    """Registrants whose name (as EDGAR has it, as filed, or a former name) contains the words; the API and the
    site search."""
    if not PUBLIC:
        return []
    words = [w for w in re.findall(r"[a-z0-9]+", (q or "").lower()) if len(w) >= 2][:6]
    if not words:
        return []
    conds = ["(c.name_core LIKE %s OR lower(c.index_name) LIKE %s OR lower(c.former_names::text) LIKE %s)"] * len(words)
    params: list = []
    for w in words:
        params += [f"%{w}%"] * 3
    try:
        with db.conn() as conn:
            if not _ok(conn):
                return []
            rows = conn.execute(f"""SELECT c.cik, c.name, c.kind, c.city, c.state, c.sic_desc, c.tickers, c.first_filed, c.last_filed,
                                           c.n_reg, c.n_amend, c.priced, c.effect, c.withdrawn
                                    FROM ipo_companies c WHERE {" AND ".join(conds)}
                                    ORDER BY c.first_filed DESC LIMIT %s""", params + [limit]).fetchall()
    except Exception:  # noqa: BLE001 - an extra group on the results page; never fail the search
        return []
    return [{**r, "path": path(r["cik"], r["name"])} for r in rows]


def ciks_with_s1(ciks: list) -> set[str]:
    """Which of these issuer CIKs filed an S-1 or F-1 (the IPO marker on person pages' insider tables)."""
    if not PUBLIC or not ciks:
        return set()
    try:
        keys = sorted({str(int(c)) for c in ciks if c is not None and str(c).strip().isdigit()})
        with db.conn() as conn:
            if not _ok(conn) or not keys:
                return set()
            return {r["cik"] for r in conn.execute("SELECT cik FROM ipo_companies WHERE cik = ANY(%s)", (keys,)).fetchall()}
    except Exception:  # noqa: BLE001
        return set()


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


@router.get("/ipos", response_class=HTMLResponse)
def hub_page(request: Request):
    _gate()
    data = overview()
    if data is None:
        raise HTTPException(404)
    return _render(request, "ipos.html", **data)


@router.get("/ipos/filings", response_class=HTMLResponse)
def filings_page(request: Request, q: str = Query("", max_length=100), year: int = Query(0, ge=0, le=2100),
                 form: str = Query("", max_length=10), state: str = Query("", max_length=2)):
    _gate()
    st = state.upper() if _STATE.match(state) else None
    f = form.upper() if form.upper() in FORMS else None
    rows = filings(q.strip(), year or None, f, st)
    return _render(request, "ipos_filings.html", q=q.strip(), year=year or None, form=f or "", state=st or "", rows=rows)


@router.get("/ipos/companies", response_class=HTMLResponse)
def companies_page(request: Request, q: str = Query("", max_length=100), year: int = Query(0, ge=0, le=2100),
                   state: str = Query("", max_length=2), sic: str = Query("", max_length=10), inc: str = Query("", max_length=2),
                   kind: str = Query("", max_length=3)):
    _gate()
    st = state.upper() if _STATE.match(state) else None
    si = inc.upper() if _STATE.match(inc) else None
    s = sic if re.fullmatch(r"\d{1,4}", sic) else None
    k = kind.upper() if kind.upper() in ("S-1", "F-1") else None
    rows = companies(q.strip(), year or None, st, s, si, k)
    label = ""
    if s and rows:
        label = rows[0]["sic_desc"] or ""
    return _render(request, "ipos_companies.html", q=q.strip(), year=year or None, state=st or "", sic=s or "", inc=si or "",
                   kind=k or "", rows=rows, sic_label=label)


@router.get("/ipos/by/{by}", response_class=HTMLResponse)
def by_page(request: Request, by: str):
    _gate()
    if by not in BY:
        raise HTTPException(404)
    return _render(request, "ipos_by.html", by=by, rows=groups(by))


@router.get("/ipos/{key}", response_class=HTMLResponse)
def company_page(request: Request, key: str):
    _gate()
    cik = cik_of(key)
    if not cik:
        raise HTTPException(404)
    data = company(cik)
    if not data:
        raise HTTPException(404)
    return _render(request, "ipos_company.html", **data)
