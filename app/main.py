"""np-explorer web app: nonprofit people search over IRS Form 990 e-filings."""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs
from contextlib import asynccontextmanager
from urllib.parse import quote, urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

import csv
import io

from app import analytics, ask, boards, contact, db, filing_view, funders, queries, sharecard, support
from app.cache import ttl_lru
from app.config import CORRECTIONS_EMAIL, GITHUB_URL, INFO_EMAIL, ROOT, SITE_URL
from app.fmt import FILTERS, current_year, propublica_filing
from app.names import normalize_org
from app.ratelimit import RateLimiter

log = logging.getLogger("np-explorer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.pool.open(wait=False)
    yield
    db.pool.close()


app = FastAPI(title="np-explorer", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
              lifespan=lifespan)
templates = Jinja2Templates(directory=ROOT / "templates")
templates.env.filters.update(FILTERS)
# Five example questions under the home page's search box (each runs when clicked).
NL_EXAMPLES_HOME = ["Who runs the Workforce Incubator Foundation?", "Highest-paid hospital executives in Ohio in 2022",
                    "Charities in Austin, Texas", "Who did the Gates Foundation give money to?",
                    "Compare Roger Goodell and Jamie Dimon"]
# What the search box can search. The first entry is the default; add more here.
SEARCH_TYPES = [("ask", "Plain text"), ("name", "Name"), ("firm", "Firm"), ("daf", "DAFs"), ("boards", "Boards")]
SEARCH_TYPE_KEYS = {k for k, _ in SEARCH_TYPES}

def _asset_version() -> str:
    """Changes whenever a stylesheet or script changes, so browsers drop their cached copy."""
    import hashlib
    h = hashlib.sha1()
    for name in ("style.css", "site.js"):
        h.update((ROOT / "static" / name).read_bytes())
    return h.hexdigest()[:10]


templates.env.globals.update(asset_version=_asset_version(), site_url=SITE_URL, github_url=GITHUB_URL, info_email=INFO_EMAIL,
                             corrections_email=CORRECTIONS_EMAIL,
                             coverage=queries.coverage, propublica_filing=propublica_filing, current_year=current_year,
                             search_types=SEARCH_TYPES, boards=boards, nl_examples=NL_EXAMPLES_HOME)
# nginx serves /static in production; this is for local runs.
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
limiter = RateLimiter()

STATIC_PAGES = {"/": "index.html", "/about": "about.html", "/data": "data.html", "/privacy": "privacy.html",
                "/support": "support.html"}
_STATE = re.compile(r"^[A-Za-z]{2}$")
_ORG_SUFFIX = re.compile(r"\s+(inc|incorporated|corp|corporation|co|company|llc|ltd|foundation|fund|trust|"
                         r"association|assn|society)$")
_EIN = re.compile(r"^\s*\d{2}-?\d{7}\s*$")


def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _int(v, lo=None, hi=None):
    try:
        n = int(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    if lo is not None and n < lo or hi is not None and n > hi:
        return None
    return n


def place_filters(request: Request) -> dict:
    """State and city for firm and DAF search (the search box's "More options")."""
    qp = request.query_params
    state = (qp.get("state") or "").strip()
    city = re.sub(r"[^A-Za-z .'-]", "", qp.get("city") or "").strip()[:60]
    return {"state": state.upper() if _STATE.match(state) else None, "city": city or None}


def search_filters(request: Request) -> dict:
    qp = request.query_params
    state = (qp.get("state") or "").strip()
    return {
        "state": state.upper() if _STATE.match(state) else None,
        "year_from": _int(qp.get("year_from"), 1990, 2100),
        "year_to": _int(qp.get("year_to"), 1990, 2100),
        "title": (qp.get("title") or "").strip()[:100] or None,
        "min_comp": _int(qp.get("min_comp"), 0),
        "org": (qp.get("org") or "").strip()[:100] or None,
    }


BAND_NAMES = {1: "exact", 2: "close", 3: "other"}

# Search runs its four parts (people, institutions, contractors, organizations) at once.
_search_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="search")


# Limits that keep one visitor from paging through the whole index.
MAX_QUERY = 100      # characters
MAX_PAGE = 20        # 50 per page: the first 1,000 results
MAX_BOARD_PAGE = 200
CSV_MAX_ROWS = 10_000


def run_searches(q: str, filters: dict, page: int):
    return _cached_searches(q, tuple(sorted(filters.items())), page)


@ttl_lru()
def _cached_searches(q: str, filters: tuple, page: int):
    filters = dict(filters)
    people = _search_pool.submit(queries.search_people, q, filters, page)
    if page > 1:
        return people.result(), [], [], []
    others = [_search_pool.submit(fn, q) for fn in
              (queries.search_institutions, queries.search_contractors, queries.search_orgs)]
    return (people.result(), *(f.result() for f in others))


cached_person = ttl_lru()(queries.person)
cached_firms = ttl_lru()(queries.search_firms)
cached_org = ttl_lru()(queries.org)


# --- pages --------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/about", response_class=HTMLResponse)
@app.get("/data", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
def static_page(request: Request):
    return render(request, STATIC_PAGES[request.url.path])


@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, canceled: int = 0, error: str | None = None, status_code: int = 200):
    return render(request, "support.html", status_code=status_code, enabled=support.enabled(),
                  monthly=support.MONTHLY, once=support.ONCE, portal_url=support.PORTAL_URL,
                  canceled=bool(canceled), error=error)


support_limit = contact.HourlyLimit(30)


@app.post("/support/checkout")
async def support_checkout(request: Request):
    """A Support button: create a Stripe Checkout Session and send the browser to it."""
    body = (await request.body())[:2000].decode("utf-8", "replace")
    form = {k: v[0] for k, v in parse_qs(body).items()}
    kind = form.get("kind", "")
    amount = support.valid(kind, form.get("amount"))
    if not support.enabled() or amount is None:
        return RedirectResponse("/support", status_code=303)
    if not support_limit.allow(_client_ip(request)):
        return support_page(request, error="Too many attempts from your connection. Please try again later.",
                            status_code=429)
    try:
        url = await run_in_threadpool(support.checkout_url, kind, amount)
    except Exception:  # noqa: BLE001 - Stripe down or not set up: say so, never a 500
        log.exception("support: creating a checkout session")
        return support_page(request, error="Payments are not available right now. Please try again later, or "
                                           "get in touch below.", status_code=502)
    analytics.event(request, "support_checkout", {"kind": kind, "amount": amount})
    return RedirectResponse(url, status_code=303)


@app.get("/support/thanks", response_class=HTMLResponse)
def support_thanks(request: Request):
    return render(request, "support_thanks.html", portal_url=support.PORTAL_URL)


@app.post("/stripe/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    """Stripe events for the Support page, verified with the webhook signing secret."""
    payload = await request.body()
    try:
        await run_in_threadpool(support.handle_webhook, payload, request.headers.get("stripe-signature"))
    except support.SupportError:
        log.error("stripe webhook: STRIPE_WEBHOOK_SECRET is not set")
        return JSONResponse({"error": "not configured"}, status_code=503)
    except Exception as e:  # noqa: BLE001 - bad signature or payload
        log.warning("stripe webhook rejected: %s", type(e).__name__)
        return JSONResponse({"error": "invalid"}, status_code=400)
    return JSONResponse({"received": True})


# --- contact form ---------------------------------------------------------------

contact_limit = contact.HourlyLimit()


def _contact_form(request: Request, form: dict | None = None, errors: list | None = None, status_code: int = 200):
    return render(request, "contact.html", status_code=status_code, sent=False, failed=False,
                  form=form or {}, errors=errors or [], topics=contact.TOPICS, token=contact.issue_token())


@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request, sent: int = 0, topic: str = ""):
    if sent:
        return render(request, "contact.html", sent=True, failed=False, form={}, errors=[])
    return _contact_form(request, {"topic": topic} if topic in contact.TOPICS else None)


@app.post("/contact", response_class=HTMLResponse)
async def contact_submit(request: Request):
    body = (await request.body())[:40000].decode("utf-8", "replace")
    raw = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}
    if contact.is_bot(raw):
        # Honeypot or too fast: drop it, but look like it worked.
        return RedirectResponse("/contact?sent=1", status_code=303)
    form, errors = contact.validate(raw)
    if errors:
        return _contact_form(request, form, errors, status_code=400)
    ip = _client_ip(request)
    if not contact_limit.allow(ip):
        return _contact_form(request, form, ["Too many messages from your connection. Please try again in an hour."],
                             status_code=429)
    if not await run_in_threadpool(contact.send, form, ip):
        return render(request, "contact.html", status_code=502, sent=False, failed=True, form={}, errors=[])
    analytics.event(request, "contact_submit", {"topic": form["topic"]})
    return RedirectResponse("/contact?sent=1", status_code=303)


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", type: str = "ask", page: int = Query(1, ge=1)):
    t0 = time.monotonic()
    raw = q.strip()[:ask.MAX_QUESTION]
    q, page = q.strip()[:MAX_QUERY], min(page, MAX_PAGE)
    nl_note = nl_parsed = None
    chosen = type if type in ("ask", "name") else "ask"   # which of the two people searches to show as selected
    # Usage stats: first pages only; /ask records its own fallbacks before redirecting here with nl=0.
    counted = page == 1 and request.query_params.get("nl") != "0"
    # Plain text (the default): a sentence goes through natural-language search; a plain name
    # never leaves the server. Name always searches names directly.
    if type == "ask" and page == 1 and request.query_params.get("nl") != "0" and raw \
            and not ask.is_plain_name(raw) and not _EIN.match(raw):
        resp, parsed = nl_search(request, raw)
        if resp:
            return resp
        nl_parsed = parsed
        nl_note = parsed.get("reason") if parsed.get("intent") == "unknown" and parsed.get("how") != "skipped" else None
        type = "name"
    nl_note = nl_note or request.query_params.get("note") or None
    place = place_filters(request)
    if not q and not (type in ("firm", "daf") and any(place.values())):
        return RedirectResponse("/", status_code=302)
    # An EIN (12-3456789 or 123456789) goes straight to that organization.
    if _EIN.match(q):
        ein = re.sub(r"\D", "", q)
        if queries.org_exists(ein):
            return RedirectResponse(f"/org/{ein}", status_code=302)
    if type not in SEARCH_TYPE_KEYS:
        type = SEARCH_TYPES[0][0]
    if type == "boards":
        if counted:
            analytics.search(request, q, "boards", ms=(time.monotonic() - t0) * 1000)
        return RedirectResponse("/boards?" + urlencode({"q": q}), status_code=302)
    if type in ("firm", "daf"):
        firms = cached_firms(q, page, daf_only=type == "daf", **place)
        if counted:
            analytics.search(request, q or "(place only)", type, results=firms.get("total", len(firms.get("rows") or [])),
                             ms=(time.monotonic() - t0) * 1000)
        keep = {"q": q, "type": type, **{k: v for k, v in place.items() if v}}
        return render(request, "search_firms.html", q=q, page=page, search_type=type, place=place, **firms,
                      page_url=lambda p: "/search?" + urlencode({**keep, "page": p}))
    filters = search_filters(request)
    people, institutions, contractors, orgs = run_searches(q, filters, page)
    if counted:
        fell_back = bool(nl_parsed) and nl_parsed.get("intent") != "plain"
        analytics.search(request, q, "nl" if fell_back else "plain" if chosen == "ask" else "name",
                         intent=nl_parsed.get("intent") if fell_back else None,
                         results=people["total"] + len(orgs) + len(contractors) + len(institutions),
                         fallback=fell_back, reason=nl_parsed.get("reason") if fell_back else None,
                         ms=(time.monotonic() - t0) * 1000)
    # Organizations whose name is what was typed (give or take Inc, Foundation...) go above the people.
    typed = normalize_org(q)
    named_orgs = [o for o in orgs if _ORG_SUFFIX.sub("", o.get("name_norm") or normalize_org(o["name"] or "")) == typed
                  or (o.get("name_norm") or "") == typed]
    on_boards = {
        "person": boards.counts("person", [r["id"] for r in people["results"]]),
        "org": boards.counts("org", [o["ein"] for o in orgs]),
        "vendor": boards.counts("vendor", [c["name_norm"] for c in contractors if c.get("name_norm")]),
    }
    base = {"q": q, "type": chosen, **{k: v for k, v in filters.items() if v is not None}}
    pages = min(MAX_PAGE, max(1, (people["total"] + queries.PAGE - 1) // queries.PAGE))
    return render(request, "search.html", q=q, page=page, pages=pages, filters=filters, people=people, search_type=chosen,
                  institutions=institutions, contractors=contractors, orgs=orgs, on_boards=on_boards,
                  named_orgs=named_orgs, nl_note=nl_note,
                  page_url=lambda p: "/search?" + urlencode({**base, "page": p}),
                  dym_url=lambda name: "/search?" + urlencode({"q": name}))


# --- leaderboards ---------------------------------------------------------------

def board_filters(request: Request) -> dict:
    qp = request.query_params
    state = (qp.get("state") or "").strip()
    form = (qp.get("form") or "").strip().upper().replace("-", "")
    return {"year": _int(qp.get("year"), 1990, 2100), "form": form if form in boards.FORMS else None,
            "state": state.upper() if _STATE.match(state) else None,
            "all": 1 if qp.get("all") == "1" else None}   # per-organization boards: every organization-year


def _board_or_404(slug: str) -> boards.Board:
    board = boards.get(slug)
    if not board:
        raise HTTPException(404)
    return board


@app.get("/boards", response_class=HTMLResponse)
def boards_index(request: Request, q: str = ""):
    q = q.strip()[:MAX_QUERY]
    meta = boards.meta()
    tops = {}
    for b in boards.visible():
        try:
            tops[b.slug] = boards.top(b, 3) if b.slug in meta else []
        except Exception:  # noqa: BLE001 - view not built yet
            tops[b.slug] = []
    return render(request, "boards.html", q=q, results=boards.search(q) if q else None, meta=meta, tops=tops)


def _png_response(board: boards.Board) -> Response:
    meta = boards.meta().get(board.slug)
    rows = boards.top(board, 10) if meta else []
    return Response(sharecard.card(board, rows, meta), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/boards/{slug}.png")
def board_png(slug: str):
    return _png_response(_board_or_404(slug))


CSV_FIELDS = ["rank", "subject_name", "subject_url", "subject_kind", "match", "org_name", "ein", "state",
              "form_type", "tax_year", "coverage_window", "filing_url", "value"]


def _row_out(board: boards.Board, r: dict, window: str) -> dict:
    out = {k: r.get(k) for k in CSV_FIELDS}
    out["subject_url"] = SITE_URL + r["subject_url"]
    out["filing_url"] = f"{SITE_URL}/filing/{r['filing_id']}" if r.get("filing_id") else None
    out["coverage_window"] = window
    for c in board.columns:
        out[c.key] = r.get(c.key)
    return out


@app.get("/boards/{slug}.csv")
def board_csv(request: Request, slug: str):
    board = _board_or_404(slug)
    window = boards.window(boards.meta().get(board.slug))
    fields = CSV_FIELDS + [c.key for c in board.columns]

    def gen():
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in boards.all_rows(board, board_filters(request), limit=CSV_MAX_ROWS):
            row = _row_out(board, r, window)
            row = {k: ("; ".join(map(str, v)) if isinstance(v, list) else v) for k, v in row.items()}
            w.writerow(row)
            if buf.tell() > 65536:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        yield buf.getvalue()

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{board.slug}.csv"'})


@app.get("/boards/{slug}", response_class=HTMLResponse)
def board_page(request: Request, slug: str, page: int = Query(1, ge=1)):
    board, page = _board_or_404(slug), min(page, MAX_BOARD_PAGE)
    filters = board_filters(request)
    meta = boards.meta().get(board.slug)
    data = boards.page(board, filters, page) if meta else {"rows": [], "total": 0}
    top_row = data["rows"][0] if data["rows"] and page == 1 and not any(filters.values()) else \
        (boards.top(board, 1) or [None])[0] if meta else None
    base = {k: v for k, v in filters.items() if v}
    pages = min(MAX_BOARD_PAGE, max(1, (data["total"] + board.per_page - 1) // board.per_page))
    per_org = boards.per_org_view(board, filters)
    toggle = {k: v for k, v in base.items() if k != "all"} | ({"all": 1} if per_org else {})
    subject = f"Leaderboard error: {board.title} ({SITE_URL}/boards/{board.slug})"
    report = f"mailto:{CORRECTIONS_EMAIL}?subject={quote(subject)}&body={quote('Which row looks wrong, and why?')}"
    return render(request, "board.html", board=board, meta=meta, filters=filters, page=page, pages=pages,
                  window=boards.window(meta), years=boards.years(board), report_url=report,
                  finding=boards.finding(board, top_row), filtered=bool({k for k in base if k != "all"}), **data,
                  per_org=per_org, toggle_url=f"/boards/{board.slug}" + ("?" + urlencode(toggle) if toggle else ""),
                  group=boards.GROUPS.get(board.group), group_boards=boards.group_members(board.group),
                  letters=boards.letters(board) if board.alphabetical and meta and not base else [],
                  page_url=lambda p: f"/boards/{board.slug}?" + urlencode({**base, "page": p}),
                  csv_url=f"/boards/{board.slug}.csv" + ("?" + urlencode(base) if base else ""))


# --- natural-language search ---------------------------------------------------------

NL_EXAMPLES = NL_EXAMPLES_HOME
NL_FIELDS = {"intent", "name", "state", "city", "daf_only", "person_a", "person_b", "org", "topic", "scope", "keywords",
             "ntee", "year", "title_contains", "limit", "board", "per_person", "include_related"}


def _intent_from_form(qp) -> dict:
    """The "edit" form: structured fields straight to the validator, no model call."""
    args = {}
    for k in NL_FIELDS - {"intent"}:
        v = (qp.get(k) or "").strip()
        if not v:
            continue
        args[k] = (int(v) if k in ("year", "limit") and v.isdigit()
                   else (v == "1") if k in ("daf_only", "per_person", "include_related") else v)
    return ask.validate(qp.get("intent") or "", args)


@ttl_lru()
def _cached_nl_run(intent: tuple):
    """Results for an intent, kept 60 seconds like the other pages (repeat questions skip the database)."""
    return ask.run(dict(intent))


def nl_search(request: Request, q: str, structured: bool = False):
    """Run a natural-language (or edited, structured) search. Returns a response, or None to fall back."""
    t0 = time.monotonic()
    if structured:
        parsed = {**_intent_from_form(request.query_params), "how": "edited"}
    else:
        parsed = ask.parse(q, _client_ip(request))
    if parsed["intent"] in ("plain", "unknown"):
        ask.record((time.monotonic() - t0) * 1000, parsed)
        return None, parsed
    try:
        result = _cached_nl_run(tuple(sorted((k, v) for k, v in parsed.items() if k not in ("how", "parse_ms"))))
    except Exception:  # noqa: BLE001 - a bad intent is a fallback, never a 500
        log.exception("nl: running intent %s", parsed.get("intent"))
        return None, {**parsed, "intent": "unknown", "reason": "error"}
    if result["kind"] == "none":
        ask.record((time.monotonic() - t0) * 1000, {**parsed, "how": parsed["how"] + "+nomatch"})
        return None, {**parsed, "intent": "unknown", "reason": "no match"}
    resp = render(request, "search_nl.html", q=q, intent=parsed, result=result, reading=ask.describe(parsed),
                  edit_url=ask.edit_url, categories=[("", "Any"), (ask.HIGHER_ED, "Higher education")]
                  + [(k, f"{v} ({k})") for k, v in ask.NTEE_GROUPS.items()], category_label=ask.category_label,
                  topics=["finances", "spending", "grants_made", "grants_received", "daf"],
                  intents=[t["name"] for t in ask.TOOLS if t["name"] != "unknown"], examples=NL_EXAMPLES)
    ask.record((time.monotonic() - t0) * 1000, parsed)
    analytics.search(request, q or "(edited search)", "edit" if structured else "nl", intent=parsed.get("intent"),
                     results=result.get("total", len(result.get("rows") or [])) if result.get("rows") is not None else 1,
                     ms=(time.monotonic() - t0) * 1000)
    return resp, parsed


@app.get("/ask", response_class=HTMLResponse)
def ask_page(request: Request, q: str = ""):
    q = q.strip()[:ask.MAX_QUESTION]
    if q or request.query_params.get("intent"):
        resp, parsed = nl_search(request, q, structured=bool(request.query_params.get("intent")))
        if resp:
            return resp
        if q:
            analytics.search(request, q, "nl", intent=parsed.get("intent"), fallback=True, reason=parsed.get("reason"))
            return RedirectResponse("/search?" + urlencode({"q": q[:MAX_QUERY], "nl": "0", "note": parsed.get("reason")
                                                            if parsed["intent"] == "unknown" else ""}), status_code=302)
    return render(request, "ask.html", q=q, examples=NL_EXAMPLES, enabled=ask.enabled())


@app.get("/contractors", response_class=HTMLResponse)
def contractor_search(request: Request, q: str = "", page: int = Query(1, ge=1)):
    q, page = q.strip()[:MAX_QUERY], min(page, MAX_PAGE)
    rows = queries.search_contractors(q, limit=50, offset=(page - 1) * 50) if q else []
    return render(request, "contractors.html", q=q, rows=rows, page=page,
                  page_url=lambda p: "/contractors?" + urlencode({"q": q, "page": p}))


@app.get("/person/{cluster_id}", response_class=HTMLResponse)
def person_page(request: Request, cluster_id: int, year: str = "", fragment: int = 0, all: int = 0):
    data = cached_person(cluster_id, full=not fragment, year=_int(year, 1990, 2100), show_all=bool(all))
    if not data:
        moved = queries.resolve_person(cluster_id)
        if moved and moved != cluster_id:
            q = request.url.query
            return RedirectResponse(f"/person/{moved}" + (f"?{q}" if q else ""), status_code=301)
        raise HTTPException(404)
    # The active tab: a year the person appears in, otherwise "all".
    y = _int(year)
    active = y if y in data["years"] else "all"
    c = data["cluster"]
    if fragment:
        # The search-results popup: header and year tabs only, no page chrome.
        resp = render(request, "_person_tabs.html", active=active, fragment=True, **data)
        resp.headers["Link"] = f'<{SITE_URL}/person/{cluster_id}>; rel="canonical"'
        resp.headers["Cache-Control"] = "private, max-age=300"
        return resp
    subject = f"Not the same person: {c['display_name']} ({SITE_URL}/person/{cluster_id})"
    report = f"mailto:{CORRECTIONS_EMAIL}?subject={quote(subject)}&body={quote('Which rows look wrong, and why?')}"
    return render(request, "person.html", report_url=report, active=active, fragment=False, **data)


@app.get("/org/{ein}", response_class=HTMLResponse)
def org_page(request: Request, ein: str):
    ein = re.sub(r"\D", "", ein).zfill(9)
    data = cached_org(ein)
    if not data:
        raise HTTPException(404)
    everyone = queries.org_people([ein]).get(ein, [])
    return render(request, "org.html", everyone=everyone, **data, **_org_funding(ein))


def _org_funding(ein: str) -> dict:
    """Funders, similar organizations and who funds them, for the org page. Never fails the page."""
    out = {"funders_ready": funders_ready(), "fu": None, "sim": None, "like": None,
           "coverage_years": _coverage_years()}
    if not out["funders_ready"]:
        return out
    try:
        out["fu"] = funders.funders(ein)
        out["sim"] = funders.similar(ein, funders.SIMILAR_MAX)
        out["like"] = funders.funders_like(ein, funders.FUNDERS_LIKE_SHOWN)
    except Exception:  # noqa: BLE001
        log.exception("org page: funders sections for %s", ein)
    return out


GRANT_CSV_FIELDS = ["tax_year", "kind", "recipient_name", "recipient_ein", "city", "state", "amount", "cash_amount",
                    "noncash_amount", "purpose", "foundation_status", "relationship", "source", "filing_url"]


def _grants_year_or_404(ein: str, year: int):
    ein = re.sub(r"\D", "", ein).zfill(9)
    if not queries.org_exists(ein):
        raise HTTPException(404)
    return ein, queries.grants_year(ein, year)


# --- funders, similar organizations, topics -------------------------------------------

@ttl_lru(ttl=60)
def funders_ready() -> bool:
    return funders.available()


def _org_or_404(ein: str) -> dict:
    ein = re.sub(r"\D", "", ein).zfill(9)
    o = queries.org_name(ein)
    if not o:
        raise HTTPException(404)
    return {"ein": ein, **o} if isinstance(o, dict) else {"ein": ein, "name": o}


@app.get("/org/{ein}/funders", response_class=HTMLResponse)
def org_funders_page(request: Request, ein: str, page: int = Query(1, ge=1)):
    o = _org_or_404(ein)
    ready = funders_ready()
    fu = funders.funders(o["ein"], 100, (min(page, 500) - 1) * 100) if ready else {"rows": [], "n_total": 0}
    pages = max(1, (fu["n_total"] + 99) // 100)
    return render(request, "org_funders.html", o=o, ready=ready, fu=fu, page=page, pages=pages,
                  coverage_years=_coverage_years())


@app.get("/org/{ein}/funders.csv")
def org_funders_csv(ein: str):
    o = _org_or_404(ein)
    rows = funders.funders(o["ein"], None)["rows"] if funders_ready() else []
    buf = io.StringIO()
    cols = ["grantor_ein", "grantor_name", "grantor_kind", "match", "fuzzy_names", "years", "n_grants", "total",
            "last_year", "last_amount"]
    w = csv.writer(buf)
    w.writerow(cols + ["grantor_url"])
    for r in rows:
        w.writerow([("; ".join(map(str, r[c])) if isinstance(r[c], list) else r[c]) for c in cols]
                   + [f"{SITE_URL}/org/{r['grantor_ein']}"])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=funders-{o['ein']}.csv"})


@app.get("/org/{ein}/funders/{grantor}", response_class=HTMLResponse)
def org_funder_grants(request: Request, ein: str, grantor: str):
    o = _org_or_404(ein)
    grantor = re.sub(r"\D", "", grantor).zfill(9)
    resp = render(request, "_funder_grants.html", grants=funders.funder_grants(o["ein"], grantor) if funders_ready() else [])
    resp.headers["Link"] = f'<{SITE_URL}/org/{o["ein"]}/funders>; rel="canonical"'
    return resp


@app.get("/org/{ein}/similar", response_class=HTMLResponse)
def org_similar_page(request: Request, ein: str, state: int = 0):
    o = _org_or_404(ein)
    ready = funders_ready()
    sim = funders.similar(o["ein"], funders.SIMILAR_MAX, state_only=bool(state)) if ready else {"me": None, "rows": []}
    return render(request, "org_similar.html", o=o, ready=ready, sim=sim, state_only=bool(state))


@app.get("/org/{ein}/funders-like", response_class=HTMLResponse)
def org_funders_like_page(request: Request, ein: str):
    o = _org_or_404(ein)
    ready = funders_ready()
    like = funders.funders_like(o["ein"]) if ready else {"rows": [], "n_similar": 0}
    return render(request, "org_funders_like.html", o=o, ready=ready, like=like)


@app.get("/topics", response_class=HTMLResponse)
def topics_page(request: Request, q: str = "", state: str = "", ntee: str = ""):
    q = q.strip()[:200]
    st = state.upper() if _STATE.match(state or "") else None
    code = ntee.upper()[:3] if re.fullmatch(r"[A-Za-z][0-9A-Za-z]{0,2}", ntee or "") else None
    ready = funders_ready()
    tf = funders.topic_funders(q, st, code) if ready and q else None
    t = tf["topic"] if tf else {"words": funders.topic_words(q), "rows": [], "codes": [], "total": 0}
    return render(request, "topics.html", q=q, ready=ready, t=t, tf=tf["rows"] if tf else None)


@ttl_lru(ttl=900)
def _coverage_years() -> str:
    try:
        c = queries.coverage()
        return f"{c['first']} to {c['last']}" if c and c.get("first") else ""
    except Exception:  # noqa: BLE001
        return ""


@app.get("/org/{ein}/grants/{year}.csv")
def org_grants_csv(ein: str, year: int):
    ein, rows = _grants_year_or_404(ein, year)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=GRANT_CSV_FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({**r, "filing_url": f"{SITE_URL}/filing/{r['fid']}"})
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="grants-{ein}-{year}.csv"'})


@app.get("/org/{ein}/grants/{year}", response_class=HTMLResponse)
def org_grants_year(request: Request, ein: str, year: int, fragment: int = 0):
    """One tax year's grants: an HTML fragment when an org page opens that year, else a full page."""
    ein, rows = _grants_year_or_404(ein, year)
    org = queries.org_name(ein)
    resp = render(request, "_grants_year.html" if fragment else "grants_year.html", ein=ein, year=year, rows=rows,
                  org=org)
    if fragment:
        resp.headers["Link"] = f'<{SITE_URL}/org/{ein}/grants/{year}>; rel="canonical"'
    return resp


@app.get("/contractor/{cid}", response_class=HTMLResponse)
def contractor_page(request: Request, cid: int):
    data = queries.contractor(cid)
    if not data:
        raise HTTPException(404)
    c = data["contractor"]
    terms = " ".join(x for x in (c["name_raw"], c["city"], c["state"]) if x)
    return render(request, "contractor.html", find_url="https://duckduckgo.com/?q=" + quote(terms), **data)


@app.get("/filing/{fid}", response_class=HTMLResponse)
def filing_page(request: Request, fid: int):
    f = queries.filing(fid)
    if not f:
        raise HTTPException(404)
    try:
        sections = filing_view.render(filing_view.load_xml(f["xml_path"]))
    except FileNotFoundError:
        sections = None
    return render(request, "filing.html", f=f, sections=sections, propublica_url=propublica_filing(f["ein"], f["object_id"]))


@app.get("/filing/{fid}/xml")
def filing_xml(fid: int):
    f = queries.filing(fid)
    if not f:
        raise HTTPException(404)
    try:
        xml = filing_view.load_xml(f["xml_path"])
    except FileNotFoundError:
        raise HTTPException(404)
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{f["object_id"]}_public.xml"'})


# --- JSON API -----------------------------------------------------------------

def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def usage_stats(request: Request, call_next):
    """Usage stats for the daily report, production only (app/analytics.py)."""
    return await analytics.middleware(request, call_next)


@app.post("/e", include_in_schema=False)
async def usage_beacon(request: Request):
    """Client-side actions for the usage stats (Copy table). Anything not on the list is ignored."""
    name = (await request.body())[:40].decode("ascii", "ignore").strip()
    if name in analytics.BEACON_EVENTS:
        analytics.event(request, name)
    return Response(status_code=204)


@app.middleware("http")
async def api_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/docs") \
            and request.url.path != "/api/openapi.json":
        if not limiter.allow(_client_ip(request)):
            return JSONResponse({"error": "rate limited; slow down to about one request a second"},
                                status_code=429, headers={"Retry-After": "5"})
    return await call_next(request)


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if type(v).__name__ == "Decimal":
        return float(v)
    return v


@app.get("/api/search")
def api_search(request: Request, q: str = "", type: str = "name", page: int = Query(1, ge=1)):
    q, page = q.strip()[:MAX_QUERY], min(page, MAX_PAGE)
    if type in ("firm", "daf"):
        place = place_filters(request)
        return _jsonable({"q": q, "type": type, "page": page, "per_page": queries.FIRM_PAGE, **place,
                          **cached_firms(q, page, daf_only=type == "daf", **place)})
    people, institutions, contractors, orgs = run_searches(q, search_filters(request), page)
    for r in people["results"]:
        r["match"] = BAND_NAMES.get(r.get("band"), "other")
    return _jsonable({"q": q, "page": page, "per_page": queries.PAGE, **people, "institutions": institutions,
                      "contractors": contractors, "organizations": orgs})


@app.get("/api/person/{cluster_id}")
def api_person(cluster_id: int):
    data = cached_person(cluster_id)
    data = dict(data) if data else data
    if not data:
        moved = queries.resolve_person(cluster_id)
        if moved and moved != cluster_id:
            return RedirectResponse(f"/api/person/{moved}", status_code=301)
        raise HTTPException(404)
    data.pop("org_names", None)
    return _jsonable(data)


@app.get("/api/org/{ein}")
def api_org(ein: str):
    data = cached_org(re.sub(r"\D", "", ein).zfill(9))
    if not data:
        raise HTTPException(404)
    return _jsonable(data)


@app.get("/api/boards")
def api_boards():
    meta = boards.meta()
    return _jsonable({"boards": [{
        "slug": b.slug, "title": b.title, "subtitle": b.subtitle, "definition": b.definition,
        "formula": b.formula, "notes": b.notes, "coverage_window": boards.window(meta.get(b.slug)),
        "rows": (meta.get(b.slug) or {}).get("n_rows"), "refreshed_at": (meta.get(b.slug) or {}).get("refreshed_at"),
        "url": f"{SITE_URL}/boards/{b.slug}", "csv": f"{SITE_URL}/boards/{b.slug}.csv"} for b in boards.visible()],
        "note": boards.STANDING_LINE})


@app.get("/api/boards/{slug}")
def api_board(request: Request, slug: str, page: int = Query(1, ge=1)):
    board, page = _board_or_404(slug), min(page, MAX_BOARD_PAGE)
    meta = boards.meta().get(board.slug)
    window = boards.window(meta)
    data = boards.page(board, board_filters(request), page) if meta else {"rows": [], "total": 0}
    return _jsonable({"slug": board.slug, "title": board.title, "subtitle": board.subtitle,
                      "definition": board.definition, "formula": board.formula, "notes": board.notes,
                      "note": boards.STANDING_LINE, "coverage_window": window, "page": page,
                      "per_page": board.per_page, "total": data["total"],
                      "value": {"key": "value", "label": board.value.label},
                      "rows": [_row_out(board, r, window) for r in data["rows"]]})


# --- errors -------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 404:
        return render(request, "404.html", status_code=404)
    return render(request, "500.html", status_code=exc.status_code)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "server error"}, status_code=500)
    return render(request, "500.html", status_code=500)
