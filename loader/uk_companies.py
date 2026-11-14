"""UK Companies House open data into schema `uk_companies` (owner, 2026-11-14).

Sources (Companies House free bulk products, https://download.companieshouse.gov.uk/):
  en_output.html   "Free Company Data Product": BasicCompanyDataAsOneFile-YYYY-MM-DD.zip, a CSV of every LIVE company on the register
                   (number, name, status, category, incorporation date, SIC codes, registered office, previous names, accounts and
                   charge counts). Updated within five working days of each month end. Dissolved companies are not in it, apart
                   from the few with a dissolution date still on the live register.
  en_pscdata.html  "People with significant control snapshot": persons-with-significant-control-snapshot-YYYY-MM-DD.zip, one JSON
                   object per line (15 GB unpacked): individual, corporate-entity and legal-person PSCs, statements.
There is NO free bulk officers (directors) file: officers are only on the REST API (free key needed, rate limited) and the
streaming API (free key). Neither is used here; see docs/uk-companies.md for what a key would add.

Licence and terms (checked 2026-11-14): Companies House says "This snapshot is provided free of charge and will not be supported";
its data is published under the Open Government Licence v3.0 (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/),
so it may be reused with the attribution "Contains public sector information licensed under the Open Government Licence v3.0.
Source: Companies House." Privacy: an individual PSC's name, nationality, country of residence, birth year and nature of control are
kept (all on the public register); their address and day of birth are not stored.

python -m loader.uk_companies download | load | psc | summarize | nightly | status
  download   one conditional download per file (a new file name on the listing page = a new snapshot), raw zips in
             /bulk/companies_house, fixed User-Agent
  load       the CSV into uk_companies.company (+ previous_name), built as company_new and swapped in one transaction
  psc        the JSON lines into uk_companies.psc, swapped in the same way
  summarize  uk_companies.company_psc (counts per company), psc_person (an individual by name + birth month/year across companies),
             sic (code lookup), board_* summary tables, counts in meta
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from loader import db
from loader.recalls import core

RAW = Path(os.environ.get("UK_COMPANIES_RAW_DIR", "/bulk/companies_house"))
UA = "furp.org data loader (info@furp.org)"
BASE = "https://download.companieshouse.gov.uk/"
PAGE_BASIC = BASE + "en_output.html"
PAGE_PSC = BASE + "en_pscdata.html"
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Source: Companies House.")
EXIT_CHANGED = 10

_AREAS = {
    "North East": "DH DL NE SR TS",
    "North West": "BB BL CA CH CW FY L LA M OL PR SK WA WN",
    "Yorkshire and The Humber": "BD DN HD HG HU HX LS S WF YO",
    "East Midlands": "DE LE LN NG NN",
    "West Midlands": "B CV DY HR ST TF WR WS WV",
    "East of England": "AL CB CM CO IP LU NR PE SG SS WD",
    "London": "E EC N NW SE SW W WC BR CR EN HA IG RM SM TW UB",
    "South East": "BN CT GU HP KT ME MK OX PO RG RH SL SO TN DA",
    "South West": "BA BH BS DT EX GL PL SN SP TA TQ TR",
    "Wales": "CF LD LL NP SA",
    "Scotland": "AB DD DG EH FK G HS IV KA KW KY ML PA PH TD ZE",
    "Northern Ireland": "BT",
    "Isle of Man": "IM", "Jersey": "JE", "Guernsey": "GY",
}
AREA_REGION = {a: r for r, areas in _AREAS.items() for a in areas.split()}
AREA_REGION.update({"SY": "West Midlands"})
_PC = re.compile(r"^\s*([A-Za-z]{1,2})\d")


def postcode_area(pc: str | None) -> str | None:
    m = _PC.match(pc or "")
    return m.group(1).upper() if m else None


def _log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} uk companies: {msg}", flush=True)


DDL = """
CREATE SCHEMA IF NOT EXISTS uk_companies;
CREATE TABLE IF NOT EXISTS uk_companies.meta (key text PRIMARY KEY, name text, rows bigint, loaded timestamptz, checked timestamptz, note text);
"""

COMPANY_COLS = ["company_number", "name", "name_core", "care_of", "po_box", "address1", "address2", "town", "county", "country",
                "postcode", "postcode_area", "region", "category", "status", "country_of_origin", "dissolved", "incorporated",
                "accounts_category", "accounts_last", "accounts_next", "charges", "charges_outstanding", "lp_gen", "lp_lim",
                "conf_next", "conf_last", "sic", "sic_text", "previous_names"]
COMPANY_DDL = """
CREATE TABLE uk_companies.company_new (
    company_number text NOT NULL, name text, name_core text, care_of text, po_box text, address1 text, address2 text, town text,
    county text, country text, postcode text, postcode_area text, region text, category text, status text, country_of_origin text,
    dissolved date, incorporated date, accounts_category text, accounts_last date, accounts_next date, charges integer,
    charges_outstanding integer, lp_gen integer, lp_lim integer, conf_next date, conf_last date, sic text[], sic_text text[],
    previous_names integer);
