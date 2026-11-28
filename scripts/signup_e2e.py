"""Nightly end-to-end test of the email signup, with real delivery (owner, 2026-11-28).

The example.com test addresses "confirmed" without any email being delivered, so tests passed while real signups failed.
This signs up a real address (E2E_ADDRESS, default signup-test@furp.org) through the public forms exactly as a visitor
would: from a home page, an organization page and a result page, one after the other. For each it checks that the
address becomes active at once, that a welcome email is accepted and then DELIVERED (Postmark's own message status,
polled for a few minutes), and that the one-click unsubscribe works (the List-Unsubscribe POST a mail app sends), which
also resets the address for the next source and the next night. The outcome goes to the table signup_e2e; scripts/health.py
turns a failure, or a night without a run, into an urgent (STUCK) alert.

    .venv/bin/python scripts/signup_e2e.py [--address a@b.org] [--base https://furp.org]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGES = [("home", "/"), ("org", "/org/530196605"), ("results", "/search?q=red+cross+disaster")]
PM = "https://api.postmarkapp.com"


def form_fields(html: str) -> dict:
    m = re.search(r'<form[^>]*data-signup.*?</form>', html, re.S)
    f = m.group(0) if m else ""
    out = {}
    for name in ("src", "t"):
        v = re.search(rf'name="{name}"\s+value="([^"]*)"', f)
        out[name] = v.group(1) if v else ""
    return out


def run(address: str, base: str, status=print) -> tuple[bool, str]:
    from app import db
    db.pool.open(wait=True)
    token = os.environ.get("POSTMARK_SERVER_TOKEN", "")
    hdr = {"X-Postmark-Server-Token": token, "Accept": "application/json"}
    notes, ok = [], True
    ua = {"User-Agent": "furp.org signup e2e (owner test)"}
    with httpx.Client(timeout=30, headers=ua, follow_redirects=True) as c:
        for label, path in PAGES:
            step = f"{label}:"
            try:
                page = c.get(base + path)
                f = form_fields(page.text)
                if not f["t"] or not f["src"]:
                    notes.append(f"{step} no signup form on {path} (HTTP {page.status_code})")
                    ok = False
                    continue
                time.sleep(4)                                     # a person takes longer than the form's 3 second bot check
                t0 = time.time()
                r = c.post(base + "/get-ideas", data={"email": address, "src": f["src"], "t": f["t"], "website": ""},
                           headers={"X-FURP-Signup": "1"})
                if r.status_code != 200 or not r.json().get("ok"):
                    notes.append(f"{step} signup answered {r.status_code} {r.text[:80]}")
                    ok = False
                    continue
                with db.conn() as conn:
                    row = conn.execute("SELECT id, status, token FROM idea_subscribers WHERE email = %s", (address,)).fetchone()
                if not row or row["status"] != "active":
                    notes.append(f"{step} not active after signup ({row['status'] if row else 'no row'})")
                    ok = False
                    continue
                delivered = None
                for _ in range(24):                               # up to about 4 minutes
                    time.sleep(10)
                    with db.conn() as conn:
                        welcomed = conn.execute("SELECT 1 FROM idea_email_events WHERE subscriber_id = %s AND kind = 'welcome_sent' "
                                                "AND ts > to_timestamp(%s)", (row["id"], t0 - 5)).fetchone()
                    if not welcomed:
                        continue
                    m = httpx.get(PM + "/messages/outbound", headers=hdr, timeout=30,
                                  params={"count": 1, "offset": 0, "recipient": address, "tag": "welcome"}).json().get("Messages", [])
                    if m:
                        det = httpx.get(f"{PM}/messages/outbound/{m[0]['MessageID']}/details", headers=hdr, timeout=30).json()
                        types = [e["Type"] for e in det.get("MessageEvents", [])]
                        if "Delivered" in types:
                            delivered = True
                            break
                        if "Bounced" in types:
                            delivered = False
                            break
                if delivered is not True:
                    notes.append(f"{step} welcome email {'bounced' if delivered is False else 'not delivered within 4 minutes'}")
                    ok = False
                u = c.post(f"{base}/get-ideas/unsubscribe?t={row['token']}", content="List-Unsubscribe=One-Click",
                           headers={"content-type": "application/x-www-form-urlencoded"})
                with db.conn() as conn:
                    st = conn.execute("SELECT status FROM idea_subscribers WHERE email = %s", (address,)).fetchone()["status"]
                if u.status_code != 200 or st != "unsubscribed":
                    notes.append(f"{step} one-click unsubscribe failed (HTTP {u.status_code}, status {st})")
                    ok = False
                if delivered is True and st == "unsubscribed":
                    notes.append(f"{step} ok (active, welcome delivered, unsubscribed)")
            except Exception as e:  # noqa: BLE001
                notes.append(f"{step} {type(e).__name__}: {e}")
                ok = False
    detail = "; ".join(notes)
    with db.conn() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS signup_e2e (at timestamptz NOT NULL DEFAULT now(), ok boolean NOT NULL, detail text)")
        conn.execute("INSERT INTO signup_e2e (ok, detail) VALUES (%s, %s)", (ok, detail[:900]))
    status(("PASS " if ok else "FAIL ") + detail)
    return ok, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", default=os.environ.get("E2E_ADDRESS", "signup-test@furp.org"))
    ap.add_argument("--base", default=os.environ.get("SITE_URL", "https://furp.org"))
    a = ap.parse_args()
    ok, _ = run(a.address, a.base.rstrip("/"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
