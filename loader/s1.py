"""IPO registrations from SEC EDGAR (owner, 2026-11-12): every Form S-1 and F-1 registration statement and its
amendments since EDGAR's full index begins (1993), the pricing prospectus (424B4, 424B1), the notice of
effectiveness (EFFECT), Rule 462(b) add-ons (S-1MEF, F-1MEF) and withdrawal requests (RW) of the companies that
filed one, and what EDGAR knows about each company (SIC, state of incorporation, business address, EIN, tickers,
former names).

Sources (SEC fair-access rules: a User-Agent naming us and a contact, well under 10 requests a second, bulk files):
- The quarterly full index, https://www.sec.gov/Archives/edgar/full-index/<year>/QTR<n>/master.gz: one line per
  filing (CIK|Company Name|Form Type|Date Filed|Filename), 1993 to now. The current quarter is fetched again on
  every run; older quarters are kept in /bulk/s1/index.
- The submissions bulk zip, https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip (about 1.5 GB):
  one JSON per CIK with the company's SIC, state of incorporation, addresses, EIN, tickers and former names. Only
  the CIKs that filed an S-1 or F-1 are read from it.

Tables (each load replaces them in one transaction; the files are complete):
  ipo_filings    one row per (accession, CIK): form, filed date, company name as filed, EDGAR URL
  ipo_companies  one row per CIK that filed an S-1 or F-1: the company's details and its registration history
                 in numbers (first and last registration, amendments, pricing, effectiveness, withdrawal)
  ipo_links      the FURP records each company ties to (loader docstring of links() has the rules); mirrored into
                 xlinks (src_kind ipo_company) so the company shows on the person, nonprofit, business-registry,
                 SEC-filer, Form D, lobbying, FEC, FARA and federal-award pages it matches

Not here yet (a second pass): the offering itself, price range, shares offered and underwriters, which live in the
prospectus text, and the registrant's financial statements, which EDGAR tags in XBRL only for newer S-1s and which
the Financial Statement Data Sets (sec_fin_subs) do not cover.

Usage: .venv/bin/python -m loader.s1 [--no-download] [--skip-companies] [--links-only]
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import re
import time
import urllib.error
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from loader import db
from loader.recalls import core
from loader.sec_bulk import filing_url

UA = "FURP furp.org mfolenick@furp.org"
INDEX = "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/master.gz"
SUBMISSIONS = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
RAW = Path("/bulk/s1")
FIRST_YEAR = 1993
REG_FORMS = {"S-1", "S-1/A", "F-1", "F-1/A"}
EXTRA_FORMS = {"424B4", "424B1", "EFFECT", "S-1MEF", "F-1MEF", "RW"}
FORMS = REG_FORMS | EXTRA_FORMS
EXTRA_WINDOW = dt.timedelta(days=730)      # an extra form counts when filed within two years of the last S-1/F-1
_SLEEP = 0.25                               # between requests: 4 a second, well under the SEC's 10

DDL = """
CREATE TABLE IF NOT EXISTS ipo_filings (
    accession text NOT NULL, cik text NOT NULL, company_name text NOT NULL, form text NOT NULL, filed date NOT NULL,
    year integer NOT NULL, url text NOT NULL, PRIMARY KEY (accession, cik));
