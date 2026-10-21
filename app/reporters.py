"""The "Get Ideas" email: a morning email of story leads for reporters, drawn from the home page's nightly pool of checked
suggestions (app/ideas.py).

- Signup (/get-ideas): email address only. We send a confirmation link (Postmark, transactional stream) and add the
  address to the list only when it is clicked. Asking again for a pending or active address just resends the link;
  the page never says whether an address is already on the list.
- Every morning (cron, deploy/cron/np-ideas) send_daily() emails each active subscriber PER_EMAIL suggestions picked
  at random from that night's pool (a different set per reader, the same set if the job is rerun that day), through
  Postmark's broadcast stream. Each suggestion links to its static search URL on the site. Replies go to
  REPLY_TO.
- Unsubscribe: every email links to /get-ideas/unsubscribe?t=<token>; one press of the button there unsubscribes
  (a plain link would be followed by the link scanners many newsrooms run, unsubscribing people who never asked).
  Postmark's own List-Unsubscribe header gives mail apps a true one-click button; Postmark then rejects sends to that
  address (InactiveRecipient), and we mark it unsubscribed.
- Every signup, verification, send and unsubscribe is a row in idea_email_events; the daily usage report counts them
  (counts()).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import logging
import os
import random
import re
import secrets
import sys
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import contact, db
from app.config import INFO_EMAIL, SITE_URL

log = logging.getLogger("np.reporters")
router = APIRouter()

FROM = "Strategy Studio <reporters@strategystudio.org>"
REPLY_TO = "reporters@strategystudio.org"
PER_EMAIL = 30
POSTMARK = "https://api.postmarkapp.com"
BATCH = 400                     # Postmark takes up to 500 messages per batch call
SIGNUP_LIMIT = contact.HourlyLimit(5)


# --- data ---------------------------------------------------------------------------------------

def _event(conn, kind: str, sub_id: int | None, detail: str | None = None) -> None:
    conn.execute("INSERT INTO idea_email_events (kind, subscriber_id, detail) VALUES (%s, %s, %s)",
                 (kind, sub_id, detail))


def _postmark(path: str, payload) -> tuple[int, object]:
    token = os.environ.get("POSTMARK_SERVER_TOKEN")
    if not token:
        return 0, {"Message": "POSTMARK_SERVER_TOKEN is not set"}
    try:
        r = httpx.post(POSTMARK + path, json=payload, timeout=60, headers={
            "X-Postmark-Server-Token": token, "Accept": "application/json", "Content-Type": "application/json"})
        return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
    except httpx.HTTPError as e:
        return 0, {"Message": type(e).__name__}


def signup(email: str) -> bool:
    """Add or refresh a pending signup and send the confirmation link. True when the email went out (or the
    address is already active, which gets nothing new)."""
    email = email.strip().lower()
    with db.conn() as conn:
        row = conn.execute("SELECT id, status, token FROM idea_subscribers WHERE email = %s", (email,)).fetchone()
        if row and row["status"] == "active":
            _event(conn, "signup_repeat", row["id"])
            return True
        token = secrets.token_urlsafe(24)
        if row:
            conn.execute("""UPDATE idea_subscribers SET status = 'pending', token = %s, created = now(),
                            unsubscribed = NULL WHERE id = %s""", (token, row["id"]))
            sub_id = row["id"]
        else:
            sub_id = conn.execute("""INSERT INTO idea_subscribers (email, token) VALUES (%s, %s)
                                     RETURNING id""", (email, token)).fetchone()["id"]
        _event(conn, "signup", sub_id)
    link = f"{SITE_URL}/get-ideas/confirm?t={token}"
    text = (f"Confirm your Get Ideas subscription:\n\n{link}\n\n"
            "Every morning you'll get 30 story leads drawn from public records on Strategy Studio "
            f"({SITE_URL}). If you didn't ask for this, ignore this email and nothing will happen.\n\n"
            f"Questions? Reply to this email or write to {REPLY_TO}.\n")
    body = _wrap(f"""<p>Confirm your <strong>Get Ideas</strong> subscription:</p>
