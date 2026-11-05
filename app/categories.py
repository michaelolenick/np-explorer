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
    out = {"furp": [], "ntee": []}
    if not q:
        return out
    with db.conn() as conn:
        if not _ok(conn):
            return out
        words = [w for w in re.split(r"[^A-Za-z0-9_]+", q) if w][:6]
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
    return f"/categories/ntee/{code}" if level != "broad" else f"/categories?view=ntee#broad-{code}"


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

@ttl_lru()
def orgs(view: str, key: str, state: str | None, page: int, source: str | None = None) -> dict | None:
    """Organizations in one NTEE code or major group, or one FURP topic or topic:sense; largest first."""
    page = max(1, min(page, MAX_PAGE))
    params: dict = {"lim": PER_PAGE + 1, "off": (page - 1) * PER_PAGE, "st": state, "src": source}
    with db.conn() as conn:
        if not _ok(conn):
            return None
        if view == "ntee":
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
        where = member + (" AND o.state = %(st)s" if state else "") + (" AND n.ntee_source = %(src)s" if source else "")
        rows = conn.execute(f"""SELECT o.ein, o.name, o.city, o.state, o.latest_filing_year, o.latest_total_revenue,
                                       n.ntee_code, n.ntee_source, n.confidence, n.furp_category, n.furp_subcategory
                                FROM {frm} WHERE {where}
                                ORDER BY o.latest_total_revenue DESC NULLS LAST, o.ein LIMIT %(lim)s OFFSET %(off)s""", params).fetchall()
        states = conn.execute(f"""SELECT o.state, count(*) AS n FROM {frm} WHERE {member} AND o.state IS NOT NULL
                                  GROUP BY 1 ORDER BY 2 DESC LIMIT 60""", params).fetchall()
    return {"node": node, "rows": rows[:PER_PAGE], "more": len(rows) > PER_PAGE, "page": page, "states": states}


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


@router.get("/categories", response_class=HTMLResponse)
def categories_page(request: Request, view: str = Query("ntee", max_length=4), q: str = Query("", max_length=300),
                    mode: str = Query("search", max_length=8)):
    _gate()
    view = "furp" if view == "furp" else "ntee"
    mode = "infer" if mode == "infer" else "search"
    q = q.strip()
    found = inferred = None
    if q and mode == "search":
        found = search_nodes(q, view)
    elif q:
        inferred = infer(q)
    return _render(request, "categories.html", view=view, q=q, mode=mode, found=found, inferred=inferred,
                   tree=tree(view), totals=totals())


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