CREATE TABLE uk_companies.previous_name_new (company_number text NOT NULL, seq smallint, ceased date, name text, name_core text);
"""
PSC_COLS = ["psc_id", "company_number", "kind", "name", "name_norm", "name_core", "forename", "surname", "nationality",
            "country_of_residence", "birth_year", "birth_month", "natures", "notified_on", "ceased_on", "reg_number",
            "reg_country", "legal_form", "addr_country", "addr_locality", "addr_postcode", "statement"]
PSC_DDL = """
CREATE TABLE uk_companies.psc_new (
    psc_id text, company_number text NOT NULL, kind text, name text, name_norm text, name_core text, forename text, surname text,
    nationality text, country_of_residence text, birth_year smallint, birth_month smallint, natures text[], notified_on date,
    ceased_on date, reg_number text, reg_country text, legal_form text, addr_country text, addr_locality text, addr_postcode text,
    statement text);
"""


def d_uk(v: str):
    v = (v or "").strip()
    m = re.match(r"^(\d\d)/(\d\d)/(\d{4})$", v)
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def d_iso(v):
    v = (v or "").strip() if isinstance(v, str) else ""
    m = re.match(r"^(\d{4})-(\d\d)-(\d\d)", v)
    if not m or m.group(1) in ("0000", "9999"):
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def txt(v):
    v = (v or "").replace("\x00", "").strip() if isinstance(v, str) else v
    return v or None


def intv(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def core_uk(name: str | None) -> str | None:
    """The site's name core, and also without a trailing UK form (plc, llp, lp, cic, cio, uk limited words are already stripped)."""
    c = core(name)
    words = c.split()
    while words and words[-1] in ("plc", "llp", "lp", "cic", "cio", "ltd", "limited", "unlimited", "partnership"):
        words.pop()
    return (" ".join(words) or c)[:200] or None


def norm_person(forename, middle, surname) -> str | None:
    s = " ".join(x for x in (forename, middle, surname) if x).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s[:200] or None


# --- download ---------------------------------------------------------------------------------------------------------