<p><a href="{html.escape(link)}" style="{BUTTON}">CONFIRM</a></p>
<p>Every morning you'll get 30 story leads drawn from public records on Strategy Studio. If you didn't ask for this,
ignore this email and nothing will happen.</p>""")
    status, resp = _postmark("/email", {"From": FROM, "To": email, "ReplyTo": REPLY_TO,
                                        "Subject": "Confirm your Get Ideas subscription", "TextBody": text,
                                        "HtmlBody": body, "MessageStream": "outbound"})
    with db.conn() as conn:
        _event(conn, "confirm_sent" if status == 200 else "confirm_failed", sub_id,
               None if status == 200 else f"{status} {resp.get('ErrorCode') if isinstance(resp, dict) else ''}")
    return status == 200


def confirm(token: str) -> bool:
    with db.conn() as conn:
        row = conn.execute("""UPDATE idea_subscribers SET status = 'active', confirmed = now()
                              WHERE token = %s AND status IN ('pending', 'active') RETURNING id""", (token,)).fetchone()
        if row:
            _event(conn, "verified", row["id"])
    return bool(row)


def unsubscribe(token: str, how: str = "link") -> bool:
    with db.conn() as conn:
        row = conn.execute("""UPDATE idea_subscribers SET status = 'unsubscribed', unsubscribed = now()
                              WHERE token = %s AND status <> 'unsubscribed' RETURNING id""", (token,)).fetchone()
        if row:
            _event(conn, "unsubscribed", row["id"], how)
    return bool(row)


def counts(conn, start: dt.datetime, end: dt.datetime) -> dict:
    """For the daily usage report: events in the window, and the list's size now."""
    by = {r["kind"]: r["n"] for r in conn.execute("""
        SELECT kind, count(*) AS n FROM idea_email_events WHERE ts >= %s AND ts < %s GROUP BY 1""",
                                                  (start, end)).fetchall()}
    subs = conn.execute("SELECT count(*) FILTER (WHERE status = 'active') AS a, "
                        "count(*) FILTER (WHERE status = 'pending') AS p FROM idea_subscribers").fetchone()
    return {"signups": by.get("signup", 0), "verifications": by.get("verified", 0), "emails_sent": by.get("sent", 0),
            "send_failures": by.get("send_failed", 0), "unsubscribes": by.get("unsubscribed", 0),
            "active_subscribers": subs["a"], "pending_confirmation": subs["p"]}


# --- the email ----------------------------------------------------------------------------------

FONT = "font-family:'Courier New',Courier,monospace"
BUTTON = (f"{FONT};display:inline-block;border:2px solid #000;padding:8px 16px;color:#000;font-weight:bold;"
          "text-decoration:none")


def _wrap(inner: str) -> str:
    return (f'<!doctype html><html><body style="margin:0;background:#fff;color:#000">'
            f'<div style="{FONT};font-size:14px;line-height:1.5;color:#000;background:#fff;padding:16px;'
            f'max-width:680px">'
            f'<p style="font-weight:bold;letter-spacing:0.05em">STRATEGY STUDIO / PUBLIC DATA EXPLORER</p>{inner}'
            f"</div></body></html>")


def pick(pool: list[dict], sub_id: int, day: dt.date, k: int = PER_EMAIL) -> list[dict]:
    """k ideas at random, seeded by reader and day: each reader gets a different set, and a rerun the same day
    sends the same one."""
    seed = int(hashlib.sha256(f"{sub_id}:{day.isoformat()}".encode()).hexdigest()[:16], 16)
    return random.Random(seed).sample(pool, min(k, len(pool)))


