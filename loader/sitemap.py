"""Nightly sitemap index: static pages, boards, and every organization, person, contractor,
filing and grants-by-year page.

Written to /data/sitemaps; nginx serves /sitemap.xml and /sitemaps/* from there.
Each file's <lastmod> in the index changes only when that file's URL list changes
(tracked in lastmod.json), so search engines can trust it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
from datetime import date
from xml.sax.saxutils import escape

from app.config import DATA_DIR, SITE_URL
from loader import db

PER_FILE = 50000   # the sitemap protocol's limit per file
OUT = DATA_DIR / "sitemaps"
STATIC_PAGES = ["/", "/boards", "/about", "/data", "/privacy", "/support", "/contact"]

# (file prefix, query, row -> path). Ordered by a stable key so new rows mostly land in
# the last file and earlier files (and their lastmod) stay unchanged.
KINDS = [
    ("org", "SELECT ein FROM organizations WHERE latest_filing_year IS NOT NULL ORDER BY ein",
     lambda r: f"/org/{r[0]}"),
    ("person", "SELECT id FROM person_clusters ORDER BY id",
     lambda r: f"/person/{r[0]}"),
    # A contractor page shows every row with that name; min(id) is its canonical URL.
    ("contractor", "SELECT min(id) FROM contractors WHERE name_norm <> '' GROUP BY name_norm ORDER BY 1",
     lambda r: f"/contractor/{r[0]}"),
    ("filing", "SELECT id FROM filings ORDER BY id",
     lambda r: f"/filing/{r[0]}"),
    ("grants", "SELECT ein, tax_year FROM grants WHERE tax_year IS NOT NULL GROUP BY ein, tax_year ORDER BY ein, tax_year",
     lambda r: f"/org/{r[0]}/grants/{r[1]}"),
]


def _write(path, urls) -> str:
    """Write one gzipped urlset; return a hash of its contents. mtime=0 keeps unchanged files byte-identical."""
    body = "".join(f"<url><loc>{escape(SITE_URL + u)}</loc></url>\n" for u in urls)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
        f.write(('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 + body + "</urlset>\n").encode("utf-8"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def run(status) -> None:
    status.phase = "sitemap"
    tmp = DATA_DIR / "sitemaps.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        previous = json.loads((OUT / "lastmod.json").read_text())
    except (OSError, ValueError):
        previous = {}
    today = date.today().isoformat()
    hashes: dict[str, str] = {}
    counts: dict[str, int] = {}

    from app import boards
    hashes["pages.xml.gz"] = _write(tmp / "pages.xml.gz", STATIC_PAGES + [f"/boards/{b.slug}" for b in boards.visible()])
    with db.connect() as conn:
        for kind, sql, path in KINDS:
            with conn.cursor(name=f"sitemap_{kind}") as cur:
                cur.itersize = PER_FILE
                cur.execute(sql)
                n = total = 0
                while rows := cur.fetchmany(PER_FILE):
                    n += 1
                    total += len(rows)
                    name = f"{kind}-{n:04d}.xml.gz"
                    hashes[name] = _write(tmp / name, (path(r) for r in rows))
                counts[kind] = total

    lastmod = {name: {"sha1": h, "lastmod": previous[name]["lastmod"]
                      if previous.get(name, {}).get("sha1") == h else today}
               for name, h in hashes.items()}
    (tmp / "lastmod.json").write_text(json.dumps(lastmod, indent=0, sort_keys=True))
    with open(tmp / "sitemap.xml", "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for name in hashes:
            f.write(f"<sitemap><loc>{SITE_URL}/sitemaps/{name}</loc><lastmod>{lastmod[name]['lastmod']}</lastmod></sitemap>\n")
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
    changed = sum(1 for v in lastmod.values() if v["lastmod"] == today)
    status.emit(f"sitemap: {len(hashes)} files, {sum(counts.values()) + len(STATIC_PAGES):,} URLs "
                f"({', '.join(f'{k} {v:,}' for k, v in counts.items())}); {changed} changed today")
