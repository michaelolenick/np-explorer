"""SEC Form ADV, from the SEC's bulk "Form ADV Data" files (FOIA page; Part 1A, all schedules), for every
registered investment adviser (IA) and exempt reporting adviser (ERA):

- adv_filings: one row per filing: CRD and SEC numbers, legal and business name, main office, date submitted,
  regulatory assets under management (IA Item 5.F.2.c) and accounts
- adv_owners: Schedule A (direct owners and executive officers) and B (indirect owners), with control persons
- adv_funds: Schedule D section 7.B.1 private funds: name, fund ID, fund type, gross asset value, beneficial
  owners, minimum investment, master/feeder
Owners and funds are kept for each adviser's latest filing in each year (annual amendments and the changes in
between say the same thing many times over). Coverage: advisers from October 2000; private funds from November
2011, when Schedule D 7.B.1 began. The SEC posts new filing-data files a few times a year; run() loads any it
hasn't (adv_runs), and links:

- adv_fund_links: a fund to the Form D offerings filed under its name (normalized; the state too when both
  have one)
- adv_person_links: individual owners and control persons to people on the site, when the normalized name
  (with a middle name or initial) belongs to exactly one person whose states include the adviser's

The SEC stopped the filing-data releases after December 2024. From 2025 on, adviser-level Part 1A comes from its
monthly "Information About Registered Investment Advisers and Exempt Reporting Advisers" reports (MONTHLY_PAGE;
xlsx through mid-2025, zipped CSV after): one row per adviser with its latest filing. monthly() adds each adviser's
latest filing dated 2025 or later to adv_filings (the bulk files cover the years before), with the report file
and date as provenance (source, source_date), plus private fund count and gross assets and employees. Owners
(Schedules A and B) and per-fund Schedule D are in no public bulk file after 2024, so adv_owners and adv_funds stop
there. Monthly rows have no SEC filing ID: their filing_id is MONTHLY_ID + CRD * 100000 + days since 2000.

Usage: .venv/bin/python -m loader.adv [--links | --monthly [--no-links]]
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from loader import db

PAGE = "https://www.sec.gov/foia-services/frequently-requested-documents/form-adv-data"
MONTHLY_PAGE = ("https://www.sec.gov/data-research/sec-markets-data/"
                "information-about-registered-investment-advisers-exempt-reporting-advisers")
MONTHLY_FROM = dt.date(2025, 1, 1)       # the bulk filing-data files run through December 2024
MONTHLY_ID = 10**12
RAW = Path("/bulk/adv")
UA = "furp.org research michael@furp.org"
csv.field_size_limit(10_000_000)


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def files() -> list[str]:
    """Filing-data zips the SEC lists, oldest first."""
    html = _get(PAGE).decode("utf-8", "replace")
    names = sorted(set(re.findall(r'href="[^"]*/(adv[-_]filing[-_]data[^"/]*\.zip)"', html)))
    return names


def fetch(name: str) -> Path:
    dest = RAW / name
    if not dest.exists() or dest.stat().st_size == 0:
        RAW.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        tmp.write_bytes(_get(f"https://www.sec.gov/files/{name}"))
        tmp.rename(dest)
    return dest


def _rows(z: zipfile.ZipFile, pattern: str):
    """Rows (dicts) of every CSV in the zip whose name matches pattern."""
    for n in z.namelist():
        if re.search(pattern, n.rsplit("/", 1)[-1], re.I):
            with z.open(n) as f:
                yield from csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline=""))


def _date(v: str | None) -> dt.date | None:
    """ "03/03/2006 05:20:46 PM" or "11/13/2012" """
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", (v or "").strip())
    return dt.date(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def _num(v):
    v = (v or "").strip().replace(",", "")
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _count(v):
    n = _num(v)
    return int(n) if n is not None and 0 <= n < 2e9 else None


def _s(v, n=300):
    v = (v or "").strip()
    return v[:n] if v else None


def _person(name: str) -> str | None:
    """ "SMITH, JOHN, A" -> normalized "john a smith" (individuals on Schedule A/B are written last, first, middle)."""
    from app.names import normalize_name
    parts = [p.strip() for p in (name or "").split(",") if p.strip()]
    if len(parts) >= 2:
        name = " ".join(parts[1:] + parts[:1])
    return normalize_name(name) or None


def load_file(path: Path, status=print) -> dict:
    """One filing-data zip (it may be one of several parts: each part holds some of the CSVs)."""
    t0 = time.time()
    z = zipfile.ZipFile(path)
    names = [n.rsplit("/", 1)[-1] for n in z.namelist()]
    out = {"filings": 0, "owners": 0, "funds": 0}
    with db.connect() as conn:
        # Filings: base data (IA and ERA).
        if any(re.search(r"ADV_Base(_A)?_", n) for n in names):
            rows = []
            for kind, pat in (("IA", r"^IA_ADV_Base_A_.*\.csv$"), ("ERA", r"^ERA_ADV_Base_.*\.csv$")):
                for r in _rows(z, pat):
                    fid = (r.get("FilingID") or "").strip()
                    if not fid.isdigit():
                        continue
                    sub = _date(r.get("DateSubmitted"))
                    rows.append((int(fid), kind, _s(r.get("1E1"), 20), _s(r.get("1D"), 30), _s(r.get("1A")),
                                 _s(r.get("1B1")), _s(r.get("1F1-Street 1")), _s(r.get("1F1-City"), 100),
                                 _s(r.get("1F1-State"), 30), _s(r.get("1F1-Country"), 60), _s(r.get("1F1-Postal"), 20),
                                 sub, sub.year if sub else None,
                                 _num(r.get("5F2c")) if kind == "IA" else None,
                                 _count(r.get("5F2f")) if kind == "IA" else None,
                                 path.name))
            conn.execute("CREATE TEMP TABLE adv_f_new (LIKE adv_filings) ON COMMIT DROP")
            with conn.cursor() as cur, cur.copy("""COPY adv_f_new (filing_id, kind, crd, sec_number, legal_name,
                                                   business_name, street, city, state, country, postal, submitted,
                                                   year, aum, accounts, source) FROM STDIN""") as cp:
                for r in rows:
                    cp.write_row(r)
            conn.execute("""INSERT INTO adv_filings SELECT DISTINCT ON (filing_id) * FROM adv_f_new
                            ON CONFLICT (filing_id) DO UPDATE SET crd = excluded.crd, legal_name = excluded.legal_name,
                            business_name = excluded.business_name, submitted = excluded.submitted,
                            year = excluded.year, aum = excluded.aum, accounts = excluded.accounts""")
            conn.commit()
            out["filings"] = len(rows)
            status(f"adv {path.name}: {len(rows):,} filings")
        # Each adviser's latest filing in each year (from every filing loaded so far).
        keep = {r[0]: (r[1], r[2]) for r in conn.execute("""
            SELECT DISTINCT ON (crd, year) filing_id, crd, year FROM adv_filings WHERE crd IS NOT NULL
            ORDER BY crd, year, submitted DESC NULLS LAST, filing_id DESC""").fetchall()}
        if any(re.search(r"Schedule_A_B_", n) for n in names):
            n_ = 0
            conn.execute("CREATE TEMP TABLE adv_o_new (LIKE adv_owners) ON COMMIT DROP")
            with conn.cursor() as cur, cur.copy("""COPY adv_o_new (filing_id, crd, year, name, name_norm, entity_kind,
                                                   title, status_acquired, ownership_code, control_person, owner_id)
                                                   FROM STDIN""") as cp:
                for r in _rows(z, r"^(IA|ERA)_Schedule_A_B_.*\.csv$"):
                    fid = (r.get("FilingID") or "").strip()
                    if not fid.isdigit() or int(fid) not in keep or not (r.get("Full Legal Name") or "").strip():
                        continue
                    crd, year = keep[int(fid)]
                    ek = _s(r.get("DE/FE/I"), 5)
                    name = _s(r.get("Full Legal Name"))
                    cp.write_row((int(fid), crd, year, name, _person(name) if ek == "I" else None, ek,
                                  _s(r.get("Title or Status")), _s(r.get("Status Acquired"), 20),
                                  _s(r.get("Ownership Code"), 5), (r.get("Control Person") or "").strip() == "Y",
                                  _s(r.get("OwnerID"), 30)))
                    n_ += 1
            conn.execute("DELETE FROM adv_owners WHERE filing_id IN (SELECT DISTINCT filing_id FROM adv_o_new)")
            conn.execute("INSERT INTO adv_owners SELECT * FROM adv_o_new")
            conn.commit()
            out["owners"] = n_
            status(f"adv {path.name}: {n_:,} owners and control persons")
        if any(re.search(r"Schedule_D_7B1_", n) for n in names):
            n_ = 0
            conn.execute("CREATE TEMP TABLE adv_d_new (LIKE adv_funds) ON COMMIT DROP")
            with conn.cursor() as cur, cur.copy("""COPY adv_d_new (filing_id, crd, year, fund_name, fund_id, state,
                                                   country, fund_type, gav, min_investment, owners, master_fund,
                                                   feeder_fund) FROM STDIN""") as cp:
                for r in _rows(z, r"^(IA|ERA)_Schedule_D_7B1_\d.*\.csv$"):
                    fid = (r.get("FilingID") or "").strip()
                    if not fid.isdigit() or int(fid) not in keep or not (r.get("Fund Name") or "").strip():
                        continue
                    crd, year = keep[int(fid)]
                    gav = _num(r.get("Gross Asset Value"))
                    cp.write_row((int(fid), crd, year, _s(r.get("Fund Name")), _s(r.get("Fund ID"), 30),
                                  _s(r.get("State"), 40), _s(r.get("Country"), 60),
                                  _s(r.get("Fund Type Other")) if (r.get("Fund Type") or "") == "Other" and r.get("Fund Type Other") else _s(r.get("Fund Type"), 60),
                                  gav if gav is not None and 0 <= gav < 1e13 else None,
                                  _num(r.get("Minimum Investment")),
                                  _count(r.get("Owners")),
                                  (r.get("Master Fund") or "").strip() == "Y", (r.get("Feeder Fund") or "").strip() == "Y"))
                    n_ += 1
            conn.execute("DELETE FROM adv_funds WHERE filing_id IN (SELECT DISTINCT filing_id FROM adv_d_new)")
            conn.execute("INSERT INTO adv_funds SELECT * FROM adv_d_new")
            conn.commit()
            out["funds"] = n_
            status(f"adv {path.name}: {n_:,} private funds")
        conn.execute("""INSERT INTO adv_runs (file, filings, owners, funds) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (file) DO UPDATE SET loaded = now(), filings = excluded.filings,
                        owners = excluded.owners, funds = excluded.funds""",
                     (path.name, out["filings"], out["owners"], out["funds"]))
        conn.commit()
    status(f"adv {path.name}: done in {time.time() - t0:.0f}s")
    return out


def link(status=print) -> dict:
    """adv_fund_links (funds to Form D offerings) and adv_person_links (owners to people)."""
    from loader.recalls import core
    with db.connect() as conn:
        conn.execute("SET work_mem = '1GB'")
        # A later file can bring a newer filing for the same adviser and year: keep only the latest.
        conn.execute("""CREATE TEMP TABLE latest AS SELECT DISTINCT ON (crd, year) filing_id FROM adv_filings
                        WHERE crd IS NOT NULL ORDER BY crd, year, submitted DESC NULLS LAST, filing_id DESC""")
        conn.execute("CREATE INDEX ON latest (filing_id)")
        for t in ("adv_owners", "adv_funds"):
            conn.execute(f"DELETE FROM {t} x WHERE NOT EXISTS (SELECT 1 FROM latest l WHERE l.filing_id = x.filing_id)")
        conn.commit()
        funds = conn.execute("""SELECT DISTINCT ON (fund_id) fund_id, fund_name, state FROM adv_funds
                                WHERE fund_id IS NOT NULL ORDER BY fund_id, year DESC""").fetchall()
        offers: dict[str, list] = {}
        for root, name, state in conn.execute("SELECT root_accession, issuer_name, state FROM sec_formd_offerings").fetchall():
            offers.setdefault(core(name), []).append((root, state))
        links = set()
        for fund_id, name, state in funds:
            cands = offers.get(core(name), [])
            if state:
                same = [c for c in cands if c[1] and state.upper().startswith(c[1].upper()[:2])]
                cands = same or cands
            if 0 < len(cands) <= 5:
                links.update((fund_id, c[0]) for c in cands)
        conn.execute("TRUNCATE adv_fund_links")
        with conn.cursor() as cur, cur.copy("COPY adv_fund_links FROM STDIN") as cp:
            for r in links:
                cp.write_row(r)
        conn.commit()
        conn.execute("""CREATE TEMP TABLE uniq AS SELECT name_norm, min(id) AS id, min(states) AS states
                        FROM person_clusters WHERE NOT is_institution AND name_norm ~ '^\\S+ \\S+ \\S+'
                        GROUP BY 1 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON uniq (name_norm)")
        conn.execute("TRUNCATE adv_person_links")
        conn.execute("""INSERT INTO adv_person_links (crd, name_norm, cluster_id)
                        SELECT DISTINCT ON (o.crd, o.name_norm) o.crd, o.name_norm, u.id
                        FROM adv_owners o JOIN uniq u ON u.name_norm = o.name_norm
                        JOIN LATERAL (SELECT state FROM adv_filings f WHERE f.crd = o.crd AND f.state IS NOT NULL
                                      ORDER BY f.submitted DESC NULLS LAST LIMIT 1) f ON f.state = ANY(u.states)
                        WHERE o.entity_kind = 'I' AND o.name_norm IS NOT NULL""")
        conn.commit()
        for t in ("adv_filings", "adv_owners", "adv_funds", "adv_fund_links", "adv_person_links"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
        r = conn.execute("""SELECT (SELECT count(DISTINCT fund_id) FROM adv_fund_links),
                                   (SELECT count(*) FROM adv_person_links),
                                   (SELECT count(DISTINCT fund_id) FROM adv_funds)""").fetchone()
    out = {"funds_linked_to_form_d": r[0], "people_linked": r[1], "funds": r[2]}
    status(f"adv links: {r[0]:,} of {r[2]:,} funds linked to Form D offerings; {r[1]:,} owners linked to people")
    return out


def run(status=print, only_new: bool = True) -> None:
    with db.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT file FROM adv_runs").fetchall()}
    new = [n for n in files() if not (only_new and n in done)]
    for name in new:
        load_file(fetch(name), status)
    if new:
        link(status)
    else:
        status("adv: no new Form ADV filing-data files")


# --- monthly adviser reports (2025 on) --------------------------------------------------------------------

def monthly_files() -> list[tuple[dt.date, str, str]]:
    """(report date, file name, url) for each monthly report from MONTHLY_FROM on, oldest first. Names carry the
    date as mmddyy ("ia100226.zip", "ia100226-exempt.zip", "ia010225_0.xlsx")."""
    html = _get(MONTHLY_PAGE).decode("utf-8", "replace")
    out = set()
    for href in re.findall(r'href="([^"]*/(ia\d{6}[^"/]*\.(?:zip|xlsx)))"', html, re.I):
        m = re.match(r"ia(\d\d)(\d\d)(\d\d)", href[1], re.I)
        try:
            d = dt.date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            continue
        if d >= MONTHLY_FROM:
            out.add((d, href[1], href[0] if href[0].startswith("http") else "https://www.sec.gov" + href[0]))
    return sorted(out)


def _report_rows(path: Path):
    """Rows (dicts of strings) of a monthly report: an xlsx, or a zip holding one CSV."""
    if path.suffix.lower() == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True)
        it = wb[wb.sheetnames[0]].iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(it)]
        for row in it:
            yield {h: (v.strftime("%m/%d/%Y") if isinstance(v, (dt.date, dt.datetime)) else
                       "" if v is None else str(int(v)) if isinstance(v, float) and v.is_integer() else str(v))
                   for h, v in zip(head, row)}
        wb.close()
    else:
        z = zipfile.ZipFile(path)
        for n in z.namelist():
            if n.lower().endswith(".csv"):
                with z.open(n) as f:
                    for r in csv.DictReader(io.TextIOWrapper(f, encoding="latin-1", newline="")):
                        yield {(k or "").strip(): v for k, v in r.items()}


