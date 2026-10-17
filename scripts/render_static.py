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

# Shared template context. The FastAPI app should pass the same values.
CONTEXT = {
    "site_url": "https://strategystudio.org",
    "github_url": "https://github.com/michaelolenick/np-explorer",
}

PAGES = ["index.html", "about.html", "data.html", "privacy.html", "404.html", "500.html"]


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