def _get(url: str, binary=False, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def listing(page: str, pattern: str) -> str | None:
    html = _get(page)
    names = re.findall(pattern, html)
    return sorted(set(names))[-1] if names else None


def _fetch(name: str, dest: Path) -> None:
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(BASE + name, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    tmp.rename(dest)


def download(force: bool = False, psc_days: int = 25) -> int:
    """One conditional download per product. Returns how many products changed. The PSC snapshot is daily; it is refetched
    only when the loaded one is older than psc_days (the rest of the pipeline is monthly)."""
    RAW.mkdir(parents=True, exist_ok=True)
    changed = 0
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        for key, page, pat, local in (("basic", PAGE_BASIC, r'href="(BasicCompanyDataAsOneFile-\d{4}-\d\d-\d\d\.zip)"', "basic.zip"),
                                      ("psc", PAGE_PSC, r'href="(persons-with-significant-control-snapshot-\d{4}-\d\d-\d\d\.zip)"', "psc.zip")):
            try:
                name = listing(page, pat)
            except Exception as e:  # noqa: BLE001
                _log(f"download: {key}: listing failed ({e}); skipped")
                continue
            if not name:
                _log(f"download: {key}: no file on the listing page")
                continue
            row = conn.execute("SELECT name, loaded FROM uk_companies.meta WHERE key = %s", ("file:" + key,)).fetchone()
            if row and row[0] == name and not force:
                conn.execute("UPDATE uk_companies.meta SET checked = now() WHERE key = %s", ("file:" + key,))
                conn.commit()
                _log(f"download: {key}: {name} already downloaded")
                continue
            if key == "psc" and row and not force and row[1] and (dt.datetime.now(dt.timezone.utc) - row[1]).days < psc_days:
                _log(f"download: psc: loaded {row[1]:%Y-%m-%d}, next refresh after {psc_days} days")
                continue
            _log(f"download: {key}: fetching {name}")
            _fetch(name, RAW / local)
            conn.execute("""INSERT INTO uk_companies.meta (key, name, loaded, checked, note) VALUES (%s, %s, NULL, now(), 'downloaded')
                            ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name, loaded = NULL, checked = now(), note = 'downloaded'""",
                         ("file:" + key, name))
            conn.commit()
            changed += 1
            time.sleep(3)
    return changed


# --- load: basic company data -------------------------------------------------------------------------------------------

def _rows_basic(zpath: Path):
    with zipfile.ZipFile(zpath) as z:
        member = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(member) as raw:
            rd = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline=""))
            header = [h.strip() for h in next(rd)]
            ix = {h: i for i, h in enumerate(header)}
            pn = [(ix.get(f"PreviousName_{n}.CONDATE"), ix.get(f"PreviousName_{n}.CompanyName")) for n in range(1, 11)]
            g = lambda r, k: r[ix[k]] if k in ix and ix[k] < len(r) else ""  # noqa: E731
            for r in rd:
                if len(r) < 20:
                    continue
                num = g(r, "CompanyNumber").strip()
                if not num:
                    continue
                name = txt(g(r, "CompanyName"))
                pc = txt(g(r, "RegAddress.PostCode"))
                area = postcode_area(pc)
                sics = [txt(g(r, f"SICCode.SicText_{i}")) for i in range(1, 5)]
                sics = [s for s in sics if s]
                codes = [s.split(" - ")[0].strip() for s in sics]
                descs = [(s.split(" - ", 1)[1].strip() if " - " in s else s) for s in sics]
                prev = []
                for i, (dci, nci) in enumerate(pn, 1):
                    if nci is not None and nci < len(r) and r[nci].strip():
                        prev.append((i, d_uk(r[dci]) if dci is not None else None, r[nci].strip()))
                company = (num, name, core_uk(name), txt(g(r, "RegAddress.CareOf")), txt(g(r, "RegAddress.POBox")),
                           txt(g(r, "RegAddress.AddressLine1")), txt(g(r, "RegAddress.AddressLine2")), txt(g(r, "RegAddress.PostTown")),
                           txt(g(r, "RegAddress.County")), txt(g(r, "RegAddress.Country")), pc, area, AREA_REGION.get(area) if area else None,
                           txt(g(r, "CompanyCategory")), txt(g(r, "CompanyStatus")), txt(g(r, "CountryOfOrigin")),
                           d_uk(g(r, "DissolutionDate")), d_uk(g(r, "IncorporationDate")), txt(g(r, "Accounts.AccountCategory")),
                           d_uk(g(r, "Accounts.LastMadeUpDate")), d_uk(g(r, "Accounts.NextDueDate")),
                           intv(g(r, "Mortgages.NumMortCharges")), intv(g(r, "Mortgages.NumMortOutstanding")),
                           intv(g(r, "LimitedPartnerships.NumGenPartners")), intv(g(r, "LimitedPartnerships.NumLimPartners")),
                           d_uk(g(r, "ConfStmtNextDueDate")), d_uk(g(r, "ConfStmtLastMadeUpDate")),
                           codes or None, descs or None, len(prev))
                yield company, prev


