"""Average tuition since student loans stopped being dischargeable in bankruptcy (data: tuition_averages, from NCES
Digest Table 330.10; loaded by loader/tuition.py). Shown on the Student loan data page and the student loan report.

All figures are national averages for full-time undergraduates at degree-granting institutions, as NCES publishes
them; "after inflation" uses NCES's own constant-dollar columns (CPI, academic-year basis)."""

from __future__ import annotations

import logging
from datetime import date

from app import db
from app.cache import ttl_lru

log = logging.getLogger("np.tuition")

# Bankruptcy law for student loans (11 U.S.C. 523(a)(8) and its predecessor). Each still allows discharge for
# "undue hardship", which courts grant rarely.
EVENTS = [
    (1976, "1976", "Education Amendments of 1976: federal student loans can't be discharged in bankruptcy in their "
                   "first five years of repayment, except for undue hardship."),
    (1998, "1998", "Higher Education Amendments of 1998: the time limit is removed; federal student loans can be "
                   "discharged only for undue hardship."),
    (2005, "2005", "Bankruptcy Abuse Prevention and Consumer Protection Act of 2005: the same rule is extended to "
                   "most private student loans."),
]
START_YEARS = [1970, 1976, 1980, 1998, 2005]          # academic years 1970-71, 1976-77, ...
CONTROLS = [("all", "All institutions"), ("public", "Public"), ("private", "Private")]
SOURCE_PAGE = "https://nces.ed.gov/programs/digest/current_tables.asp"

W, H, PAD = 640, 160, 8


@ttl_lru()
def summary() -> dict | None:
    """Chart geometry and the 'increase since' table; None before the table is loaded (the section is hidden)."""
    try:
        with db.conn() as conn:
            rows = conn.execute("""SELECT control, year_start, academic_year, tuition_fees_current, tuition_fees_constant,
                                          constant_base, edition_year, source_url
                                   FROM tuition_averages WHERE level = 'all' AND control IN ('all', 'public', 'private')
                                   ORDER BY control, year_start""").fetchall()
    except Exception:  # noqa: BLE001 - table not created yet
        log.info("tuition: no tuition_averages table")
        return None
    if not rows:
        return None
    series = {c: {r["year_start"]: r for r in rows if r["control"] == c} for c, _ in CONTROLS}
    allr = series["all"]
    years = sorted(y for y, r in allr.items() if r["tuition_fees_constant"] is not None)
    if len(years) < 2:
        return None
    latest = years[-1]
    base, edition, url = allr[latest]["constant_base"], allr[latest]["edition_year"], allr[latest]["source_url"]

    # chart: all institutions, tuition and fees, constant dollars
    x0, x1 = years[0], years[-1]
    vals = [float(allr[y]["tuition_fees_constant"]) for y in years]
    hi = max(vals)

    def x(y):
        return PAD + (y - x0) / max(1, x1 - x0) * (W - 2 * PAD)

    def yy(v):
        return H - PAD - v / hi * (H - 2 * PAD)

    line = " ".join(f"{x(y):.1f},{yy(float(allr[y]['tuition_fees_constant'])):.1f}" for y in years)
    marks = [{"x": round(x(y), 1), "label": label, "text": text} for y, label, text in EVENTS if x0 <= y <= x1]

    table = []
    for start in START_YEARS:
        row = {"start": start, "cells": []}
        for c, _ in CONTROLS:
            a, b = series[c].get(start), series[c].get(latest)
            if a and b and a["tuition_fees_constant"] and b["tuition_fees_constant"]:
                then, now = float(a["tuition_fees_constant"]), float(b["tuition_fees_constant"])
                row["cells"].append({"then": then, "now": now, "pct": (now / then - 1) * 100,
                                     "then_current": float(a["tuition_fees_current"] or 0) or None})
            else:
                row["cells"].append(None)
        row["label"] = (series["all"].get(start) or {}).get("academic_year") or f"{start}-{(start + 1) % 100:02d}"
        if any(row["cells"]):
            table.append(row)
    return {"line": line, "w": W, "h": H, "marks": marks, "first": allr[x0]["academic_year"],
            "last": allr[latest]["academic_year"], "low": min(vals), "high": hi, "base": base, "edition": edition,
            "source_url": url, "controls": CONTROLS, "table": table, "events": EVENTS,
            "now_current": float(allr[latest]["tuition_fees_current"] or 0)}


def dollars(v) -> str:
    return "" if v is None else f"${v:,.0f}"