CREATE INDEX IF NOT EXISTS ipo_filings_cik ON ipo_filings (cik, filed);
CREATE INDEX IF NOT EXISTS ipo_filings_filed ON ipo_filings (filed DESC);
CREATE INDEX IF NOT EXISTS ipo_filings_form_year ON ipo_filings (form, year);
CREATE TABLE IF NOT EXISTS ipo_companies (
    cik text PRIMARY KEY, name text NOT NULL, index_name text, name_core text, kind text NOT NULL,
    sic text, sic_desc text, state_inc text, entity_type text, street text, city text, state text, zip text, ein text,
    tickers text, exchanges text, former_names jsonb, first_filed date NOT NULL, last_filed date NOT NULL,
    n_filings integer NOT NULL, n_reg integer NOT NULL, n_amend integer NOT NULL, priced date, effect date,
    withdrawn date, loaded timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS ipo_companies_core ON ipo_companies (name_core);
CREATE INDEX IF NOT EXISTS ipo_companies_first ON ipo_companies (first_filed DESC);
CREATE INDEX IF NOT EXISTS ipo_companies_state ON ipo_companies (state);
CREATE INDEX IF NOT EXISTS ipo_companies_sic ON ipo_companies (sic);
CREATE INDEX IF NOT EXISTS ipo_companies_ein ON ipo_companies (ein) WHERE ein IS NOT NULL;
CREATE TABLE IF NOT EXISTS ipo_links (
    cik text NOT NULL, dst_kind text NOT NULL, dst_key text NOT NULL, dst_name text, how text NOT NULL,
    PRIMARY KEY (cik, dst_kind, dst_key));
CREATE INDEX IF NOT EXISTS ipo_links_dst ON ipo_links (dst_kind, dst_key);
"""


# --- fetching -------------------------------------------------------------------------------------------

def _get(url: str, dest: Path | None = None) -> bytes | None:
    """One EDGAR request, streamed to dest when given; None on 404; retried on other failures."""
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=300) as r:
                if dest is None:
                    data = r.read()
                    time.sleep(_SLEEP)
                    return data
                tmp = dest.with_suffix(dest.suffix + ".part")
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                tmp.replace(dest)
                time.sleep(_SLEEP)
                return b"ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"SEC kept failing: {url}")


def quarters(first: int = FIRST_YEAR, today: dt.date | None = None) -> list[tuple[int, int]]:
    today = today or dt.date.today()
    out = []
    for y in range(first, today.year + 1):
        for q in range(1, 5):
            if (y, q) <= (today.year, (today.month - 1) // 3 + 1):
                out.append((y, q))
    return out


def index_path(year: int, q: int) -> Path:
    return RAW / "index" / f"{year}QTR{q}.master.gz"


def download(status=print, companies: bool = True) -> None:
    """The quarterly indexes (the current quarter again each run; the others only when missing) and, weekly, the
    submissions zip."""
    (RAW / "index").mkdir(parents=True, exist_ok=True)
    qs = quarters()
    for y, q in qs:
        p = index_path(y, q)
        if p.exists() and (y, q) != qs[-1]:
            continue
        if _get(INDEX.format(year=y, q=q), p) is None:
            status(f"s1: {y} QTR{q}: no index yet")
        else:
            status(f"s1: {y} QTR{q}: {p.stat().st_size:,} bytes")
    if companies:
        z = RAW / "submissions.zip"
        age = (time.time() - z.stat().st_mtime) / 86400 if z.exists() else None
        if age is None or age > 6:
            status("s1: submissions.zip (about 1.5 GB)")
            _get(SUBMISSIONS, z)
            status(f"s1: submissions.zip {z.stat().st_size:,} bytes")


# --- parsing --------------------------------------------------------------------------------------------

def parse_line(line: str) -> tuple | None:
    """(cik, name, form, filed, accession) from one master.idx line, or None for headers and forms we don't keep."""
    parts = line.rstrip("\n").split("|")
    if len(parts) != 5:
        return None
    cik, name, form, filed, fname = parts
    if form not in FORMS or not cik.isdigit():
        return None
    try:
        d = dt.date.fromisoformat(filed.strip())
    except ValueError:
        return None
    m = re.search(r"(\d{10}-\d{2}-\d{6})\.txt$", fname.strip())
    if not m:
        return None
    return str(int(cik)), name.strip()[:300] or cik, form, d, m.group(1)


def read_index(path: Path):
    with gzip.open(path, "rt", encoding="latin-1", errors="replace") as f:
        for line in f:
            row = parse_line(line)
            if row:
                yield row


def select_filings(rows) -> tuple[list[tuple], dict[str, dict]]:
    """Keep every S-1/F-1 row, and the extra forms (pricing, effectiveness, add-ons, withdrawals) of those CIKs
    filed between their first registration and two years after their last. Returns the filing rows and, per CIK,
    the registration summary."""
    by_cik: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        by_cik[r[0]].append(r)
    out, summary = [], {}
    for cik, rs in by_cik.items():
        regs = [r for r in rs if r[2] in REG_FORMS]
        if not regs:
            continue
        first = min(r[3] for r in regs)
        last = max(r[3] for r in regs)
        keep = {r[4]: r for r in regs}
        for r in rs:
            if r[2] in EXTRA_FORMS and first <= r[3] <= last + EXTRA_WINDOW:
                keep.setdefault(r[4], r)
        rows_ = sorted(keep.values(), key=lambda r: (r[3], r[4]))
        out.extend(rows_)
        forms = [r[2] for r in rows_]
        kinds = sorted({f.split("/")[0] for f in forms if f in REG_FORMS})
        pricing = [r[3] for r in rows_ if r[2] in ("424B4", "424B1")]
        effect = [r[3] for r in rows_ if r[2] == "EFFECT"]
        rw = [r[3] for r in rows_ if r[2] == "RW"]
        latest_name = max(regs, key=lambda r: (r[3], r[4]))[1]
        summary[cik] = {"index_name": latest_name, "kind": ", ".join(kinds), "first_filed": first, "last_filed": last,
                        "n_filings": len(rows_), "n_reg": sum(1 for f in forms if f in ("S-1", "F-1")),
                        "n_amend": sum(1 for f in forms if f in ("S-1/A", "F-1/A")),
                        "priced": min(pricing) if pricing else None, "effect": min(effect) if effect else None,
                        "withdrawn": min(rw) if rw else None}
    return out, summary


def _s(v, n: int = 300) -> str | None:
    v = (str(v) if v is not None else "").strip()
    return v[:n] or None


def company_facts(sub: dict) -> dict:
    """What a submissions JSON says about the company."""
    addr = (sub.get("addresses") or {}).get("business") or (sub.get("addresses") or {}).get("mailing") or {}
    ein = re.sub(r"\D", "", str(sub.get("ein") or ""))
    return {"name": _s(sub.get("name")), "sic": _s(sub.get("sic"), 10), "sic_desc": _s(sub.get("sicDescription"), 200),
            "state_inc": _s(sub.get("stateOfIncorporation"), 10), "entity_type": _s(sub.get("entityType"), 50),
            "street": _s(", ".join(x for x in (addr.get("street1"), addr.get("street2")) if x)),
            "city": _s(addr.get("city"), 100), "state": _s(addr.get("stateOrCountry"), 10), "zip": _s(addr.get("zipCode"), 20),
            "ein": ein if len(ein) == 9 and ein != "000000000" else None,
            "tickers": _s(", ".join(sub.get("tickers") or [])), "exchanges": _s(", ".join(x for x in (sub.get("exchanges") or []) if x)),
            "former_names": [{"name": f.get("name"), "from": (f.get("from") or "")[:10], "to": (f.get("to") or "")[:10]}
                             for f in (sub.get("formerNames") or []) if f.get("name")][:30]}


def read_companies(ciks: set[str], status=print) -> dict[str, dict]:
    z = RAW / "submissions.zip"
    out = {}
    if not z.exists():
        status("s1: no submissions.zip; company details skipped")
        return out
    with zipfile.ZipFile(z) as zf:
        names = set(zf.namelist())
        for i, cik in enumerate(sorted(ciks, key=int)):
            n = f"CIK{int(cik):010d}.json"
            if n not in names:
                continue
            try:
                out[cik] = company_facts(json.loads(zf.read(n)))
            except (ValueError, KeyError):
                continue
            if i % 5000 == 0 and i:
                status(f"s1: company details {i:,}/{len(ciks):,}")
    status(f"s1: company details for {len(out):,} of {len(ciks):,} filers")
    return out


# --- loading --------------------------------------------------------------------------------------------

def load(status=print, companies: bool = True) -> dict:
    rows = []
    per_file = {}
    for y, q in quarters():
        p = index_path(y, q)
        if not p.exists():
            continue
        n0 = len(rows)
        rows.extend(read_index(p))
        per_file[f"s1:index:{y}QTR{q}"] = (y, len(rows) - n0)
    filings, summary = select_filings(rows)
    status(f"s1: {len(rows):,} index rows of the forms kept, {len(filings):,} filings of {len(summary):,} S-1/F-1 filers")
    facts = read_companies(set(summary), status) if companies else {}
    now = dt.datetime.now(dt.UTC)
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("SET statement_timeout = 0")
        conn.execute("TRUNCATE ipo_filings, ipo_companies")
        with conn.cursor() as cur:
            seen = set()
            def filing_rows():
                for cik, name, form, filed, acc in filings:
                    if (acc, cik) in seen:
                        continue
                    seen.add((acc, cik))
                    yield (acc, cik, name, form, filed, filed.year, filing_url(cik, acc))
            nf = db.copy_rows(cur, "ipo_filings", ["accession", "cik", "company_name", "form", "filed", "year", "url"],
                              filing_rows())
            def company_rows():
                for cik, s in summary.items():
                    f = facts.get(cik) or {}
                    name = f.get("name") or s["index_name"]
                    yield (cik, name, s["index_name"], core(name)[:300], s["kind"], f.get("sic"), f.get("sic_desc"),
                           f.get("state_inc"), f.get("entity_type"), f.get("street"), f.get("city"), f.get("state"),
                           f.get("zip"), f.get("ein"), f.get("tickers"), f.get("exchanges"),
                           json.dumps(f.get("former_names") or []), s["first_filed"], s["last_filed"], s["n_filings"],
                           s["n_reg"], s["n_amend"], s["priced"], s["effect"], s["withdrawn"], now)
            nc = db.copy_rows(cur, "ipo_companies", ["cik", "name", "index_name", "name_core", "kind", "sic", "sic_desc",
                                                     "state_inc", "entity_type", "street", "city", "state", "zip", "ein",
                                                     "tickers", "exchanges", "former_names", "first_filed", "last_filed",
                                                     "n_filings", "n_reg", "n_amend", "priced", "effect", "withdrawn",
                                                     "loaded"], company_rows())
        for file, (year, n) in per_file.items():
            db.progress(conn, file, "done", kind="s1", year=year, rows=n)
        db.progress(conn, "s1:filings", "done", kind="s1", rows=nf)
        db.progress(conn, "s1:companies", "done", kind="s1", rows=nc)
        conn.commit()
        status(f"s1: {nf:,} filings, {nc:,} companies")
        out = {"filings": nf, "companies": nc}
        out.update(links(conn, status))
        conn.commit()
    return out


def links(conn, status=print) -> dict:
    """ipo_links: each S-1/F-1 filer tied to the site's records.
    EXACT ties: the same CIK (SEC insider-filing issuers, financial-statement filers, Form D issuers), the same EIN
    (nonprofits, state business registrations, lobbying clients and registrants, Form 5500 sponsors, federal award
    recipients). Fuzzy ties (the site's usual rule): the same name core and state, one record on each side for
    nonprofits, Form D issuers and advisers; up to 12 state registrations, lobbying ids, PACs, UEIs and FARA
    registrations with that name and state. People: the officers, directors and 10% owners who filed Forms 3, 4
    or 5 for the issuer and are linked to a person page (sec_person_links)."""
    conn.execute("SET statement_timeout = 0")
    conn.execute("SET work_mem = '512MB'")
    conn.execute("DELETE FROM ipo_links")
    has = lambda t: conn.execute("SELECT to_regclass(%s) IS NOT NULL", (t,)).fetchone()[0]  # noqa: E731
    n = {}
    if has("sec_insider_filings"):
        n["sec"] = conn.execute("""
            INSERT INTO ipo_links SELECT c.cik, 'sec', c.cik, min(f.issuer_name), 'CIK (EXACT)'
            FROM ipo_companies c JOIN sec_insider_filings f ON f.issuer_cik ~ '^\\d+$' AND f.issuer_cik::bigint = c.cik::bigint
            GROUP BY c.cik ON CONFLICT DO NOTHING""").rowcount
    if has("sec_fin_subs"):
        n["sec_fin"] = conn.execute("""
            INSERT INTO ipo_links SELECT c.cik, 'sec', c.cik, min(f.name), 'CIK (EXACT)'
            FROM ipo_companies c JOIN sec_fin_subs f ON f.cik::text ~ '^\\d+$' AND f.cik::text::bigint = c.cik::bigint
            GROUP BY c.cik ON CONFLICT DO NOTHING""").rowcount
    if has("sec_formd_offerings"):
        n["formd"] = conn.execute("""
            INSERT INTO ipo_links SELECT DISTINCT ON (c.cik) c.cik, 'formd', o.cik, o.issuer_name, 'CIK (EXACT)'
            FROM ipo_companies c JOIN sec_formd_offerings o ON o.cik ~ '^\\d+$' AND o.cik::bigint = c.cik::bigint
            ORDER BY c.cik, o.latest_date DESC ON CONFLICT DO NOTHING""").rowcount
    # EIN, exact
    n["org_ein"] = conn.execute("""
        INSERT INTO ipo_links SELECT c.cik, 'org', o.ein, o.name, 'EIN (EXACT)'
        FROM ipo_companies c JOIN organizations o ON o.ein = c.ein WHERE c.ein IS NOT NULL ON CONFLICT DO NOTHING""").rowcount
    if has("biz_entities"):
        # Up to 12 registrations per company, the ones with the company's name first: a few registries carry the
        # EIN as filed, and a franchisor's or platform's EIN turns up on hundreds of its operators' LLCs.
        n["biz_ein"] = conn.execute("""
            INSERT INTO ipo_links SELECT cik, 'biz', state || ':' || entity_id, name, 'EIN (EXACT, as the state registration reports it)'
            FROM (SELECT c.cik, b.state, b.entity_id, b.name,
                         row_number() OVER (PARTITION BY c.cik ORDER BY b.name_core = c.name_core DESC, b.name) AS rk
                  FROM ipo_companies c JOIN biz_entities b ON b.ein = c.ein WHERE c.ein IS NOT NULL AND b.source <> 'form5500') t
            WHERE rk <= 12 ON CONFLICT DO NOTHING""").rowcount
    if has("lda_filings"):
        n["lda_ein"] = conn.execute("""
            INSERT INTO ipo_links SELECT DISTINCT ON (c.cik, l.client_id) c.cik, 'lda_client', l.client_id::text, l.client_name, 'EIN (EXACT)'
            FROM ipo_companies c JOIN lda_filings l ON regexp_replace(l.client_ein, '\\D', '', 'g') = c.ein
            WHERE c.ein IS NOT NULL AND l.client_id IS NOT NULL ORDER BY c.cik, l.client_id, l.dt_posted DESC
            ON CONFLICT DO NOTHING""").rowcount
        n["lda_reg_ein"] = conn.execute("""
            INSERT INTO ipo_links SELECT DISTINCT ON (c.cik, l.registrant_id) c.cik, 'lda_registrant', l.registrant_id::text, l.registrant_name, 'EIN (EXACT)'
            FROM ipo_companies c JOIN lda_filings l ON regexp_replace(l.registrant_ein, '\\D', '', 'g') = c.ein
            WHERE c.ein IS NOT NULL AND l.registrant_id IS NOT NULL ORDER BY c.cik, l.registrant_id, l.dt_posted DESC
            ON CONFLICT DO NOTHING""").rowcount
    if has("form5500_filings"):
        n["f5500_ein"] = conn.execute("""
            INSERT INTO ipo_links SELECT DISTINCT ON (c.cik) c.cik, 'f5500', f.sponsor_ein, f.sponsor_name, 'EIN (EXACT)'
            FROM ipo_companies c JOIN form5500_filings f ON f.sponsor_ein = c.ein WHERE c.ein IS NOT NULL
            ORDER BY c.cik, f.plan_year DESC NULLS LAST ON CONFLICT DO NOTHING""").rowcount
    if has("fed_recipient_names"):
        n["fed_ein"] = conn.execute("""
            INSERT INTO ipo_links SELECT c.cik, 'fed', f.uei, f.name, 'EIN (EXACT)'
            FROM ipo_companies c JOIN fed_recipient_names f ON regexp_replace(f.ein, '\\D', '', 'g') = c.ein
            WHERE c.ein IS NOT NULL ON CONFLICT DO NOTHING""").rowcount
    # Name core and state, fuzzy: the targets as loader/xlinks.py builds them.
    conn.execute("CREATE TEMP TABLE ipo_t (dst_kind text, dst_key text, dst_name text, core text, state text) ON COMMIT DROP")
    def add(kind, sql):
        rows = conn.execute(sql).fetchall()
        with conn.cursor() as cur:
            db.copy_rows(cur, "ipo_t", ["dst_kind", "dst_key", "dst_name", "core", "state"],
                         ((kind, str(k), name, core(name)[:300], st) for k, name, st in rows if name and st and len(core(name)) >= 4))
    add("org", "SELECT ein, name, state FROM organizations WHERE name IS NOT NULL AND state IS NOT NULL")
    if has("biz_entities"):
        conn.execute("""INSERT INTO ipo_t SELECT 'biz', state || ':' || entity_id, name, name_core, addr_state FROM biz_entities
                        WHERE length(name_core) >= 4 AND addr_state IS NOT NULL AND source <> 'form5500'""")
    if has("lda_filings"):
        add("lda_client", "SELECT client_id, min(client_name), min(client_state) FROM lda_filings WHERE client_name IS NOT NULL GROUP BY 1")
        add("lda_registrant", "SELECT registrant_id, min(registrant_name), min(registrant_state) FROM lda_filings WHERE registrant_name IS NOT NULL GROUP BY 1")
    if has("sec_formd_offerings"):
        add("formd", """SELECT DISTINCT ON (cik) cik, issuer_name, state FROM sec_formd_offerings WHERE issuer_name IS NOT NULL
                        ORDER BY cik, latest_date DESC""")
    if has("adv_filings"):
        add("adv", """SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name), state FROM adv_filings WHERE crd IS NOT NULL
                      ORDER BY crd, submitted DESC NULLS LAST""")
    if has("fec_committees"):
        rows = conn.execute("""SELECT DISTINCT ON (cmte_id) cmte_id, connected_org, state, name FROM fec_committees
                               WHERE connected_org IS NOT NULL AND connected_org <> '' ORDER BY cmte_id, cycle DESC""").fetchall()
        with conn.cursor() as cur:
            db.copy_rows(cur, "ipo_t", ["dst_kind", "dst_key", "dst_name", "core", "state"],
                         (("fec_committee", cid, f"{cname} (connected to {org})", core(org)[:300], st) for cid, org, st, cname in rows
                          if st and len(core(org)) >= 4))
    if has("fara_registrants"):
        conn.execute("""INSERT INTO ipo_t SELECT 'fara_registrant', reg_number, name, name_core, state FROM fara_registrants
                        WHERE length(name_core) >= 4 AND state IS NOT NULL""")
    if has("fed_recipient_names"):
        conn.execute("""INSERT INTO ipo_t SELECT 'fed', uei, name, core, state FROM fed_recipient_names
                        WHERE length(core) >= 4 AND state IS NOT NULL""")
    conn.execute("CREATE INDEX ON ipo_t (core, state)")
    conn.execute("ANALYZE ipo_t")
    n["name_one"] = conn.execute("""
        INSERT INTO ipo_links SELECT c.cik, t.dst_kind, t.dst_key, t.dst_name, 'name and state'
        FROM ipo_companies c
        JOIN (SELECT dst_kind, core, state, min(dst_key) AS dst_key, min(dst_name) AS dst_name FROM ipo_t
              WHERE dst_kind IN ('org', 'formd', 'adv') GROUP BY 1, 2, 3 HAVING count(*) = 1) t
             ON t.core = c.name_core AND t.state = c.state
        WHERE c.state IS NOT NULL AND length(c.name_core) >= 4 ON CONFLICT DO NOTHING""").rowcount
    n["name_many"] = conn.execute("""
        INSERT INTO ipo_links SELECT c.cik, t.dst_kind, t.dst_key, t.dst_name, 'name and state'
        FROM ipo_companies c
        JOIN (SELECT dst_kind, core, state, dst_key, dst_name,
                     row_number() OVER (PARTITION BY dst_kind, core, state ORDER BY dst_key) AS rk FROM ipo_t
              WHERE dst_kind IN ('biz', 'lda_client', 'lda_registrant', 'fec_committee', 'fed', 'fara_registrant')) t
             ON t.core = c.name_core AND t.state = c.state AND t.rk <= 12
        WHERE c.state IS NOT NULL AND length(c.name_core) >= 4 ON CONFLICT DO NOTHING""").rowcount
    # People: insiders of the issuer who are linked to a person page.
    if has("sec_person_links") and has("sec_insider_owners"):
        n["person"] = conn.execute("""
            INSERT INTO ipo_links SELECT DISTINCT ON (c.cik, l.cluster_id) c.cik, 'person', l.cluster_id::text, p.display_name,
                   'officer, director or 10% owner on the company''s Forms 3, 4 and 5 (' || coalesce(nullif(o.relationship, ''), 'insider') || ')'
            FROM ipo_companies c
            JOIN sec_insider_filings f ON f.issuer_cik ~ '^\\d+$' AND f.issuer_cik::bigint = c.cik::bigint
            JOIN sec_insider_owners o ON o.accession = f.accession
            JOIN sec_person_links l ON l.source = 'insider' AND l.key = o.owner_cik
            JOIN person_clusters p ON p.id = l.cluster_id
            ORDER BY c.cik, l.cluster_id, f.filing_date DESC ON CONFLICT DO NOTHING""").rowcount
    total = conn.execute("SELECT count(*) FROM ipo_links").fetchone()[0]
    db.progress(conn, "s1:links", "done", kind="s1", rows=total)
    conn.commit()
    mirror(conn, status)
    status("s1 links: " + ", ".join(f"{k} {v:,}" for k, v in n.items()) + f"; {total:,} in all")
    return {"links": total, **{f"links_{k}": v for k, v in n.items()}}


def mirror(conn, status=print) -> int:
    """Copy ipo_links into xlinks (src_kind ipo_company) so every page the company matches shows it; a full xlinks
    rebuild (loader/xlinks.py) does the same from ipo_links."""
    if not conn.execute("SELECT to_regclass('xlinks') IS NOT NULL").fetchone()[0]:
        return 0
    conn.execute("DELETE FROM xlinks WHERE src_kind = 'ipo_company'")
    n = conn.execute("""INSERT INTO xlinks SELECT 'ipo_company', l.cik, c.name, c.state, l.dst_kind, l.dst_key, l.dst_name, l.how
                        FROM ipo_links l JOIN ipo_companies c USING (cik) ON CONFLICT DO NOTHING""").rowcount
    if conn.execute("SELECT to_regclass('xlink_counts') IS NOT NULL").fetchone()[0]:
        conn.execute("DELETE FROM xlink_counts WHERE src_kind = 'ipo_company'")
        conn.execute("""INSERT INTO xlink_counts SELECT src_kind, dst_kind, count(*), count(DISTINCT src_key), now()
                        FROM xlinks WHERE src_kind = 'ipo_company' GROUP BY 1, 2""")
    conn.commit()
    status(f"s1: {n:,} links mirrored into xlinks")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--no-download", action="store_true", help="load the files already in %s" % RAW)
    ap.add_argument("--skip-companies", action="store_true", help="no submissions.zip: company details from the index only")
    ap.add_argument("--links-only", action="store_true", help="rebuild ipo_links (and the xlinks mirror) from the loaded tables")
    a = ap.parse_args(argv)
    if a.links_only:
        with db.connect() as conn:
            conn.execute(DDL)
            links(conn)
            conn.commit()
        return 0
    if not a.no_download:
        download(companies=not a.skip_companies)
    load(companies=not a.skip_companies)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
