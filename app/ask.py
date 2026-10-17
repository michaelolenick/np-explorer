"""Ask in plain English: a language model turns the question into one of the site's own queries.

The model never writes SQL. It picks a tool (people search, an organization's people,
organizations by name or place, an organization's money, a leaderboard) and fills in
its parameters; the app runs that query the same way the search pages do. That keeps
it fast, and a question can't make the database do anything the site doesn't already do.

Needs ANTHROPIC_API_KEY in .env; without it /ask says so and offers the normal search.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict

import httpx

from app import boards, queries
from app.contact import HourlyLimit

log = logging.getLogger("np-explorer.ask")

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("NP_ASK_MODEL", "claude-haiku-5-5")
MAX_QUESTION = 300
PER_HOUR = 20                  # questions per IP per hour (per worker)
PER_DAY = 2000                 # model calls per worker per day: a cost ceiling
CACHE_SECONDS = 24 * 3600
TIMEOUT = 15

limit = HourlyLimit(PER_HOUR)
_day = {"date": "", "n": 0}
_cache: OrderedDict = OrderedDict()
_lock = threading.Lock()

_PLACE = {
    "state": {"type": "string", "description": "Two-letter US state code, e.g. TX"},
    "city": {"type": "string", "description": "City name, e.g. Austin"},
}
TOOLS = [
    {"name": "people_search",
     "description": "Find people (officers, directors, trustees, key employees) by name across all filings.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "The person's name"},
         "state": _PLACE["state"],
         "organization": {"type": "string", "description": "Only people at organizations whose name has this"},
         "min_pay": {"type": "integer", "description": "Only people paid at least this much in one filing"},
         "year_from": {"type": "integer"}, "year_to": {"type": "integer"}},
         "required": ["name"]}},
    {"name": "organization_people",
     "description": "Everyone who has served at one organization (who runs it, who is on the board, who is paid).",
     "input_schema": {"type": "object", "properties": {
         "organization": {"type": "string", "description": "Organization name or EIN"}, **_PLACE},
         "required": ["organization"]}},
    {"name": "find_organizations",
     "description": "Find charities and other nonprofits by name and/or location; can limit to donor-advised "
                    "fund sponsors.",
     "input_schema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "All or part of the name; omit to list by place"},
         **_PLACE, "daf_only": {"type": "boolean", "description": "Only donor-advised fund sponsors"}}}},
    {"name": "organization_money",
     "description": "One organization's money: finances by year, where its money went (expenses, events, "
                    "pay), grants it made, grants it received, or its donor-advised funds.",
     "input_schema": {"type": "object", "properties": {
         "organization": {"type": "string", "description": "Organization name or EIN"}, **_PLACE,
         "topic": {"type": "string", "enum": ["finances", "spending", "grants_made", "grants_received", "daf"]}},
         "required": ["organization", "topic"]}},
    {"name": "leaderboard",
     "description": "A ranked list (leaderboard) such as the highest-paid people or vendors.",
     "input_schema": {"type": "object", "properties": {
         "board": {"type": "string", "enum": [b.slug for b in boards.visible()]},
         "year": {"type": "integer"}, "state": _PLACE["state"]},
         "required": ["board"]}},
]
SYSTEM = (
    "You turn questions about US nonprofits into exactly one tool call for a site built from IRS Form 990 "
    "filings. Pick the single best tool and fill in only what the question says; never invent names, years "
    "or places. Leaderboards: " + "; ".join(f"{b.slug} = {b.title}" for b in boards.visible()) + ". "
    "If the question is not about nonprofits, people at nonprofits, or their money, call people_search with "
    "the question's most name-like words."
)

ANCHORS = {"finances": "", "spending": "#spending", "grants_made": "#grants-made",
           "grants_received": "#grants-received", "daf": "#daf"}


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _norm_question(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def _budget_ok() -> bool:
    today = time.strftime("%Y-%m-%d")
    with _lock:
        if _day["date"] != today:
            _day.update(date=today, n=0)
        if _day["n"] >= PER_DAY:
            return False
        _day["n"] += 1
        return True


def interpret(question: str) -> dict:
    """{"tool": name, "args": {...}} for a question, or {"error": ...}. Cached for a day."""
    key = _norm_question(question)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    if not _budget_ok():
        return {"error": "busy"}
    try:
        r = httpx.post(API_URL, timeout=TIMEOUT, headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
            "content-type": "application/json"}, json={
            "model": MODEL, "max_tokens": 300, "system": SYSTEM, "tools": TOOLS,
            "tool_choice": {"type": "any"},
            "messages": [{"role": "user", "content": question}]})
    except httpx.HTTPError as e:
        log.error("ask: model call failed (%s)", type(e).__name__)
        return {"error": "unavailable"}
    if r.status_code != 200:
        log.error("ask: model call returned %s", r.status_code)   # status only: never the key or the body
        return {"error": "unavailable"}
    use = next((c for c in r.json().get("content", []) if c.get("type") == "tool_use"), None)
    if not use:
        return {"error": "unclear"}
    out = {"tool": use["name"], "args": use.get("input") or {}}
    with _lock:
        _cache[key] = (time.time(), out)
        while len(_cache) > 5000:
            _cache.popitem(last=False)
    return out


# --- running the chosen query -------------------------------------------------------

def _state(v):
    v = (v or "").strip().upper()
    return v if re.fullmatch(r"[A-Z]{2}", v) else None


def _resolve_org(name: str, state=None, city=None) -> dict | None:
    digits = re.sub(r"\D", "", name or "")
    if len(digits) == 9 and queries.org_exists(digits):
        return {"ein": digits, "name": None}
    return queries.best_org(name or "", state=_state(state), city=city or None)


def run(plan: dict) -> dict:
    """Run a plan from interpret(): a description of what was searched, results, and a link to the full page."""
    tool, a = plan["tool"], plan["args"]
    if tool == "people_search":
        filters = {"state": _state(a.get("state")), "year_from": a.get("year_from"), "year_to": a.get("year_to"),
                   "title": None, "min_comp": a.get("min_pay"), "org": a.get("organization")}
        res = queries.search_people(str(a.get("name", ""))[:100], filters, 1)
        what = f"People named “{a.get('name')}”" + "".join(
            f", {lab} {v}" for lab, v in (("in", filters["state"]), ("at", filters["org"]),
                                          ("paid at least $", a.get("min_pay"))) if v)
        params = {"q": a.get("name", ""), **{k: v for k, v in filters.items() if v}}
        return {"kind": "people", "what": what, "rows": res["results"][:50], "total": res["total"],
                "url": "/search?" + _qs(params)}
    if tool in ("organization_people", "organization_money"):
        org = _resolve_org(str(a.get("organization", "")), a.get("state"), a.get("city"))
        if not org:
            return {"kind": "none", "what": f"No organization found matching “{a.get('organization')}”"}
        o = queries.org(org["ein"])
        name = o["org"]["name"] if o else org["ein"]
        if tool == "organization_people":
            people = queries.org_people([org["ein"]]).get(org["ein"], [])
            return {"kind": "org_people", "what": f"Everyone who has served at {name}", "org": o["org"],
                    "rows": people, "total": len(people), "url": f"/org/{org['ein']}#people"}
        topic = a.get("topic") or "finances"
        return {"kind": "org_money", "topic": topic, "org": o["org"], "data": o,
                "what": f"{name}: " + {"finances": "finances by year", "spending": "where the money went",
                                       "grants_made": "grants it made", "grants_received": "grants it received",
                                       "daf": "donor-advised funds"}.get(topic, topic),
                "url": f"/org/{org['ein']}{ANCHORS.get(topic, '')}"}
    if tool == "find_organizations":
        state, city = _state(a.get("state")), (a.get("city") or None)
        rows = queries.search_orgs(str(a.get("name") or ""), limit=50, daf_only=bool(a.get("daf_only")),
                                   state=state, city=city)
        where = ", ".join(x for x in (city and city.title(), state) if x)
        what = ("DAF sponsors" if a.get("daf_only") else "Organizations") + (
            f" named “{a['name']}”" if a.get("name") else "") + (f" in {where}" if where else "")
        params = {"q": a.get("name") or "", "type": "daf" if a.get("daf_only") else "firm",
                  **({"state": state} if state else {}), **({"city": city} if city else {})}
        return {"kind": "orgs", "what": what, "rows": rows, "total": len(rows), "url": "/search?" + _qs(params)}
    if tool == "leaderboard":
        b = boards.get(a.get("board") or "")
        if not b:
            return {"kind": "none", "what": "No such leaderboard"}
        filters = {"year": a.get("year"), "form": None, "state": _state(a.get("state"))}
        page = boards.page(b, filters, 1, per_page=25) if boards.meta().get(b.slug) else {"rows": [], "total": 0}
        params = {k: v for k, v in filters.items() if v}
        return {"kind": "board", "board": b, "what": b.title + "".join(
            f", {k} {v}" for k, v in params.items()), "rows": page["rows"], "total": page["total"],
            "url": f"/boards/{b.slug}" + ("?" + _qs(params) if params else "")}
    return {"kind": "none", "what": "That question didn't map to a search"}


def _qs(params: dict) -> str:
    from urllib.parse import urlencode
    return urlencode({k: v for k, v in params.items() if v not in (None, "")})


def describe(plan: dict) -> str:
    """The plan as plain text, shown so people can see how their question was read."""
    return f"{plan['tool'].replace('_', ' ')}: " + json.dumps(plan["args"], ensure_ascii=False)
