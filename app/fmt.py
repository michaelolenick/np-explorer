"""Jinja filters."""

from __future__ import annotations

import re
from datetime import date


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


def year_ranges(years) -> str:
    """[2015, 2016, 2017, 2019] -> "2015-2017, 2019"."""
    ys = sorted({int(y) for y in years or [] if y is not None})
    out, i = [], 0
    while i < len(ys):
        j = i
        while j + 1 < len(ys) and ys[j + 1] == ys[j] + 1:
            j += 1
        out.append(str(ys[i]) if i == j else f"{ys[i]}-{ys[j]}")
        i = j + 1
    return ", ".join(out)


def current_year() -> int:
    """Today's year. Templates call it per render, so it rolls over without an app restart."""
    return date.today().year


def propublica_filing(ein, object_id) -> str:
    """ProPublica's rendering of the entire original e-filed return."""
    return f"https://projects.propublica.org/nonprofits/organizations/{int(ein)}/{object_id}/full"


FILTERS = {"money": money, "short_money": short_money, "num": num, "ein": ein, "years": years, "year_ranges": year_ranges, "humanize": humanize,
           "website_url": website_url}