def load(force: bool = False) -> None:
    zpath = RAW / "basic.zip"
    if not zpath.exists():
        _log("load: no basic.zip; run download first")
        return
    with db.connect() as conn:
        conn.execute(DDL)
        row = conn.execute("SELECT name, loaded FROM uk_companies.meta WHERE key = 'file:basic'").fetchone()
        done = conn.execute("SELECT name FROM uk_companies.meta WHERE key = 'table:company'").fetchone()
        if not force and row and done and done[0] == row[0]:
            _log("load: company: up to date")
            return
        t0, n, m = time.time(), 0, 0
        conn.execute("DROP TABLE IF EXISTS uk_companies.company_new")
        conn.execute("DROP TABLE IF EXISTS uk_companies.previous_name_new")
        conn.execute(COMPANY_DDL)
        conn.commit()
        with db.connect() as conn2, conn.cursor() as cur, conn2.cursor() as cur2:
            with cur.copy(f"COPY uk_companies.company_new ({', '.join(COMPANY_COLS)}) FROM STDIN") as cc, \
                    cur2.copy("COPY uk_companies.previous_name_new (company_number, seq, ceased, name, name_core) FROM STDIN") as cp:
                for company, prev in _rows_basic(zpath):
                    cc.write_row(company)
                    n += 1
                    for seq, ceased, pname in prev:
                        cp.write_row((company[0], seq, ceased, pname, core_uk(pname)))
                        m += 1
                    if n % 500000 == 0:
                        _log(f"load: company: {n:,} rows ...")
        conn.commit()
        _log(f"load: company_new copied {n:,} rows, {m:,} previous names in {time.time() - t0:.0f}s; indexing")
        conn.execute("SET maintenance_work_mem = '256MB'")
        conn.execute("ALTER TABLE uk_companies.company_new ADD PRIMARY KEY (company_number)")
        conn.execute("CREATE INDEX ON uk_companies.company_new (name_core text_pattern_ops)")
        conn.execute("CREATE INDEX ON uk_companies.company_new (name_core)")
        conn.execute("CREATE INDEX ON uk_companies.company_new (incorporated)")
        conn.execute("CREATE INDEX ON uk_companies.company_new (region, status)")
        conn.execute("CREATE INDEX ON uk_companies.company_new USING gin (sic)")
        conn.execute("CREATE INDEX ON uk_companies.company_new (postcode_area)")
        conn.execute("CREATE INDEX ON uk_companies.previous_name_new (company_number)")
        conn.execute("CREATE INDEX ON uk_companies.previous_name_new (name_core text_pattern_ops)")
        conn.commit()
        _log("load: btree indexes done; trigram index on name")
        conn.execute("CREATE INDEX ON uk_companies.company_new USING gin (name gin_trgm_ops)")
        conn.commit()
        conn.execute("ANALYZE uk_companies.company_new")
        conn.execute("ANALYZE uk_companies.previous_name_new")
        conn.commit()
        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS uk_companies.company CASCADE")
            conn.execute("DROP TABLE IF EXISTS uk_companies.previous_name")
            conn.execute("ALTER TABLE uk_companies.company_new RENAME TO company")
            conn.execute("ALTER TABLE uk_companies.previous_name_new RENAME TO previous_name")
            conn.execute("""INSERT INTO uk_companies.meta (key, name, rows, loaded, checked, note) VALUES ('table:company', %s, %s, now(), now(), 'loaded')
                            ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name, rows = EXCLUDED.rows, loaded = now(), checked = now()""",
                         (row[0] if row else None, n))
            conn.execute("""INSERT INTO uk_companies.meta (key, name, rows, loaded, checked, note) VALUES ('table:previous_name', %s, %s, now(), now(), 'loaded')
                            ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name, rows = EXCLUDED.rows, loaded = now(), checked = now()""",
                         (row[0] if row else None, m))
            conn.execute("UPDATE uk_companies.meta SET loaded = now(), note = 'loaded' WHERE key = 'file:basic'")
        _log(f"load: company {n:,} rows, previous_name {m:,} rows in {time.time() - t0:.0f}s")


