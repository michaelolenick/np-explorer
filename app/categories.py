"""Nonprofit categories (loader/ntee.py): the /categories page (the NTEE tree or FURP's own topic index, a code or
name search, and a "describe it" lookup that asks a small model for the three likeliest codes), one org list per
category, the NTEE and FURP lines on organization pages, and the category filters in organization search."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app import db
from app.cache import ttl_lru

router = APIRouter()
PUBLIC = os.environ.get("CATEGORIES_PUBLIC", "1") == "1"
PER_PAGE = 100
MAX_PAGE = 50
INFER_PER_HOUR = int(os.environ.get("CATEGORIES_INFER_PER_HOUR", "300"))   # "describe it" model calls, site-wide
SOURCE = ("NTEE codes: the IRS Exempt Organizations Business Master File (published) and, for organizations the IRS "
          "lists without one, a code inferred by a small language model from the name and Form 990 text (inferred, "
          "with the model's confidence). Taxonomy: NCCS at the Urban Institute.")
# What the published codes are worth (owner, 2026-11-05): the IRS assigns an NTEE code when it rules on an application
# and rarely revisits it; the test in loader/ntee.py found them often plainly wrong. Shown on /categories and the lists.
CAVEAT_EXAMPLES = [("461660103", "Kingdom Gates Ministries", "D20", "Animal Protection and Welfare"),
                   ("473430279", "Joy of the Gospel Ministries", "K35", "Soup Kitchens"),
                   ("414406975", "Aspiring Hope Ministries", "F60", "Counseling, Support Groups")]
_CODE = re.compile(r"^[A-Za-z][0-9A-Za-z]{0,2}$")
_BROAD = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)$")      # NCCS broad categories are numbered I to X
_STATE = re.compile(r"^[A-Za-z]{2}$")
_FURP = re.compile(r"^[a-z_]{1,40}(:[a-z_]{1,40})?$")
_lock = threading.Lock()
_infer_calls: list[float] = []


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, cats=sys.modules[__name__], **ctx)


def _ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('ntee_counts') AS t").fetchone()["t"] is not None


@ttl_lru(ttl=3600)
def names() -> dict:
    """{(level, code): name} for every taxonomy node and FURP topic."""
    with db.conn() as conn:
        if not _ok(conn):
            return {}
        return {(r["level"], r["code"]): r["name"] for r in conn.execute("SELECT level, code, name FROM ntee_counts").fetchall()}


def code_name(code: str | None) -> str:
    """'Scholarships, Student Financial Aid Services, Awards' for B82; '' when unknown."""
    if not code:
        return ""
    n = names()
    return n.get(("code", code)) or n.get(("major", code[:1])) or ""


def major_name(code: str | None) -> str:
    return names().get(("major", (code or "")[:1].upper()), "") if code else ""


def furp_label(topic: str | None, sense: str | None = None) -> str:
    if not topic:
        return ""
    t = topic.replace("_", " ")
    return f"{t}: {sense.replace('_', ' ')}" if sense else t


@ttl_lru(ttl=600)
def tree(view: str) -> list[dict]:
    """The NTEE view: broad categories, each with its major groups, each with its codes. The FURP view: topics with
    their senses. Every node carries orgs, published and inferred counts."""
    with db.conn() as conn:
        if not _ok(conn):
            return []
        rows = conn.execute("SELECT level, code, parent, name, orgs, published, inferred FROM ntee_counts WHERE view = %s ORDER BY code", (view,)).fetchall()
    if view == "furp":
        topics = [dict(r, children=[]) for r in rows if r["level"] == "topic"]
        by = {t["code"]: t for t in topics}
        for r in rows:
            if r["level"] == "sense" and r["parent"] in by:
                by[r["parent"]]["children"].append(dict(r))
        for t in topics:
            t["children"].sort(key=lambda c: -c["orgs"])
        return sorted(topics, key=lambda t: -t["orgs"])
    broad = [dict(r, children=[]) for r in rows if r["level"] == "broad"]
    broad.sort(key=lambda b: _roman(b["code"]))
    majors = {r["code"]: dict(r, children=[]) for r in rows if r["level"] == "major"}
    for r in rows:
        if r["level"] == "code" and r["parent"] in majors:
            majors[r["parent"]]["children"].append(dict(r))
    bby = {b["code"]: b for b in broad}
    for m in majors.values():
        if m["parent"] in bby:
            bby[m["parent"]]["children"].append(m)
    return broad


def _roman(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10}
    total = 0
    for i, ch in enumerate(s):
        v = vals.get(ch, 0)
        total += -v if i + 1 < len(s) and vals.get(s[i + 1], 0) > v else v
    return total


def totals() -> dict | None:
    with db.conn() as conn:
        if not _ok(conn) or conn.execute("SELECT to_regclass('nonprofit_ntee') AS t").fetchone()["t"] is None:
            return None
        r = conn.execute("""SELECT count(*) AS orgs, count(*) FILTER (WHERE ntee_source = 'published') AS published,
                                   count(*) FILTER (WHERE ntee_source = 'inferred') AS inferred,
                                   count(furp_category) AS furp, max(inferred_at) AS inferred_at FROM nonprofit_ntee""").fetchone()
        r = dict(r)
        r["all_orgs"] = conn.execute("SELECT count(*) AS n FROM organizations").fetchone()["n"]
    return r


def search_nodes(q: str, view: str) -> dict:
    """Direct search, both ways at once: FURP categories (the topics and senses the 990 text index labeled) and the
    stated NTEE categories (published or inferred). A code (or its start) matches NTEE codes; words match names."""
    q = q.strip()
    out = {"furp": [], "ntee": [], "formd": []}
    if not q:
        return out
    with db.conn() as conn:
        if not _ok(conn):
            return out
        words = [w for w in re.split(r"[^A-Za-z0-9_]+", q) if w][:6]
        out["formd"] = formd_search_nodes(words)
        if _CODE.match(q):
            out["ntee"] = conn.execute("""SELECT level, code, parent, name, orgs, published, inferred FROM ntee_counts
                                          WHERE view = 'ntee' AND level IN ('major', 'code') AND code LIKE %s ORDER BY code LIMIT 60""",
                                       (q.upper() + "%",)).fetchall()
        if words:
            where = " AND ".join(f"(name ILIKE %(w{i})s OR code ILIKE %(w{i})s)" for i in range(len(words)))
            params = {f"w{i}": f"%{w}%" for i, w in enumerate(words)}
            for v in ("furp", "ntee"):
                if v == "ntee" and out["ntee"]:
                    continue
                out[v] = conn.execute(f"""SELECT level, code, parent, name, orgs, published, inferred FROM ntee_counts
                                          WHERE view = %(v)s AND {where} ORDER BY orgs DESC LIMIT 60""", {**params, "v": v}).fetchall()
    return out


def node_url(view: str, level: str, code: str, parent: str | None = None) -> str:
    if view == "furp":
        return f"/categories/furp/{code.replace(':', '/')}"
    return f"/categories/ntee/{code}" if level != "broad" else f"/categories/broad/{code}"


def broad_name(code: str | None) -> str:
    return names().get(("broad", (code or "").upper()), "") if code else ""


def broad_of(major: str | None) -> str:
    """The broad category (I to X) a major-group letter belongs to."""
    if not major:
        return ""
    with db.conn() as conn:
        if not _ok(conn):
            return ""
        r = conn.execute("SELECT parent FROM ntee_counts WHERE view = 'ntee' AND level = 'major' AND code = %s", (major[:1].upper(),)).fetchone()
    return (r and r["parent"]) or ""


# --- the "describe it" lookup ---------------------------------------------------------------------

INFER_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"],
                "properties": {"r": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["c", "p"],
                    "properties": {"c": {"type": "string"}, "p": {"type": "number"}}}}}}


def _norm_q(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())[:300]


def infer(q: str) -> dict:
    """{'codes': [{code, name, major, p}], 'how': 'cache' | 'model' | 'resting' | 'off' | 'failed'} for a description
    of what an organization does. The model sees the whole code list (loader.ntee.system_prompt) and answers with
    up to three codes; invalid ones are dropped. Answers are kept in ntee_infer_cache."""
    key = _norm_q(q)
    if len(key) < 3:
        return {"codes": [], "how": "off"}
    with db.conn() as conn:
        if not _ok(conn):
            return {"codes": [], "how": "off"}
        hit = conn.execute("SELECT result FROM ntee_infer_cache WHERE q = %s", (key,)).fetchone()
        if hit:
            return {"codes": hit["result"], "how": "cache"}
    if not os.environ.get("OPENROUTER_API_KEY"):
        return {"codes": [], "how": "off"}
    now = time.monotonic()
    with _lock:
        while _infer_calls and now - _infer_calls[0] > 3600:
            _infer_calls.pop(0)
        if len(_infer_calls) >= INFER_PER_HOUR:
            return {"codes": [], "how": "resting"}
        _infer_calls.append(now)
    from loader import ntee as lntee
    with db.conn() as conn:
        majors = dict(conn.execute("SELECT code, name FROM ntee_taxonomy WHERE level = 'major' ORDER BY code").fetchall())
        codes = dict(conn.execute("SELECT code, name FROM ntee_taxonomy WHERE level = 'code'").fetchall())
    system = lntee.system_prompt(majors, codes) + (
        "\n\nFor this request: the user describes what an organization does, in their own words. Answer with the three "
        "likeliest codes, best first: {\"r\":[{\"c\":\"<code>\",\"p\":<confidence 0 to 1>}, ...]}.")
    parsed, usage, err = _post_json(system, "Description: " + q.strip()[:600])
    if not parsed:
        return {"codes": [], "how": "failed"}
    out = []
    for item in (parsed.get("r") or [])[:5]:
        c = str((item or {}).get("c") or "").strip().upper()
        if c in codes and c not in {x["code"] for x in out}:
            out.append({"code": c, "name": codes[c], "major": majors.get(c[0], ""), "p": lntee._conf(item.get("p"))})
    out = out[:3]
    with db.conn() as conn:
        conn.execute("""INSERT INTO ntee_infer_cache (q, result, model, cost) VALUES (%s, %s::jsonb, %s, %s)
                        ON CONFLICT (q) DO UPDATE SET result = EXCLUDED.result, model = EXCLUDED.model, cost = EXCLUDED.cost, created = now()""",
                     (key, json.dumps(out), lntee.MODEL, float((usage or {}).get("cost") or 0.0)))
    return {"codes": out, "how": "model"}


def _post_json(system: str, user: str):
    """One model call through loader.ntee._post with the three-code schema (the key never leaves the server)."""
    from loader import ntee as lntee
    saved = lntee.SCHEMA
    try:
        lntee.SCHEMA = INFER_SCHEMA
        return lntee._post(system, user, 120)
    finally:
        lntee.SCHEMA = saved


# --- organizations in a category, and one organization's lines ----------------------------------

def _members(conn, view: str, key: str, level: str | None) -> tuple | None:
    """(node, member predicate, FROM clause, params) for one NTEE code, major group or broad category, or one FURP
    topic or topic:sense; None when the node does not exist."""
    params: dict = {}
    if view == "ntee" and level == "broad":     # broad codes (I, V, X) collide with major-group letters: own level
        node = conn.execute("SELECT * FROM ntee_counts WHERE view = 'ntee' AND code = %s AND level = 'broad'", (key,)).fetchone()
        if not node:
            return None
        params["majors"] = [r["code"] for r in conn.execute("SELECT code FROM ntee_counts WHERE view = 'ntee' AND level = 'major' AND parent = %s", (key,)).fetchall()]
        member = "left(n.ntee_code, 1) = ANY(%(majors)s)"    # an array, not a subquery: the planner then sees how common it is
        frm = "nonprofit_ntee n JOIN organizations o ON o.ein = n.ein"
    elif view == "ntee":
        node = conn.execute("SELECT * FROM ntee_counts WHERE view = 'ntee' AND code = %s AND level IN ('major', 'code') ORDER BY level LIMIT 1", (key,)).fetchone()
        if not node:
            return None
        params["code"] = key
        member = "left(n.ntee_code, 1) = %(code)s" if node["level"] == "major" else "n.ntee_code = %(code)s"
        frm = "nonprofit_ntee n JOIN organizations o ON o.ein = n.ein"
    else:
        topic, _, sense = key.partition(":")
        node = conn.execute("SELECT * FROM ntee_counts WHERE view = 'furp' AND code = %s", (key,)).fetchone()
        if not node:
            return None
        params["field"] = key if sense else topic + ":%"
        member = "EXISTS (SELECT 1 FROM research.org_fields f WHERE f.ein = o.ein AND f.field " + ("= %(field)s)" if sense else "LIKE %(field)s)")
        frm = "organizations o LEFT JOIN nonprofit_ntee n ON n.ein = o.ein"
    return node, member, frm, params


@ttl_lru(ttl=3600)
def state_counts(view: str, key: str, level: str | None = None) -> list:
    """Organizations per state in one node, cached: a broad category spans up to a million rows."""
    with db.conn(timeout="20s") as conn:
        if not _ok(conn):
            return []
        found = _members(conn, view, key, level)
        if not found:
            return []
        _, member, frm, params = found
        return conn.execute(f"""SELECT o.state, count(*) AS n FROM {frm} WHERE {member} AND o.state IS NOT NULL
                                GROUP BY 1 ORDER BY 2 DESC LIMIT 60""", params).fetchall()


@ttl_lru()
def orgs(view: str, key: str, state: str | None, page: int, source: str | None = None, level: str | None = None) -> dict | None:
    """Organizations in one NTEE code or major group (or, with level="broad", one of the ten broad categories), or one
    FURP topic or topic:sense; largest first."""
    page = max(1, min(page, MAX_PAGE))
    with db.conn(timeout="20s") as conn:        # a broad category or major group can hold a million organizations
        if not _ok(conn):
            return None
        found = _members(conn, view, key, level)
        if not found:
            return None
        node, member, frm, params = found
        params.update({"lim": PER_PAGE + 1, "off": (page - 1) * PER_PAGE, "st": state, "src": source})
        where = member + (" AND o.state = %(st)s" if state else "") + (" AND n.ntee_source = %(src)s" if source else "")
        rows = conn.execute(f"""SELECT o.ein, o.name, o.city, o.state, o.latest_filing_year, o.latest_total_revenue,
                                       n.ntee_code, n.ntee_source, n.confidence, n.furp_category, n.furp_subcategory
                                FROM {frm} WHERE {where}
                                ORDER BY o.latest_total_revenue DESC NULLS LAST, o.ein LIMIT %(lim)s OFFSET %(off)s""", params).fetchall()
    return {"node": node, "rows": rows[:PER_PAGE], "more": len(rows) > PER_PAGE, "page": page, "states": state_counts(view, key, level)}


def for_org(ein: str) -> dict | None:
    """The organization page's lines: code, name, major group, source, confidence, FURP topic and sense."""
    with db.conn() as conn:
        if conn.execute("SELECT to_regclass('nonprofit_ntee') AS t").fetchone()["t"] is None:
            return None
        r = conn.execute("SELECT * FROM nonprofit_ntee WHERE ein = %s", (ein,)).fetchone()
        if not r:
            return None
        r = dict(r)
        r["name"] = code_name(r["ntee_code"])
        r["major"] = major_name(r["ntee_code"])
        r["furp_fields"] = [x["field"] for x in conn.execute("SELECT field FROM research.org_fields WHERE ein = %s ORDER BY field", (ein,)).fetchall()] \
            if conn.execute("SELECT to_regclass('research.org_fields') AS t").fetchone()["t"] else []
    return r


