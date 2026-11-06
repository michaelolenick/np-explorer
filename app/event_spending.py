"""The event-spending leaderboard's own CSV (owner, 2026-11-03): the same columns, order and headers as the
screen (templates/board_event_spending.html). Blank fields stay blank in the file (Not reported on screen)."""

from __future__ import annotations

import csv
import io

from fastapi import Request
from fastapi.responses import StreamingResponse

from app import boards, csvfoot
from app.config import SITE_URL
from app.fmt import propublica_filing

SLUG = "event-spending"
TEMPLATE = "board_event_spending.html"

# Owner, 2026-11-06: the answer column (cost per dollar raised, or the column the reader sorted by) right after
# the name, the other figures next, the identifiers (EIN, state, year, form) and the links last.
FIGURES = [("value", "Cost per dollar raised (cents)"), ("gross_receipts", "Raised at events (Schedule G line 1)"),
           ("direct_expenses", "Spent on events (8b)"), ("kept", "Kept (line 1 minus 8b)")]
TAIL = ["Gross income (8a)", "Net (8c)", "Donations at events (line 1c)", "8b source",
        "Two largest events (as described)", "Event types", "EIN", "HQ state", "Tax year", "Form", "Filing", "Verify"]


def figures(spec=None) -> list[tuple[str, str]]:
    """The four figures, the sorted one first."""
    if spec and spec[0] != "value" and any(k == spec[0] for k, _ in FIGURES):
        return [f for f in FIGURES if f[0] == spec[0]] + [f for f in FIGURES if f[0] != spec[0]]
    return FIGURES


def headers(spec=None) -> list[str]:
    return ["Rank", "Name"] + [label for _, label in figures(spec)] + TAIL


HEADERS = headers()


def cents(v) -> int | None:
    return None if v is None else round(float(v) * 100)


def verify_url(r: dict) -> str | None:
    """The IRS e-filed return as published by ProPublica (we store the IRS object id of every filing)."""
    return propublica_filing(r["ein"], r["object_id"]) if r.get("ein") and r.get("object_id") else None


def row(r: dict, spec=None) -> list:
    return ([r.get("rank"), r.get("subject_name")]
            + [cents(r.get("value")) if k == "value" else r.get(k) for k, _ in figures(spec)]
            + [r.get("gross_income"), r.get("net"), r.get("contributions"), r.get("direct_source"),
               r.get("event_names"), r.get("categories"), r.get("ein"), r.get("state"), r.get("tax_year"),
               boards.FORMS.get(r.get("form_type"), r.get("form_type")),
               f"{SITE_URL}/filing/{r['filing_id']}" if r.get("filing_id") else None, verify_url(r)])


def csv_response(board: boards.Board, filters: dict, limit: int) -> StreamingResponse:
    spec = boards.sort_spec(board, filters.get("sort"), filters.get("dir"))

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(headers(spec))
        for r in boards.all_rows(board, filters, limit=limit):
            w.writerow(row(r, spec))
            if buf.tell() > 65536:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        yield buf.getvalue() + csvfoot.footer(f"/boards/{board.slug}")

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8", headers=csvfoot.disposition(board.slug))
