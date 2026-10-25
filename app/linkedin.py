"""Daily LinkedIn posts of FURP findings to the owner's personal profile (owner, 2026-10-22).

- Connect: /linkedin/connect?key=<LINKEDIN_ADMIN_KEY> starts LinkedIn's OAuth flow (scopes "openid profile
  w_member_social"); /linkedin/callback exchanges the code, reads the person id ("sub") from the userinfo endpoint,
  and writes the token, its expiry and the id to the server's .env (never the repo). The key keeps anyone else
  from connecting their own account; the state parameter is signed and expires in 15 minutes.
- Every day, weekends too (cron, deploy/cron/np-linkedin, America/Chicago; owner, 2026-10-23):
    08:00  `draft`: run every search in the day's pool of checked suggestions, give the results to Claude Opus
           5.5, which picks exactly 5 of the strongest and writes a hook and one short line each with its most
           surprising number; every number must appear in that search's results (app/answer.numbers_ok). During
           the review period (LINKEDIN_REVIEW_UNTIL, the first week after connecting) the draft is emailed to
           the owner: reply "skip", or press Skip on the page the email links to, before 08:30 to stop it.
           Also: 7 and 1 days before the token expires, an email with the reconnect link.
    08:30  `post`: unless skipped, post it as the owner (Posts API, author urn:li:person:<id>), then add the first
           comment: each item's furp.org link (utm_source=linkedin&utm_medium=social&utm_campaign=daily) and
           furp.org/today. A failure is emailed once, not retried, and right away (the batch is sent then, not at
           the next 07:00): a failed draft or post, a failed comment, a crash, or nothing posted by the 11:30 run.
- Replies: the draft's Reply-To is the Postmark server's inbound address; Postmark posts replies to
  /linkedin/inbound?key=<LINKEDIN_INBOUND_KEY>, and a reply from the owner's address containing "skip" skips.
- Clicks: page views carrying utm_source=linkedin are counted in the nightly usage report.

Usage: .venv/bin/python -m app.linkedin draft|post|status
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import db, mailer
from app.config import REPORT_TO, ROOT, SITE_URL

log = logging.getLogger("np.linkedin")
router = APIRouter()

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
POSTS_URL = "https://api.linkedin.com/rest/posts"
SCOPES = "openid profile w_member_social"
ENV_FILE = ROOT / ".env"
REDIRECT = f"{SITE_URL}/linkedin/callback"
UTM = "utm_source=linkedin&utm_medium=social&utm_campaign=daily"
CLOSER = "Free, sourced to the filings. Links in the first comment."
INTRO = ("FURP, the system we created when loading data into VSTRAT and realizing there's much more "
         "interesting data.")   # the first line of every post (owner, 2026-10-25); "FURP", not "FURP.org": no links
# Anything LinkedIn would turn into a link (a URL or a bare domain like furp.org): the post itself carries none.
LINKISH = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:org|com|net|gov|edu|io|ai|us|co|info)\b", re.I)
REVIEW_DAYS = 7
MODEL = os.environ.get("LINKEDIN_MODEL", "claude-opus-5-5")
CENTRAL = "America/Chicago"


# --- settings in .env (read fresh: the callback writes them while the app runs) -------------------------------

def env() -> dict:
    out = {}
    try:
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except OSError:
        pass
    return {**{k: v for k, v in os.environ.items() if k.startswith("LINKEDIN_")}, **out}


def set_env(updates: dict) -> None:
    """Replace or add these lines in .env (atomically, owner-only permissions)."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [l for l in lines if l.split("=", 1)[0].strip() not in updates]
    lines += [f"{k}={v}" for k, v in updates.items()]
    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_FILE)


def keys() -> dict:
    """The admin key (connect link) and inbound key (Postmark webhook), created once."""
    e = env()
    new = {k: secrets.token_urlsafe(24) for k in ("LINKEDIN_ADMIN_KEY", "LINKEDIN_INBOUND_KEY") if not e.get(k)}
    if new:
        set_env(new)
        e.update(new)
    return {"admin": e["LINKEDIN_ADMIN_KEY"], "inbound": e["LINKEDIN_INBOUND_KEY"]}


def connect_link() -> str:
    return f"{SITE_URL}/linkedin/connect?key={keys()['admin']}"


def _sign(s: str) -> str:
    from app.contact import _secret
    return hmac.new(_secret(), s.encode(), hashlib.sha256).hexdigest()[:32]


def today() -> dt.date:
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(CENTRAL)).date()


def _notify_to() -> list[str]:
    return [a.strip() for a in env().get("LINKEDIN_NOTIFY", REPORT_TO).split(",") if a.strip()]


def _owner_senders() -> set[str]:
    return {a.lower() for a in _notify_to()} | {a.strip().lower() for a in env().get(
        "LINKEDIN_OWNER_EMAILS", "michael@furp.org,mfolenick@gmail.com").split(",") if a.strip()}


