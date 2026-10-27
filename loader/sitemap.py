"""Nightly sitemap index: static pages, boards, and every organization, person, contractor,
filing and grants-by-year page.

Written to /data/sitemaps; nginx serves /sitemap.xml and /sitemaps/* from there.
Each file's <lastmod> in the index changes only when that file's URL list changes
(tracked in lastmod.json), so search engines can trust it. run() returns the URLs that
weren't in the previous sitemap (new pages), for loader/indexnow.py.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
from datetime import date
from xml.sax.saxutils import escape

from app.config import DATA_DIR, SITE_URL
from loader import db

PER_FILE = 50000   # the sitemap protocol's limit per file
OUT = DATA_DIR / "sitemaps"
STATIC_PAGES = ["/", "/boards", "/schools", "/schools/990s", "/schools/pay", "/schools/student-loans", "/about", "/data", "/privacy", "/terms", "/support", "/contact"]

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
    # Built by loader/funders.py; skipped until its tables exist (REQUIRES below).
    ("funders", "SELECT DISTINCT recipient_ein FROM org_funders ORDER BY 1", lambda r: f"/org/{r[0]}/funders"),
    ("similar", "SELECT ein FROM org_profile WHERE ntee_code IS NOT NULL ORDER BY ein", lambda r: f"/org/{r[0]}/similar"),
    ("funders-like", "SELECT ein FROM org_profile WHERE ntee_code IS NOT NULL ORDER BY ein",
     lambda r: f"/org/{r[0]}/funders-like"),
    # Schools (loader/colleges.py).
    ("institution", "SELECT unitid FROM colleges WHERE NOT closed ORDER BY unitid", lambda r: f"/institution/{r[0]}"),
    ("institution-payroll", "SELECT DISTINCT unitid FROM college_payroll_years ORDER BY 1",
     lambda r: f"/institution/{r[0]}/payroll"),
]
REQUIRES = {"funders": "org_funders", "similar": "org_profile", "funders-like": "org_profile",
            "institution": "colleges", "institution-payroll": "college_payroll_years"}
# Kinds added after launch use smaller files (at most 45,000 URLs); the older kinds keep the protocol's
# 50,000 so their existing files (and lastmod dates) stay as they are.
PER_KIND = {"institution": 45000, "institution-payroll": 45000}

# === BEGIN student-loans block (student loan ABS pages) ===
STATIC_PAGES.append("/student-loans")
KINDS += [
    ("student-loan-trust", "SELECT cik FROM student_loan_trusts ORDER BY cik", lambda r: f"/student-loans/trust/{r[0]}"),
    ("student-loan-issuer", "SELECT slug FROM student_loan_parties ORDER BY slug",
     lambda r: f"/student-loans/issuer/{r[0]}"),
]
REQUIRES.update({"student-loan-trust": "student_loan_trusts", "student-loan-issuer": "student_loan_parties"})
PER_KIND.update({"student-loan-trust": 45000, "student-loan-issuer": 45000})
# === END student-loans block ===


def _write(path, urls) -> str:
    """Write one gzipped urlset; return a hash of its contents. mtime=0 keeps unchanged files byte-identical."""
    body = "".join(f"<url><loc>{escape(SITE_URL + u)}</loc></url>\n" for u in urls)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as f:
        f.write(('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 + body + "</urlset>\n").encode("utf-8"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


_LOC = re.compile(r"<loc>([^<]+)</loc>")


def _locs(path) -> set[str]:
    """The URLs in a previously written urlset (already XML-escaped, which is fine for comparing)."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return set(_LOC.findall(f.read()))