def filter_sql(alias: str, ntee: str | None, furp: str | None, params: dict) -> str:
    """WHERE fragments for organization searches: an NTEE letter or code, a FURP topic or topic:sense."""
    out = ""
    if ntee and _CODE.match(ntee):
        params["f_ntee"] = ntee.upper() + ("%" if len(ntee) < 3 else "")
        out += f" AND EXISTS (SELECT 1 FROM nonprofit_ntee fn WHERE fn.ein = {alias}.ein AND fn.ntee_code LIKE %(f_ntee)s)"
    if furp and _FURP.match(furp):
        params["f_furp"] = furp if ":" in furp else furp + ":%"
        out += f" AND EXISTS (SELECT 1 FROM research.org_fields ff WHERE ff.ein = {alias}.ein AND ff.field LIKE %(f_furp)s)"
    return out


def clean_ntee(v: str | None) -> str | None:
    v = (v or "").strip()
    return v.upper() if _CODE.match(v) else None


def clean_furp(v: str | None) -> str | None:
    v = (v or "").strip().lower().replace(" ", "_")
    return v if _FURP.match(v) else None


# --- routes -------------------------------------------------------------------------------------

def _gate():
    if not PUBLIC:
        raise HTTPException(404)


VIEWS = ("ntee", "furp", "formd")
VIEW_COOKIE = "cat_view"        # the set the visitor chose last (owner, 2026-11-05: remember it for the visit)