def render_email(ideas: list[dict], token: str, day: dt.date) -> tuple[str, str, str]:
    """(subject, text, html) for one reader."""
    unsub = f"{SITE_URL}/get-ideas/unsubscribe?t={token}"
    subject = f"Get Ideas: {len(ideas)} story leads from public records, {day:%B} {day.day}"
    lines = [f"{i + 1}. {x['question']}\n   {SITE_URL}{x['url']}" for i, x in enumerate(ideas)]
    note = ("Using any of this? Please cite furp.org, and tell a colleague: it's free, and it stays free "
            "when people spread the word.")
    talk = (f"We like talking to reporters. Hit reply (it goes to {REPLY_TO}) for help with the data, a source, an "
            "interview, a podcast, or whatever you're working on.")
    text = (f"{subject}\n\nEach link opens a search that has already been run and checked on furp.org.\n\n"
            + "\n\n".join(lines)
            + f"\n\n{note}\n\n{talk}\n\nDonate: {SITE_URL}/support\nContact us: {SITE_URL}/contact\n"
            f"Unsubscribe: {unsub}\n")
    items = "".join(f'<li style="margin:0 0 10px"><a href="{html.escape(SITE_URL + x["url"])}" '
                    f'style="color:#000">{html.escape(x["question"])}</a></li>' for x in ideas)
    body = _wrap(f"""<p style="font-size:16px;font-weight:bold">{len(ideas)} story leads from public records</p>
<p>Each link opens a search that has already been run and checked on furp.org.</p>
<ol style="padding-left:24px">{items}</ol>
<hr style="border:0;border-top:2px solid #000;margin:20px 0">
<p>{html.escape(note)}</p>
<p>{html.escape(talk)}</p>
<p><a href="{SITE_URL}/support" style="{BUTTON}">DONATE</a></p>
<p><a href="{SITE_URL}/contact" style="color:#000">Contact us</a> &middot;
<a href="{html.escape(unsub)}" style="color:#000">Unsubscribe</a></p>
<p style="font-size:12px">You're getting this because you signed up for Get Ideas at furp.org.</p>""")
    return subject, text, body


def _pool(day: dt.date) -> list[dict]:
    """That night's pool ({id, question, url}); the latest pool if tonight's isn't there."""
    from app import ideas
    with db.conn() as conn:
        rows = conn.execute("""SELECT id FROM home_ideas
                               WHERE pool = coalesce((SELECT max(pool) FROM home_ideas WHERE pool <= %s),
                                                     (SELECT max(pool) FROM home_ideas))
                               ORDER BY id""", (day,)).fetchall()
    return ideas.fetch([r["id"] for r in rows])


def send_daily(day: dt.date | None = None, only: str | None = None, status=print) -> int:
    """Email every active subscriber (or only the address `only`) once for `day`. Returns emails sent."""
    from app.ideas import pool_date
    day = day or pool_date()
    pool = _pool(day)
    if len(pool) < 10:
        status(f"get-ideas: pool too small ({len(pool)}), nothing sent")
        return 0
    with db.conn() as conn:
        subs = conn.execute("""SELECT s.id, s.email, s.token FROM idea_subscribers s
                               WHERE s.status = 'active' AND (%s::text IS NULL OR s.email = %s)
                                 AND NOT EXISTS (SELECT 1 FROM idea_email_sends x
                                                 WHERE x.subscriber_id = s.id AND x.day = %s)
                               ORDER BY s.id""", (only, only, day)).fetchall()
    sent = 0
    for i in range(0, len(subs), BATCH):
        chunk = subs[i:i + BATCH]
        msgs, picks = [], []
        for s in chunk:
            chosen = pick(pool, s["id"], day)
            subject, text, body = render_email(chosen, s["token"], day)
            msgs.append({"From": FROM, "To": s["email"], "ReplyTo": REPLY_TO, "Subject": subject, "TextBody": text,
                         "HtmlBody": body, "MessageStream": "broadcast", "Tag": "get-ideas"})
            picks.append([x["id"] for x in chosen])
        code, resp = _postmark("/email/batch", msgs)
        results = resp if isinstance(resp, list) else [{"ErrorCode": -1, "Message": str(resp)}] * len(chunk)
        with db.conn() as conn:
            for s, ids, r in zip(chunk, picks, results):
                if code == 200 and r.get("ErrorCode") == 0:
                    conn.execute("INSERT INTO idea_email_sends (subscriber_id, day, idea_ids) VALUES (%s, %s, %s) "
                                 "ON CONFLICT DO NOTHING", (s["id"], day, ids))
                    _event(conn, "sent", s["id"])
                    sent += 1
                elif r.get("ErrorCode") == 406:            # Postmark: inactive recipient (unsubscribed or bounced)
                    conn.execute("UPDATE idea_subscribers SET status = 'unsubscribed', unsubscribed = now() "
                                 "WHERE id = %s", (s["id"],))
                    _event(conn, "unsubscribed", s["id"], "postmark inactive recipient")
                else:
                    _event(conn, "send_failed", s["id"], f"{code} {r.get('ErrorCode')}")
    status(f"get-ideas: {sent} of {len(subs)} emails sent for {day}")
    return sent


