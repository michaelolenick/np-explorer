"""Outgoing email helpers: the furp.org sender with a fallback, and the temporary rename note.

Mail goes out from @furp.org addresses. Until Postmark has verified furp.org as a sender, it rejects those with a
sender-signature error; the same message is then sent again from the same mailbox at the old domain
(FALLBACK_DOMAIN), so nothing is lost and the switch happens by itself once furp.org is verified.

Every email we send to readers ends with RENAME_NOTE ("furp.org is the new name of Strategy Studio") until
RENAME_NOTE_UNTIL, two weeks after the rename (owner, 2026-10-21); after that it is dropped automatically.
"""

from __future__ import annotations

import datetime as dt
import html

SEND_DOMAIN = "furp.org"
FALLBACK_DOMAIN = "strategystudio.org"
RENAME_NOTE = "furp.org is the new name of Strategy Studio."
RENAME_NOTE_UNTIL = dt.date(2026, 11, 4)


def address(local: str, name: str | None = None) -> str:
    a = f"{local}@{SEND_DOMAIN}"
    return f"{name} <{a}>" if name else a


def is_signature_error(body) -> bool:
    return isinstance(body, dict) and "signature" in str(body.get("Message", "")).lower()


def fallback(payload: dict) -> dict:
    """The same message from the old domain."""
    return {**payload, "From": payload["From"].replace(f"@{SEND_DOMAIN}", f"@{FALLBACK_DOMAIN}")}


def rename_note(today: dt.date | None = None) -> str:
    return RENAME_NOTE if (today or dt.date.today()) <= RENAME_NOTE_UNTIL else ""


def rename_note_text(today: dt.date | None = None) -> str:
    n = rename_note(today)
    return f"\n{n}\n" if n else ""


def rename_note_html(today: dt.date | None = None) -> str:
    n = rename_note(today)
    return f"<p style=\"font-size:12px\">{html.escape(n)}</p>" if n else ""


def send(payload: dict, timeout: float = 20) -> bool:
    """One message through Postmark's API, resent from the old domain on a sender-signature error. True when
    Postmark accepted it. Logs status and error code only."""
    import logging
    import os
    import httpx
    token = os.environ.get("POSTMARK_SERVER_TOKEN")
    if not token:
        return False
    headers = {"X-Postmark-Server-Token": token, "Accept": "application/json", "Content-Type": "application/json"}
    try:
        r = httpx.post("https://api.postmarkapp.com/email", json=payload, timeout=timeout, headers=headers)
        body = r.json() if r.content else {}
        if r.status_code != 200 and is_signature_error(body):
            r = httpx.post("https://api.postmarkapp.com/email", json=fallback(payload), timeout=timeout, headers=headers)
            body = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        logging.getLogger("np.mailer").warning("mail: %s", type(e).__name__)
        return False
    if r.status_code != 200 or body.get("ErrorCode"):
        logging.getLogger("np.mailer").warning("mail: postmark %s code %s", r.status_code, body.get("ErrorCode"))
        return False
    return True