@router.get("/categories", response_class=HTMLResponse)
def categories_page(request: Request, view: str = Query("", max_length=5), q: str = Query("", max_length=300),
                    mode: str = Query("search", max_length=8)):
    _gate()
    chosen = view if view in VIEWS else ""
    remembered = request.cookies.get(VIEW_COOKIE, "")
    view = chosen or (remembered if remembered in VIEWS else "ntee")
    mode = "infer" if mode == "infer" else "search"
    q = q.strip()
    found = inferred = None
    if q and mode == "search":
        found = search_nodes(q, view)
    elif q:
        inferred = infer(q)
    resp = _render(request, "categories.html", view=view, q=q, mode=mode, found=found, inferred=inferred,
                   tree=tree(view) if view != "formd" else [], fd=formd_tree() if view == "formd" else None, totals=totals(),
                   xds=cross_dataset_counts())
    if chosen and chosen != remembered:
        resp.set_cookie(VIEW_COOKIE, chosen, path="/categories", samesite="lax", httponly=True)    # session cookie: the visit
    return resp


@router.get("/categories/broad/{code}", response_class=HTMLResponse)
def broad_list(request: Request, code: str, state: str = Query("", max_length=2), page: int = Query(1, ge=1),
               source: str = Query("", max_length=9)):
    """Organizations in one of the ten NCCS broad categories (all of its major groups together)."""
    _gate()
    code = code.upper()
    if not _BROAD.match(code):
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    src = source if source in ("published", "inferred") else None
    data = orgs("ntee", code, st, page, src, level="broad")
    if not data:
        raise HTTPException(404)
    return _render(request, "categories_list.html", view="ntee", key=code, state=st or "", source=src or "",
                   list_path=f"/categories/broad/{code}", **data)


