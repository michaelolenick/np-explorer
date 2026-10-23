"""np-explorer web app: furp.org's public data explorer (IRS Form 990 e-filings, public payrolls and more)."""

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

from app import analytics, ask, boards, colleges, contact, db, filing_view, funders, queries, sharecard, support
from app import cite, csvfoot  # source credit: Cite this panel, CSV footers
from app.cache import ttl_lru
from app.config import GA_MEASUREMENT_ID, CORRECTIONS_EMAIL, GITHUB_URL, INFO_EMAIL, ROOT, SITE_URL
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
# A worker keeps the templates it loaded until it restarts: during a deploy's rolling restart, old workers must not
# pick up new templates that call globals only the new code defines (2026-10-22).
templates.env.auto_reload = False
templates.env.filters.update(FILTERS)
cite.install(templates.env)
# Five example questions under the home page's search box (each runs when clicked).
NL_EXAMPLES_HOME = ["Who runs the Workforce Incubator Foundation?", "Highest-paid hospital executives in Ohio in 2022",
                    "Charities in Austin, Texas", "Who did the Gates Foundation give money to?",
                    "Compare Roger Goodell and Jamie Dimon"]
# What the search box can search. The first entry is the default; add more here.
SEARCH_TYPES = [("ask", "Plain text"), ("name", "Name"), ("firm", "Firm"), ("daf", "DAFs"), ("boards", "Boards")]
SEARCH_TYPE_KEYS = {k for k, _ in SEARCH_TYPES}

def _asset_version() -> str:
    """Changes whenever a stylesheet, script or icon changes, so browsers drop their cached copy."""
    import hashlib
    h = hashlib.sha1()
    for name in ("style.css", "site.js", "nav.js", "favicon.svg", "favicon.ico", "apple-touch-icon.png"):
        h.update((ROOT / "static" / name).read_bytes())
    return h.hexdigest()[:10]


templates.env.globals.update(evidence_text=colleges.evidence_text, colleges=colleges)
from app import slugs as _slugs  # noqa: E402

templates.env.globals["entity_path"] = _slugs.canonical
from app import seo as _seo  # noqa: E402

templates.env.globals["seo_ld"] = _seo.ld
templates.env.globals["ideas_token"] = contact.issue_token     # the daily-finds signup boxes (app/reporters.py)   # readable entity URLs (app/slugs.py)
templates.env.globals.update(ga_id=GA_MEASUREMENT_ID)   # Google Analytics tag in base.html (prod only)
templates.env.globals.update(asset_version=_asset_version(), site_url=SITE_URL, github_url=GITHUB_URL, info_email=INFO_EMAIL,
                             corrections_email=CORRECTIONS_EMAIL,
                             coverage=queries.coverage, propublica_filing=propublica_filing, current_year=current_year,
                             search_types=SEARCH_TYPES, boards=boards, nl_examples=NL_EXAMPLES_HOME)
# nginx serves /static in production; this is for local runs.
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
limiter = RateLimiter()

STATIC_PAGES = {"/": "index.html", "/about": "about.html", "/data": "data.html", "/privacy": "privacy.html",
                "/terms": "terms.html", "/support": "support.html"}
_STATE = re.compile(r"^[A-Za-z]{2}$")
_ORG_SUFFIX = re.compile(r"\s+(inc|incorporated|corp|corporation|co|company|llc|ltd|foundation|fund|trust|"
                         r"association|assn|society)$")
_EIN = re.compile(r"^\s*\d{2}-?\d{7}\s*$")


# Query parameters that never belong in a shared or canonical address: ad/referral tracking and one-time notices.
QUERY_DROP = {"fbclid", "gclid", "msclkid", "dclid", "mc_cid", "mc_eid", "ref", "canceled", "sent", "error"}
# Parameters that only re-order or re-arrange the same rows: kept in shared links, left out of the canonical link
# so search engines see one page, not one per sort order.
QUERY_PRESENTATION = {"sort", "dir", "view", "more", "seen"}


def page_queries(request: Request) -> tuple[str, str]:
    """(share_query, canonical_query) for the page being rendered: the request's own query string without
    tracking or one-time parameters and blanks; the canonical one also without presentation parameters."""
    items = [(k, v) for k, v in request.query_params.multi_items()
             if v.strip() and k not in QUERY_DROP and not k.startswith("utm_")]
    return urlencode(items), urlencode([(k, v) for k, v in items if k not in QUERY_PRESENTATION])


