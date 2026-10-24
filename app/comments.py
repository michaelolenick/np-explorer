"""Anonymous comments on entity pages (owner, 2026-10-23): no accounts, no email, no IP stored with a comment.

Posting: an optional display name (default "Anonymous") and up to 2,000 characters. Spam controls without logins:
a hidden honeypot field; a signed form timestamp (no faster than 3 seconds); a salted SHA-256 hash of the IP (salt
rotated monthly) limiting each poster to 5 comments an hour and 20 a day; at most one link, and none from a poster
with no approved comment yet; banned hashes refused. Every comment is classified by Claude Haiku (ok, spam,
abusive, threat, personal_info): "ok" is published at once, anything else waits in /admin/comments unpublished.
A reader can report a comment, which puts it in the queue too (it stays up until reviewed).

Comments render on the server, so they're part of the page search engines index. The owner hears about the queue
in the daily batch email (queue_digest, from scripts/report.py).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import contact, db

router = APIRouter()
log = logging.getLogger("np.comments")
MAX_BODY = 2000
MAX_NAME = 60
MIN_SECONDS = 3
PER_HOUR, PER_DAY = 5, 20
MODEL = os.environ.get("COMMENTS_MODEL", "claude-haiku-5-5")
LABELS = ("ok", "spam", "abusive", "threat", "personal_info")
URL_RX = re.compile(r"(?:https?://|www\.)\S+|\b[a-z0-9-]+\.(?:com|org|net|io|co|info|biz|us|ru|xyz)\b\S*", re.I)
# Where each kind of page lives, for links back (admin queue, "Recently discussed").
PATHS = {"org": "/org/{id}", "person": "/person/{id}", "formd": "/corporate/form-d/{id}", "fund": "/corporate/fund/{id}",
         "entity": "/corporate/entity/{id}", "fundperson": "/corporate/fund-person/{id}", "filing": "/filing/{id}",
         "school": "/institution/{id}", "company": "/corporate/company/{id}", "business": "/business/{id}",
         "contractor": "/contractor/{id}"}
KINDS = {"org": "Organization", "person": "Person", "formd": "Private offering", "fund": "Private fund",
         "entity": "Fund organization", "fundperson": "Fund person", "filing": "Filing", "school": "School",
         "company": "Company", "business": "Business", "contractor": "Contractor"}
SYSTEM = """You moderate comments on furp.org, a public-records site about nonprofits, pay, companies and funds. \
Classify the comment: "ok" (on topic or harmless, including criticism of public figures and organizations), \
"spam" (ads, link farming, gibberish, SEO), "abusive" (slurs, harassment, insults aimed at private people), \
"threat" (threats of violence or harm), or "personal_info" (a private person's home address, phone number, \
personal email, Social Security number or similar). Give a one-sentence reason."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["label", "reason"],
          "properties": {"label": {"type": "string", "enum": list(LABELS)}, "reason": {"type": "string"}}}


def entity_url(kind: str, key: str) -> str:
    if kind == "business":
        st, _, eid = key.partition(":")
        return f"/business/{st}/{eid}"
    if kind == "formd":
        return f"/corporate/form-d/{key}"
    return PATHS.get(kind, "/").format(id=key)


def _salt() -> bytes:
    """Rotates monthly: the same IP hashes differently each month."""
    secret = (os.environ.get("COMMENTS_SECRET") or os.environ.get("CONTACT_FORM_SECRET") or "np-comments").encode()
    return hmac.new(secret, dt.date.today().strftime("%Y-%m").encode(), hashlib.sha256).digest()


def ip_hash(ip: str) -> str:
    return hashlib.sha256(_salt() + (ip or "").encode()).hexdigest()


def client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()


def count(kind: str, key) -> int:
    try:
        with db.conn() as conn:
            return conn.execute("SELECT count(*) AS n FROM comments WHERE entity_type = %s AND entity_id = %s AND status = 'published'",
                                (kind, str(key))).fetchone()["n"]
    except Exception:  # noqa: BLE001
        return 0


def for_page(kind: str, key) -> list[dict]:
    try:
        with db.conn() as conn:
            return conn.execute("""SELECT id, display_name, body, created FROM comments WHERE entity_type = %s
                                   AND entity_id = %s AND status = 'published' ORDER BY created DESC LIMIT 200""",
                                (kind, str(key))).fetchall()
    except Exception:  # noqa: BLE001
        return []