@router.get("/categories/ntee/{code}", response_class=HTMLResponse)
def ntee_list(request: Request, code: str, state: str = Query("", max_length=2), page: int = Query(1, ge=1),
              source: str = Query("", max_length=9)):
    _gate()
    if not _CODE.match(code):
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    src = source if source in ("published", "inferred") else None
    data = orgs("ntee", code.upper(), st, page, src)
    if not data:
        raise HTTPException(404)
    return _render(request, "categories_list.html", view="ntee", key=code.upper(), state=st or "", source=src or "", **data)


@router.get("/categories/furp/{topic}", response_class=HTMLResponse)
@router.get("/categories/furp/{topic}/{sense}", response_class=HTMLResponse)
def furp_list(request: Request, topic: str, sense: str = "", state: str = Query("", max_length=2), page: int = Query(1, ge=1),
              source: str = Query("", max_length=9)):
    _gate()
    key = clean_furp(topic + (":" + sense if sense else ""))
    if not key:
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    src = source if source in ("published", "inferred") else None
    data = orgs("furp", key, st, page, src)
    if not data:
        raise HTTPException(404)
    return _render(request, "categories_list.html", view="furp", key=key, state=st or "", source=src or "", **data)


# --- Form D categories (form_d_category, filled by loader/categorize.py; owner, 2026-11-05) --------------