def _email(subject: str, text: str, reply_to: str | None = None) -> bool:
    """A LinkedIn update for the owner, in the daily batch (mailer.send_digest)."""
    return mailer.notify_owner("LinkedIn", subject, text, reply_to=reply_to)


def _alert(subject: str, text: str) -> bool:
    """A failure: queued like any update, then the batch is sent right away so the owner hears the same morning
    (a failure at 08:30 or later otherwise waited for the next day's 07:00 email; 2026-10-25)."""
    queued = _email(subject, text)
    try:
        sent = mailer.send_digest(status=lambda m: None)
    except Exception as ex:  # noqa: BLE001 - the notice stays queued for the next daily email
        log.warning("linkedin: alert not sent now: %s", type(ex).__name__)
        sent = False
    print(f"linkedin: alert {'sent' if sent else 'queued (send failed)' if queued else 'NOT queued'}: {subject}")
    return sent


# --- OAuth -----------------------------------------------------------------------------------------------------

@router.get("/linkedin/connect", include_in_schema=False)
def connect(key: str = ""):
    e = env()
    if not e.get("LINKEDIN_CLIENT_ID") or not e.get("LINKEDIN_ADMIN_KEY") \
            or not hmac.compare_digest(key, e["LINKEDIN_ADMIN_KEY"]):
        return _page("Private link", "<p>This link needs its private key. Use the full connect link from the "
                                     "setup email or message.</p>", 403)
    ts = str(int(time.time()))
    return RedirectResponse(AUTH_URL + "?" + urlencode({
        "response_type": "code", "client_id": e["LINKEDIN_CLIENT_ID"], "redirect_uri": REDIRECT,
        "state": f"{ts}.{_sign(ts)}", "scope": SCOPES}), status_code=302)


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><meta name=robots content=noindex>"
                        f"<title>{title} | furp.org</title><link rel=stylesheet href=/static/style.css>"
                        f"<main style='max-width:640px;margin:2em auto;padding:0 16px'><h1>{title}</h1>{body}</main>",
                        status_code=status)


