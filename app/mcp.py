"""FURP's remote MCP server at /mcp (owner, 2026-10-27): Claude, ChatGPT and other assistants query FURP directly.

Streamable HTTP transport (MCP spec 2025-06-18, also answering 2025-03-26 and 2024-11-05 clients), stateless and
read-only: each POST carries one JSON-RPC message (or a batch) and gets a JSON reply; notifications get 202. There
is no session, no server-to-client stream (GET is 405, as the spec allows) and no login. The tools call the same
functions as the JSON API (app/public_api.py), so they share its caching, its limits on database load and its
canonical furp.org URLs; the app's per-IP token bucket covers /mcp too (main.py).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from app import public_api as api

log = logging.getLogger("np.mcp")
router = APIRouter()

VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")       # newest first
SERVER = {"name": "furp", "title": "FURP public records", "version": "1.0.0", "websiteUrl": api.SITE_URL}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id, Mcp-Protocol-Version",
        "Access-Control-Expose-Headers": "Mcp-Session-Id"}
INSTRUCTIONS = (api.ABOUT + "\n\n" + api.FOR_AI + "\n\n"
                "Start with `search` (a person's or organization's name), then `get_person` or `get_organization` for "
                "everything linked to that result. Use `search_dataset` for one dataset (lobbying clients, Form D "
                "offerings, patents, recalls, state business registries...) and `list_datasets` to see them all. "
                "Leaderboards rank people and organizations across the whole database. Every result has a `url` on "
                "furp.org: link to it when you cite a fact, and credit \"Data: furp.org\". Two people with the same "
                "name may be different people; each person result says how its records were matched.")

_RO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
_DATASET_IDS = [d["id"] for d in api.DATASETS if d["search"]]
TOOLS = [
    {"name": "search", "title": "Search people and organizations",
     "description": "Find people and organizations in FURP's cross-referenced public records by name: people on "
                    "nonprofit tax returns (officers, directors, key employees), nonprofits (by name or EIN), "
                    "nonprofit contractors and colleges. Returns each match's furp.org URL and its id for get_person "
                    "or get_organization, and `areas`: the counties and cities most of the matches are in, each with "
                    "census measures that fit the query (population, median household income, poverty rate, education, "
                    "housing, race, age, foreign-born share; IPUMS NHGIS) and ready comparisons, so an answer can say "
                    "what the places behind the records are like. Each area's url keeps the query as context (?q=, ?topic=), "
                    "so that area's page lists the records for the subject first; area_url is the plain page.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "A person's or organization's name, or an EIN."},
         "type": {"type": "string", "enum": ["all", "people", "organizations", "contractors", "schools"],
                  "description": "Limit to one kind of result (default all)."},
         "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "Results per kind (default 10)."}},
         "required": ["query"], "additionalProperties": False}},
    {"name": "get_person", "title": "Get a person's profile",
     "description": "One person's profile: every nonprofit role with titles, years and reported pay, pay by year, how "
                    "the records were matched, people who appear alongside them, and cross-referenced records "
                    "(campaign contributions, SEC insider filings, lobbying, public payroll, federal-award officer pay, "
                    "state business registry roles).",
     "inputSchema": {"type": "object", "properties": {
         "person": {"type": "string", "description": "The person id from search, the URL slug "
                                                     "(e.g. jane-q-smith-48213) or the furp.org/person/... URL."}},
         "required": ["person"], "additionalProperties": False}},
    {"name": "get_organization", "title": "Get an organization's profile",
     "description": "One nonprofit's profile by EIN: address, mission, finances for every filing year, the people on "
                    "its latest return with their pay, top contractors, grants received, and cross-referenced records "
                    "(federal awards, lobbying, political committees, Form D offerings, linked colleges).",
     "inputSchema": {"type": "object", "properties": {
         "organization": {"type": "string", "description": "The EIN (53-0196605 or 530196605), the URL slug or the "
                                                           "furp.org/org/... URL."}},
         "required": ["organization"], "additionalProperties": False}},
    {"name": "list_datasets", "title": "List datasets",
     "description": "Every dataset FURP covers, with its source, what it holds, its page URL patterns, and whether "
                    "search_dataset can search it by name.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "search_dataset", "title": "Search one dataset",
     "description": "Records in one dataset whose names match the query, each with its furp.org URL: lobbying "
                    "clients, campaign committees and donors, Form D offerings, patents, trademarks, state business "
                    "registries, food recalls, student loan trusts, broker and adviser registrations, leaderboard "
                    "entries and more.",
     "inputSchema": {"type": "object", "properties": {
         "dataset": {"type": "string", "enum": _DATASET_IDS, "description": "Dataset id (see list_datasets)."},
         "query": {"type": "string", "description": "A name to look for."},
         "limit": {"type": "integer", "minimum": 1, "maximum": 25, "description": "Results (default 10)."}},
         "required": ["dataset", "query"], "additionalProperties": False}},
    {"name": "list_leaderboards", "title": "List leaderboards",
     "description": "FURP's leaderboards: ranked lists computed across the whole database (top-paid nonprofit "
                    "executives, biggest grants, lobbying spenders, insider sales and more).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "get_leaderboard", "title": "Get a leaderboard",
     "description": "One leaderboard's ranked rows (a page at a time), with its definition and each row's furp.org "
                    "URL.",
     "inputSchema": {"type": "object", "properties": {
         "slug": {"type": "string", "description": "The leaderboard's slug from list_leaderboards."},
         "page": {"type": "integer", "minimum": 1, "description": "Page number (default 1)."}},
         "required": ["slug"], "additionalProperties": False}},
    {"name": "get_links", "title": "Get every record cross-referenced to one record",
     "description": "Every record on the site linked to one record, in any dataset, each with the rule that made the "
                    "link (an identifier such as an EIN or CIK: EXACT; the same name and state or city, the same street "
                    "address, a full name to a person page: FUZZY) and its furp.org URL, plus the record's interests "
                    "(NTEE code, topics, lobbying issues, industries) so records with the same interests can be found. "
                    "Kinds: org (EIN), person (id), contractor, fed (UEI), lda_client, lda_registrant, lda_lobbyist, "
                    "fec_committee, fec_donor, sec (CIK), sec_insider (CIK), formd (CIK), formd_party, adv (CRD), "
                    "adv_person, f5500_sponsor (EIN), op_payer, op_recipient, fara_registrant, biz (state:entity_id), "
                    "recallfirm, pat_assignee, pat_inventor, tm_owner, college (IPEDS unit id), ipo_company (CIK), "
                    "ipo_underwriter, sl_issuer. A shared name is not proof of the same person or organization.",
     "inputSchema": {"type": "object", "properties": {
         "kind": {"type": "string", "description": "The record kind (see the description)."},
         "key": {"type": "string", "description": "The record's id as its furp.org URL carries it."}},
         "required": ["kind", "key"], "additionalProperties": False}},
    {"name": "get_area", "title": "Get a place's census facts, current economy and FURP records",
     "description": "The `economy` field is the place's current economy from FRED (Federal Reserve Bank of St. Louis): "
                    "the latest monthly unemployment rate, per capita personal income, population, house price index and "
                    "GDP of its county or state, each with its period, one-, five- and ten-year changes and FRED series link. "
                    "A census area (state, county, city or census tract) by ZIP code, city and state, a county or place "
                    "name, or an NHGIS GISJOIN: population, median household income, poverty rate, median age, education, "
                    "housing and race (ACS 2020-2024 and the 2020 census via IPUMS NHGIS; each figure names its census "
                    "table), with the FURP records in the area: nonprofits and their revenue, the highest-paid people and "
                    "their pay as a multiple of the local median income, contractors, schools, lobbying clients, federal "
                    "recipients and more, each with its furp.org URL. Credit \"Data: IPUMS NHGIS\" with the citation.",
     "inputSchema": {"type": "object", "properties": {
         "zip": {"type": "string", "description": "A five-digit ZIP code (gives its county)."},
         "city": {"type": "string", "description": "A city or town name; pass state too."},
         "state": {"type": "string", "description": "Two-letter state code (or name)."},
         "query": {"type": "string", "description": "A place or county name (\"Cook County, Illinois\", \"Austin, TX\", \"Ohio\")."},
         "gisjoin": {"type": "string", "description": "An NHGIS GISJOIN from an earlier result (e.g. G4804530)."}},
         "additionalProperties": False}},
]
for _t in TOOLS:
    _t["annotations"] = {"title": _t["title"], **_RO}
_RUN = {
    "search": lambda a: api.search(a["query"], a.get("type") or "all", a.get("limit") or 10),
    "get_person": lambda a: api.person(str(a["person"])),
    "get_organization": lambda a: api.organization(str(a["organization"])),
    "list_datasets": lambda a: {"datasets": api.datasets(), "license": api.LICENSE},
    "search_dataset": lambda a: api.dataset_search(a["dataset"], a["query"], a.get("limit") or 10),
    "list_leaderboards": lambda a: api.leaderboards(),
    "get_leaderboard": lambda a: api.leaderboard(a["slug"], a.get("page") or 1),
    "get_links": lambda a: api.xlinks_view(a["kind"], str(a["key"])),
    "get_area": lambda a: __import__("app.census", fromlist=["x"]).api_area(a.get("query"), a.get("zip"), a.get("city"),
                                                                          a.get("state"), a.get("gisjoin")),
}


def _ok(i, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": i, "result": result}


def _err(i, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": i, "error": {"code": code, "message": message}}


def _call(name: str, args: dict) -> dict:
    """A tool result: the data as JSON text (for every client) and as structuredContent. Bad input or a record
    that isn't there is a tool error the model can read and correct, not a protocol error."""
    try:
        data = _RUN[name](args)
    except HTTPException as ex:
        msg = ex.detail if ex.status_code != 503 else "FURP is busy; try again in a few seconds."
        return {"content": [{"type": "text", "text": str(msg)}], "isError": True}
    except (KeyError, TypeError, ValueError) as ex:
        return {"content": [{"type": "text", "text": f"bad arguments: {type(ex).__name__}: {ex}"}], "isError": True}
    data = api.plain(data)
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str)}],
            "structuredContent": data, "isError": False}


