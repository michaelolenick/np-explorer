"""np-explorer web app: nonprofit people search over IRS Form 990 e-filings."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from urllib.parse import quote, urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import db, filing_view, queries
from app.config import CONTACT_EMAIL, GITHUB_URL, ROOT, SITE_URL
from app.fmt import FILTERS, propublica_filing
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
templates.env.globals.update(site_url=SITE_URL, github_url=GITHUB_URL, contact_email=CONTACT_EMAIL,
                             coverage=queries.coverage, propublica_filing=propublica_filing)
# nginx serves /static in production; this is for local runs.
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
limiter = RateLimiter()

STATIC_PAGES = {"/": "index.html", "/about": "about.html", "/data": "data.html", "/privacy": "privacy.html"}
_STATE = re.compile(r"^[A-Za-z]{2}$")


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


def run_searches(q: str, filters: dict, page: int):
    people = _search_pool.submit(queries.search_people, q, filters, page)
    if page > 1:
        return people.result(), [], [], []
    others = [_search_pool.submit(fn, q) for fn in
              (queries.search_institutions, queries.search_contractors, queries.search_orgs)]
    return (people.result(), *(f.result() for f in others))


# --- pages --------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
@app.get("/about", response_class=HTMLResponse)
@app.get("/data", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
def static_page(request: Request):
    return render(request, STATIC_PAGES[request.url.path])


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", page: int = Query(1, ge=1, le=1000)):
    q = q.strip()[:200]
    if not q:
        return RedirectResponse("/", status_code=302)
    filters = search_filters(request)
    people, institutions, contractors, orgs = run_searches(q, filters, page)
    base = {"q": q, **{k: v for k, v in filters.items() if v is not None}}
    pages = max(1, (people["total"] + queries.PAGE - 1) // queries.PAGE)
    return render(request, "search.html", q=q, page=page, pages=pages, filters=filters, people=people,
                  institutions=institutions, contractors=contractors, orgs=orgs,
                  page_url=lambda p: "/search?" + urlencode({**base, "page": p}),
                  dym_url=lambda name: "/search?" + urlencode({"q": name}))


@app.get("/contractors", response_class=HTMLResponse)
def contractor_search(request: Request, q: str = "", page: int = Query(1, ge=1, le=200)):
    q = q.strip()[:200]
    rows = queries.search_contractors(q, limit=50, offset=(page - 1) * 50) if q else []
    return render(request, "contractors.html", q=q, rows=rows, page=page,
                  page_url=lambda p: "/contractors?" + urlencode({"q": q, "page": p}))


@app.get("/person/{cluster_id}", response_class=HTMLResponse)
def person_page(request: Request, cluster_id: int, year: str = "", fragment: int = 0, all: int = 0):
    data = queries.person(cluster_id, full=not fragment, year=_int(year, 1990, 2100), show_all=bool(all))
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
        resp.headers["X-Robots-Tag"] = "noindex"
        resp.headers["Cache-Control"] = "private, max-age=300"
        return resp
    subject = f"Not the same person: {c['display_name']} ({SITE_URL}/person/{cluster_id})"
    report = f"mailto:{CONTACT_EMAIL}?subject={quote(subject)}&body={quote('Which rows look wrong, and why?')}"
    return render(request, "person.html", report_url=report, active=active, fragment=False, **data)


@app.get("/org/{ein}", response_class=HTMLResponse)
def org_page(request: Request, ein: str):
    ein = re.sub(r"\D", "", ein).zfill(9)
    data = queries.org(ein)
    if not data:
        raise HTTPException(404)
    return render(request, "org.html", **data)


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
def api_search(request: Request, q: str, page: int = Query(1, ge=1, le=1000)):
    q = q.strip()[:200]
    people, institutions, contractors, orgs = run_searches(q, search_filters(request), page)
    for r in people["results"]:
        r["match"] = BAND_NAMES.get(r.get("band"), "other")
    return _jsonable({"q": q, "page": page, "per_page": queries.PAGE, **people, "institutions": institutions,
                      "contractors": contractors, "organizations": orgs})


@app.get("/api/person/{cluster_id}")
def api_person(cluster_id: int):
    data = queries.person(cluster_id)
    if not data:
        moved = queries.resolve_person(cluster_id)
        if moved and moved != cluster_id:
            return RedirectResponse(f"/api/person/{moved}", status_code=301)
        raise HTTPException(404)
    data.pop("org_names", None)
    return _jsonable(data)


@app.get("/api/org/{ein}")
def api_org(ein: str):
    data = queries.org(re.sub(r"\D", "", ein).zfill(9))
    if not data:
        raise HTTPException(404)
    return _jsonable(data)


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