# --- load: PSC snapshot -------------------------------------------------------------------------------------------------

def _psc_row(d: dict):
    data = d.get("data") or {}
    num = d.get("company_number")
    if not num:
        return None
    kind = (data.get("kind") or "").replace("-person-with-significant-control", "").replace("-beneficial-owner", "-bo")
    links = (data.get("links") or {}).get("self") or ""
    psc_id = links.rsplit("/", 1)[-1] if links else None
    ne = data.get("name_elements") or {}
    ident = data.get("identification") or {}
    addr = data.get("address") or {}
    dob = data.get("date_of_birth") or {}
    name = txt(data.get("name"))
    indiv = kind.startswith("individual")
    forename, surname = txt(ne.get("forename")), txt(ne.get("surname"))
    nm = norm_person(forename, ne.get("middle_name"), surname) if indiv else None
    year = dob.get("year") if isinstance(dob.get("year"), int) else None
    month = dob.get("month") if isinstance(dob.get("month"), int) else None
    stmt = txt(data.get("statement")) or (txt(data.get("description")) if kind in ("super-secure",) else None)
    return (psc_id, num, kind or None, name, nm, None if indiv else (core_uk(name) if name else None), forename, surname,
            txt(data.get("nationality")), txt(data.get("country_of_residence")), year, month, data.get("natures_of_control") or None,
            d_iso(data.get("notified_on")), d_iso(data.get("ceased_on")), None if indiv else txt(ident.get("registration_number")),
            None if indiv else txt(ident.get("country_registered")), None if indiv else txt(ident.get("legal_form")),
            None if indiv else txt(addr.get("country")), None if indiv else txt(addr.get("locality")),
            None if indiv else txt(addr.get("postal_code")), stmt)


def load_psc(force: bool = False) -> None:
    zpath = RAW / "psc.zip"
    if not zpath.exists():
        _log("psc: no psc.zip; run download first")
        return
    with db.connect() as conn:
        conn.execute(DDL)
        row = conn.execute("SELECT name FROM uk_companies.meta WHERE key = 'file:psc'").fetchone()
        done = conn.execute("SELECT name FROM uk_companies.meta WHERE key = 'table:psc'").fetchone()
        if not force and row and done and done[0] == row[0]:
            _log("psc: up to date")
            return
        t0, n, bad = time.time(), 0, 0
        conn.execute("DROP TABLE IF EXISTS uk_companies.psc_new")
        conn.execute(PSC_DDL)
        conn.commit()
        with zipfile.ZipFile(zpath) as z:
            member = next(nm for nm in z.namelist() if nm.endswith(".txt"))
            with z.open(member) as raw, conn.cursor() as cur, \
                    cur.copy(f"COPY uk_companies.psc_new ({', '.join(PSC_COLS)}) FROM STDIN") as cp:
                for line in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
                    try:
                        r = _psc_row(json.loads(line))
                    except ValueError:
                        bad += 1
                        continue
                    if r is None:
                        bad += 1
                        continue
                    cp.write_row(r)
                    n += 1
                    if n % 1000000 == 0:
                        _log(f"psc: {n:,} rows ... ({time.time() - t0:.0f}s)")
        conn.commit()
        _log(f"psc: copied {n:,} rows ({bad} skipped) in {time.time() - t0:.0f}s; indexing")
        conn.execute("SET maintenance_work_mem = '256MB'")
        conn.execute("CREATE INDEX ON uk_companies.psc_new (company_number)")
        conn.execute("CREATE INDEX ON uk_companies.psc_new (name_norm, birth_year, birth_month) WHERE name_norm IS NOT NULL")
        conn.execute("CREATE INDEX ON uk_companies.psc_new (name_core) WHERE name_core IS NOT NULL")
        conn.execute("CREATE INDEX ON uk_companies.psc_new (reg_number) WHERE reg_number IS NOT NULL")
        conn.commit()
        conn.execute("ANALYZE uk_companies.psc_new")
        conn.commit()
        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS uk_companies.psc")
            conn.execute("ALTER TABLE uk_companies.psc_new RENAME TO psc")
            conn.execute("""INSERT INTO uk_companies.meta (key, name, rows, loaded, checked, note) VALUES ('table:psc', %s, %s, now(), now(), 'loaded')
                            ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name, rows = EXCLUDED.rows, loaded = now(), checked = now()""",
                         (row[0] if row else None, n))
            conn.execute("UPDATE uk_companies.meta SET loaded = now(), note = 'loaded' WHERE key = 'file:psc'")
        _log(f"psc: {n:,} rows in {time.time() - t0:.0f}s")