FUND_LABELS = {"venture": "Venture capital fund", "private_equity": "Private equity fund", "hedge": "Hedge fund",
               "real_estate": "Real estate fund", "operating_company": "Operating company", "other": "Other pooled vehicle"}
_FD_GROUP = re.compile(r"^[A-Za-z &]{3,40}$")


def _fd_ok(conn) -> bool:
    return conn.execute("SELECT to_regclass('form_d_category') AS t").fetchone()["t"] is not None \
        and conn.execute("SELECT to_regclass('formd_taxonomy') AS t").fetchone()["t"] is not None


@ttl_lru(ttl=3600)
def formd_taxonomy() -> dict:
    """{group: [industries]} from formd_taxonomy, in the SEC's order."""
    with db.conn() as conn:
        if not _fd_ok(conn):
            return {}
        out: dict = {}
        for r in conn.execute("SELECT group_name, industry FROM formd_taxonomy ORDER BY group_name, industry").fetchall():
            out.setdefault(r["group_name"], []).append(r["industry"])
    return out


def fund_label(key: str | None) -> str:
    return FUND_LABELS.get(key or "", key or "")


def clean_fd(v: str | None) -> str | None:
    """A Form D category filter: 'Group' or 'Group/Industry', matched to the taxonomy ignoring case."""
    v = (v or "").strip()
    if not v or len(v) > 80:
        return None
    g, _, s = v.partition("/")
    tax = formd_taxonomy()
    gm = next((k for k in tax if k.lower() == g.strip().lower()), None)
    if not gm:
        return None
    if not s.strip():
        return gm
    sm = next((i for i in tax[gm] if i.lower() == s.strip().lower()), None)
    return f"{gm}/{sm}" if sm else None


def clean_fund(v: str | None) -> str | None:
    v = (v or "").strip().lower().replace(" ", "_")
    return v if v in FUND_LABELS else None


def formd_for_cik(cik: str | None) -> dict | None:
    """The inferred category line for a Form D issuer, or None."""
    if not cik:
        return None
    with db.conn() as conn:
        if not _fd_ok(conn):
            return None
        r = conn.execute("SELECT * FROM form_d_category WHERE cik = %s AND category IS NOT NULL", (cik.zfill(10),)).fetchone()
    if not r:
        return None
    r = dict(r)
    r["fund_label"] = fund_label(r["fund_type"])
    return r


