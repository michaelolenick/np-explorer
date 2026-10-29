"""Accounts: Google sign-in and email magic links, server-side sessions, signup and email opt-ins (owner, 2026-10-29).

Logging in is for Deep Queries (app/deep.py). Two ways in:

- Google (OAuth 2.0 authorization code): /auth/google sends the browser to Google with a random state (also in a
  short-lived cookie); /auth/google/callback checks the state, swaps the code for tokens and reads the verified email
  and name. Off until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set.
- Email magic link: /login/email emails a one-time link (Postmark, app/mailer.py). Only the token's sha256 is
  stored; it expires in 15 minutes and works once. The link opens a page with a button that logs in (a POST), so
  mail scanners that open links don't use it up.

A session is a random token in an HttpOnly, Secure, SameSite=Lax cookie; the database keeps its sha256
(user_sessions). Forms posted while logged in carry a token derived from the session (csrf()).

On first login, /signup asks for a name and two opt-ins, both unchecked: "Daily FURP blast" and "FURP newsletter"
(stored with the time each was last changed; nothing is sent yet). /unsubscribe?u=<id>&t=<signature> turns both off.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import contact, db, mailer
from app.config import SITE_URL

router = APIRouter()
log = logging.getLogger("np.accounts")

COOKIE = "furp_session"
STATE_COOKIE = "furp_oauth_state"
SESSION_DAYS = 30
LINK_MINUTES = 15
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[a-z]{2,}$", re.I)
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
ip_limit = contact.HourlyLimit(10)       # magic-link emails per connection per hour
email_limit = contact.HourlyLimit(3)     # and per address


def _secret() -> bytes:
    return (os.environ.get("SESSION_SECRET") or os.environ.get("CONTACT_FORM_SECRET") or "np-explorer-accounts").encode()


def _sign(*parts) -> str:
    return hmac.new(_secret(), "|".join(str(p) for p in parts).encode(), hashlib.sha256).hexdigest()[:32]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _secure() -> bool:
    return SITE_URL.startswith("https://")


def google_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def normalize_email(email: str | None) -> str | None:
    e = (email or "").strip().lower()
    return e if EMAIL_RE.match(e) and len(e) <= 254 else None


# --- sessions ----------------------------------------------------------------------------------

def current_user(request: Request) -> dict | None:
    """The logged-in user, or None. Cached on the request."""
    if "furp_user" in request.scope:
        return request.scope["furp_user"]
    user = None
    token = request.cookies.get(COOKIE)
    if token and len(token) < 200:
        try:
            with db.conn() as conn:
                user = conn.execute("""
                    UPDATE user_sessions s SET last_seen = now() FROM users u
                    WHERE s.token_hash = %s AND s.expires_at > now() AND u.id = s.user_id
                    RETURNING u.*, s.token_hash AS session_hash""", (_hash(token),)).fetchone()
        except Exception:  # noqa: BLE001 - tables not there yet: logged out
            log.exception("session lookup")
    request.scope["furp_user"] = user
    return user


def csrf(user: dict | None) -> str:
    return _sign("csrf", user["session_hash"]) if user else ""


def csrf_ok(user: dict | None, form: dict) -> bool:
    return bool(user) and hmac.compare_digest(csrf(user), form.get("csrf", ""))


def _login(conn, email: str, method: str, name: str | None, request: Request, next_url: str):
    u = conn.execute("""
        INSERT INTO users (email, name, auth_method, last_login) VALUES (%s, %s, %s, now())
        ON CONFLICT (email) DO UPDATE SET last_login = now(), name = coalesce(users.name, excluded.name)
        RETURNING *""", (email, name, method)).fetchone()
    token = secrets.token_urlsafe(32)
    conn.execute("""INSERT INTO user_sessions (token_hash, user_id, expires_at)
                    VALUES (%s, %s, now() + make_interval(days => %s))""", (_hash(token), u["id"], SESSION_DAYS))
    target = "/signup?" + urlencode({"next": next_url}) if u["status"] == "new" else next_url
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=_secure(), samesite="lax",
                    path="/")
    return resp


def _safe_next(n: str | None) -> str:
    """Only a path on this site (never //host or a full URL)."""
    n = n or "/deep"
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n else "/deep"


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render
    resp = render(request, template, user=current_user(request), google=google_enabled(), **ctx)
    resp.headers["Cache-Control"] = "no-store"          # per-user pages: never cached
    return resp


async def _form(request: Request) -> dict:
    from urllib.parse import parse_qs
    body = (await request.body())[:8000].decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


# --- pages -------------------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/deep", sent: int = 0, error: str = ""):
    if current_user(request) and not sent:
        return RedirectResponse(_safe_next(next), status_code=303)
    return _render(request, "login.html", next=_safe_next(next), sent=bool(sent), error=error[:40],
                   token=contact.issue_token())


@router.post("/login/email", response_class=HTMLResponse)
async def login_email(request: Request):
    from app.main import _client_ip
    form = await _form(request)
    nxt = _safe_next(form.get("next"))
    if contact.is_bot(form):
        return RedirectResponse("/login?" + urlencode({"sent": 1, "next": nxt}), status_code=303)
    email = normalize_email(form.get("email"))
    if not email:
        return RedirectResponse("/login?" + urlencode({"error": "email", "next": nxt}), status_code=303)
    if not ip_limit.allow(_client_ip(request)) or not email_limit.allow(email):
        return RedirectResponse("/login?" + urlencode({"error": "limit", "next": nxt}), status_code=303)
    token = secrets.token_urlsafe(32)
    with db.conn() as conn:
        conn.execute("""INSERT INTO login_tokens (token_hash, email, expires_at, ip)
                        VALUES (%s, %s, now() + make_interval(mins => %s), %s)""",
                     (_hash(token), email, LINK_MINUTES, _client_ip(request)))
    link = f"{SITE_URL}/auth/magic?" + urlencode({"t": token, "next": nxt})
    sent = mailer.send({
        "From": mailer.address("login", "FURP"), "To": email, "Subject": "Your FURP login link",
        "TextBody": (f"Log in to FURP:\n\n{link}\n\nThe link works once and expires in {LINK_MINUTES} minutes. "
                     "If you didn't ask for it, ignore this email: nothing happens without the link.\n\nFURP (furp.org)"),
        "MessageStream": "outbound"})
    if not sent:
        log.warning("magic link: send failed")
        return RedirectResponse("/login?" + urlencode({"error": "send", "next": nxt}), status_code=303)
    # The same answer whether or not the address has an account.
    return RedirectResponse("/login?" + urlencode({"sent": 1, "next": nxt}), status_code=303)


@router.get("/auth/magic", response_class=HTMLResponse)
def magic_page(request: Request, t: str = "", next: str = "/deep"):
    """A button, not an automatic login: link scanners open links, and the link works once."""
    with db.conn() as conn:
        row = conn.execute("SELECT email, expires_at > now() AS live, used_at FROM login_tokens WHERE token_hash = %s",
                           (_hash(t),)).fetchone() if t and len(t) < 100 else None
    ok = bool(row and row["live"] and not row["used_at"])
    return _render(request, "login_magic.html", t=t if ok else "", next=_safe_next(next),
                   email=row["email"] if ok else None, expired=not ok)


@router.post("/auth/magic")
async def magic_login(request: Request):
    form = await _form(request)
    t = form.get("t", "")
    with db.conn() as conn:
        row = conn.execute("""UPDATE login_tokens SET used_at = now()
                              WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()
                              RETURNING email""", (_hash(t),)).fetchone() if t and len(t) < 100 else None
        if not row:
            return RedirectResponse("/login?error=expired", status_code=303)
        return _login(conn, row["email"], "email", None, request, _safe_next(form.get("next")))


@router.get("/auth/google")
def google_start(request: Request, next: str = "/deep"):
    if not google_enabled():
        return RedirectResponse("/login?error=google", status_code=303)
    state = secrets.token_urlsafe(24)
    url = GOOGLE_AUTH + "?" + urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": f"{SITE_URL}/auth/google/callback",
        "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"})
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(STATE_COOKIE, f"{state}|{_safe_next(next)}", max_age=600, httponly=True, secure=_secure(),
                    samesite="lax", path="/auth/google")
    return resp