# --- US-resident individual PSCs: the state, for the person cross-reference (loader/uk_companies_xref.py) ------------------

US_STATES = {"alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO", "connecticut": "CT",
             "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
             "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
             "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
             "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
             "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
             "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
             "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY"}
_STATE_CODES = set(US_STATES.values())
_US_NAMES = ("united states", "usa", "u.s.a", "america")


def _us_state(region: str | None) -> str | None:
    r = (region or "").strip()
    if r.upper() in _STATE_CODES:
        return r.upper()
    return US_STATES.get(re.sub(r"[^a-z ]", "", r.lower()).strip())


def psc_us_state(force: bool = False) -> None:
    """Rescan the PSC file for individuals who live in the US and keep (psc_id, company, name, state): the state is the one thing the
    person cross-reference needs. Only the state of the service address is kept, never the street."""
    zpath = RAW / "psc.zip"
    with db.connect() as conn:
        row = conn.execute("SELECT name FROM uk_companies.meta WHERE key = 'file:psc'").fetchone()
        done = conn.execute("SELECT name FROM uk_companies.meta WHERE key = 'table:psc_us_state'").fetchone()
        if not force and row and done and done[0] == row[0]:
            _log("psc_us_state: up to date")
            return
        t0, n = time.time(), 0
        conn.execute("DROP TABLE IF EXISTS uk_companies.psc_us_state_new")
        conn.execute("CREATE TABLE uk_companies.psc_us_state_new (psc_id text, company_number text, name_norm text, state text)")
        conn.commit()
        with zipfile.ZipFile(zpath) as z:
            member = next(nm for nm in z.namelist() if nm.endswith(".txt"))
            with z.open(member) as raw, conn.cursor() as cur, \
                    cur.copy("COPY uk_companies.psc_us_state_new (psc_id, company_number, name_norm, state) FROM STDIN") as cp:
                for line in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
                    if "individual-person" not in line or not any(w in line.lower() for w in _US_NAMES):
                        continue
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    data = d.get("data") or {}
                    if data.get("kind") != "individual-person-with-significant-control" or data.get("ceased_on"):
                        continue
                    if not any(w in (data.get("country_of_residence") or "").lower() for w in _US_NAMES):
                        continue
                    ne = data.get("name_elements") or {}
                    nm = norm_person(txt(ne.get("forename")), ne.get("middle_name"), txt(ne.get("surname")))
                    st = _us_state((data.get("address") or {}).get("region"))
                    sid = ((data.get("links") or {}).get("self") or "").rsplit("/", 1)[-1]
                    if nm and st and sid:
                        cp.write_row((sid, d.get("company_number"), nm, st))
                        n += 1
        conn.commit()
        conn.execute("CREATE INDEX ON uk_companies.psc_us_state_new (name_norm, state)")
        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS uk_companies.psc_us_state")
            conn.execute("ALTER TABLE uk_companies.psc_us_state_new RENAME TO psc_us_state")
            conn.execute("""INSERT INTO uk_companies.meta (key, name, rows, loaded, checked, note) VALUES ('table:psc_us_state', %s, %s, now(), now(), 'loaded')
                            ON CONFLICT (key) DO UPDATE SET name = EXCLUDED.name, rows = EXCLUDED.rows, loaded = now(), checked = now()""",
                         (row[0] if row else None, n))
        _log(f"psc_us_state: {n:,} US-resident individual PSCs with a state in {time.time() - t0:.0f}s")


