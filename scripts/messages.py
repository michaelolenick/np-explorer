#!/usr/bin/env python3
"""Read messages sent through the site's contact form.

Usage:
  scripts/messages.py            new (unhandled) messages, oldest first
  scripts/messages.py --all      every message
  scripts/messages.py --done ID  mark a message handled
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from app.config import DATABASE_URL  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--done", type=int, metavar="ID")
    args = ap.parse_args()
    with psycopg.connect(DATABASE_URL) as conn:
        if args.done:
            conn.execute("UPDATE contact_messages SET handled = true WHERE id = %s", (args.done,))
            print(f"message {args.done} marked handled")
            return
        where = "" if args.all else "WHERE NOT handled"
        rows = conn.execute(f"SELECT id, created_at, name, email, subject, message, handled FROM contact_messages "
                            f"{where} ORDER BY created_at").fetchall()
    if not rows:
        print("no messages")
    for id_, at, name, email, subject, message, handled in rows:
        print(f"#{id_}  {at:%Y-%m-%d %H:%M}  {name} <{email}>{'  [handled]' if handled else ''}")
        if subject:
            print(f"Subject: {subject}")
        print(message.strip())
        print("-" * 60)


if __name__ == "__main__":
    main()