# --- pages --------------------------------------------------------------------------------------

def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render  # app.main includes this router, so import at call time
    return render(request, template, **ctx)


def _form(request: Request, email: str = "", errors: list | None = None, status_code: int = 200) -> HTMLResponse:
    return _render(request, "get_ideas.html", status_code=status_code, state="form", email=email,
                   errors=errors or [], token=contact.issue_token(), per_email=PER_EMAIL, reply_to=REPLY_TO)


@router.get("/get-ideas", response_class=HTMLResponse)
def page(request: Request, sent: int = 0):
    if sent:
        return _render(request, "get_ideas.html", state="sent", per_email=PER_EMAIL, reply_to=REPLY_TO)
    return _form(request)


@router.post("/get-ideas", response_class=HTMLResponse)
async def submit(request: Request):
    from starlette.concurrency import run_in_threadpool
    body = (await request.body())[:4000].decode("utf-8", "replace")
    raw = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}
    if contact.is_bot(raw):
        return RedirectResponse("/get-ideas?sent=1", status_code=303)      # look like it worked
    email = (raw.get("email") or "").strip()[:254]
    if not contact._EMAIL.match(email):
        return _form(request, email, ["Enter your email address."], 400)
    ip = request.client.host if request.client else "unknown"
    if not SIGNUP_LIMIT.allow(ip):
        return _form(request, email, ["Too many signups from your connection. Please try again in an hour."], 429)
    if not await run_in_threadpool(signup, email):
        return _render(request, "get_ideas.html", status_code=502, state="failed", info_email=INFO_EMAIL,
                       per_email=PER_EMAIL, reply_to=REPLY_TO)
    return RedirectResponse("/get-ideas?sent=1", status_code=303)


@router.get("/get-ideas/confirm", response_class=HTMLResponse)
def confirm_page(request: Request, t: str = ""):
    ok = bool(re.fullmatch(r"[A-Za-z0-9_-]{20,64}", t)) and confirm(t)
    return _render(request, "get_ideas.html", state="confirmed" if ok else "bad_link", per_email=PER_EMAIL,
                   reply_to=REPLY_TO, status_code=200 if ok else 404)


@router.get("/get-ideas/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(request: Request, t: str = ""):
    return _render(request, "get_ideas.html", state="unsubscribe", t=t, per_email=PER_EMAIL, reply_to=REPLY_TO)


@router.post("/get-ideas/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_submit(request: Request):
    body = (await request.body())[:2000].decode("utf-8", "replace")
    t = (parse_qs(body).get("t") or [""])[0]
    if re.fullmatch(r"[A-Za-z0-9_-]{20,64}", t):
        unsubscribe(t)
    return _render(request, "get_ideas.html", state="unsubscribed", per_email=PER_EMAIL, reply_to=REPLY_TO)


if __name__ == "__main__":
    db.pool.open(wait=True)
    args = sys.argv[1:]
    if args[:1] == ["send"]:
        only = args[args.index("--only") + 1] if "--only" in args else None
        send_daily(only=only)