# --- summaries --------------------------------------------------------------------------------------------------------------

SUMMARY_SQL = [
    ("company_psc", """
        CREATE TABLE uk_companies.company_psc_new AS
        SELECT company_number,
               count(*) FILTER (WHERE ceased_on IS NULL AND kind NOT LIKE '%%statement%%' AND kind <> 'super-secure') AS active,
               count(*) AS total,
               count(*) FILTER (WHERE ceased_on IS NULL AND kind LIKE 'individual%%') AS active_individuals,
               count(*) FILTER (WHERE ceased_on IS NULL AND kind LIKE 'corporate%%') AS active_corporate
        FROM uk_companies.psc GROUP BY company_number""",
     "CREATE UNIQUE INDEX ON uk_companies.company_psc_new (company_number)"),
    ("psc_person", """
        CREATE TABLE uk_companies.psc_person_new AS
        SELECT p.name_norm, p.birth_year, p.birth_month, (array_agg(p.name ORDER BY p.notified_on))[1] AS name,
               (array_agg(p.nationality ORDER BY p.notified_on) FILTER (WHERE p.nationality IS NOT NULL))[1] AS nationality,
               (array_agg(p.country_of_residence ORDER BY p.notified_on) FILTER (WHERE p.country_of_residence IS NOT NULL))[1] AS country_of_residence,
               count(DISTINCT p.company_number) AS companies, min(p.notified_on) AS first_notified,
               (array_agg(p.company_number ORDER BY p.notified_on DESC))[1] AS example_company
        FROM uk_companies.psc p JOIN uk_companies.company c USING (company_number)
        WHERE p.kind = 'individual' AND p.ceased_on IS NULL AND p.name_norm IS NOT NULL AND array_length(string_to_array(p.name_norm, ' '), 1) >= 2
              AND p.birth_year IS NOT NULL AND p.birth_month IS NOT NULL
        GROUP BY p.name_norm, p.birth_year, p.birth_month
        HAVING count(DISTINCT p.company_number) >= 2""",
     "CREATE INDEX ON uk_companies.psc_person_new (companies DESC); CREATE INDEX ON uk_companies.psc_person_new (name_norm, birth_year, birth_month)"),
    ("sic", """
        CREATE TABLE uk_companies.sic_new AS
        SELECT code, (array_agg(descr ORDER BY n DESC))[1] AS descr, sum(n) AS companies FROM (
            SELECT s.code, s.descr, count(*) AS n FROM uk_companies.company c,
                   LATERAL unnest(c.sic, c.sic_text) AS s(code, descr)
            GROUP BY s.code, s.descr) q GROUP BY code""",
     "CREATE UNIQUE INDEX ON uk_companies.sic_new (code)"),
    ("stats", """
        CREATE TABLE uk_companies.stats_new AS
        SELECT 'status' AS kind, coalesce(status, 'Not stated') AS k, count(*) AS n, 0::bigint AS active, 0::bigint AS other, 0::bigint AS extra
        FROM uk_companies.company GROUP BY 2
        UNION ALL
        SELECT 'region', coalesce(region, 'No UK postcode'), count(*), count(*) FILTER (WHERE status = 'Active'),
               count(*) FILTER (WHERE status <> 'Active'), 0 FROM uk_companies.company GROUP BY 2
        UNION ALL
        SELECT 'category', coalesce(category, 'Not stated'), count(*), 0, 0, 0 FROM uk_companies.company GROUP BY 2
        UNION ALL
        SELECT 'sic_new', u.code, count(*) FILTER (WHERE c.incorporated >= current_date - 365), 0, 0, 0
        FROM uk_companies.company c, LATERAL unnest(c.sic) AS u(code) WHERE c.incorporated >= current_date - 365 GROUP BY 2""",
     "CREATE INDEX ON uk_companies.stats_new (kind, n DESC)"),
]