def run(status) -> list[str]:
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
    # New URLs by kind. Only files whose contents changed are compared with their previous
    # version; with no previous sitemap at all, nothing counts as new (it would be everything).
    added: dict[str, list[str]] = {}
    have_previous = OUT.exists()

    def write(name: str, kind: str, paths: list[str]) -> None:
        hashes[name] = _write(tmp / name, paths)
        if have_previous and previous.get(name, {}).get("sha1") != hashes[name]:
            old = _locs(OUT / name) if (OUT / name).exists() else set()
            added.setdefault(kind, []).extend(u for u in (escape(SITE_URL + p) for p in paths) if u not in old)

    from app import boards
    write("pages.xml.gz", "pages", STATIC_PAGES + [f"/boards/{b.slug}" for b in boards.visible()])
    with db.connect() as conn:
        for kind, sql, path in KINDS:
            need = REQUIRES.get(kind)
            if need and not conn.execute("SELECT to_regclass(%s) IS NOT NULL", (need,)).fetchone()[0]:
                continue
            with conn.cursor(name=f"sitemap_{kind.replace('-', '_')}") as cur:
                per = PER_KIND.get(kind, PER_FILE)
                cur.itersize = per
                cur.execute(sql)
                n = total = 0
                while rows := cur.fetchmany(per):
                    n += 1
                    total += len(rows)
                    name = f"{kind}-{n:04d}.xml.gz"
                    write(name, kind, [path(r) for r in rows])
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
    new = sum(len(v) for v in added.values())
    status.emit(f"sitemap: {len(hashes)} files, {sum(counts.values()) + len(STATIC_PAGES):,} URLs "
                f"({', '.join(f'{k} {v:,}' for k, v in counts.items())}); {changed} changed today, {new:,} new URLs")
    # Most useful first: a re-cluster can renumber many person pages, so they go last.
    order = ["pages", "filing", "org", "institution", "institution-payroll", "contractor", "grants", "funders",
             "similar", "funders-like", "student-loan-trust",
             "student-loan-issuer", "person"]
    return [u.replace("&amp;", "&") for k in sorted(added, key=lambda k: order.index(k) if k in order else len(order))
            for u in added[k]]

# FEC campaign contributions (app/politics.py): the hub, committees and donors of $10,000+ in a cycle.
STATIC_PAGES.extend(["/more", "/get-ideas"])
if __import__("os").environ.get("POLITICS_PUBLIC") == "1":
    STATIC_PAGES.extend(["/politics", "/politics/donors"])
    KINDS += [
        ("politics-committee", "SELECT DISTINCT cmte_id FROM fec_committee_totals ORDER BY 1",
         lambda r: f"/politics/committee/{r[0]}"),
        ("politics-donor", "SELECT DISTINCT coalesce(zip5, '00000'), name_norm FROM fec_donor_totals ORDER BY 1, 2",
         lambda r: "/politics/donor/{}/{}".format(r[0], "-".join(__import__("re").sub("[^a-z0-9]+", " ", r[1]).split()))),
    ]
REQUIRES.update({"politics-committee": "fec_committee_totals", "politics-donor": "fec_donor_totals"})

if __import__("os").environ.get("FEDSPEND_PUBLIC") == "1":
    STATIC_PAGES.append("/federal-spending")

if __import__("os").environ.get("SEC_PUBLIC") == "1":
    STATIC_PAGES.append("/corporate")
    KINDS += [
        ("corporate-company", "SELECT DISTINCT ltrim(issuer_cik, '0') FROM sec_insider_filings WHERE issuer_cik IS NOT NULL ORDER BY 1",
         lambda r: f"/corporate/company/{r[0]}"),
        ("corporate-insider", "SELECT DISTINCT ltrim(key, '0') FROM sec_person_links WHERE source = 'insider' ORDER BY 1",
         lambda r: f"/corporate/insider/{r[0]}"),
    ]
    REQUIRES.update({"corporate-company": "sec_insider_filings", "corporate-insider": "sec_person_links"})
    # Private funds (Form ADV, app/adv.py) with at least two years of reports and $1 million at some point.
    KINDS += [("corporate-fund", "SELECT fund_id FROM adv_funds WHERE fund_id ~ '^805-[0-9]+$' GROUP BY fund_id "
               "HAVING count(DISTINCT year) >= 2 AND max(gav) >= 1000000 ORDER BY 1",
               lambda r: f"/corporate/fund/{r[0]}")]
    REQUIRES["corporate-fund"] = "adv_funds"

if __import__("os").environ.get("LDA_PUBLIC") == "1":
    STATIC_PAGES.append("/lobbying")
    KINDS += [("lobbying-client", "SELECT DISTINCT client_id FROM lda_filings ORDER BY 1",
               lambda r: f"/lobbying/client/{r[0]}"),
              ("lobbying-firm", "SELECT DISTINCT registrant_id FROM lda_filings ORDER BY 1",
               lambda r: f"/lobbying/firm/{r[0]}")]
    KINDS += [("lobbying-lobbyist", "SELECT DISTINCT lobbyist_id FROM lda_activity_lobbyists ORDER BY 1",
               lambda r: f"/lobbying/lobbyist/{r[0]}")]
    REQUIRES.update({"lobbying-client": "lda_filings", "lobbying-firm": "lda_filings",
                     "lobbying-lobbyist": "lda_activity_lobbyists"})