@router.get("/linkedin/callback", include_in_schema=False)
def callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    import html as _html
    if error:
        log.warning("linkedin: connect refused: %s %s", error, error_description[:300])   # kept for diagnosis
        _email("LinkedIn connect failed", f"LinkedIn refused the connection: {error}: {error_description}\n")
        return _page("LinkedIn not connected", f"<p>LinkedIn said: {_html.escape(error)} "
                                               f"{_html.escape(error_description)}</p>", 400)
    if not code or not state:
        return _page("Missing code", "<p>LinkedIn sends you here with a code after you approve the connection. "
                                     "This visit had none: start from the connect link.</p>", 400)
    ts, _, sig = state.partition(".")
    if not ts.isdigit() or not hmac.compare_digest(sig, _sign(ts)) or time.time() - int(ts) > 900:
        return _page("Link expired", "<p>This sign-in wasn't started here, or took more than 15 minutes. Start "
                                     "again from the connect link.</p>", 400)
    e = env()
    r = httpx.post(TOKEN_URL, timeout=30, data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": e["LINKEDIN_CLIENT_ID"], "client_secret": e["LINKEDIN_CLIENT_SECRET"]})
    if r.status_code != 200:
        log.warning("linkedin: token exchange %s", r.status_code)
        return _page("LinkedIn not connected", f"<p>The token exchange failed (HTTP {r.status_code}).</p>", 502)
    tok = r.json()
    me = httpx.get(USERINFO_URL, timeout=30, headers={"Authorization": f"Bearer {tok['access_token']}"})
    if me.status_code != 200:
        return _page("LinkedIn not connected", f"<p>Reading your profile failed (HTTP {me.status_code}).</p>", 502)
    info = me.json()
    expires = int(time.time()) + int(tok.get("expires_in") or 0)
    updates = {"LINKEDIN_ACCESS_TOKEN": tok["access_token"], "LINKEDIN_TOKEN_EXPIRES": str(expires),
               "LINKEDIN_PERSON_ID": info["sub"]}
    if tok.get("refresh_token"):            # kept so check_token can renew it (a reconnect replaces the old one)
        updates["LINKEDIN_REFRESH_TOKEN"] = tok["refresh_token"]
    if not e.get("LINKEDIN_REVIEW_UNTIL"):
        updates["LINKEDIN_REVIEW_UNTIL"] = (today() + dt.timedelta(days=REVIEW_DAYS)).isoformat()
    set_env(updates)
    when = dt.datetime.fromtimestamp(expires).strftime("%B %-d, %Y")
    return _page("LinkedIn connected", f"<p>Connected as <strong>{info.get('name', 'you')}</strong>. "
                                       f"The connection lasts until {when}; you'll get an email a week and a day "
                                       f"before, with the link to reconnect.</p><p>Daily posts start at 8:30 AM "
                                       f"Central. Until {env().get('LINKEDIN_REVIEW_UNTIL')} each draft is emailed "
                                       f"at 8:00 first.</p>")


# --- picking and writing the post ----------------------------------------------------------------------------

SYSTEM = """You write a short LinkedIn post for furp.org, a free public-records explorer, from searches that \
have already been run. You get candidates: each has an id, a question and DATA (the search's own results). Pick \
the 8 most surprising, specific and varied (different subjects and datasets), best first (the post uses the first 3 \
whose numbers check out), then write:
- hook: one line, plain and curious, no hashtags, no emoji, no exclamation marks, at most 90 characters, and \
never a count of the items (the post has three, not the number you pick);
- for each pick, a line of at most 140 characters stating one finding with its single most surprising number.
Use only numbers that appear in that candidate's DATA, written the way DATA has them or rounded (e.g. $1.2 \
million). Don't work out new numbers (multiples, ratios, percentages, differences) unless DATA has them. Write names in normal capitalization (William H. Gates III, not WILLIAM H GATES III). Never use an em dash. No links, no hashtags (they're added after)."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["hook", "items"], "properties": {
    "hook": {"type": "string"},
    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                         "required": ["id", "line"],
                                         "properties": {"id": {"type": "integer"}, "line": {"type": "string"}}}}}}


NO_REPEAT_DAYS = 182          # an insight posted to LinkedIn isn't posted again for six months (owner, 2026-10-23)


def used_key(url: str, question: str) -> tuple[str, str]:
    """What makes two insights the same: the search behind it (its URL without the question text) and the
    question in plain words, either one. Nightly pools make new ids for old questions, so ids can't be used."""
    from urllib.parse import parse_qsl, urlencode, urlsplit
    u = urlsplit(url or "")
    search = u.path + "?" + urlencode(sorted((k, v) for k, v in parse_qsl(u.query) if k not in ("q", "id") and not k.startswith("utm_")))
    return search, re.sub(r"[^a-z0-9]+", " ", (question or "").lower()).strip()


def recently_posted(days: int = NO_REPEAT_DAYS) -> set[str]:
    """Keys (used_key) of every insight posted in the last `days` days."""
    with db.conn() as conn:
        rows = conn.execute("""SELECT items FROM linkedin_posts WHERE status = 'posted' AND items IS NOT NULL
                               AND day >= current_date - %s""", (days,)).fetchall()
    out = set()
    for r in rows:
        for it in r["items"] or []:
            out.update(used_key(it.get("url"), it.get("question")))
    return out


def candidates() -> tuple[dt.date | None, list[dict]]:
    """The day's pool, each idea run: [{id, question, url, data}] (only ideas whose search returns rows, and none
    posted in the last six months)."""
    from app import answer, ask, ideas
    day, items = ideas.pool_items()
    used = recently_posted()
    items = [x for x in items if not used & set(used_key(x["url"], x["question"]))]
    if not items:
        return day, []
    with db.conn() as conn:
        intents = {r["id"]: r["intent"] for r in conn.execute("SELECT id, intent FROM home_ideas WHERE id = ANY(%s)",
                                                              ([x["id"] for x in items],)).fetchall()}
    out = []
    for x in items:
        try:
            res = ask.run_page({**intents[x["id"]]}, 1)
            data, _ = answer.data_for(res)
        except Exception:  # noqa: BLE001 - a search that fails is not a candidate
            continue
        if data and (data.get("rows") or data.get("summary") or len(json.dumps(data, default=str)) > 200):
            out.append({**x, "data": data})
    return day, out


COUNT_WORDS = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s+(things|finds|"
                         r"facts|insights|surprises|numbers|records|findings)\b", re.I)
FALLBACK_HOOK = "Three things in public records today"
POST_ITEMS = 3      # insights in every post: exactly three, never more or fewer (owner, 2026-10-25; was five)


def _ask(cands: list[dict]) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    listing = "\n\n".join(f"id {c['id']}: {c['question']}\nDATA: {json.dumps(c['data'], default=str)[:2000]}"
                          for c in cands)
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=300, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 16000, "system": SYSTEM,
              "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
              "messages": [{"role": "user", "content": listing}]})
    if r.status_code != 200:
        raise RuntimeError(f"model call failed: HTTP {r.status_code}")
    return json.loads("".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text"))


HOOK_SYSTEM = """You write the one-line hook that opens a LinkedIn post for furp.org, a free public-records \
explorer. You get the post's three finding lines. The hook must fit all three exactly as they are: name only what \
they really have in common (if one is about lobbying, a company or a patent, don't call them all nonprofit tax \
filings; if they share no subject, say what they share, such as public records). Plain and curious, at most 90 \
characters, no time words (last year, this week, recently: the filings span years), no numbers, never a count of the items (not "three things", "3 finds"), no hashtags, no emoji, no exclamation marks, no em dash, no links."""
HOOK_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["hook"],
               "properties": {"hook": {"type": "string"}}}


