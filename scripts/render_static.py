#!/usr/bin/env python3
"""Render templates/ to static HTML in public/ for nginx to serve.

Stopgap until the FastAPI app renders the same templates with Jinja2.
Usage: .venv/bin/python scripts/render_static.py
"""

import os
import shutil
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
PUBLIC = ROOT / "public"

import sys

sys.path.insert(0, str(ROOT))
from app import boards, colleges  # noqa: E402
from app.fmt import current_year  # noqa: E402
from app.config import SITE_URL  # noqa: E402

# Shared template context. The FastAPI app should pass the same values.
CONTEXT = {
    "boards": boards,
    "colleges": colleges,   # the Data page lists which payroll states and years are loaded
    "current_year": current_year,
    "site_url": SITE_URL,   # from .env, so the dev box renders its own address
    "github_url": "https://github.com/michaelolenick/np-explorer",
    "info_email": "info@strategystudio.org",
    "corrections_email": "corrections@strategystudio.org",
    "asset_version": __import__("hashlib").sha1(
        b"".join((Path(__file__).resolve().parent.parent / "static" / n).read_bytes()
                 for n in ("style.css", "site.js"))).hexdigest()[:10],
}

# Not support.html: its donation forms depend on the app (Stripe keys, ?canceled=1), so the app always serves it.
PAGES = ["index.html", "about.html", "data.html", "privacy.html", "404.html", "500.html",
         "429.html"]


def main() -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    # Render into a temp dir, then swap it in so nginx never serves a half-written site.
    tmp = Path(tempfile.mkdtemp(prefix=".public-", dir=ROOT))
    try:
        for name in PAGES:
            html = env.get_template(name).render(**CONTEXT)
            (tmp / name).write_text(html, encoding="utf-8")
            print(f"rendered {name}")
        tmp.chmod(0o755)
        for f in tmp.iterdir():
            f.chmod(0o644)
        old = ROOT / ".public-old"
        if PUBLIC.exists():
            PUBLIC.rename(old)
        os.rename(tmp, PUBLIC)
        shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    print(f"wrote {len(PAGES)} pages to {PUBLIC}")


if __name__ == "__main__":
    main()