def recent(limit: int = 15) -> list[dict]:
    """"Recently discussed": the pages with the newest published comments (/boards)."""
    try:
        with db.conn() as conn:
            rows = conn.execute("""SELECT entity_type, entity_id, max(entity_name) AS entity_name, max(page_path) AS page_path,
                                          count(*) AS n, max(created) AS last FROM comments WHERE status = 'published'
                                   GROUP BY 1, 2 ORDER BY max(created) DESC LIMIT %s""", (limit,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    for r in rows:
        r["url"], r["kind"] = r["page_path"] or entity_url(r["entity_type"], r["entity_id"]), KINDS.get(r["entity_type"], "")
    return rows


def moderate(body: str, name: str) -> tuple[str, str]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return "pending_review", "moderation unavailable"
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=20, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 300, "system": SYSTEM,
                  "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
                  "messages": [{"role": "user", "content": f"Display name: {name}\n\nComment:\n{body}"}]})
        r.raise_for_status()
        out = json.loads("".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text"))
        return (out["label"] if out.get("label") in LABELS else "pending_review"), (out.get("reason") or "")[:500]
    except Exception as e:  # noqa: BLE001 - when moderation fails, a person decides
        log.warning("comment moderation failed: %s", type(e).__name__)
        return "pending_review", f"moderation failed ({type(e).__name__})"


def _name_of(conn, kind: str, key: str) -> str | None:
    q = {"org": "SELECT name FROM organizations WHERE ein = %s",
         "person": "SELECT display_name FROM person_clusters WHERE id = %s::bigint",
         "formd": "SELECT issuer_name FROM sec_formd WHERE cik = %s OR accession = %s LIMIT 1",
         "fund": "SELECT fund_name FROM adv_funds WHERE fund_id = %s LIMIT 1",
         "entity": "SELECT name FROM sec_formd_parties WHERE id = %s::bigint",
         "fundperson": "SELECT name FROM sec_formd_parties WHERE id = %s::bigint",
         "filing": "SELECT coalesce(name, org_name) FROM filings WHERE id = %s::bigint",
         "school": "SELECT name FROM colleges WHERE unitid::text = %s",
         "company": "SELECT issuer_name FROM sec_insider_filings WHERE ltrim(issuer_cik, '0') = ltrim(%s, '0') LIMIT 1",
         "business": "SELECT name FROM biz_entities WHERE state || ':' || entity_id = %s",
         "contractor": "SELECT name_raw FROM contractors WHERE id = %s::bigint"}.get(kind)
    if not q:
        return None
    try:
        r = conn.execute(q, (key,) * q.count("%s")).fetchone()
        return list(r.values())[0] if r else None
    except Exception:  # noqa: BLE001
        conn.rollback()
        return None


def submit(request: Request, raw: dict) -> tuple[bool, str]:
    """(published, message for the reader)."""
    kind, key = raw.get("type", ""), str(raw.get("id", ""))[:200]
    if kind not in KINDS or not key:
        raise HTTPException(400)
    if raw.get("website"):
        return False, "Thanks."                                   # honeypot: say nothing useful to a bot
    age = contact.token_age(raw.get("t", ""))
    if age is None or age < MIN_SECONDS or age > 86400:
        return False, "Please take a moment and try again."
    body = (raw.get("body") or "").replace("\r\n", "\n").strip()
    name = " ".join((raw.get("name") or "").split())[:MAX_NAME] or "Anonymous"
    if not body:
        return False, "Write a comment first."
    if len(body) > MAX_BODY:
        return False, f"Keep it under {MAX_BODY:,} characters."
    h = ip_hash(client_ip(request))
    with db.conn() as conn:
        conn.execute("DELETE FROM comment_rate WHERE ts < now() - interval '1 day'")
        poster = conn.execute("SELECT approved, banned FROM comment_posters WHERE hash = %s", (h,)).fetchone() or \
            {"approved": 0, "banned": False}
        if poster["banned"]:
            return False, "Thanks."
        n = conn.execute("""SELECT count(*) FILTER (WHERE ts > now() - interval '1 hour') AS hour, count(*) AS day
                            FROM comment_rate WHERE hash = %s""", (h,)).fetchone()
        if n["hour"] >= PER_HOUR or n["day"] >= PER_DAY:
            return False, "You've posted a lot of comments today. Please try again later."
        links = len(URL_RX.findall(body))
        if links > 1 or (links and not poster["approved"]):
            return False, ("Please include at most one link." if links > 1 else
                           "Links can be added once you've had a comment approved. Please post without the link.")
        conn.execute("INSERT INTO comment_rate (hash) VALUES (%s)", (h,))
        label, reason = moderate(body, name)
        status = "published" if label == "ok" else "pending"
        back = (raw.get("back") or "").split("?")[0].split("#")[0]
        page = back if back.startswith("/") and not back.startswith("//") else entity_url(kind, key)
        row = conn.execute("""INSERT INTO comments (entity_type, entity_id, entity_name, page_path, display_name, body, status, label, reason)
                              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                           (kind, key, _name_of(conn, kind, key), page[:300], name, body, status, label, reason)).fetchone()
        conn.execute("INSERT INTO comment_hash_map (comment_id, hash) VALUES (%s, %s)", (row["id"], h))
        conn.execute("DELETE FROM comment_hash_map WHERE created < now() - interval '62 days'")
        if status == "published":
            conn.execute("""INSERT INTO comment_posters (hash, approved) VALUES (%s, 1)
                            ON CONFLICT (hash) DO UPDATE SET approved = comment_posters.approved + 1, updated = now()""", (h,))
    return (True, "Thanks, your comment is up.") if status == "published" else \
        (False, "Thanks. Your comment will appear once it's been reviewed.")


async def _form(request: Request) -> dict[str, list[str]]:
    """The posted form (urlencoded; the site doesn't use python-multipart)."""
    from urllib.parse import parse_qs
    return parse_qs((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)


# --- routes ------------------------------------------------------------------------------------------------------

def _back(raw: dict, msg: str) -> RedirectResponse:
    from urllib.parse import quote
    url = raw.get("back") or "/"
    if not url.startswith("/") or url.startswith("//"):
        url = "/"
    url = url.split("#")[0]
    sep = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{sep}c={quote(msg)}#comments", status_code=303)


@router.post("/comments", include_in_schema=False)
async def post_comment(request: Request):
    raw = {k: v[0] for k, v in (await _form(request)).items()}
    ok, msg = submit(request, raw)
    return _back(raw, msg)


@router.post("/comments/{cid}/report", include_in_schema=False)
async def report_comment(request: Request, cid: int):
    raw = {k: v[0] for k, v in (await _form(request)).items()}
    with db.conn() as conn:
        conn.execute("UPDATE comments SET reports = reports + 1, reviewed_at = NULL WHERE id = %s AND status = 'published'", (cid,))
    return _back(raw, "Thanks, we'll take a look.")


# --- admin -------------------------------------------------------------------------------------------------------

def _admin_ok(request: Request, key: str | None) -> bool:
    from app.linkedin import env as env_file          # .env read fresh: a new key works without a restart
    want = env_file().get("ADMIN_KEY") or os.environ.get("ADMIN_KEY", "")
    if not want:
        return False
    got = key or request.cookies.get("furp_admin", "")
    return hmac.compare_digest(got, want)


def queue() -> list[dict]:
    with db.conn() as conn:
        rows = conn.execute("""SELECT c.*, m.hash, (SELECT banned FROM comment_posters p WHERE p.hash = m.hash) AS banned
                               FROM comments c LEFT JOIN comment_hash_map m ON m.comment_id = c.id
                               WHERE c.status = 'pending' OR (c.reports > 0 AND c.reviewed_at IS NULL AND c.status <> 'deleted')
                               ORDER BY c.created DESC LIMIT 500""").fetchall()
    for r in rows:
        r["url"] = r["page_path"] or entity_url(r["entity_type"], r["entity_id"])
    return rows


@router.get("/admin/comments", response_class=HTMLResponse, include_in_schema=False)
def admin_page(request: Request, key: str | None = None):
    from app.main import render
    if not _admin_ok(request, key):
        raise HTTPException(404)
    resp = render(request, "admin_comments.html", rows=queue(), robots="noindex, nofollow")
    if key:
        resp.set_cookie("furp_admin", key, httponly=True, secure=True, samesite="strict", max_age=30 * 86400)
    return resp


@router.post("/admin/comments", include_in_schema=False)
async def admin_action(request: Request):
    if not _admin_ok(request, None):
        raise HTTPException(404)
    form = await _form(request)
    action = (form.get("action") or [""])[0]
    ids = [int(x) for x in form.get("id", []) if str(x).isdigit()]
    with db.conn() as conn:
        for cid in ids:
            if action == "approve":
                conn.execute("UPDATE comments SET status = 'published', reviewed_at = now() WHERE id = %s", (cid,))
                conn.execute("""INSERT INTO comment_posters (hash, approved)
                                SELECT hash, 1 FROM comment_hash_map WHERE comment_id = %s
                                ON CONFLICT (hash) DO UPDATE SET approved = comment_posters.approved + 1, updated = now()""", (cid,))
            elif action == "delete":
                conn.execute("UPDATE comments SET status = 'deleted', reviewed_at = now() WHERE id = %s", (cid,))
            elif action == "keep":
                conn.execute("UPDATE comments SET reviewed_at = now() WHERE id = %s", (cid,))
            elif action == "ban":
                conn.execute("""INSERT INTO comment_posters (hash, banned) SELECT hash, true FROM comment_hash_map WHERE comment_id = %s
                                ON CONFLICT (hash) DO UPDATE SET banned = true, updated = now()""", (cid,))
                conn.execute("UPDATE comments SET status = 'deleted', reviewed_at = now() WHERE id = %s", (cid,))
            elif action == "edit" and form.get(f"body_{cid}"):
                conn.execute("UPDATE comments SET body = %s, edited = true WHERE id = %s",
                             (form[f"body_{cid}"][0][:MAX_BODY], cid))
    return RedirectResponse("/admin/comments", status_code=303)


def queue_digest(status=print) -> int:
    """The moderation queue, in the owner's daily batch email."""
    from app import mailer
    from app.config import SITE_URL
    try:
        rows = queue()
    except Exception:  # noqa: BLE001
        return 0
    if not rows:
        return 0
    lines = []
    for r in rows[:50]:
        reports = f" ({r['reports']} reports)" if r["reports"] else ""
        lines.append(f"- [{r['label'] or 'reported'}] {r['display_name']} on {r['entity_name'] or r['entity_id']}{reports}: "
                     f"{r['body'][:160]!r}")
    mailer.notify_owner("Comments", f"{len(rows)} comment{'s' if len(rows) != 1 else ''} to review",
                        "\n".join(lines) + f"\n\nReview: {SITE_URL}/admin/comments\n")
    status(f"comments: {len(rows)} in the queue, added to the daily email")
    return len(rows)


# --- admin: low-confidence fund placements (loader/formd_order.py) --------------------------------------------------

@router.get("/admin/fund-order", response_class=HTMLResponse, include_in_schema=False)
def fund_order_page(request: Request, key: str | None = None):
    """Funds the ordering couldn't place confidently, newest first, for a person to check."""
    from app.main import render
    if not _admin_ok(request, key):
        raise HTTPException(404)
    with db.conn() as conn:
        rows = conn.execute("""SELECT o.issuer_name, o.latest_accession, o.first_date, f.family_key, f.fund_kind, f.series_label,
                                      f.method, f.reason, (SELECT p.issuer_name FROM sec_formd_offerings p WHERE p.root_accession = f.parent_root) AS parent
                               FROM formd_order f JOIN sec_formd_offerings o USING (root_accession)
                               WHERE f.confidence = 'low' ORDER BY o.first_date DESC NULLS LAST LIMIT 500""").fetchall()
        n = conn.execute("SELECT count(*) AS n FROM formd_order WHERE confidence = 'low'").fetchone()["n"]
    resp = render(request, "admin_fund_order.html", rows=rows, total=n, robots="noindex, nofollow")
    if key:
        resp.set_cookie("furp_admin", key, httponly=True, secure=True, samesite="strict", max_age=30 * 86400)
    return resp