STATIC_PAGES.append("/about/news")
STATIC_PAGES.append("/developers")      # the API and MCP server for AI assistants (owner, 2026-10-27)


# === Readable entity URLs (owner, 2026-10-21) ===
# Entity pages are listed under their slug URLs (app/slugs.py), every one of them (owner, 2026-10-25: no gradual
# rollout), split into files of PER_FILE. Pages with almost no data are left out (and carry noindex) until they
# have more.
from app import slugs as _slugs  # noqa: E402


def _entity(kind, sql, slug_kind):
    return (kind, sql, lambda r: _slugs.canonical(slug_kind, r[0], r[1]))


_ENTITY = {
    "org": _entity("org", """SELECT ein, name FROM organizations WHERE latest_filing_year IS NOT NULL ORDER BY ein""",
                   "org"),
    "person": _entity("person", """SELECT id, display_name FROM person_clusters
                                   WHERE NOT is_institution AND NOT (n_filings < 2 AND coalesce(max_comp, 0) = 0)
                                   ORDER BY id""", "person"),
    "contractor": _entity("contractor", """SELECT min(id) AS id, min(name_raw) AS name FROM contractors
                                           WHERE name_norm <> '' GROUP BY name_norm ORDER BY 1""", "contractor"),
    "institution": _entity("institution", "SELECT unitid, name FROM colleges WHERE NOT closed ORDER BY unitid",
                           "institution"),
    "student-loan-trust": _entity("student-loan-trust", "SELECT cik, name FROM student_loan_trusts ORDER BY cik", "trust"),
    "politics-committee": _entity("politics-committee", """SELECT DISTINCT ON (t.cmte_id) t.cmte_id, c.name
                                  FROM fec_committee_totals t LEFT JOIN fec_committees c ON c.cmte_id = t.cmte_id
                                  ORDER BY t.cmte_id, c.cycle DESC""", "committee"),
    "corporate-company": _entity("corporate-company", """SELECT DISTINCT ON (issuer_cik) ltrim(issuer_cik, '0'), issuer_name
                                 FROM sec_insider_filings WHERE issuer_cik IS NOT NULL ORDER BY issuer_cik, filing_date DESC""",
                                 "company"),
    "corporate-insider": _entity("corporate-insider", """SELECT DISTINCT ON (o.owner_cik) ltrim(o.owner_cik, '0'), o.owner_name
                                 FROM sec_person_links l JOIN sec_insider_owners o ON o.owner_cik = l.key
                                 WHERE l.source = 'insider' ORDER BY o.owner_cik""", "insider"),
    "lobbying-client": _entity("lobbying-client", """SELECT DISTINCT ON (client_id) client_id, client_name FROM lda_filings
                               ORDER BY client_id, dt_posted DESC NULLS LAST""", "client"),
    "lobbying-firm": _entity("lobbying-firm", """SELECT DISTINCT ON (registrant_id) registrant_id, registrant_name FROM lda_filings
                             ORDER BY registrant_id, dt_posted DESC NULLS LAST""", "firm"),
}
_ENTITY["lobbying-lobbyist"] = _entity("lobbying-lobbyist", """SELECT DISTINCT ON (lobbyist_id) lobbyist_id, name
                                       FROM lda_activity_lobbyists ORDER BY lobbyist_id""", "lobbyist")
KINDS[:] = [_ENTITY.get(k[0], k) for k in KINDS]

# Food recalls (app/recalls.py): the hub and firms with at least two recalls (single-recall firms carry noindex).
STATIC_PAGES.append("/recalls")
KINDS.append(_entity("recall-firm", "SELECT firm_id, name FROM food_recall_firms WHERE recalls >= 2 ORDER BY firm_id",
                     "recallfirm"))
REQUIRES["recall-firm"] = "food_recall_firms"

# The day's finds (app/ideas.py): /today, the About index, and one page per nightly pool.
STATIC_PAGES += ["/today", "/about/daily"]
KINDS.append(("today", "SELECT DISTINCT pool FROM home_ideas WHERE pool IS NOT NULL ORDER BY 1",
              lambda r: f"/today/{r[0].isoformat()}"))
REQUIRES["today"] = "home_ideas"
