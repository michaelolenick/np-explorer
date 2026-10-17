"""The contact form: validation, spam checks, and delivery through Postmark.

Nothing is stored. A message is emailed to us; only if Postmark fails is it
appended to logs/contact-failed.jsonl so it isn't lost.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import httpx

from app.config import INFO_EMAIL, ROOT

log = logging.getLogger("np-explorer.contact")

TOPICS = ["Correction or removal request", "Press", "Feedback", "Supporting the project", "Other"]
MAX_MESSAGE = 5000
MAX_LINKS = 2
MIN_SECONDS = 3            # faster than this is a bot
MAX_AGE = 24 * 3600        # a form older than a day must be reloaded
PER_HOUR = 5               # per IP, per worker process

POSTMARK_URL = "https://api.postmarkapp.com/email"
FAILED_LOG = ROOT / "logs" / "contact-failed.jsonl"

_EMAIL = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")
_LINK = re.compile(r"https?://|www\.", re.I)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _secret() -> bytes:
    return os.environ.get("CONTACT_FORM_SECRET", "").encode() or b"np-explorer-contact"


def issue_token(now: float | None = None) -> str:
    """A signed timestamp for the form's hidden field."""
    ts = str(int(now if now is not None else time.time()))
    sig = hmac.new(_secret(), ts.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{ts}.{sig}"


def token_age(token: str, now: float | None = None) -> float | None:
    """Seconds since the form was issued, or None when the token is missing or forged."""
    ts, _, sig = (token or "").partition(".")
    if not ts.isdigit():
        return None
    good = hmac.new(_secret(), ts.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig):
        return None
    return (now if now is not None else time.time()) - int(ts)


def _clean(v: str, limit: int) -> str:
    return _CONTROL.sub("", (v or "").replace("\r\n", "\n")).strip()[:limit + 1]


def validate(raw: dict) -> tuple[dict, list[str]]:
    """Trimmed form values and the problems a person should fix."""
    form = {
        "name": " ".join(_clean(raw.get("name", ""), 200).split()),
        "email": _clean(raw.get("email", ""), 254),
        "topic": _clean(raw.get("topic", ""), 100),
        "message": _clean(raw.get("message", ""), MAX_MESSAGE),
    }
    errors = []
    if not _EMAIL.match(form["email"]) or len(form["email"]) > 254:
        errors.append("Enter an email address we can reply to.")
    if form["topic"] not in TOPICS:
        errors.append("Choose a topic.")
    if not form["message"]:
        errors.append("Write a message.")
    elif len(form["message"]) > MAX_MESSAGE:
        errors.append(f"Keep the message under {MAX_MESSAGE:,} characters.")
    if len(form["name"]) > 200:
        errors.append("That name is longer than the form allows.")
    if len(_LINK.findall(form["message"])) > MAX_LINKS:
        errors.append(f"Please include no more than {MAX_LINKS} links.")
    return form, errors


def is_bot(raw: dict, now: float | None = None) -> bool:
    """Honeypot filled in, or the form came back too fast, too late, or unsigned."""
    if raw.get("website"):
        return True
    age = token_age(raw.get("t", ""), now)
    return age is None or age < MIN_SECONDS or age > MAX_AGE


class HourlyLimit:
    """At most `limit` sends per key in any hour (in memory, per worker)."""

    def __init__(self, limit: int = PER_HOUR, window: float = 3600) -> None:
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self.hits) > 50_000:
                for k in [k for k, v in self.hits.items() if not v]:
                    del self.hits[k]
            return True


def truncate_ip(ip: str) -> str:
    """The sender's network, not the address: IPv4 to /24, IPv6 to /48."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    bits = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{ip}/{bits}", strict=False))


def subject(form: dict) -> str:
    first = " ".join(form["message"].split())[:60]
    return f"[Strategy Studio] {form['topic']}: {first}"


def text_body(form: dict, sent_at: str, ip: str) -> str:
    return (f"Name: {form['name'] or '(not given)'}\n"
            f"Email: {form['email']}\n"
            f"Topic: {form['topic']}\n"
            f"Time: {sent_at}\n"
            f"Sender IP: {truncate_ip(ip)}\n"
            f"\n{form['message']}\n")


def send(form: dict, ip: str) -> bool:
    """Email the message to us through Postmark. On failure, keep it in the failed log."""
    sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "From": INFO_EMAIL,
        "To": INFO_EMAIL,
        "ReplyTo": form["email"],
        "Subject": subject(form),
        "TextBody": text_body(form, sent_at, ip),
        "MessageStream": "outbound",
    }
    token = os.environ.get("POSTMARK_SERVER_TOKEN", "")
    status, code = None, None
    if token:
        try:
            r = httpx.post(POSTMARK_URL, json=payload, timeout=10,
                           headers={"X-Postmark-Server-Token": token, "Accept": "application/json"})
            status = r.status_code
            try:
                code = r.json().get("ErrorCode")
            except ValueError:
                code = None
            if status == 200 and not code:
                log.info("contact form: postmark status 200")
                return True
        except httpx.HTTPError as e:
            status = type(e).__name__
    else:
        status = "no token configured"
    # Status and Postmark's error code only: never the token or the message.
    log.error("contact form: postmark failed (status %s, error code %s)", status, code)
    _save_failed(payload, sent_at)
    return False


def _save_failed(payload: dict, sent_at: str) -> None:
    FAILED_LOG.parent.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(FAILED_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps({"failed_at": sent_at, **payload}, ensure_ascii=False) + "\n")
    os.chmod(FAILED_LOG, 0o600)