def _hook(lines: list[str]) -> str:
    """The hook, written for the post's final lines (owner, 2026-10-25: the intro must make sense given the items;
    the first call's hook was written for its eight picks, before any were dropped). "" if the call fails."""
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
            "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01",
            "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 2000, "system": HOOK_SYSTEM,
                  "output_config": {"format": {"type": "json_schema", "schema": HOOK_SCHEMA}},
                  "messages": [{"role": "user", "content": "\n".join(f"- {x}" for x in lines)}]})
        if r.status_code != 200:
            return ""
        text = "".join(c.get("text", "") for c in r.json().get("content", []) if c.get("type") == "text")
        return (json.loads(text).get("hook") or "").strip()
    except Exception:  # noqa: BLE001 - the first call's hook, checked the same way, is used instead
        return ""


def compose(cands: list[dict]) -> dict | None:
    """{hook, items: [{id, question, url, line}]}: exactly POST_ITEMS lines, every number checked against the
    search's own data, or None. A line whose numbers don't check out is dropped and, if that leaves fewer than
    POST_ITEMS, the model is asked again with the candidates not yet used."""
    from app import answer
    if not os.environ.get("ANTHROPIC_API_KEY") or len(cands) < POST_ITEMS:
        return None
    by_id = {c["id"]: c for c in cands}
    picks, tried, hook = [], set(), ""
    for _ in range(2):
        left = [c for c in cands if c["id"] not in tried]
        if len(left) < POST_ITEMS - len(picks):
            break
        reply = _ask(left)
        hook = hook or answer.no_em_dash((reply.get("hook") or "").strip())
        for it in reply.get("items", []):
            c = by_id.get(it.get("id"))
            if not c or c["id"] in tried:
                continue
            tried.add(c["id"])
            line = answer.no_em_dash((it.get("line") or "").strip())
            if line and not LINKISH.search(line) and answer.numbers_ok(line, c["data"]) and len(picks) < POST_ITEMS:
                picks.append({"id": c["id"], "question": c["question"], "url": c["url"], "line": line})
        if len(picks) == POST_ITEMS:
            break
    if len(picks) == POST_ITEMS:
        for _ in range(2):                                   # once more if it counted the items anyway
            fit = answer.no_em_dash(_hook([x["line"] for x in picks]))
            if fit and not COUNT_WORDS.search(fit) and not re.search(r"\d", fit):
                hook = fit
                break
    if COUNT_WORDS.search(hook) or LINKISH.search(hook):    # "Eight things...": the post has three; no links
        hook = FALLBACK_HOOK
    if len(picks) != POST_ITEMS or not hook or re.search(r"\d", hook) and not answer.numbers_ok(hook, {"c": [c["data"] for c in cands]}):
        return None
    return {"hook": hook, "items": picks}


_LITTLE = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def little_text(s: str) -> str:
    """LinkedIn's post commentary is "little text": these characters must be escaped to show as written."""
    return _LITTLE.sub(r"\\\1", s)


BASE_TAGS = ["PublicRecords", "OpenData"]
# Hashtags by the front-page theme of each insight in the post (app/ideas.theme), owner 2026-10-23.
THEME_TAGS = {"Pay": ["Nonprofits", "ExecutivePay"], "Money and grants": ["Philanthropy", "Nonprofits"],
              "Politics and lobbying": ["Lobbying", "CampaignFinance"], "Schools and loans": ["HigherEd", "StudentLoans"],
              "Companies and recalls": ["Investing", "CorporateGovernance"]}
MAX_TAGS = 5


def hashtags(items: list[dict]) -> list[str]:
    """Up to MAX_TAGS hashtags: #PublicRecords and #OpenData, then the topics of the day's insights (most common first)."""
    from collections import Counter
    from app import ideas
    themes = Counter()
    try:
        with db.conn() as conn:
            for r in conn.execute("SELECT intent FROM home_ideas WHERE id = ANY(%s)", ([x["id"] for x in items],)).fetchall():
                themes[ideas.theme(r["intent"])] += 1
    except Exception:  # noqa: BLE001
        pass
    tags = list(BASE_TAGS)
    for t, _ in themes.most_common():
        for tag in THEME_TAGS.get(t, []):
            if tag not in tags:
                tags.append(tag)
    tags.append("DataJournalism") if "DataJournalism" not in tags else None
    return tags[:MAX_TAGS]