@ttl_lru(ttl=600)
def formd_tree() -> dict:
    """The SEC industry groups with their industries, each with issuers as filed and issuers inferred, plus fund types."""
    tax = formd_taxonomy()
    if not tax:
        return {"groups": [], "funds": [], "filed_total": 0, "inferred_total": 0}
    with db.conn() as conn:
        filed = {r["industry"]: r["n"] for r in conn.execute("SELECT industry, count(DISTINCT cik) AS n FROM sec_formd_offerings WHERE industry IS NOT NULL GROUP BY 1").fetchall()}
        inferred = {(r["category"], r["subcategory"]): r["n"] for r in conn.execute("SELECT category, subcategory, count(*) AS n FROM form_d_category WHERE category IS NOT NULL GROUP BY 1, 2").fetchall()}
        ffiled = {r["fund_type"]: r["n"] for r in conn.execute("SELECT fund_type, count(DISTINCT cik) AS n FROM sec_formd_offerings WHERE fund_type IS NOT NULL GROUP BY 1").fetchall()}
        finf = {r["fund_type"]: r["n"] for r in conn.execute("SELECT fund_type, count(*) AS n FROM form_d_category WHERE fund_type IS NOT NULL GROUP BY 1").fetchall()}
        total_inf = conn.execute("SELECT count(*) AS n FROM form_d_category WHERE category IS NOT NULL").fetchone()["n"]
        total_filed = conn.execute("SELECT count(DISTINCT cik) AS n FROM sec_formd_offerings").fetchone()["n"]
    groups = []
    for g, inds in tax.items():
        children = [{"code": f"{g}/{i}", "name": i, "filed": filed.get(i, 0), "inferred": inferred.get((g, i), 0)} for i in inds]
        groups.append({"code": g, "name": g, "filed": sum(c["filed"] for c in children), "inferred": sum(c["inferred"] for c in children),
                       "children": children})
    filed_fund_names = {"Venture Capital Fund": "venture", "Private Equity Fund": "private_equity", "Hedge Fund": "hedge", "Other Investment Fund": "other"}
    funds = [{"code": k, "name": v, "filed": sum(n for fn, n in ffiled.items() if filed_fund_names.get(fn) == k), "inferred": finf.get(k, 0)}
             for k, v in FUND_LABELS.items()]
    return {"groups": groups, "funds": funds, "filed_total": total_filed, "inferred_total": total_inf}


def formd_search_nodes(words: list[str]) -> list[dict]:
    """Form D groups, industries and fund types whose names contain every word."""
    if not words:
        return []
    t = formd_tree()
    out = []
    for g in t["groups"]:
        for node in [g, *g["children"]]:
            if all(w.lower() in node["name"].lower() for w in words):
                out.append({"kind": "industry", **node})
    for f in t["funds"]:
        if all(w.lower() in f["name"].lower() for w in words):
            out.append({"kind": "fund", **f})
    return out[:60]


_FD_SIZE = "coalesce(nullif(o.latest_offering, 999999999999), 0) + coalesce(o.latest_sold, 0)"


@ttl_lru()
def formd_orgs(kind: str, key: str, state: str | None, page: int, source: str | None = None) -> dict | None:
    """Issuers in one Form D group or industry (kind 'cat', key 'Group' or 'Group/Industry'), or one fund type
    (kind 'fund'), largest latest offering first. source: 'inferred' (the model's category), 'filed' (the industry
    on the filing), or both."""
    page = max(1, min(page, MAX_PAGE))
    tax = formd_taxonomy()
    params: dict = {"lim": PER_PAGE + 1, "off": (page - 1) * PER_PAGE, "st": state}
    if kind == "cat":
        g, _, s = key.partition("/")
        if g not in tax or (s and s not in tax[g]):
            return None
        inds = [s] if s else tax[g]
        params.update(g=g, s=s or None, inds=inds)
        inferred = "(c.category = %(g)s" + (" AND c.subcategory = %(s)s" if s else "") + ")"
        filed = "o.industry = ANY(%(inds)s)"
        node = {"code": key, "name": s or g, "group": g, "industry": s or None}
    else:
        if key not in FUND_LABELS:
            return None
        filed_names = {"venture": ["Venture Capital Fund"], "private_equity": ["Private Equity Fund"], "hedge": ["Hedge Fund"],
                       "other": ["Other Investment Fund"]}.get(key, [])
        params.update(f=key, fnames=filed_names)
        inferred = "c.fund_type = %(f)s"
        filed = "o.fund_type = ANY(%(fnames)s)" if filed_names else "false"
        node = {"code": key, "name": fund_label(key), "group": None, "industry": None}
    member = {"inferred": inferred, "filed": filed}.get(source or "", f"({inferred} OR {filed})")
    with db.conn() as conn:
        if not _fd_ok(conn):
            return None
        rows = conn.execute(f"""
            SELECT * FROM (SELECT DISTINCT ON (o.cik) o.cik, o.issuer_name, o.city, o.state, o.latest_accession AS accession, o.latest_date,
                                  o.latest_offering, o.latest_sold, o.indefinite, o.industry, o.fund_type AS fund_type_filed,
                                  c.category, c.subcategory, c.fund_type, c.confidence, {_FD_SIZE} AS size
                           FROM sec_formd_offerings o LEFT JOIN form_d_category c ON c.cik = o.cik
                           WHERE {member}{" AND o.state = %(st)s" if state else ""}
                           ORDER BY o.cik, o.latest_date DESC NULLS LAST) x
            ORDER BY x.size DESC, x.cik LIMIT %(lim)s OFFSET %(off)s""", params).fetchall()
        states = conn.execute(f"""SELECT o.state, count(DISTINCT o.cik) AS n FROM sec_formd_offerings o LEFT JOIN form_d_category c ON c.cik = o.cik
                                  WHERE {member} AND o.state IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 60""", params).fetchall()
        counts = conn.execute(f"""SELECT count(DISTINCT o.cik) FILTER (WHERE {inferred}) AS inferred, count(DISTINCT o.cik) FILTER (WHERE {filed}) AS filed
                                  FROM sec_formd_offerings o LEFT JOIN form_d_category c ON c.cik = o.cik WHERE {member}""", params).fetchone()
    for r in rows:
        r["fund_label"] = fund_label(r["fund_type"])
    return {"node": node, "rows": rows[:PER_PAGE], "more": len(rows) > PER_PAGE, "page": page, "states": states, "counts": counts}


