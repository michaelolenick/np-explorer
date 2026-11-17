"""OpenRouter only with the owner's say-so (owner, 2026-11-17: "if you ever need to fall back to openrouter do NOT do it
automatically. ALWAYS ask").

No code path may call OpenRouter unless `allowed()` is true. The approval is a file the owner (or Claude, after the
owner says yes in chat) writes: ~/furp-config/openrouter_ok.txt containing `until YYYY-MM-DD` (server date, inclusive).
Write today's date for a one-day yes; a past date, a missing file or anything else means no. When something needs
OpenRouter and has no approval, `ask_owner(what)` emails mfolenick@gmail.com (once a day per reason) and the caller
shows or logs that the owner was asked; nothing is retried through OpenRouter in the meantime.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path

log = logging.getLogger("np.llm")
OWNER = "mfolenick@gmail.com"


def _dir() -> Path:
    return Path(os.environ.get("OPENROUTER_APPROVAL_DIR", "~/furp-config")).expanduser()


def allowed(today: date | None = None) -> bool:
    """True only while openrouter_ok.txt says `until <date>` and that date has not passed."""
    try:
        text = (_dir() / "openrouter_ok.txt").read_text()
    except OSError:
        return False
    m = re.search(r"until\s+(\d{4}-\d{2}-\d{2})", text)
    if not m:
        return False
    try:
        return (today or date.today()) <= date.fromisoformat(m.group(1))
    except ValueError:
        return False


def ask_owner(what: str) -> bool:
    """Email the owner once a day (per reason) asking to approve OpenRouter. True when an email went out."""
    day = date.today().isoformat()
    key = re.sub(r"[^a-z0-9]+", "-", what.lower())[:40].strip("-") or "llm"
    marker = _dir() / f"openrouter_asked_{day}_{key}.txt"
    try:
        if marker.exists():
            return False
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(what)
    except OSError:
        return False
    log.warning("llm: OpenRouter needs the owner's approval (%s)", what)
    try:
        from app import mailer
        body = (f"Something on FURP needs OpenRouter and has no approval from you, so it was NOT sent there.\n\n"
                f"What: {what}\n\nTo approve for today, tell Claude \"approve OpenRouter today\" (it writes "
                f"~/furp-config/openrouter_ok.txt with `until {day}`). Until then the site answers with its error "
                f"and nothing goes to OpenRouter. This email comes at most once a day per reason.")
        return mailer.send({"From": mailer.address("alerts", "FURP"), "To": OWNER,
                            "Subject": "FURP: approve OpenRouter? (not used until you say yes)", "TextBody": body})
    except Exception:  # noqa: BLE001 - asking must never break a page
        log.exception("llm: approval email")
        return False
