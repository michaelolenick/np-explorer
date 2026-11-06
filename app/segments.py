"""Segments sent from VSTRAT (owner, 2026-11-06): a customer or market segment ("first-generation college students",
"regional hospital systems") with its description and the strategy project's context; FURP answers with the
organizations that match it, nonprofits and firms, on a page of its own and as JSON. The contract VSTRAT follows is
docs/vstrat-segments.md.

How a segment is read: one small-model call (Claude Haiku, thinking off, cached by input in nl_cache for 30 days)
turns segment + description + context into a guess: name search terms, NTEE categories for nonprofits, Form D
categories for firms, and what the user wants (customers, peers, competitors, funders). A little off is fine. The
matches then come from SQL: organizations in the categories (largest first) and name matches on the terms, ranked
by how many ways they match. When nothing matches with confidence, no lookalikes: the page says none were found and
asks one short question, and the JSON carries that question."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from app import analytics, ask, corporate, db, queries
from app.cache import ttl_lru
from app.config import SITE_URL

log = logging.getLogger("furp.segments")
router = APIRouter()

MODEL = os.environ.get("SEGMENTS_MODEL", "claude-haiku-5-5")
TIMEOUT = 12.0
KINDS = ("both", "nonprofits", "firms")
DEFAULT_LIMIT, MAX_LIMIT = 25, 100
MAX_SEGMENT, MAX_TEXT = 200, 1000
MIN_CONFIDENCE = 0.5          # below this, or with fewer than MIN_MATCHES matches, the answer is a question
MIN_MATCHES = 3
WANTS = ("customers", "peers", "competitors", "funders", "unclear")
API_KEY = os.environ.get("SEGMENTS_API_KEY", "")        # when set, POST /api/segments needs X-FURP-Key
# Browser calls from any VSTRAT environment (analytics.VSTRAT_HOSTS: prod, bench, dev) get CORS headers.
ORIGINS = {o.strip() for o in os.environ.get("SEGMENTS_ORIGINS", ",".join("https://" + h for h in sorted(analytics.VSTRAT_HOSTS))).split(",") if o.strip()}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "terms": {"type": "array", "items": {"type": "string"}},
        "ntee": {"type": "array", "items": {"type": "string"}},
        "formd": {"type": "array", "items": {"type": "string"}},
        "wants": {"type": "string", "enum": list(WANTS)},
        "confidence": {"type": "number"},
    },
    "required": ["terms", "ntee", "formd", "wants", "confidence"],
}

SYSTEM_HEAD = """You read a customer or market segment from VSTRAT, strategy software, so that FURP (a public-records \
explorer of US nonprofits and private companies) can find the organizations in it. You get the segment's name, a \
description (may be empty) and the context of the strategy project (its offering, industry and user). Reply with JSON only:
- terms: up to five short name-search phrases (one to three words each) that organizations IN this segment would carry in \
their names, for example "food bank", "community college". Not generic words like "organization" or "services".
- ntee: up to four NTEE codes (from the list below) for the nonprofits in the segment, best first; empty if the segment \
is not nonprofits.
- formd: up to four Form D categories (from the list below, written exactly as "Group/Industry") for the private \
companies in the segment, best first; empty if the segment is not companies.
- wants: what the user is after, judging from the context: customers (the segment buys the offering), peers (like the \
user's own organization), competitors (rivals of the offering), funders (who would fund the segment), or unclear.
- confidence: 0 to 1, how well the segment maps to these codes and terms.
A guess is fine; a little off is better than nothing. The segment itself decides nonprofit versus company (a \
"students" segment is served by nonprofits; "regional hospital systems" are both; "SaaS startups" are companies)."""


def _norm(s: str | None, n: int) -> str:
    return " ".join((s or "").split())[:n]


def context_text(context) -> str:
    """The context as one line: a string as is, an object as "offering: ...; industry: ...; user: ..."."""
    if isinstance(context, dict):
        return "; ".join(f"{k}: {_norm(str(v), 300)}" for k, v in context.items() if v is not None and str(v).strip())[:MAX_TEXT]
    return _norm(str(context) if context is not None else "", MAX_TEXT)


@ttl_lru(ttl=3600)
def taxonomy() -> dict:
    """{'ntee': {code: name}, 'majors': {letter: name}, 'formd': {'Group/Industry': n}}, from the database."""
    with db.conn() as conn:
        ntee = {r["code"]: r["name"] for r in conn.execute("SELECT code, name FROM ntee_taxonomy WHERE level = 'code'").fetchall()}
        majors = {r["code"]: r["name"] for r in conn.execute("SELECT code, name FROM ntee_taxonomy WHERE level = 'major' ORDER BY code").fetchall()}
        formd = {f"{r['category']}/{r['subcategory']}": r["n"] for r in conn.execute(
            """SELECT category, subcategory, count(*) AS n FROM form_d_category
               WHERE category IS NOT NULL AND subcategory IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 3 DESC""").fetchall()}
    return {"ntee": ntee, "majors": majors, "formd": formd}


def system_prompt(tax: dict) -> str:
    lines = [SYSTEM_HEAD, "", "NTEE major groups:"]
    lines += [f"{k} {v}" for k, v in tax["majors"].items()]
    lines += ["", "NTEE codes (code name):"] + [f"{k} {v}" for k, v in sorted(tax["ntee"].items())]
    lines += ["", "Form D categories (Group/Industry):"] + sorted(tax["formd"])
    return "\n".join(lines)


def _key(segment: str, description: str, context: str) -> str:
    return "segment:" + hashlib.sha256(json.dumps([segment.lower(), description.lower(), context.lower()]).encode()).hexdigest()


def empty_reading(how: str) -> dict:
    return {"terms": [], "ntee": [], "formd": [], "wants": "unclear", "confidence": 0.0, "how": how}


def parse(segment: str, description: str = "", context: str = "") -> dict:
    """The segment read as search terms and categories (cached per input), with how it was read:
    cache | model | off | failed."""
    segment, description, context = _norm(segment, MAX_SEGMENT), _norm(description, MAX_TEXT), _norm(context, MAX_TEXT)
    if not segment:
        return empty_reading("off")
    key = _key(segment, description, context)
    hit = ask._shared_get(key)
    if isinstance(hit, dict) and hit.get("terms") is not None:
        return {**hit, "how": "cache"}
    if not ask.enabled():
        return empty_reading("off")
    tax = taxonomy()
    user = f"Segment: {segment}\nDescription: {description or '(none)'}\nContext: {context or '(none)'}"
    body = {"model": MODEL, "max_tokens": 400, "system": system_prompt(tax), "thinking": {"type": "disabled"},
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
            "messages": [{"role": "user", "content": user}]}
    try:
        r = ask.post(body, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        log.warning("segments: call failed (%s)", type(e).__name__)
        return empty_reading("failed")
    if r.status_code != 200:
        log.warning("segments: model returned %s", r.status_code)
        return empty_reading("failed")
    data = r.json()
    u = data.get("usage") or {}
    ask._usage(input_tokens=int(u.get("input_tokens") or 0), output_tokens=int(u.get("output_tokens") or 0))
    text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
    try:
        raw = json.loads(text)
    except ValueError:
        log.info("segments: reply was not JSON")
        return empty_reading("failed")
    reading = clean(raw, tax)
    if reading["terms"] or reading["ntee"] or reading["formd"]:
        ask._shared_put(key, reading)
    return {**reading, "how": "model"}


def clean(raw: dict, tax: dict) -> dict:
    """Only codes and categories that exist; short terms; a confidence between 0 and 1."""
    terms = []
    for t in raw.get("terms") or []:
        t = _norm(str(t), 40).lower()
        if t and 1 <= len(t.split()) <= 3 and max(len(w) for w in t.split()) <= 25 and t not in terms:
            terms.append(t)
    # the model sometimes writes "B42 Undergraduate College": keep the code
    ntee = [m.group(1) for m in (re.match(r"\s*([A-Z]\d{2})\b", str(x).upper()) for x in raw.get("ntee") or []) if m and m.group(1) in tax["ntee"]]
    formd = [c for c in (str(x).strip() for x in raw.get("formd") or []) if c in tax["formd"] and c != "Other/Other"]   # a catch-all says nothing
    wants = raw.get("wants") if raw.get("wants") in WANTS else "unclear"
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
    except (TypeError, ValueError):
        conf = 0.0
    return {"terms": terms[:5], "ntee": list(dict.fromkeys(ntee))[:4], "formd": list(dict.fromkeys(formd))[:4],
            "wants": wants, "confidence": round(conf, 2)}


# --- the matches, from SQL -----------------------------------------------------------------------

def orgs_in_codes(codes: list[str], limit: int, state: str | None = None) -> list[dict]:
    if not codes:
        return []
    with db.conn(timeout="20s") as conn:
        return conn.execute("""
            SELECT o.ein, o.name, o.city, o.state, o.latest_total_revenue, n.ntee_code
            FROM nonprofit_ntee n JOIN organizations o ON o.ein = n.ein
            WHERE n.ntee_code = ANY(%(codes)s) AND (%(state)s::text IS NULL OR o.state = %(state)s)
            ORDER BY o.latest_total_revenue DESC NULLS LAST, o.ein LIMIT %(lim)s""",
            {"codes": codes, "state": state, "lim": limit}).fetchall()


def nonprofits(reading: dict, limit: int, state: str | None = None) -> list[dict]:
    """Nonprofits in the segment: in its NTEE categories or carrying one of its terms in the name; both first,
    then by latest revenue. Each row says how it matched."""
    found: dict[str, dict] = {}
    for o in orgs_in_codes(reading["ntee"], limit * 2, state):
        found[o["ein"]] = {**o, "by_category": True, "by_name": False}
    for term in reading["terms"][:4]:
        for o in queries.search_orgs(term, limit=limit, state=state):
            row = found.get(o["ein"])
            if row:
                row["by_name"] = True
            else:
                found[o["ein"]] = {**o, "by_category": o.get("ntee_code") in reading["ntee"], "by_name": True}
    rows = sorted(found.values(), key=lambda r: (-(r["by_category"] + r["by_name"]), -(r["latest_total_revenue"] or 0)))
    for r in rows:
        r["matched"] = "name and category" if r["by_category"] and r["by_name"] else "category" if r["by_category"] else "name"
        r["url"] = f"{SITE_URL}/org/{r['ein']}"
    return rows[:limit]


def firms(reading: dict, limit: int, state: str | None = None) -> list[dict]:
    """Form D issuers in the segment: in its Form D categories (largest offerings) or named by its terms (newest
    filing first); both first, then by amount raised."""
    found: dict[str, dict] = {}
    for cat in reading["formd"][:4]:
        for f in corporate.search_formd("", limit=limit * 2, fd_cat=cat):
            if not state or f.get("state") == state:
                found[f["cik"]] = {**f, "by_category": True, "by_name": False}
    for term in reading["terms"][:4]:
        for f in corporate.search_formd(term, limit=limit):
            if state and f.get("state") != state:
                continue
            row = found.get(f["cik"])
            if row:
                row["by_name"] = True
            else:
                in_cat = f"{f.get('category')}/{f.get('subcategory')}" in reading["formd"]
                found[f["cik"]] = {**f, "by_category": in_cat, "by_name": True}
    rows = sorted(found.values(), key=lambda r: (-(r["by_category"] + r["by_name"]), -(r["amount_sold"] or 0)))
    from app.slugs import canonical
    for r in rows:
        r["matched"] = "name and category" if r["by_category"] and r["by_name"] else "category" if r["by_category"] else "name"
        r["name"] = r.get("issuer_name")
        r["url"] = SITE_URL + canonical("formd", r["accession"], r["issuer_name"])
    return rows[:limit]


def answer(segment: str, description: str, context: str, kinds: str, limit: int, state: str | None = None) -> dict:
    """The whole answer: the reading, the matches, and when they are thin, the question instead."""
    kinds = kinds if kinds in KINDS else "both"
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    reading = parse(segment, description, context)
    nps = nonprofits(reading, limit, state) if kinds in ("both", "nonprofits") and (reading["ntee"] or reading["terms"]) else []
    fms = firms(reading, limit, state) if kinds in ("both", "firms") and (reading["formd"] or reading["terms"]) else []
    confident = reading["confidence"] >= MIN_CONFIDENCE and len(nps) + len(fms) >= min(MIN_MATCHES, limit)
    params = {"segment": _norm(segment, MAX_SEGMENT), "description": _norm(description, MAX_TEXT),
              "context": _norm(context, MAX_TEXT), "kinds": kinds, "limit": limit}
    if state:
        params["state"] = state
    page_url = f"{SITE_URL}/segments?" + urlencode({k: v for k, v in params.items() if v not in ("", None)})
    out = {"status": "ok" if confident else ("off" if reading["how"] in ("off", "failed") else "ask"),
           "segment": params["segment"], "kinds": kinds, "limit": limit, "page_url": page_url,
           "reading": {"terms": reading["terms"], "wants": reading["wants"], "confidence": reading["confidence"],
                       "how": reading["how"],
                       "ntee": [{"code": c, "name": taxonomy()["ntee"].get(c, "")} for c in reading["ntee"]],
                       "formd": reading["formd"]},
           "nonprofits": [_np_out(r) for r in nps] if confident else [],
           "firms": [_firm_out(r) for r in fms] if confident else [],
           "question": None}
    if not confident:
        out["question"] = (f"What is “{params['segment']}”? Describe the organizations in it, or the kind of "
                           f"nonprofit or company they resemble.")
        if reading["how"] in ("off", "failed"):
            out["question"] = None
            out["note"] = "The segment reader is not available right now; try again in a minute."
    return out


def _np_out(r: dict) -> dict:
    return {"ein": r["ein"], "name": r["name"], "city": r.get("city"), "state": r.get("state"),
            "ntee_code": r.get("ntee_code"), "latest_total_revenue": r.get("latest_total_revenue"),
            "matched": r["matched"], "url": r["url"]}


def _firm_out(r: dict) -> dict:
    return {"cik": r.get("cik"), "name": r.get("name"), "city": r.get("city"), "state": r.get("state"),
            "industry": r.get("industry"), "category": r.get("category"), "subcategory": r.get("subcategory"),
            "amount_sold": r.get("amount_sold"), "offering_amount": r.get("offering_amount"),
            "filing_date": r.get("filing_date"), "matched": r["matched"], "url": r["url"]}


# --- routes ---------------------------------------------------------------------------------------

def _cors(request: Request, resp: Response) -> Response:
    origin = request.headers.get("origin", "")
    if origin in ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-FURP-Key"
        resp.headers["Vary"] = "Origin"
    return resp


def _args(d: dict) -> dict:
    return {"segment": _norm(str(d.get("segment") or ""), MAX_SEGMENT), "description": _norm(str(d.get("description") or ""), MAX_TEXT),
            "context": context_text(d.get("context")), "kinds": str(d.get("kinds") or "both").lower(),
            "limit": d.get("limit") or DEFAULT_LIMIT,
            "state": (str(d.get("state") or "").strip().upper() or None) if re.fullmatch(r"[A-Za-z]{2}", str(d.get("state") or "")) else None}


@router.options("/api/segments", include_in_schema=False)
def segments_preflight(request: Request):
    return _cors(request, Response(status_code=204))


@router.post("/api/segments")
async def segments_api(request: Request):
    """Matches for a segment, as JSON (docs/vstrat-segments.md)."""
    if API_KEY and request.headers.get("x-furp-key") != API_KEY:
        return _cors(request, JSONResponse({"error": "missing or wrong X-FURP-Key"}, status_code=401))
    try:
        body = await request.json()
    except ValueError:
        return _cors(request, JSONResponse({"error": "the body must be JSON"}, status_code=400))
    if not isinstance(body, dict) or not _norm(str(body.get("segment") or ""), MAX_SEGMENT):
        return _cors(request, JSONResponse({"error": "segment is required"}, status_code=400))
    a = _args(body)
    try:
        limit = int(a["limit"])
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    _sent(request, a)
    return _cors(request, JSONResponse(_plain(answer(a["segment"], a["description"], a["context"], a["kinds"], limit, a["state"]))))


def _plain(x):
    """JSON-safe copies (dates, decimals)."""
    return json.loads(json.dumps(x, default=str))


def _sent(request: Request, a: dict) -> None:
    """A segment sent to the API: one 'segment' event for the daily report (source=vstrat when VSTRAT sent it)."""
    analytics.event(request, "segment", {"kinds": a["kinds"]})


@router.get("/api/segments")
def segments_api_get(request: Request):
    """The same answer for a GET with query parameters (easy to try in a browser)."""
    qp = request.query_params
    if not _norm(qp.get("segment"), MAX_SEGMENT):
        return _cors(request, JSONResponse({"error": "segment is required"}, status_code=400))
    a = _args(dict(qp))
    try:
        limit = int(a["limit"])
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    _sent(request, a)
    return _cors(request, JSONResponse(_plain(answer(a["segment"], a["description"], a["context"], a["kinds"], limit, a["state"]))))


@router.get("/segments", response_class=HTMLResponse)
def segments_page(request: Request):
    """The results page VSTRAT opens in its own tab: FURP's look and navigation, every match linked to its page.
    Without a segment, a form to enter one."""
    from app.main import render
    qp = request.query_params
    a = _args(dict(qp))
    try:
        limit = int(a["limit"])
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    res = answer(a["segment"], a["description"], a["context"], a["kinds"], limit, a["state"]) if a["segment"] else None
    return render(request, "segments.html", a=a, res=res, kinds=KINDS,
                  from_vstrat=analytics.source_of(request.headers) == "vstrat")