def render(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    share, canonical = page_queries(request)
    ctx.setdefault("share_query", share)
    ctx.setdefault("canonical_query", canonical)
    resp = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    if status_code == 200 and not name.startswith("_"):
        from app import slugs
        body = resp.body.decode("utf-8")
        new = slugs.rewrite_links(body)
        if new != body:
            resp.body = new.encode("utf-8")
            resp.headers["content-length"] = str(len(resp.body))
    return resp


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
        return people.result(), [], [], [], []
    others = [_search_pool.submit(fn, q) for fn in
              (queries.search_institutions, queries.search_contractors, queries.search_orgs, _schools)]
    return (people.result(), *(f.result() for f in others))


def _alias(q: str) -> dict | None:
    try:
        from app import aliases
        return aliases.lookup(q)
    except Exception:  # noqa: BLE001 - an extra; never fail a search
        return None


def _alt(q: str) -> dict | None:
    try:
        from app import aliases
        alt = aliases.alt_matches(q)
    except Exception:  # noqa: BLE001 - an extra; never fail a search
        return None
    return alt


def _schools(q: str) -> list[dict]:
    try:
        return colleges.search(q, 5)
    except Exception:  # noqa: BLE001 - schools are an extra; never fail a search
        log.exception("search: schools")
        return []


cached_person = ttl_lru()(queries.person)
cached_firms = ttl_lru()(queries.search_firms)
cached_org = ttl_lru()(queries.org)


# --- pages --------------------------------------------------------------------

@app.get("/about", response_class=HTMLResponse)
@app.get("/data", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
@app.get("/terms", response_class=HTMLResponse)
def static_page(request: Request):
    return render(request, STATIC_PAGES[request.url.path])


@app.get("/support", response_class=HTMLResponse)
def support_page(request: Request, canceled: int = 0, other: str = "", error: str | None = None,
                 status_code: int = 200):
    return render(request, "support.html", status_code=status_code, enabled=support.enabled(),
                  monthly=support.MONTHLY, once=support.ONCE, dollars=support.dollars, portal_url=support.PORTAL_URL,
                  other_min=support.OTHER_MIN, other_max=support.OTHER_MAX,
                  other=other if other in ("monthly", "once") else "", canceled=bool(canceled), error=error)


support_limit = contact.HourlyLimit(30)


@app.post("/support/checkout")
async def support_checkout(request: Request):
    """A Support button: create a Stripe Checkout Session and send the browser to it."""
    body = (await request.body())[:2000].decode("utf-8", "replace")
    form = {k: v[0] for k, v in parse_qs(body).items()}
    kind = form.get("kind", "")
    other = "amount_dollars" in form
    if not support.enabled() or kind not in ("monthly", "once"):
        return RedirectResponse("/support", status_code=303)
    if "other" in form and not other:               # the Other button without JavaScript: show its form inline
        return RedirectResponse(f"/support?other={kind}#other-{kind}", status_code=303)
    amount = support.other_cents(kind, form["amount_dollars"]) if other else support.valid(kind, form.get("amount"))
    if amount is None and other:
        return support_page(request, other=kind, status_code=400,
                            error=f"Please enter an amount from {support.dollars(support.OTHER_MIN)} to "
                                  f"{support.dollars(support.OTHER_MAX)}.")
    if amount is None:
        return RedirectResponse("/support", status_code=303)
    if not support_limit.allow(_client_ip(request)):
        return support_page(request, error="Too many attempts from your connection. Please try again later.",
                            status_code=429)
    try:
        url = await run_in_threadpool(support.checkout_url, kind, amount, other)
    except Exception:  # noqa: BLE001 - Stripe down or not set up: say so, never a 500
        log.exception("support: creating a checkout session")
        return support_page(request, error="Payments are not available right now. Please try again later, or "
                                           "get in touch below.", status_code=502)
    analytics.event(request, "support_checkout", {"kind": kind, "amount": amount, "other": other})
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


# --- home page --------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def home(request: Request, more: int = 0, seen: str = ""):
    """Home page with "Interesting ideas…" (app/ideas.py): five at random from the nightly pool; More adds five
    unseen ones, up to MAX_TOTAL (40). The ideas shown are in the URL (?seen=ids), so a shared link shows the same list."""
    from app import ideas as home_ideas
    shown = home_ideas.parse_seen(seen)[:home_ideas.MAX_TOTAL]
    remembered = home_ideas.parse_seen(request.cookies.get(home_ideas.COOKIE))[:home_ideas.MAX_TOTAL]
    if more:
        ids = shown + home_ideas.more_ids(shown)
    else:
        ids = shown or remembered or home_ideas.first_ids()     # a link's list, else this session's, else at random
    items = home_ideas.fetch(ids[:home_ideas.MAX_TOTAL])
    more_url = ("/?" + urlencode({"more": 1, "seen": ",".join(str(i["id"]) for i in items)}) + "#ideas"
                if len(items) < home_ideas.MAX_TOTAL else None)
    today_day, today_items = home_ideas.pool_items()
    resp = render(request, "index.html", ideas=items, ideas_more_url=more_url, idea_groups=home_ideas.group(items),
                  today_count=len(today_items))
    if more or shown:          # remember this visitor's list for the session (no expiry: gone when the browser closes)
        resp.set_cookie(home_ideas.COOKIE, ".".join(str(i["id"]) for i in items), httponly=True, samesite="lax",
                        secure=SITE_URL.startswith("https://"))
    return resp


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
    people, institutions, contractors, orgs, schools = run_searches(q, filters, page)
    formd_issuers = corporate.search_formd(q) if page == 1 else []
    formd_fam = corporate.formd_families(q) if page == 1 and formd_issuers else None
    formd_people = corporate.search_formd_people(q) if page == 1 else []
    alt_match = None if _alias(q) else _alt(q)
    if alt_match and alt_match.get("chapter") and formd_issuers:
        alt_match = None        # "geek ventures": Form D issuers by that name, not a "GEEK" acronym plus a chapter
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
    # A misspelled organization name ("memorial sloan kettring"): the closest one, offered at the top, since the
    # organizations table is below the people.
    org_dym = None
    if not named_orgs and orgs and len(typed.split()) >= 2:
        import difflib
        top = orgs[0]
        nn = top.get("name_norm") or ""
        if nn != typed and difflib.SequenceMatcher(None, typed, nn[:len(typed) + 3]).ratio() >= 0.8:
            org_dym = top
    on_boards = {
        "person": boards.counts("person", [r["id"] for r in people["results"]]),
        "org": boards.counts("org", [o["ein"] for o in orgs]),
        "vendor": boards.counts("vendor", [c["name_norm"] for c in contractors if c.get("name_norm")]),
    }
    base = {"q": q, "type": chosen, **{k: v for k, v in filters.items() if v is not None}}
    pages = min(MAX_PAGE, max(1, (people["total"] + queries.PAGE - 1) // queries.PAGE))
    return render(request, "search.html", q=q, page=page, pages=pages, filters=filters, people=people, search_type=chosen,
                  institutions=institutions, contractors=contractors, orgs=orgs, on_boards=on_boards,
                  named_orgs=named_orgs, org_dym=org_dym, nl_note=nl_note, schools=schools, alias=_alias(q),
                  formd_issuers=formd_issuers, formd_people=formd_people, formd_fam=formd_fam,
                  alt=alt_match,
                  page_url=lambda p: "/search?" + urlencode({**base, "page": p}),
                  dym_url=lambda name: "/search?" + urlencode({"q": name}))


# --- leaderboards ---------------------------------------------------------------

def board_filters(request: Request) -> dict:
    qp = request.query_params
    state = (qp.get("state") or "").strip()
    form = (qp.get("form") or "").strip().upper().replace("-", "")
    return {"year": _int(qp.get("year"), 1990, 2100), "form": form if form in boards.FORMS else None,
            "state": state.upper() if _STATE.match(state) else None,
            "all": 1 if qp.get("all") == "1" else None,   # per-organization boards: every organization-year
            "sort": (qp.get("sort") or "")[:40] or None, "dir": "asc" if qp.get("dir") == "asc" else None,
            # Payroll and school boards: dropdowns, toggles and the name box (validated in boards._where).
            **{k: (qp.get(k) or "").strip()[:80] or None for k in BOARD_EXTRA_FILTERS}}


BOARD_EXTRA_FILTERS = ("sport", "source", "head", "control", "sector", "has_orgs", "international", "country", "q",
                       "view")    # view: the Schools Report Card topic (schools_hub.VIEWS); never a SQL filter


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
    # Payroll-only people have no page of their own (subject_url NULL): leave the link blank.
    out["subject_url"] = SITE_URL + r["subject_url"] if r.get("subject_url") else None
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
        yield buf.getvalue() + csvfoot.footer(f"/boards/{board.slug}")

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers=csvfoot.disposition(board.slug))


@app.get("/boards/{slug}", response_class=HTMLResponse)
def board_page(request: Request, slug: str, page: int = Query(1, ge=1)):
    board, page = _board_or_404(slug), min(page, MAX_BOARD_PAGE)
    filters = board_filters(request)
    spec = boards.sort_spec(board, filters["sort"], filters["dir"])
    filters["sort"], filters["dir"] = (spec if spec else (None, None))
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
    from app import seo as board_seo
    board_csv_url = f"/boards/{board.slug}.csv" + ("?" + urlencode(base) if base else "")
    # The description leads with this view's own top row (a filtered view: its first row, not the board's).
    finding_text = boards.finding(board, data["rows"][0] if data["rows"] and page == 1 else top_row)
    bseo = board_seo.board(board, boards.window(meta) if board.kind == "990" else None, finding_text, filters,
                           board_csv_url, f"/boards/{board.slug}")
    return render(request, "board.html", board=board, meta=meta, filters=filters, page=page, pages=pages,
                  seo=bseo, seo_title=bseo["title"],
                  window=boards.window(meta), years=boards.years(board), report_url=report,
                  finding=boards.finding(board, top_row), filtered=bool({k for k in base if k not in ("all", "sort", "dir", "view")}), **data,
                  per_org=per_org, toggle_url=f"/boards/{board.slug}" + ("?" + urlencode(toggle) if toggle else ""),
                  sort_spec=spec, sortable=boards.sortable(board),
                  filter_options=boards.filter_options(board) if board.filters else {},
                  payroll_coverage=colleges.coverage() if board.kind in ("payroll", "school") and colleges.available() else None,
                  sort_url=lambda col: f"/boards/{board.slug}?" + urlencode(
                      {**{k: v for k, v in base.items() if k not in ("sort", "dir")}, "sort": col,
                       **({"dir": "asc"} if spec == (col, "desc") else {})}),
                  group=boards.GROUPS.get(board.group), group_boards=boards.group_members(board.group),
                  letters=boards.letters(board) if board.alphabetical and meta and not base else [],
                  page_url=lambda p: f"/boards/{board.slug}?" + urlencode({**base, "page": p}),
                  csv_url=f"/boards/{board.slug}.csv" + ("?" + urlencode(base) if base else ""),
                  shown_columns=schools_hub.view_columns(board, filters.get("view")),
                  school_crumb=schools_hub.crumb(board, filters.get("view")),
                  back_url=f"/boards/{board.slug}" + ("?" + urlencode({k: v for k, v in base.items() if k in ("all", "view")})
                                                      if {k for k in base if k in ("all", "view")} else ""))


# --- natural-language search ---------------------------------------------------------

NL_EXAMPLES = NL_EXAMPLES_HOME
NL_FIELDS = {"intent", "name", "state", "city", "daf_only", "person_a", "person_b", "org", "topic", "scope", "keywords",
             "ntee", "year", "title_contains", "limit", "board", "per_person", "include_related",
             "institution", "sport", "head_only", "metrics", "year_from", "year_to", "yoy", "cumulative",
             "condition", "metric_a", "metric_b", "threshold", "percent"}


def _intent_from_form(qp) -> dict:
    """The "edit" form: structured fields straight to the validator, no model call."""
    args = {}
    for k in NL_FIELDS - {"intent"}:
        v = (qp.get(k) or "").strip()
        if not v:
            continue
        if k == "metrics":
            args[k] = [m.strip() for m in v.split(",") if m.strip()]
        elif k in ("threshold", "percent"):
            try:
                args[k] = float(v)
            except ValueError:
                pass
        else:
            args[k] = (int(v) if k in ("year", "limit", "year_from", "year_to") and v.isdigit()
                       else (v == "1") if k in ("daf_only", "per_person", "include_related", "head_only", "yoy",
                                                "cumulative") else v)
    return ask.validate(qp.get("intent") or "", args)


def intent_key(intent: dict) -> tuple:
    """A hashable cache key for an intent (lists, such as metrics, become tuples)."""
    return tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in intent.items()
                        if k not in ("how", "parse_ms")))


@ttl_lru()
def _cached_nl_run(intent: tuple):
    """Results for an intent (one page of it), kept 60 seconds like the other pages (repeat questions skip the
    database)."""
    d = {k: list(v) if isinstance(v, tuple) else v for k, v in intent}
    return ask.run_page({k: v for k, v in d.items() if k != "page"}, d.get("page") or 1)


def nl_search(request: Request, q: str, structured: bool = False):
    """Run a natural-language (or edited, structured) search. Returns a response, or None to fall back."""
    t0 = time.monotonic()
    if structured:
        parsed = {**_intent_from_form(request.query_params), "how": "edited"}
    else:
        parsed = ask.parse(q, _client_ip(request))
    if parsed["intent"] == "unknown" and parsed.get("suggestion") and not structured:
        # The model read the question but no search fits: say so and offer the closest one, rather than run the
        # words as a name search and show unrelated results.
        ask.record((time.monotonic() - t0) * 1000, parsed)
        return render(request, "search_nl.html", q=q, intent=parsed, result={"kind": "unsupported", "total": 0},
                      reading=parsed.get("understood") or "your question", edit_url=ask.edit_url, categories=[],
                      category_label=ask.category_label, topics=[], intents=[t["name"] for t in ask.TOOLS
                                                                            if t["name"] != "unknown"],
                      examples=NL_EXAMPLES), parsed
    if parsed["intent"] in ("plain", "unknown"):
        ask.record((time.monotonic() - t0) * 1000, parsed)
        return None, parsed
    pg = (request.query_params.get("page") or "1").strip()
    page = min(ask.MAX_PAGE, max(1, int(pg))) if pg.isdigit() else 1
    try:
        result = _cached_nl_run(intent_key({**parsed, "page": page}))
    except Exception:  # noqa: BLE001 - a bad intent is a fallback, never a 500
        log.exception("nl: running intent %s", parsed.get("intent"))
        return None, {**parsed, "intent": "unknown", "reason": "error"}
    if result["kind"] == "none":
        # Nothing found: say so and offer a related question that does return results (from the checked
        # suggestions), rather than running the words as a name search.
        ask.record((time.monotonic() - t0) * 1000, {**parsed, "how": parsed["how"] + "+nomatch"})
        from app import ideas as home_ideas
        result = {"kind": "empty", "total": 0, "related": home_ideas.related(q or ask.describe(parsed))}
    # The short answer on top (app/answer.py): cached ones inline, otherwise fetched by static/site.js.
    from app import answer as nl_answer
    search_url = ask.edit_url(parsed)
    answer_html = answer_src = None
    if page == 1 and result["kind"] not in ("empty", "unsupported", "org_choices", "school_choices"):
        answer_html = nl_answer.cached(search_url)
        if answer_html is None:
            answer_src = "/ask/answer?" + search_url.split("?", 1)[1] + (("&" + urlencode({"q": q})) if q else "")
    resp = render(request, "search_nl.html", q=q, intent=parsed, result=result, reading=ask.describe(parsed),
                  answer_html=answer_html, answer_src=answer_src,
                  edit_url=ask.edit_url, page_url=lambda p: ask.edit_url(parsed) + f"&page={p}"
                  + (("&" + urlencode({"q": q})) if q else ""), categories=[("", "Any"), (ask.HIGHER_ED, "Higher education")]
                  + [(k, f"{v} ({k})") for k, v in ask.NTEE_GROUPS.items()], category_label=ask.category_label,
                  topics=["finances", "spending", "grants_made", "grants_received", "daf"],
                  intents=[t["name"] for t in ask.TOOLS if t["name"] != "unknown"], examples=NL_EXAMPLES)
    ask.record((time.monotonic() - t0) * 1000, parsed)
    analytics.search(request, q or "(edited search)", "edit" if structured else "nl", intent=parsed.get("intent"),
                     results=result.get("total", len(result.get("rows") or [])) if result.get("rows") is not None else 1,
                     ms=(time.monotonic() - t0) * 1000)
    return resp, parsed


@app.get("/ask/answer", response_class=HTMLResponse)
def ask_answer(request: Request, q: str = ""):
    """The short plain-English answer for a search (a fragment for static/site.js), from the cache or the model."""
    from app import answer as nl_answer
    parsed = _intent_from_form(request.query_params)
    if parsed.get("intent") in (None, "unknown", "plain"):
        return HTMLResponse("")
    try:
        result = _cached_nl_run(intent_key({**parsed, "page": 1}))
    except Exception:  # noqa: BLE001
        return HTMLResponse("")
    if result.get("kind") in ("none", "unsupported"):
        return HTMLResponse("")
    html_out = nl_answer.answer(q.strip()[:ask.MAX_QUESTION] or ask.describe(parsed), ask.edit_url(parsed), result)
    return HTMLResponse(html_out, headers={"Cache-Control": "private, max-age=3600"})


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


# --- schools and institutions ------------------------------------------------------------

@app.get("/schools", response_class=HTMLResponse)
def schools_page(request: Request):
    """Schools overview: the three Schools pages with their leaders. /schools used to be the Report Card, so old
    links with a query string (a page, a sort, a filter) go to the Report Card itself."""
    if request.url.query:
        return RedirectResponse(f"/boards/schools?{request.url.query}", status_code=301)
    return render(request, "schools_overview.html", **schools_hub.overview_context())


@app.get("/schools/{section}", response_class=HTMLResponse)
def schools_section(request: Request, section: str):
    if section not in schools_hub.SECTIONS:
        raise HTTPException(404)
    ctx = schools_hub.section_context(section)
    return render(request, "schools_section.html", sections_all=schools_hub.SECTIONS,
                  sl_summary=student_loans.summary() if section == "student-loans" else None, **ctx)


@app.get("/institution/{key}", response_class=HTMLResponse)
def institution_page(request: Request, key: str):
    from app import slugs
    uid = slugs.parse("institution", key)
    unitid = int(uid) if uid else 0
    data = cached_institution(unitid) if uid else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "institution", unitid, data["college"]["name"])
    if moved:
        return moved
    top = colleges.payroll_people(unitid, None, 1, per_page=colleges.TOP_SHOWN)
    return render(request, "institution.html", top=top, undated=colleges.undated_count(unitid), **data)


