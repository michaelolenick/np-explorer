"""Ready-made citations for a page ("Cite this"): plain text, APA and MLA.

Used by templates/_cite.html through the `cite` template global (installed in app/main.py).
Copy only: nothing here touches data.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

from app.config import SITE_URL

PUBLISHER = "furp.org"

# What each page is, for the APA bracket and the plain-text line.
KINDS = {
    "org": "Nonprofit organization profile",
    "person": "Person profile",
    "board": "Leaderboard",
    "institution": "Institution profile",
    "school": "School profile",
    "trust": "Trust profile",
}

_MLA_MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]


def page_url(path: str) -> str:
    """The full address of a page path, keeping its query string (a search or filter), without any #fragment."""
    path = (path or "/").split("#", 1)[0]
    return SITE_URL.rstrip("/") + ("" if path.startswith("/") else "/") + path


def year_range(years) -> str:
    """'2015-2023' from a list of tax years (blanks ignored), a (first, last) pair or a ready string."""
    if not years:
        return ""
    if isinstance(years, str):
        return years
    ys = sorted({int(y) for y in years if y not in (None, "")}) if isinstance(years, Iterable) else []
    if not ys:
        return ""
    return str(ys[0]) if ys[0] == ys[-1] else f"{ys[0]}–{ys[-1]}"


def citations(title: str, path: str, kind: str | None = None, years=None, today: dt.date | None = None) -> dict:
    """Plain, APA and MLA citations for one page, retrieved today.

    title  the page title (e.g. the organization's name)
    path   the canonical page path, e.g. "/org/123456789"
    kind   one of KINDS (org, person, board, institution, school, trust) or None
    years  tax years on the page: a list, a (first, last) pair or a string; None to leave out
    """
    today = today or dt.date.today()
    url = page_url(path)
    title = " ".join((title or PUBLISHER).split())
    label = KINDS.get(kind or "", "")
    span = year_range(years)
    iso = today.isoformat()
    long_date = f"{today.strftime('%B')} {today.day}, {today.year}"
    mla_date = f"{today.day} {_MLA_MONTHS[today.month - 1]} {today.year}"
    tax = f"tax years {span}" if span else ""

    end = "" if title.endswith((".", "?", "!")) else "."
    plain = f"{title}{end} {PUBLISHER}" + (f", {label.lower()}" if label else "") + (f", {tax}" if tax else "") \
        + f". {url}. Retrieved {iso}."
    bracket = "; ".join(x for x in (label or "Data set", tax) if x)
    apa = f"{PUBLISHER}. (n.d.). {title} [{bracket}]. Retrieved {long_date}, from {url}"
    mla_title = title if title.endswith((".", "?", "!")) else title + "."
    mla = f"“{mla_title}” {PUBLISHER}" + (f", {tax}" if tax else "") + f", {url}. Accessed {mla_date}."
    return {"title": title, "url": url, "date": iso, "years": span,
            "formats": [("Plain text", plain), ("APA", apa), ("MLA", mla)]}


def install(env) -> None:
    """Make `cite(...)` available to every template."""
    env.globals["cite"] = citations
