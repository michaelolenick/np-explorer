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

HEADERS = ["Rank", "Name", "Tax year", "Raised at events (Schedule G line 1)", "Spent on events (8b)",
           "Cost per dollar raised (cents)", "Kept (line 1 minus 8b)", "HQ state", "EIN", "Form",
           "Gross income (8a)", "Net (8c)", "Donations at events (line 1c)", "8b source",
           "Two largest events (as described)", "Event types", "Filing", "Verify"]


def cents(v) -> int | None:
    return None if v is None else round(float(v) * 100)


def verify_url(r: dict) -> str | None:
    """The IRS e-filed return as published by ProPublica (we store the IRS object id of every filing)."""
    return propublica_filing(r["ein"], r["object_id"]) if r.get("ein") and r.get("object_id") else None


def row(r: dict) -> list:
    return [r.get("rank"), r.get("subject_name"), r.get("tax_year"), r.get("gross_receipts"), r.get("direct_expenses"),
            cents(r.get("value")), r.get("kept"), r.get("state"), r.get("ein"), boards.FORMS.get(r.get("form_type"), r.get("form_type")),
            r.get("gross_income"), r.get("net"), r.get("contributions"), r.get("direct_source"), r.get("event_names"),
            r.get("categories"), f"{SITE_URL}/filing/{r['filing_id']}" if r.get("filing_id") else None, verify_url(r)]


def csv_response(board: boards.Board, filters: dict, limit: int) -> StreamingResponse:
    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(HEADERS)
        for r in boards.all_rows(board, filters, limit=limit):
            w.writerow(row(r))
            if buf.tell() > 65536:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        yield buf.getvalue() + csvfoot.footer(f"/boards/{board.slug}")

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8", headers=csvfoot.disposition(board.slug))