@ttl_lru(ttl=600)
def cross_dataset_counts() -> dict | None:
    """The counts build_cross_dataset_counts() stored (category_xref_counts), or None before the first build."""
    try:
        with db.conn() as conn:
            if conn.execute("SELECT to_regclass('category_xref_counts') AS t").fetchone()["t"] is None:
                return None
            rows = conn.execute("SELECT name, n, built FROM category_xref_counts").fetchall()
    except Exception:  # noqa: BLE001 - an extra paragraph; never fail the page
        return None
    if not rows:
        return None
    out = {r["name"]: r["n"] for r in rows}
    out["built"] = max(r["built"] for r in rows)
    return out


XREF_SQL = {
    # nonprofits with an NTEE code that are also a categorized Form D issuer, three ways
    "formd_ein": """SELECT count(DISTINCT n.ein) FROM nonprofit_ntee n JOIN sec_formd d ON d.issuer_ein = n.ein
                    JOIN form_d_category c ON c.cik = d.cik AND c.category IS NOT NULL""",
    "formd_registry": """SELECT count(DISTINCT n.ein) FROM nonprofit_ntee n
                         JOIN biz_links bo ON bo.kind = 'org' AND bo.key = n.ein
                         JOIN biz_links bf ON bf.state = bo.state AND bf.entity_id = bo.entity_id AND bf.kind = 'formd'
                         JOIN form_d_category c ON c.cik = lpad(bf.key, 10, '0') AND c.category IS NOT NULL""",
    "formd_5500": """SELECT count(DISTINCT n.ein) FROM nonprofit_ntee n
                     JOIN xlinks x ON x.src_kind = 'f5500_sponsor' AND x.dst_kind = 'formd' AND x.src_key = n.ein
                     JOIN form_d_category c ON (c.cik = lpad(x.dst_key, 10, '0') OR c.accession = x.dst_key) AND c.category IS NOT NULL""",
    "formd_any": """SELECT count(*) FROM nonprofit_ntee n WHERE n.ein IN (
                      SELECT d.issuer_ein FROM sec_formd d JOIN form_d_category c ON c.cik = d.cik AND c.category IS NOT NULL
                      UNION SELECT bo.key FROM biz_links bo JOIN biz_links bf ON bf.state = bo.state AND bf.entity_id = bo.entity_id AND bf.kind = 'formd'
                             JOIN form_d_category c ON c.cik = lpad(bf.key, 10, '0') AND c.category IS NOT NULL WHERE bo.kind = 'org'
                      UNION SELECT x.src_key FROM xlinks x JOIN form_d_category c ON (c.cik = lpad(x.dst_key, 10, '0') OR c.accession = x.dst_key)
                             AND c.category IS NOT NULL WHERE x.src_kind = 'f5500_sponsor' AND x.dst_kind = 'formd')""",
    # nonprofits with an NTEE code that appear in another dataset by EIN
    "fec": "SELECT count(DISTINCT ein) FROM fec_org_committees WHERE ein IN (SELECT ein FROM nonprofit_ntee)",
    "lobbying": """SELECT count(DISTINCT e) FROM (SELECT client_ein AS e FROM lda_filings WHERE client_ein IS NOT NULL
                   UNION SELECT registrant_ein FROM lda_filings WHERE registrant_ein IS NOT NULL) x WHERE e IN (SELECT ein FROM nonprofit_ntee)""",
    "federal": """SELECT count(DISTINCT e) FROM (SELECT ein AS e FROM fed_recipient_names WHERE ein IS NOT NULL
                  UNION SELECT recipient_ein FROM usa_recipient_totals WHERE recipient_ein IS NOT NULL) x WHERE e IN (SELECT ein FROM nonprofit_ntee)""",
    "form5500": "SELECT count(*) FROM form5500_sponsors WHERE ein IN (SELECT ein FROM nonprofit_ntee)",
    "openpayments": "SELECT count(DISTINCT target_key) FROM op_org_links WHERE target_kind = 'org' AND target_key IN (SELECT ein FROM nonprofit_ntee)",
    "fara": "SELECT count(DISTINCT key) FROM fara_org_links WHERE kind = 'org' AND key IN (SELECT ein FROM nonprofit_ntee)",
    "any_other": """SELECT count(*) FROM nonprofit_ntee n WHERE n.ein IN (
                      SELECT ein FROM fec_org_committees UNION SELECT client_ein FROM lda_filings WHERE client_ein IS NOT NULL
                      UNION SELECT registrant_ein FROM lda_filings WHERE registrant_ein IS NOT NULL
                      UNION SELECT ein FROM fed_recipient_names WHERE ein IS NOT NULL UNION SELECT recipient_ein FROM usa_recipient_totals WHERE recipient_ein IS NOT NULL
                      UNION SELECT ein FROM form5500_sponsors UNION SELECT target_key FROM op_org_links WHERE target_kind = 'org'
                      UNION SELECT key FROM fara_org_links WHERE kind = 'org'
                      UNION SELECT d.issuer_ein FROM sec_formd d JOIN form_d_category c ON c.cik = d.cik AND c.category IS NOT NULL)""",
    "ntee_total": "SELECT count(*) FROM nonprofit_ntee",
    "formd_total": "SELECT count(*) FROM form_d_category WHERE category IS NOT NULL",
}