def commentary(text: str) -> str:
    """The post text as LinkedIn "little text": everything escaped, except hashtags, which become real hashtags."""
    tags = re.findall(r"(?<!\S)#([A-Za-z][A-Za-z0-9]*)", text)
    out = little_text(re.sub(r"(?<!\S)#([A-Za-z][A-Za-z0-9]*)", lambda m: f"\x00{tags.index(m.group(1))}\x00", text))
    return re.sub(r"\x00(\d+)\x00", lambda m: "{hashtag|\\#|" + tags[int(m.group(1))] + "}", out)


def render_post(d: dict) -> tuple[str, str]:
    """(post text, first comment). The post: INTRO, the hook, the items as plain text and the hashtags, with no
    links at all. The first comment: the FURP link on top, then one short line per item with its link (owner,
    2026-10-25)."""
    body = (INTRO + "\n\n" + d["hook"] + "\n\n" + "\n".join(f"- {x['line']}" for x in d["items"]) + "\n\n" + CLOSER
            + "\n\n" + " ".join(f"#{t}" for t in hashtags(d["items"])))
    lines = [f"{i + 1}. {x['question']} {SITE_URL}{x['url']}{'&' if '?' in x['url'] else '?'}{UTM}"
             for i, x in enumerate(d["items"])]
    comment = f"{SITE_URL}/?{UTM}\n" + "\n".join(lines)
    return body, comment


# --- the daily jobs --------------------------------------------------------------------------------------------

def _row(day: dt.date) -> dict | None:
    with db.conn() as conn:
        return conn.execute("SELECT * FROM linkedin_posts WHERE day = %s", (day,)).fetchone()


def _save(day: dt.date, **cols) -> None:
    # An existing day is updated in place: INSERT ... ON CONFLICT checks NOT NULL on the would-be new row first, so
    # saving only an error (no status) on a posted day failed and stopped the run before its email (2026-10-25).
    names = list(cols)
    vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in cols.values()]
    with db.conn() as conn:
        n = conn.execute(f"UPDATE linkedin_posts SET {', '.join(f'{c} = %s' for c in names)} WHERE day = %s",
                         [*vals, day]).rowcount
        if not n:
            conn.execute(f"""INSERT INTO linkedin_posts (day, {', '.join(names)}) VALUES (%s, {', '.join(['%s'] * len(names))})
                             ON CONFLICT (day) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in names)}""",
                         [day, *vals])


def in_review(day: dt.date | None = None) -> bool:
    until = env().get("LINKEDIN_REVIEW_UNTIL")
    return bool(until) and (day or today()) <= dt.date.fromisoformat(until)


def refresh_token(status=print) -> bool:
    """A new access token from the refresh token (LinkedIn: refresh tokens last a year). True when saved."""
    e = env()
    if not e.get("LINKEDIN_REFRESH_TOKEN"):
        return False
    try:
        r = httpx.post(TOKEN_URL, timeout=30, data={
            "grant_type": "refresh_token", "refresh_token": e["LINKEDIN_REFRESH_TOKEN"],
            "client_id": e["LINKEDIN_CLIENT_ID"], "client_secret": e["LINKEDIN_CLIENT_SECRET"]})
    except httpx.HTTPError as ex:
        status(f"linkedin: token refresh failed: {type(ex).__name__}")
        return False
    if r.status_code != 200:
        status(f"linkedin: token refresh failed: HTTP {r.status_code} {r.text[:200]}")
        return False
    tok = r.json()
    updates = {"LINKEDIN_ACCESS_TOKEN": tok["access_token"],
               "LINKEDIN_TOKEN_EXPIRES": str(int(time.time()) + int(tok.get("expires_in") or 0))}
    if tok.get("refresh_token"):
        updates["LINKEDIN_REFRESH_TOKEN"] = tok["refresh_token"]
    set_env(updates)
    status("linkedin: access token refreshed")
    return True


def check_token(status=print) -> None:
    """Two weeks before the access token expires, refresh it; if that fails, email the reconnect link a week and
    a day before."""
    e = env()
    exp = int(e.get("LINKEDIN_TOKEN_EXPIRES") or 0)
    if not exp:
        return
    days = (dt.date.fromtimestamp(exp) - today()).days
    if days <= 14 and refresh_token(status):
        return
    if days in (7, 1):
        _email(f"LinkedIn posting stops in {days} day{'s' if days != 1 else ''}: reconnect",
               f"The LinkedIn connection for the daily FURP posts expires on "
               f"{dt.date.fromtimestamp(exp):%B %-d, %Y}. Reconnect here (it takes a minute):\n\n{connect_link()}\n")
        status(f"linkedin: expiry reminder sent ({days} days)")


