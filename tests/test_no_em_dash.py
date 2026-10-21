"""No em dashes in user-facing text (owner, 2026-10-21): templates, static files, content, app strings (page text,
emails, leaderboard definitions) and a sample of rendered pages and emails. Use commas, colons, periods or parentheses."""

import datetime as dt
import re
from pathlib import Path

from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
EM = re.compile("—|&mdash;|&#8212;|&#x2014;", re.I)
SUFFIXES = (".html", ".js", ".css", ".py", ".yml", ".txt", ".svg", ".webmanifest")


def test_no_em_dash_in_source_text():
    files = [p for d in ("templates", "static", "content", "app") for p in (ROOT / d).rglob("*")
             if p.is_file() and p.suffix in SUFFIXES and "__pycache__" not in p.parts]
    bad = [f"{p.relative_to(ROOT)}:{i}" for p in files
           for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1) if EM.search(line)]
    assert not bad, "em dashes: " + ", ".join(bad[:20])


def test_no_em_dash_in_rendered_pages_and_emails():
    from app import main, reporters
    client = TestClient(main.app)
    for path in ("/", "/about", "/about/news", "/support", "/data", "/privacy", "/terms", "/contact", "/get-ideas",
                 "/more", "/boards", "/schools"):
        assert not EM.search(client.get(path).text), path
    ideas = [{"id": 1, "question": "Q?", "url": "/ask?intent=x"}]
    subject, text, body = reporters.render_email(ideas, "tok", dt.date(2026, 10, 21))
    assert not EM.search(subject + text + body)