@app.get("/institution/{unitid}/payroll", response_class=HTMLResponse)
def institution_payroll_page(request: Request, unitid: int, year: str = "", q: str = "",
                             page: int = Query(1, ge=1)):
    data = cached_institution(unitid)
    if not data:
        raise HTTPException(404)
    q = q.strip()[:60]
    page = min(page, MAX_BOARD_PAGE)
    yr = colleges.YEAR_NOT_PUBLISHED if year == colleges.YEAR_NOT_PUBLISHED else _int(year, 1990, 2100)
    people = colleges.payroll_people(unitid, yr, page, q or None)
    pages = max(1, (people["total"] + colleges.PEOPLE_PAGE - 1) // colleges.PEOPLE_PAGE)
    base = {k: v for k, v in {"year": people["year"], "q": q}.items() if v}
    return render(request, "institution_payroll.html", college=data["college"], years=data["years"], data=people,
                  undated=colleges.undated_count(unitid),
                  q=q, page=page, pages=pages,
                  page_url=lambda p: f"/institution/{unitid}/payroll?" + urlencode({**base, "page": p}))


cached_institution = ttl_lru()(colleges.institution)


@app.get("/person/{key}", response_class=HTMLResponse)
def person_page(request: Request, key: str, year: str = "", fragment: int = 0, all: int = 0):
    from app import slugs
    cid = slugs.parse("person", key)
    if not cid:
        raise HTTPException(404)
    cluster_id = int(cid)
    data = cached_person(cluster_id, full=not fragment, year=_int(year, 1990, 2100), show_all=bool(all))
    if not data:
        moved = queries.resolve_person(cluster_id)
        if moved and moved != cluster_id:
            q = request.url.query
            return RedirectResponse(f"/person/{moved}" + (f"?{q}" if q else ""), status_code=301)
        raise HTTPException(404)
    if not fragment:
        moved = slugs.redirect(request, "person", cluster_id, data["cluster"]["display_name"])
        if moved:
            return moved
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
    from app import seo
    extras = {"payroll": colleges.person_payroll(cluster_id), "politics": politics.person_contributions(cluster_id),
              "fedpay": fedspend.person_pay(cluster_id), "secrec": corporate.person_sec(cluster_id),
              "lobbying": lobbying.person_lobbying(cluster_id)}
    meta = seo.person(data, extras, slugs.canonical("person", cluster_id, c["display_name"]))
    return render(request, "person.html", report_url=report, active=active, fragment=False, seo=meta,
                  **extras, **data)


@app.get("/org/{key}", response_class=HTMLResponse)
def org_page(request: Request, key: str):
    from app import slugs
    ein = slugs.parse("org", key)
    data = cached_org(ein) if ein else None
    if not data:
        raise HTTPException(404)
    moved = slugs.redirect(request, "org", ein, data["org"]["name"])
    if moved:
        return moved
    everyone = queries.org_people([ein]).get(ein, [])
    from app import seo
    extras = {"committees": politics.org_committees(ein), "fed": fedspend.org_awards(ein),
              "formd_rows": corporate.org_formd(ein), "lobby": lobbying.org_lobbying(ein)}
    meta = seo.org(data, everyone, extras, slugs.canonical("org", ein, data["org"]["name"]))
    try:
        connected = queries.org_connected(ein, (data.get("headline") or {}).get("id"))
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        log.exception("org page: connected for %s", ein)
        connected = []
    return render(request, "org.html", everyone=everyone, org_institutions=colleges.org_institutions(ein),
                  seo=meta, connected=connected, **extras, **data, **_org_funding(ein))


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
    return Response(buf.getvalue() + csvfoot.footer(f"/org/{o['ein']}/funders"), media_type="text/csv",
                    headers=csvfoot.disposition(f"org-{o['ein']}-funders"))


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
    return Response(buf.getvalue() + csvfoot.footer(f"/org/{ein}/grants/{year}"), media_type="text/csv; charset=utf-8",
                    headers=csvfoot.disposition(f"org-{ein}-grants-{year}"))


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


@app.get("/contractor/{key}", response_class=HTMLResponse)
def contractor_page(request: Request, key: str):
    from app import slugs
    cid = slugs.parse("contractor", key)
    data = queries.contractor(int(cid)) if cid else None
    if not data:
        raise HTTPException(404)
    # Every record of a vendor name has one page: the canonical record's (merged duplicates).
    moved = slugs.redirect(request, "contractor", data["canonical_id"], data["contractor"]["name_raw"])
    if moved:
        return moved
    c = data["contractor"]
    terms = " ".join(x for x in (c["name_raw"], c["city"], c["state"]) if x)
    from app import seo
    meta = seo.contractor(data, slugs.canonical("contractor", data["canonical_id"], c["name_raw"]))
    return render(request, "contractor.html", find_url="https://duckduckgo.com/?q=" + quote(terms), seo=meta, **data)


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
    import psycopg
    if isinstance(exc, (psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable)) or \
            type(exc).__name__ in ("PoolTimeout", "TooManyRequests"):
        # A query hit the statement timeout (or the pool was full): a brief "try again", not a server error.
        log.warning("busy: %s on %s", type(exc).__name__, request.url.path)
        headers = {"Retry-After": "10", "Cache-Control": "no-store"}
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "busy, try again in a few seconds"}, status_code=503, headers=headers)
        resp = render(request, "busy.html", status_code=503)
        resp.headers.update(headers)
        return resp
    log.exception("unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "server error"}, status_code=500)
    return render(request, "500.html", status_code=500)


from app import schools_hub  # noqa: E402

# === BEGIN student-loans block (student loan ABS pages: app/student_loans.py) ===
from app import student_loans  # noqa: E402

app.include_router(student_loans.router)
templates.env.globals["sl_last_update"] = student_loans.last_update   # coverage notice: last updated
from app import tuition  # noqa: E402
templates.env.globals.update(tuition_summary=tuition.summary, tuition_dollars=tuition.dollars)   # templates/_tuition.html
# === END student-loans block ===

# === BEGIN politics block (FEC campaign contributions: app/politics.py) ===
from app import politics  # noqa: E402

app.include_router(politics.router)
templates.env.globals["politics_public"] = politics.PUBLIC
# === END politics block ===

# === BEGIN get-ideas block (morning email for reporters: app/reporters.py) ===
from app import reporters  # noqa: E402

app.include_router(reporters.router)
# === END get-ideas block ===

# === BEGIN fedspend block (USAspending federal awards: app/fedspend.py) ===
from app import fedspend  # noqa: E402

app.include_router(fedspend.router)
templates.env.globals["fedspend_public"] = fedspend.PUBLIC
# === END fedspend block ===

# === BEGIN corporate block (SEC insiders, Form D, CEO pay: app/corporate.py) ===
from app import corporate  # noqa: E402

app.include_router(corporate.router)
templates.env.globals["sec_public"] = corporate.PUBLIC
from app import adv  # noqa: E402  (Form ADV fund pages and person sections: app/adv.py)

app.include_router(adv.router)
templates.env.globals["adv"] = adv
# === END corporate block ===

# === BEGIN lobbying block (federal lobbying: app/lobbying.py) ===
from app import lobbying  # noqa: E402

app.include_router(lobbying.router)
templates.env.globals["lda_public"] = lobbying.PUBLIC
# === END lobbying block ===

# Helpers the data sections on person and organization pages use (they are included outside their own routes).
templates.env.globals.update(pol=politics, fs=fedspend, sec=corporate, lob=lobbying)
NL_FIELDS.update({"firm", "classification", "reason"})     # the food_recalls question (app/ask.py)

# === BEGIN explain block ("Explain what I'm seeing": app/explain.py) ===
from app import explain as page_explain  # noqa: E402

templates.env.globals["explain_prefixes"] = page_explain.PREFIXES


@app.get("/explain", response_class=HTMLResponse, include_in_schema=False)
def explain_page(request: Request, u: str = ""):
    """A plain-English explanation of one page's data (HTML fragment for static/site.js), on click only."""
    if not u.startswith("/") or u.startswith("//") or len(u) > 1500 or not u.startswith(page_explain.PREFIXES):
        return HTMLResponse("", status_code=400)
    # Owner, 2026-10-21: 3 explanations a day per visitor (a plain cookie, "day:count"), then a pointer to Support.
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    day, _, n = (request.cookies.get(EXPLAIN_COOKIE) or "").partition(":")
    used = int(n) if day == today and n.isdigit() else 0
    if used >= EXPLAIN_PER_DAY:
        return HTMLResponse(EXPLAIN_LIMIT_HTML, headers={"Cache-Control": "no-store"})
    if not page_explain.cached_only(u) and not page_explain.LIMIT.allow(_client_ip(request)):
        return HTMLResponse("", status_code=429)
    try:
        out = page_explain.explain(u)
    except Exception:  # noqa: BLE001 - an explanation never breaks anything
        log.exception("explain: %s", u)
        out = ""
    resp = HTMLResponse(out, headers={"Cache-Control": "no-store"})
    resp.set_cookie(EXPLAIN_COOKIE, f"{today}:{used + 1}", max_age=2 * 86400, httponly=True, secure=True,
                    samesite="lax")
    return resp


EXPLAIN_COOKIE = "furp_explain"
EXPLAIN_PER_DAY = 3
EXPLAIN_LIMIT_HTML = ("<p>That's today's 3 free explanations. Each one is written by an AI model that costs us money "
                      "to run. <a href=\"/support\">Support FURP</a> to help keep them coming; you get 3 more "
                      "tomorrow.</p>")
# === END explain block ===

# === BEGIN news block (FURP in the News: app/news.py, content/in-the-news.yml) ===
from app import news as furp_news  # noqa: E402

templates.env.globals["furp_news"] = furp_news.articles


@app.get("/about/news", response_class=HTMLResponse)
def news_page(request: Request):
    return render(request, "about_news.html", news_items=furp_news.articles())
# === END news block ===

# === BEGIN recalls block (food recalls: app/recalls.py) ===
from app import recalls as food_recalls  # noqa: E402

app.include_router(food_recalls.router)
templates.env.globals["rc"] = food_recalls            # _recalls_section.html on org, company, client, recipient pages
templates.env.globals["recalls_public"] = food_recalls.PUBLIC
# === END recalls block ===

# === BEGIN map block (map-ready CSV and GeoJSON: app/geo.py) ===
from app import geo as map_geo  # noqa: E402

MAP_KINDS = ("orgs", "daf_orgs", "top_paid", "vendors", "board", "recalls", "payroll", "coaches")
templates.env.globals["map_kinds"] = MAP_KINDS
templates.env.globals["map_ready"] = map_geo.ready
from app import irs_info  # noqa: E402

templates.env.globals["irs_info"] = irs_info          # exempt status on organization pages (loader/irs_status.py)


def _map_format(request: Request) -> str:
    return "geojson" if request.query_params.get("format") == "geojson" else "csv"


@app.get("/boards/{slug}/map", include_in_schema=False)
def board_map(request: Request, slug: str):
    """A leaderboard (with its filters) as map-ready CSV or GeoJSON: rows placed at their organization's ZIP."""
    board = _board_or_404(slug)
    window = boards.window(boards.meta().get(board.slug))
    raw = boards.all_rows(board, board_filters(request), limit=CSV_MAX_ROWS) if boards.meta().get(board.slug) else []
    rows = [{**_row_out(board, r, window), "subject_key": r.get("subject_key")} for r in raw]
    located = map_geo.locate(rows)
    fields = map_geo.fields_for(located, CSV_FIELDS + [c.key for c in board.columns])
    return map_geo.response(located, [f for f in fields if f != "subject_key"], _map_format(request), board.slug,
                            f"/boards/{board.slug}")


@app.get("/ask/map", include_in_schema=False)
def ask_map(request: Request):
    """A plain-text search's results (its structured form, as in the Edit link) as map-ready CSV or GeoJSON."""
    parsed = _intent_from_form(request.query_params)
    if parsed.get("intent") in (None, "unknown", "plain"):
        raise HTTPException(404)
    res = ask.run({**parsed, "limit": ask.MAX_LIMIT})
    rows = res.get("rows") if isinstance(res.get("rows"), list) and res.get("kind") in MAP_KINDS else []
    rows = [dict(r) for r in rows]
    for r in rows:
        if res.get("kind") == "vendors" and r.get("name_norm"):
            r.setdefault("subject_kind", "vendor")
            r.setdefault("subject_key", r["name_norm"])
    located = map_geo.locate(rows, individuals=res.get("kind") == "people")
    return map_geo.response(located, map_geo.fields_for(located), _map_format(request),
                            parsed.get("intent", "search"), "/ask")


@app.get("/search/map", include_in_schema=False)
def search_map(request: Request, q: str = "", table: str = "orgs"):
    """The organizations or contractors table of a name search as map-ready CSV or GeoJSON."""
    q = q.strip()[:MAX_QUERY]
    if not q:
        raise HTTPException(404)
    if table == "contractors":
        rows = [{**r, "subject_kind": "vendor", "subject_key": r.get("name_norm")}
                for r in queries.search_contractors(q, limit=50)]
    else:
        rows = [dict(r) for r in queries.search_orgs(q, limit=50)]
    located = map_geo.locate(rows)
    return map_geo.response(located, map_geo.fields_for(located, ["name"]), _map_format(request),
                            f"search-{table}-{q}", "/search")
# === END map block ===

# === BEGIN today block (the day's checked suggestions: app/ideas.py) ===
@app.get("/today", response_class=HTMLResponse)
@app.get("/today/{day}", response_class=HTMLResponse)
def today_page(request: Request, day: str | None = None):
    """Every checked suggestion in a day's pool, grouped by theme: /today is the latest, /today/YYYY-MM-DD any day."""
    import datetime as _dt
    from app import ideas as home_ideas
    want = None
    if day is not None:
        try:
            want = _dt.date.fromisoformat(day)
        except ValueError:
            raise HTTPException(404)
    d, items = home_ideas.pool_items(want)
    if not items:
        raise HTTPException(404)
    latest = home_ideas.pools()[0]["day"] if home_ideas.pools() else d
    from app import seo as day_seo
    path = f"/today/{d.isoformat()}"
    return render(request, "today.html", day=d, items=items, groups=home_ideas.group(items), is_latest=(d == latest),
                  page_path=path, seo={"jsonld": day_seo.item_list(f"Finds from public records, {d.isoformat()}",
                                                                   path, items)})


@app.get("/about/daily", response_class=HTMLResponse)
def daily_index(request: Request):
    """About > Daily Interesting Things: an index of the /today/YYYY-MM-DD pages, newest first."""
    from app import ideas as home_ideas
    return render(request, "about_daily.html", pools=home_ideas.pools())
# === END today block ===

# === BEGIN linkedin block (daily LinkedIn posts: app/linkedin.py) ===
from app import linkedin as li_posts  # noqa: E402

app.include_router(li_posts.router)
# === END linkedin block ===