def draft(status=print) -> dict | None:
    """Build today's post (every day); during the review period, email it to the owner."""
    day = today()
    check_token(status)
    row = _row(day)
    if row and row["status"] in ("draft", "skipped", "posted"):
        return row
    cands = []
    try:
        pool_day, cands = candidates()
        d = compose(cands)
    except Exception as ex:  # noqa: BLE001
        d, err = None, f"{type(ex).__name__}: {ex}"[:500]
    else:
        err = None if d else (f"couldn't write {POST_ITEMS} insights with checked numbers from {len(cands)} candidates")
    if not d:
        _save(day, status="failed", error=err, drafted_at=dt.datetime.now(dt.timezone.utc))
        _alert("LinkedIn post not drafted today", f"Today's LinkedIn post wasn't drafted: {err}\nNothing will be posted.")
        status(f"linkedin: draft failed: {err}")
        return None
    text, comment = render_post(d)
    _save(day, status="draft", text=text, comment=comment, items=d["items"], drafted_at=dt.datetime.now(dt.timezone.utc))
    if in_review(day):
        token = _sign(f"skip:{day.isoformat()}")
        inbound = _inbound_address()
        _email(f"LinkedIn draft for {day:%A, %B %-d}: posts at 8:30 unless you skip",
               f"This posts to your LinkedIn at 8:30 AM Central. To stop it, reply \"skip\""
               f"{'' if inbound else ' (replies are not set up yet; use the link)'} or press Skip here:\n"
               f"{SITE_URL}/linkedin/skip?d={day.isoformat()}&t={token}\n\n--- POST ---\n{text}\n\n--- FIRST COMMENT ---\n"
               f"{comment}\n", reply_to=inbound)
        status("linkedin: draft emailed for review")
    return _row(day)


def _versions() -> list[str]:
    """LinkedIn API versions to try, newest first: LINKEDIN_API_VERSION if set, then this month and the five before.
    LinkedIn retires a version after about a year (2026-10-23: 202509 answered "not active")."""
    d = today().replace(day=1)
    months = []
    for _ in range(6):
        months.append(f"{d:%Y%m}")
        d = (d - dt.timedelta(days=1)).replace(day=1)
    pinned = env().get("LINKEDIN_API_VERSION")
    return ([pinned] if pinned else []) + [m for m in months if m != pinned]


def _api_headers(token: str, version: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token}", "LinkedIn-Version": version or _versions()[0],
            "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}


def _api_post(url: str, token: str, body: dict) -> httpx.Response:
    """POST to LinkedIn's versioned API, stepping back a month while the version isn't active (HTTP 426)."""
    r = None
    for v in _versions():
        r = httpx.post(url, timeout=60, headers=_api_headers(token, v), json=body)
        if r.status_code != 426:
            break
    return r


def _comment(urn: str, token: str, author: str, text: str) -> httpx.Response:
    """The first comment, through the unversioned v2 endpoint: the versioned /rest one answers 403 for this app's
    w_member_social access, the v2 one accepts it (2026-10-25)."""
    return httpx.post(f"https://api.linkedin.com/v2/socialActions/{quote(urn, safe='')}/comments", timeout=60,
                      headers={"Authorization": f"Bearer {token}", "X-Restli-Protocol-Version": "2.0.0"},
                      json={"actor": author, "object": urn, "message": {"text": text}})


def draft_sent_at(day: dt.date | None = None) -> dt.datetime | None:
    """When the daily email carrying the day's LinkedIn draft went out (None: not yet). The day is the Central
    day: the database runs in UTC, and its current_date is already tomorrow after 7 PM Central."""
    with db.conn() as conn:
        return conn.execute("""SELECT max(sent_at) AS t FROM owner_notices WHERE topic = 'LinkedIn'
                               AND subject LIKE 'LinkedIn draft%%'
                               AND (created AT TIME ZONE %s)::date = %s""", (CENTRAL, day or today())).fetchone()["t"]


LAST_POST_HOUR = 11     # the last post run is 11:30 Central (deploy/cron/np-linkedin); not a new window


def _last_run() -> bool:
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo(CENTRAL)).hour >= LAST_POST_HOUR


def _not_posted(day: dt.date, why: str) -> None:
    """The last run of the morning and nothing went out: tell the owner (once a day)."""
    subject = "LinkedIn post not published today"
    with db.conn() as conn:
        if conn.execute("""SELECT 1 FROM owner_notices WHERE topic = 'LinkedIn' AND subject = %s
                           AND (created AT TIME ZONE %s)::date = %s""", (subject, CENTRAL, day)).fetchone():
            return
    _alert(subject, f"Nothing was posted to LinkedIn today ({day:%A, %B %-d}) by the last try at 11:30.\n\n{why}\n")


