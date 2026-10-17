"""Nightly sitemap index: static pages, every organization and every person page.

Written to /data/sitemaps; nginx serves /sitemap.xml and /sitemaps/* from there.
"""

from __future__ import annotations

import gzip
import os
import shutil
from datetime import date
from xml.sax.saxutils import escape

from app.config import DATA_DIR, SITE_URL
from loader import db

PER_FILE = 50000
OUT = DATA_DIR / "sitemaps"
STATIC_PAGES = ["/", "/about", "/data", "/privacy", "/support", "/contact"]


def _write(path, urls):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            f.write(f"<url><loc>{escape(SITE_URL + u)}</loc></url>\n")
        f.write("</urlset>\n")


def run(status) -> None:
    status.phase = "sitemap"
    tmp = DATA_DIR / "sitemaps.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    files = []
    _write(tmp / "pages.xml.gz", STATIC_PAGES)
    files.append("pages.xml.gz")
    with db.connect() as conn:
        for kind, sql in (("org", "SELECT ein FROM organizations o WHERE latest_filing_year IS NOT NULL ORDER BY ein"),
                          ("person", "SELECT id FROM person_clusters ORDER BY id")):
            with conn.cursor(name=f"sitemap_{kind}") as cur:
                cur.itersize = PER_FILE
                cur.execute(sql)
                n = 0
                while rows := cur.fetchmany(PER_FILE):
                    n += 1
                    name = f"{kind}-{n:04d}.xml.gz"
                    _write(tmp / name, (f"/{kind}/{r[0]}" for r in rows))
                    files.append(name)
    today = date.today().isoformat()
    with open(tmp / "sitemap.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for name in files:
            f.write(f"<sitemap><loc>{SITE_URL}/sitemaps/{name}</loc><lastmod>{today}</lastmod></sitemap>\n")
        f.write("</sitemapindex>\n")
    for p in tmp.iterdir():
        p.chmod(0o644)
    tmp.chmod(0o755)
    old = DATA_DIR / "sitemaps.old"
    shutil.rmtree(old, ignore_errors=True)
    if OUT.exists():
        OUT.rename(old)
    os.rename(tmp, OUT)
    shutil.rmtree(old, ignore_errors=True)
    status.emit(f"sitemap: {len(files)} files")