def _postal(v: str | None, country: str | None) -> str | None:
    v = _s(v, 20)
    if v and (country or "").startswith("United States") and v.isdigit() and len(v) < 5:
        v = v.zfill(5)                   # the xlsx reports store zip codes as numbers (02110 -> 2110)
    return v


def _monthly_columns() -> None:
    """The columns monthly rows add, if missing (checked first: the ALTER takes its lock even with nothing to add).
    It waits at most 5 minutes for that lock (owner, 2026-10-25); if still busy, the run fails and the next night
    tries again."""
    with db.connect() as conn:
        if conn.execute("""SELECT count(*) FROM information_schema.columns WHERE table_name = 'adv_filings'
                           AND column_name IN ('source_date', 'private_funds', 'private_fund_assets',
                                               'employees')""").fetchone()[0] == 4:
            return
        conn.execute("SET lock_timeout = '5min'")
        conn.execute("""ALTER TABLE adv_filings ADD COLUMN IF NOT EXISTS source_date date,
                        ADD COLUMN IF NOT EXISTS private_funds int, ADD COLUMN IF NOT EXISTS private_fund_assets numeric,
                        ADD COLUMN IF NOT EXISTS employees int""")
        conn.commit()


def load_monthly(path: Path, report: dt.date, status=print) -> int:
    """One monthly report: each adviser's latest filing, when it is dated MONTHLY_FROM or later. A filing already
    loaded from an earlier report is updated to this report's values and provenance."""
    _monthly_columns()
    rows = {}
    for r in _report_rows(path):
        crd = (r.get("Organization CRD#") or "").strip()
        sub = _date(r.get("Latest ADV Filing Date"))
        if not crd.isdigit() or not sub or sub < MONTHLY_FROM:
            continue
        kind = "ERA" if (r.get("Firm Type") or "").strip().upper().startswith("ERA") else "IA"
        fid = MONTHLY_ID + int(crd) * 100000 + (sub - dt.date(2000, 1, 1)).days
        country = _s(r.get("Main Office Country"), 60)
        gav = _num(r.get("Total Gross Assets of Private Funds"))
        rows[fid] = (fid, kind, crd, _s(r.get("SEC#"), 30), _s(r.get("Legal Name")), _s(r.get("Primary Business Name")),
                     _s(r.get("Main Office Street Address 1")), _s(r.get("Main Office City"), 100),
                     _s(r.get("Main Office State"), 30), country, _postal(r.get("Main Office Postal Code"), country),
                     sub, sub.year,
                     _num(r.get("5F(2)(c)")) if kind == "IA" else None,
                     _count(r.get("5F(2)(f)")) if kind == "IA" else None,
                     path.name, report, _count(r.get("Count of Private Funds - 7B(1)")),
                     gav if gav is not None and 0 <= gav < 1e14 else None,
                     _count(r.get("5A")) if kind == "IA" else None)
    cols = ("filing_id, kind, crd, sec_number, legal_name, business_name, street, city, state, country, postal, "
            "submitted, year, aum, accounts, source, source_date, private_funds, private_fund_assets, employees")
    with db.connect() as conn:
        conn.execute("CREATE TEMP TABLE adv_m_new (LIKE adv_filings) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy(f"COPY adv_m_new ({cols}) FROM STDIN") as cp:
            for r in rows.values():
                cp.write_row(r)
        sets = ", ".join(f"{c} = excluded.{c}" for c in cols.split(", ")[1:])
        conn.execute(f"""INSERT INTO adv_filings ({cols}) SELECT {cols} FROM adv_m_new
                         ON CONFLICT (filing_id) DO UPDATE SET {sets}
                         WHERE adv_filings.source_date IS NULL OR adv_filings.source_date <= excluded.source_date""")
        conn.execute("""INSERT INTO adv_runs (file, filings, owners, funds) VALUES (%s, %s, 0, 0)
                        ON CONFLICT (file) DO UPDATE SET loaded = now(), filings = excluded.filings""",
                     (path.name, len(rows)))
        conn.commit()
    status(f"adv monthly {path.name} ({report}): {len(rows):,} advisers with a filing since {MONTHLY_FROM}")
    return len(rows)


def monthly(status=print, links: bool = True) -> int:
    """Loads every monthly report not loaded yet (adv_runs), oldest first, then relinks."""
    with db.connect() as conn:
        done = {r[0] for r in conn.execute("SELECT file FROM adv_runs").fetchall()}
    n = 0
    new = [f for f in monthly_files() if f[1] not in done]
    for report, name, url in new:
        dest = RAW / "monthly" / name
        if not dest.exists() or dest.stat().st_size == 0:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(_get(url))
            tmp.rename(dest)
        n += load_monthly(dest, report, status)
    if new and links:
        link(status)
    elif not new:
        status("adv: no new monthly adviser reports")
    return n


if __name__ == "__main__":
    if "--links" in sys.argv:
        link()
    elif "--monthly" in sys.argv:
        monthly(links="--no-links" not in sys.argv)
    else:
        run(only_new="--all" not in sys.argv)