def post(status=print) -> None:
    """Post today's draft (drafting it first after the review period), then the first comment. Errors are
    emailed once; nothing is retried."""
    day = today()
    row = _row(day) or (draft(status) if not in_review(day) else None)
    if row and row["status"] == "draft" and in_review(day):
        # The draft goes out in the owner's daily email; give at least 30 minutes to skip after it has been sent,
        # then post it.
        sent = draft_sent_at(day)
        if not sent or (dt.datetime.now(dt.timezone.utc) - sent).total_seconds() < 1800:
            status("linkedin: draft not reviewed yet (daily email not sent, or under 30 minutes ago); trying again later")
            if _last_run():
                _not_posted(day, "The draft was ready, but the daily email carrying it " +
                            (f"only went out at {sent:%H:%M} UTC" if sent else "never went out") +
                            ", so the 30 minutes to skip it never passed before the last try.")
            return
    if not row or row["status"] != "draft":                 # skipped, already posted, failed, or no draft
        status(f"linkedin: nothing to post ({row['status'] if row else 'no draft'})")
        if not row and _last_run():                         # failed days were alerted when they failed
            _not_posted(day, "There was no draft for today: the 06:45 draft run didn't save one (see "
                             "/var/log/np-explorer/linkedin.log on the server).")
        return
    e = env()
    token, person = e.get("LINKEDIN_ACCESS_TOKEN"), e.get("LINKEDIN_PERSON_ID")
    exp = int(e.get("LINKEDIN_TOKEN_EXPIRES") or 0)
    if not token or not person or exp < time.time():
        _fail(day, "LinkedIn isn't connected (or the connection expired). Reconnect: " + connect_link())
        return
    author = f"urn:li:person:{person}"
    try:
        r = _api_post(POSTS_URL, token, {
            "author": author, "commentary": commentary(row["text"]), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False})
        if r.status_code not in (200, 201):
            _fail(day, f"The post failed: HTTP {r.status_code} {r.text[:500]}")
            return
    except httpx.HTTPError as ex:
        _fail(day, f"LinkedIn didn't answer: {type(ex).__name__}")
        return
    urn = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id")
    _save(day, status="posted", post_urn=urn, posted_at=dt.datetime.now(dt.timezone.utc))
    status(f"linkedin: posted {urn}")
    # From here the post is live: a comment problem never marks the day failed (it would also let the same
    # insights be posted again, as recently_posted counts only posted days).
    link = f"https://www.linkedin.com/feed/update/{urn}/" if urn else "(LinkedIn didn't return its id)"
    if not row.get("comment"):
        return                                              # links are in the post (no first comment)
    try:
        if not urn:
            raise RuntimeError("LinkedIn didn't return the post's id, so the comment couldn't be attached")
        c = _comment(urn, token, author, row["comment"])
        err = None if c.status_code in (200, 201) else f"HTTP {c.status_code} {c.text[:500]}"
    except (httpx.HTTPError, RuntimeError) as ex:
        c, err = None, f"{type(ex).__name__}: {ex}"[:500]
    if err:
        _alert("LinkedIn post up, first comment failed",
               f"Today's post is up: {link}\nbut the links comment failed: {err}\n"
               f"Add it by hand if you like:\n\n{row['comment']}\n")
        _save(day, error=f"comment failed: {err[:300]}")
    else:
        _save(day, comment_urn=c.headers.get("x-restli-id") or (c.json() or {}).get("$URN"))


def post_now(status=print) -> str | None:
    """An extra post right now, built like the daily one from insights not yet posted. Its items are added to
    today's row so they aren't posted again; returns the post's link."""
    day = today()
    e = env()
    token, person = e.get("LINKEDIN_ACCESS_TOKEN"), e.get("LINKEDIN_PERSON_ID")
    if not token or not person or int(e.get("LINKEDIN_TOKEN_EXPIRES") or 0) < time.time():
        status("linkedin: not connected: " + connect_link())
        return None
    _, cands = candidates()
    d = compose(cands)
    if not d:
        status(f"linkedin: couldn't write {POST_ITEMS} checked insights from {len(cands)} candidates")
        return None
    text, comment = render_post(d)
    r = _api_post(POSTS_URL, token, {
        "author": f"urn:li:person:{person}", "commentary": commentary(text), "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False})
    if r.status_code not in (200, 201):
        status(f"linkedin: the post failed: HTTP {r.status_code} {r.text[:300]}")
        return None
    urn = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id")
    row = _row(day)
    if row:
        _save(day, items=(row.get("items") or []) + d["items"])
    else:
        _save(day, status="posted", text=text, comment="", items=d["items"], post_urn=urn,
              posted_at=dt.datetime.now(dt.timezone.utc))
    link = f"https://www.linkedin.com/feed/update/{urn}/"
    c = _comment(urn, token, f"urn:li:person:{person}", comment)
    status(f"linkedin: posted now {urn} {link}; links comment HTTP {c.status_code}")
    return link


def _fail(day: dt.date, err: str) -> None:
    _save(day, status="failed", error=err)
    _alert("LinkedIn post failed today", f"Today's FURP post was not published.\n\n{err}\n\nIt won't be retried.")
    log.warning("linkedin: %s", err[:200])


# --- skipping: a button on a page (link scanners don't press buttons), or a reply "skip" ---------------------------

@router.get("/linkedin/skip", include_in_schema=False)
def skip_page(d: str = "", t: str = ""):
    if not hmac.compare_digest(t, _sign(f"skip:{d}")):
        raise HTTPException(404)
    row = _row(dt.date.fromisoformat(d))
    state = row["status"] if row else "none"
    if state != "draft":
        return _page("LinkedIn post", f"<p>Today's post is {state}; nothing to skip.</p>")
    return _page("Skip today's LinkedIn post?", f"<form method=post action=/linkedin/skip><input type=hidden name=d "
                                                f"value={d}><input type=hidden name=t value={t}><button "
                                                f"type=submit>SKIP TODAY'S POST</button></form>")


@router.post("/linkedin/skip", include_in_schema=False)
async def skip_submit(request: Request):
    from urllib.parse import parse_qs
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode()[:500]).items()}
    d, t = form.get("d", ""), form.get("t", "")
    if not hmac.compare_digest(t, _sign(f"skip:{d}")):
        raise HTTPException(404)
    row = _row(dt.date.fromisoformat(d))
    if row and row["status"] == "draft":
        _save(row["day"], status="skipped", skipped_by="button")
        return _page("Skipped", "<p>Today's LinkedIn post won't go out.</p>")
    return _page("LinkedIn post", f"<p>Today's post is {row['status'] if row else 'not drafted'}; nothing changed.</p>")