def summarize() -> None:
    t0 = time.time()
    with db.connect() as conn:
        conn.execute(DDL)
        have_psc = conn.execute("SELECT to_regclass('uk_companies.psc') IS NOT NULL").fetchone()[0]
        for name, create, idx in SUMMARY_SQL:
            if name in ("company_psc", "psc_person") and not have_psc:
                continue
            conn.execute(f"DROP TABLE IF EXISTS uk_companies.{name}_new")
            conn.commit()
            conn.execute(create)
            for stmt in idx.split(";"):
                conn.execute(stmt)
            conn.commit()
            conn.execute(f"ANALYZE uk_companies.{name}_new")
            conn.commit()
            with conn.transaction():
                conn.execute(f"DROP TABLE IF EXISTS uk_companies.{name}")
                conn.execute(f"ALTER TABLE uk_companies.{name}_new RENAME TO {name}")
            n = conn.execute(f"SELECT count(*) FROM uk_companies.{name}").fetchone()[0]
            conn.execute("""INSERT INTO uk_companies.meta (key, rows, loaded, checked, note) VALUES (%s, %s, now(), now(), 'summary')
                            ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""", ("summary:" + name, n))
            conn.commit()
            _log(f"summarize: {name}: {n:,} rows ({time.time() - t0:.0f}s)")


def nightly(force: bool = False) -> int:
    """Monthly refresh: download only when the listing shows a new file; reload what changed; summaries; then the cross-references
    (loader.uk_companies_xref). Returns EXIT_CHANGED when anything was reloaded."""
    changed = download(force=force)
    if not changed and not force:
        _log("nightly: Companies House has not published a new file")
        return 0
    from loader import offpeak
    offpeak.wait("uk companies reload", status=_log)
    load(force=force)
    load_psc(force=force)
    psc_us_state(force=force)
    summarize()
    try:
        from loader import uk_companies_xref
        uk_companies_xref.match()
        with db.connect() as conn:
            published = conn.execute("SELECT 1 FROM uk_companies.meta WHERE key = 'xlinks'").fetchone()
        if published:
            uk_companies_xref.publish()
    except Exception as e:  # noqa: BLE001
        _log(f"nightly: cross-references failed: {e}")
    return EXIT_CHANGED


def status() -> None:
    with db.connect() as conn:
        if conn.execute("SELECT to_regclass('uk_companies.meta') IS NULL").fetchone()[0]:
            print("uk companies: nothing loaded")
            return
        for k, name, rows, loaded in conn.execute("SELECT key, name, rows, loaded FROM uk_companies.meta ORDER BY key").fetchall():
            print(f"uk companies: {k}: name={name} rows={rows} loaded={loaded}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("steps", nargs="*", default=["download", "load", "psc", "summarize"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    for s in a.steps:
        if s == "download":
            download(force=a.force)
        elif s == "load":
            load(force=a.force)
        elif s == "psc":
            load_psc(force=a.force)
        elif s == "summarize":
            summarize()
        elif s == "psc_us":
            psc_us_state(force=a.force)
        elif s == "nightly":
            return nightly(force=a.force)
        elif s == "status":
            status()
        else:
            ap.error(f"unknown step {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