async def handle(msg) -> dict | None:
    """One JSON-RPC message: its response, or None for a notification."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    i, method, params = msg.get("id"), msg["method"], msg.get("params") or {}
    if "id" not in msg:                                     # notifications (initialized, cancelled...): nothing back
        return None
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _ok(i, {"protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
                       "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER,
                       "instructions": INSTRUCTIONS})
    if method == "ping":
        return _ok(i, {})
    if method == "tools/list":
        return _ok(i, {"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        if name not in _RUN:
            return _err(i, -32602, f"Unknown tool: {name}")
        if not isinstance(args, dict):
            return _err(i, -32602, "arguments must be an object")
        try:
            return _ok(i, await run_in_threadpool(_call, name, args))
        except Exception:  # noqa: BLE001
            log.exception("mcp: %s failed", name)
            return _ok(i, {"content": [{"type": "text", "text": "FURP hit an error running this tool; try again "
                                                                   "shortly."}], "isError": True})
    if method in ("resources/list", "prompts/list"):
        return _ok(i, {method.split("/")[0]: []})
    return _err(i, -32601, f"Method not found: {method}")


@router.post("/mcp", include_in_schema=False)
async def mcp_post(request: Request):
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse(_err(None, -32700, "Parse error"), status_code=400, headers=CORS)
    if isinstance(body, list):
        if not body:
            return JSONResponse(_err(None, -32600, "Invalid Request"), status_code=400, headers=CORS)
        replies = [r for r in [await handle(m) for m in body[:20]] if r is not None]
        return JSONResponse(replies, headers=CORS) if replies else Response(status_code=202, headers=CORS)
    reply = await handle(body)
    return JSONResponse(reply, headers=CORS) if reply is not None else Response(status_code=202, headers=CORS)


@router.get("/mcp", include_in_schema=False)
async def mcp_get():
    # No server-initiated stream (the spec allows 405 here). People who open the URL get a pointer to the docs.
    return JSONResponse({"error": "This is FURP's MCP server: add https://furp.org/mcp to your assistant as a remote "
                                  "MCP server (streamable HTTP). Setup: https://furp.org/developers"},
                        status_code=405, headers={**CORS, "Allow": "POST, OPTIONS"})


@router.delete("/mcp", include_in_schema=False)
async def mcp_delete():
    return Response(status_code=405, headers={**CORS, "Allow": "POST, OPTIONS"})


@router.options("/mcp", include_in_schema=False)
async def mcp_options():
    return Response(status_code=204, headers=CORS)