def _inbound_address() -> str | None:
    """The Postmark server's inbound address, if replies are wired to /linkedin/inbound."""
    tok = os.environ.get("POSTMARK_SERVER_TOKEN") or env().get("POSTMARK_SERVER_TOKEN")
    try:
        d = httpx.get("https://api.postmarkapp.com/server", timeout=20, headers={
            "X-Postmark-Server-Token": tok, "Accept": "application/json"}).json()
    except Exception:  # noqa: BLE001
        return None
    return d.get("InboundAddress") if "/linkedin/inbound" in (d.get("InboundHookUrl") or "") else None


@router.post("/linkedin/inbound", include_in_schema=False)
async def inbound(request: Request, key: str = ""):
    """Postmark inbound webhook: a reply "skip" from the owner skips today's draft."""
    if not env().get("LINKEDIN_INBOUND_KEY") or not hmac.compare_digest(key, env()["LINKEDIN_INBOUND_KEY"]):
        raise HTTPException(404)
    msg = await request.json()
    sender = ((msg.get("FromFull") or {}).get("Email") or msg.get("From") or "").lower()
    reply = (msg.get("StrippedTextReply") or msg.get("TextBody") or "")[:2000]
    day = today()
    row = _row(day)
    if sender in _owner_senders() and re.search(r"\bskip\b", reply, re.I) and row and row["status"] == "draft":
        _save(day, status="skipped", skipped_by=f"reply from {sender}")
        mailer.notify_owner("LinkedIn", "Post skipped today", f"Today's post won't go out (reply from {sender}).")
    return JSONResponse({"ok": True})


def clicks(conn, start, end) -> dict:
    """LinkedIn clicks for the usage report: page views tagged utm_source=linkedin."""
    rows = conn.execute("""SELECT path, visitor_id FROM events WHERE name = 'page' AND ts >= %s AND ts < %s
                           AND meta->>'utm_source' = 'linkedin' AND ua_class = 'human'""", (start, end)).fetchall()
    from collections import Counter
    return {"clicks": len(rows), "visitors": len({r["visitor_id"] for r in rows}),
            "top_pages": Counter(r["path"] for r in rows).most_common(5)}


if __name__ == "__main__":
    db.pool.open(wait=True)
    cmd = sys.argv[1:2] or ["status"]
    if cmd in (["draft"], ["post"]):
        def stamped(m: str) -> None:            # the log had no times, which made the runs hard to tell apart
            print(f"{dt.datetime.now():%Y-%m-%d %H:%M} {m}", flush=True)
        try:
            draft(stamped) if cmd == ["draft"] else post(stamped)
        except Exception as ex:  # noqa: BLE001 - a crash (2026-10-25: NOT NULL on save) must not be silent
            stamped(f"linkedin: {cmd[0]} crashed")
            _alert(f"LinkedIn {cmd[0]} run crashed", f"The {cmd[0]} run of today's LinkedIn post stopped with "
                   f"{type(ex).__name__}: {str(ex)[:500]}\n\nToday's state: {(_row(today()) or {}).get('status', 'no row')}. "
                   f"Details: /var/log/np-explorer/linkedin.log on the server.\n")
            raise
    elif cmd == ["post-now"]:
        post_now()
    else:
        e = env()
        print({"connected": bool(e.get("LINKEDIN_ACCESS_TOKEN")), "expires": e.get("LINKEDIN_TOKEN_EXPIRES"),
               "review_until": e.get("LINKEDIN_REVIEW_UNTIL"), "connect": connect_link()})