def build_cross_dataset_counts() -> dict:
    """Count the entities that carry a category in more than one dataset (XREF_SQL) and store the numbers in
    category_xref_counts for the Categories page. Minutes of joins, so it runs from the nightly script and after a
    categorization wave, never from a page request."""
    from loader import db as ldb
    out = {}
    with ldb.connect() as conn:
        conn.execute("SET statement_timeout = '3600s'")
        conn.execute("CREATE TABLE IF NOT EXISTS category_xref_counts (name text PRIMARY KEY, n bigint NOT NULL, built timestamptz NOT NULL DEFAULT now())")
        for name, sql in XREF_SQL.items():
            out[name] = conn.execute(sql).fetchone()[0]
            conn.execute("INSERT INTO category_xref_counts (name, n, built) VALUES (%s, %s, now()) ON CONFLICT (name) DO UPDATE SET n = EXCLUDED.n, built = now()",
                         (name, out[name]))
            conn.commit()
    cross_dataset_counts.cache_clear() if hasattr(cross_dataset_counts, "cache_clear") else None
    return out


@router.get("/categories/formd/fund/{fund}", response_class=HTMLResponse)
def formd_fund_list(request: Request, fund: str, state: str = Query("", max_length=2), page: int = Query(1, ge=1),
                    source: str = Query("", max_length=8)):
    _gate()
    key = clean_fund(fund)
    if not key:
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    src = source if source in ("inferred", "filed") else None
    data = formd_orgs("fund", key, st, page, src)
    if not data:
        raise HTTPException(404)
    return _render(request, "categories_formd_list.html", kind="fund", key=key, state=st or "", source=src or "", **data)


@router.get("/categories/formd/{group}", response_class=HTMLResponse)
@router.get("/categories/formd/{group}/{industry}", response_class=HTMLResponse)
def formd_cat_list(request: Request, group: str, industry: str = "", state: str = Query("", max_length=2), page: int = Query(1, ge=1),
                   source: str = Query("", max_length=8)):
    _gate()
    key = clean_fd(group + ("/" + industry if industry else ""))
    if not key:
        raise HTTPException(404)
    st = state.upper() if _STATE.match(state) else None
    src = source if source in ("inferred", "filed") else None
    data = formd_orgs("cat", key, st, page, src)
    if not data:
        raise HTTPException(404)
    return _render(request, "categories_formd_list.html", kind="cat", key=key, state=st or "", source=src or "", **data)
