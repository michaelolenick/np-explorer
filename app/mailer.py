"""Outgoing email helpers: the furp.org sender.

Mail goes out from @furp.org addresses through Postmark (furp.org verified 2026-10-22; the old-domain fallback is
gone).

The two-week rename note at the foot of emails was dropped on 2026-10-22 (owner: the old name appears nowhere
except to visitors arriving from the old domain).
"""

from __future__ import annotations

import datetime as dt
import html
import re

SEND_DOMAIN = "furp.org"


def address(local: str, name: str | None = None) -> str:
    a = f"{local}@{SEND_DOMAIN}"
    return f"{name} <{a}>" if name else a


def report_subject(summary: str) -> str:
    """Every update FURP sends the owner: "FURP Report: [very brief summary]" (owner, 2026-10-23)."""
    return f"FURP Report: {summary}"


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


# --- updates for the owner: one email a day (owner, 2026-10-23: "Send me email updates batched! Not individual.") ---

def notify_owner(topic: str, subject: str, body: str, reply_to: str | None = None) -> bool:
    """Queue an update for the owner's daily email (send_digest). topic groups it ("Site check", "LinkedIn", ...)."""
    import psycopg
    from app.config import DATABASE_URL
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=10) as conn:
            conn.execute("INSERT INTO owner_notices (topic, subject, body, reply_to) VALUES (%s, %s, %s, %s)",
                         (topic, subject[:300], body, reply_to))
        return True
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("np.mailer").warning("notice not queued: %s", type(e).__name__)
        return False


def send_digest(status=print) -> bool:
    """Everything queued for the owner, in one email: "FURP Report: N updates (date)" with a line per update, then
    each in full. A LinkedIn draft in the batch sets Reply-To to the LinkedIn reply address, so "skip" still works."""
    import psycopg
    from app.config import DATABASE_URL, REPORT_FROM, REPORT_TO
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute("""SELECT id, created, topic, subject, body, reply_to FROM owner_notices
                               WHERE sent_at IS NULL ORDER BY created""").fetchall()
        if not rows:
            status("digest: nothing to send")
            return True
        day = dt.date.today()
        # A check failing three nights running leads the subject: "FURP Report: 1 STUCK, 2 updates" (owner, 2026-10-28).
        stuck = sum(int(m.group(1)) for r in rows if (m := re.match(r"(\d+) STUCK\b", r[3] or "")))
        heads = [f"- {t}: {s}" for _, _, t, s, _, _ in rows]
        parts = [f"== {t}: {s} ==\n{b.strip()}\n" for _, _, t, s, b, _ in rows]
        text = (f"{len(rows)} update{'s' if len(rows) != 1 else ''} from furp.org\n\n" + "\n".join(heads) + "\n\n"
                + "\n".join(parts))
        payload = {"From": REPORT_FROM, "To": REPORT_TO,
                   "Subject": report_subject((f"{stuck} STUCK, " if stuck else "")
                                             + f"{len(rows)} update{'s' if len(rows) != 1 else ''}, {day:%B} {day.day}"),
                   "TextBody": text, "MessageStream": "outbound",
                   "HtmlBody": ('<pre style="font-family:\'Courier New\',Courier,monospace;font-size:13px;white-space:pre-wrap">'
                                + html.escape(text) + "</pre>")}
        reply = next((r[5] for r in rows if r[5]), None)
        if reply:
            payload["ReplyTo"] = reply
        if not send(payload, timeout=30):
            status("digest: send failed, kept for the next try")
            return False
        conn.execute("UPDATE owner_notices SET sent_at = now() WHERE id = ANY(%s)", ([r[0] for r in rows],))
    status(f"digest: sent {len(rows)} updates")
    return True


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["digest"]:
        send_digest()
