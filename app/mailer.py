"""Outgoing email helpers: the furp.org sender.

Mail goes out from @furp.org addresses through Postmark (furp.org verified 2026-10-22; the old-domain fallback is
gone).

The two-week rename note at the foot of emails was dropped on 2026-10-22 (owner: the old name appears nowhere
except to visitors arriving from the old domain).
"""

from __future__ import annotations

import datetime as dt
import html

SEND_DOMAIN = "furp.org"


def address(local: str, name: str | None = None) -> str:
    a = f"{local}@{SEND_DOMAIN}"
    return f"{name} <{a}>" if name else a


def send(payload: dict, timeout: float = 20) -> bool:
    """One message through Postmark's API. True when Postmark accepted it. Logs status and error code only."""
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
    except Exception as e:  # noqa: BLE001
        logging.getLogger("np.mailer").warning("mail: %s", type(e).__name__)
        return False
    if r.status_code != 200 or body.get("ErrorCode"):
        logging.getLogger("np.mailer").warning("mail: postmark %s code %s", r.status_code, body.get("ErrorCode"))
        return False
    return True
