"""The /top hub (owner, 2026-10-30): the largest organizations, the biggest funders and the highest-paid people,
from priority_pages (loader/priority.py), in pages of PER_PAGE. Linked from the footer and Leaderboards, so every
priority page is three clicks from the home page: home, /top, a page of the list, the entity.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app import db, slugs

router = APIRouter()
PER_PAGE = 500
# kind: (heading, what the figure is, slug kind for the entity's URL)
KINDS = {
    "org": ("Largest organizations", "by latest reported revenue, then the most visited on FURP", "Revenue", "org"),
    "funder": ("Biggest funders", "by total grants reported, all years", "Granted", "org"),
    "person": ("Highest-paid people", "by highest reported pay in a single year", "Pay", "person"),
}


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, **ctx)


def counts() -> dict[str, int]:
    try:
        with db.conn() as conn:
            rows = conn.execute("SELECT kind, count(*) AS n FROM priority_pages GROUP BY 1").fetchall()
    except Exception:  # noqa: BLE001 - table not built yet: an empty hub, never a 500
        return {}
    return {r["kind"]: r["n"] for r in rows}


def pages(n: int) -> list[tuple[int, int, int]]:
    """(page number, first rank, last rank) for a list of n rows."""
    return [(p + 1, p * PER_PAGE + 1, min(n, (p + 1) * PER_PAGE)) for p in range((n + PER_PAGE - 1) // PER_PAGE)]


@router.get("/top", response_class=HTMLResponse)
def top_hub(request: Request):
    n = counts()
    return _render(request, "top.html", kinds=KINDS, lists={k: pages(n.get(k, 0)) for k in KINDS})


@router.get("/top/{kind}/{page}", response_class=HTMLResponse)
def top_page(request: Request, kind: str, page: int):
    if kind not in KINDS or page < 1:
        raise HTTPException(404)
    with db.conn() as conn:
        rows = conn.execute("SELECT rank, ident, name, figure, detail, why FROM priority_pages WHERE kind = %s "
                            "AND rank > %s AND rank <= %s ORDER BY rank",
                            (kind, (page - 1) * PER_PAGE, page * PER_PAGE)).fetchall()
    if not rows:
        raise HTTPException(404)
    slug_kind = KINDS[kind][3]
    for r in rows:
        r["url"] = slugs.canonical(slug_kind, r["ident"], r["name"])
    return _render(request, "top_list.html", kind=kind, info=KINDS[kind], page=page, rows=rows,
                   lists=pages(counts().get(kind, 0)))
