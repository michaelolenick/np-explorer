"""/opt-out: the opt-out page for the fundraiser outreach emails (owner, 2026-11-16).

The emails link here (and carry List-Unsubscribe headers, one-click POST included). Submitting an address records it in
outreach_optouts and marks its row in outreach_contacts "Opted out" (synced_to_sheet = false, so the next sheet sync writes
it into the Google Sheet), and the daily sender (~/claude_scripts/outreach/outreach_daily.py) never mails it again. The
answer is the same whether or not the address was on the list. Opting an address out is always harmless, so no token is needed.
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app import db

log = logging.getLogger("np.outreach")
router = APIRouter()
EMAIL = re.compile(r"^[^@\s]{1,100}@[^@\s]{1,200}\.[A-Za-z]{2,}$")
DDL = """
CREATE TABLE IF NOT EXISTS outreach_optouts (email text PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), via text);
CREATE TABLE IF NOT EXISTS outreach_contacts (
    sheet_row integer PRIMARY KEY, email text NOT NULL, first_name text, name text, organization text, title text, segment text,
    status text NOT NULL DEFAULT 'Not contacted', sent_on date, template text, send_ok boolean NOT NULL DEFAULT true,
    email_status text, notes text, synced_to_sheet boolean NOT NULL DEFAULT true, sent_at timestamptz);
CREATE INDEX IF NOT EXISTS outreach_contacts_email ON outreach_contacts (lower(email));
"""


def opt_out(email: str, via: str = "page") -> None:
    em = email.strip().lower()
    with db.conn() as conn:
        conn.execute(DDL)
        conn.execute("INSERT INTO outreach_optouts (email, via) VALUES (%s, %s) ON CONFLICT DO NOTHING", (em, via))
        conn.execute("""UPDATE outreach_contacts SET status = 'Opted out', send_ok = false, synced_to_sheet = false
                        WHERE lower(email) = %s AND status <> 'Opted out'""", (em,))


def _page(request: Request, email: str = "", done: bool = False, bad: bool = False):
    from app.main import render
    resp = render(request, "optout.html", email=email, done=done, bad=bad)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/opt-out", response_class=HTMLResponse)
def unsubscribe_page(request: Request, e: str = ""):
    return _page(request, email=e.strip()[:200])


@router.post("/opt-out", response_class=HTMLResponse)
async def unsubscribe_submit(request: Request):
    """The page's button, and a mail client's one-click unsubscribe (RFC 8058: POST with the address in the URL's query)."""
    form = await request.form()
    email = (str(form.get("email") or "") or request.query_params.get("e") or "").strip()
    if not EMAIL.match(email):
        return _page(request, email=email[:200], bad=True)
    try:
        opt_out(email, "one-click" if "List-Unsubscribe" in form else "page")
    except Exception:  # noqa: BLE001 - the page still answers; the owner can add the address to the opt-out file
        log.exception("unsubscribe")
    return _page(request, email=email, done=True)