@router.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    saved, _, nxt = (request.cookies.get(STATE_COOKIE) or "").partition("|")
    if error or not code or not state or not saved or not hmac.compare_digest(saved, state) or not google_enabled():
        return RedirectResponse("/login?error=google", status_code=303)
    try:
        tok = httpx.post(GOOGLE_TOKEN, timeout=10, data={
            "code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "redirect_uri": f"{SITE_URL}/auth/google/callback", "grant_type": "authorization_code"})
        info = httpx.get(GOOGLE_USERINFO, timeout=10,
                         headers={"Authorization": f"Bearer {tok.json()['access_token']}"}).json() \
            if tok.status_code == 200 else {}
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("google sign-in: %s", type(e).__name__)
        info = {}
    email = normalize_email(info.get("email"))
    if not email or info.get("email_verified") is not True:
        return RedirectResponse("/login?error=google", status_code=303)
    with db.conn() as conn:
        resp = _login(conn, email, "google", (info.get("name") or "")[:200] or None, request, _safe_next(nxt))
    resp.delete_cookie(STATE_COOKIE, path="/auth/google")
    return resp


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, next: str = "/deep", error: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login?" + urlencode({"next": "/signup"}), status_code=303)
    return _render(request, "signup.html", next=_safe_next(next), csrf=csrf(user), error=error == "name")


@router.post("/signup")
async def signup_save(request: Request):
    user = current_user(request)
    form = await _form(request)
    if not csrf_ok(user, form):
        return RedirectResponse("/login", status_code=303)
    nxt = _safe_next(form.get("next"))
    name = re.sub(r"\s+", " ", form.get("name", "")).strip()[:200]
    if not name:
        return RedirectResponse("/signup?" + urlencode({"next": nxt, "error": "name"}), status_code=303)
    blast, news = form.get("daily_blast") == "1", form.get("newsletter") == "1"
    with db.conn() as conn:
        conn.execute("""UPDATE users SET name = %s, status = 'active',
                            daily_blast = %s, daily_blast_at = now(), newsletter = %s, newsletter_at = now()
                        WHERE id = %s""", (name, blast, news, user["id"]))
    return RedirectResponse(nxt, status_code=303)


@router.post("/logout")
async def logout(request: Request):
    user = current_user(request)
    form = await _form(request)
    if csrf_ok(user, form):
        with db.conn() as conn:
            conn.execute("DELETE FROM user_sessions WHERE token_hash = %s", (user["session_hash"],))
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE, path="/")
    return resp


def unsubscribe_url(user: dict) -> str:
    return f"{SITE_URL}/unsubscribe?" + urlencode({"u": user["id"], "t": _sign("unsub", user["id"])})


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(request: Request, u: int = 0, t: str = "", done: int = 0):
    ok = bool(u) and hmac.compare_digest(_sign("unsub", u), t or "")
    return _render(request, "unsubscribe.html", u=u, t=t, ok=ok, done=bool(done))


@router.post("/unsubscribe")
async def unsubscribe(request: Request):
    form = await _form(request)
    u = form.get("u", "")
    if not u.isdigit() or not hmac.compare_digest(_sign("unsub", int(u)), form.get("t", "")):
        return RedirectResponse("/unsubscribe", status_code=303)
    with db.conn() as conn:
        conn.execute("""UPDATE users SET daily_blast = false, daily_blast_at = now(), newsletter = false,
                            newsletter_at = now() WHERE id = %s""", (int(u),))
    return RedirectResponse("/unsubscribe?" + urlencode({"u": u, "t": form["t"], "done": 1}), status_code=303)
