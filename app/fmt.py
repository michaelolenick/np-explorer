"""Jinja filters."""

from __future__ import annotations

import re


def money(v) -> str:
    if v is None:
        return "-"
    v = int(v)
    return f"-${-v:,}" if v < 0 else f"${v:,}"


def short_money(v) -> str:
    """$155.7M, $8.1M, $1.45B, $412K: for one-line summaries."""
    if v is None:
        return "-"
    v = int(v)
    sign, a = ("-" if v < 0 else ""), abs(v)
    for size, unit, digits in ((1e9, "B", 2), (1e6, "M", 1), (1e3, "K", 0)):
        if a >= size:
            return f"{sign}${a / size:,.{digits}f}{unit}"
    return f"{sign}${a:,}"


def num(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float) or hasattr(v, "is_integer"):
        f = float(v)
        return f"{int(f):,}" if f.is_integer() else f"{f:,.1f}"
    return f"{int(v):,}"


def ein(v) -> str:
    v = str(v or "")
    return f"{v[:2]}-{v[2:]}" if len(v) == 9 else v


def years(a, b) -> str:
    if not a:
        return "-"
    return str(a) if a == b or not b else f"{a}-{b}"


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def humanize(tag: str) -> str:
    """CYTotalRevenueAmt -> "CY Total Revenue Amt"."""
    return _CAMEL.sub(" ", tag)


def website_url(v) -> str | None:
    if not v:
        return None
    v = v.strip()
    return v if re.match(r"^https?://", v, re.I) else "http://" + v


def propublica_filing(ein, object_id) -> str:
    """ProPublica's rendering of the entire original e-filed return."""
    return f"https://projects.propublica.org/nonprofits/organizations/{int(ein)}/{object_id}/full"


FILTERS = {"money": money, "short_money": short_money, "num": num, "ein": ein, "years": years, "humanize": humanize,
           "website_url": website_url}
