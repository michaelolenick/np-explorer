"""IRS exempt-status sources, so every tax-exempt organization has a page even without a full Form 990:

- the full Business Master File row (data/raw/bmf/*.csv, downloaded by loader/bmf.py): ruling date, deductibility,
  foundation type, status, organization type, income and assets (irs_bmf_detail)
- Form 990-N e-postcards (organizations with gross receipts normally $50,000 or less): tax years, principal
  officer, website (irs_epostcard)
- Publication 78: organizations eligible to receive tax-deductible contributions, with codes (irs_pub78)
- the automatic revocation list: exemptions revoked for not filing three years running, and reinstatements
  (irs_revocations)

The three IRS bulk files (apps.irs.gov/pub/epostcard) are downloaded when the IRS has republished them
(Last-Modified). Each table is loaded into a copy (<table>_new) and swapped in with a rename, so pages reading it
never wait on the load (2026-10-22: a TRUNCATE + COPY in one transaction held every org page for 5 s). Organizations that appear in these files but not in
organizations (revoked, terminated, or only ever a postcard filer) are added there with in_bmf false, so search
finds them and they get a page.

Usage: .venv/bin/python -m loader.irs_status
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import os
import zipfile

from loader import db, irs

BASE = "https://apps.irs.gov/pub/epostcard/data-download-{name}.zip"
NAMES = ("epostcard", "pub78", "revocation")


def _d(v: str, fmt: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(v.strip(), fmt).date() if v and v.strip() else None
    except ValueError:
        return None


def _ein(v: str) -> str | None:
    v = (v or "").strip()
    return v.zfill(9) if v.isdigit() and v.strip("0") else None


def _s(v):
    v = (v or "").strip()
    return v or None


def _int(v):
    v = (v or "").strip()
    return int(v) if v.lstrip("-").isdigit() else None


def _fetch(name: str) -> zipfile.ZipFile:
    dest = irs.RAW_DIR / "irs_status" / f"{name}.zip"
    url = BASE.format(name=name)
    remote = irs.remote_mtime(url)
    if dest.exists() and remote is not None and remote > dest.stat().st_mtime:
        dest.unlink()
    irs.download(url, dest)
    if remote is not None:
        os.utime(dest, (remote, remote))
    return zipfile.ZipFile(dest)


def _lines(z: zipfile.ZipFile):
    with z.open(z.namelist()[0]) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
            line = line.rstrip("\r\n")
            if line.strip():
                yield line.split("|")


def bmf_rows():
    seen = set()
    for p in sorted((irs.RAW_DIR / "bmf").glob("*.csv")):
        with open(p, newline="", encoding="latin-1") as f:
            for r in csv.DictReader(f):
                ein = _ein(r.get("EIN"))
                if not ein or ein in seen:
                    continue
                seen.add(ein)
                yield (ein, _s(r.get("ICO")), _s(r.get("GROUP")), _s(r.get("SUBSECTION")), _s(r.get("AFFILIATION")),
                       _s(r.get("CLASSIFICATION")), _s(r.get("RULING")), _s(r.get("DEDUCTIBILITY")),
                       _s(r.get("FOUNDATION")), _s(r.get("ACTIVITY")), _s(r.get("ORGANIZATION")), _s(r.get("STATUS")),
                       _s(r.get("TAX_PERIOD")), _s(r.get("FILING_REQ_CD")), _int(r.get("ASSET_AMT")),
                       _int(r.get("INCOME_AMT")), _int(r.get("REVENUE_AMT")))


def epostcard_rows(z):
    seen = set()
    for f in _lines(z):
        f += [""] * (26 - len(f))
        ein, year = _ein(f[0]), _int(f[1])
        if not ein or not year or (ein, year) in seen:
            continue
        seen.add((ein, year))
        dba = "; ".join(x for x in (_s(f[23]), _s(f[24]), _s(f[25])) if x) or None
        yield (ein, year, _s(f[2]), f[3].strip() == "T", f[4].strip() == "T", _d(f[5], "%m-%d-%Y"),
               _d(f[6], "%m-%d-%Y"), _s(f[7]), _s(f[8]), _s(f[11]), _s(f[13]),
               ", ".join(x for x in (_s(f[16]), _s(f[17])) if x) or None, _s(f[18]), _s(f[20]), _s(f[21]),
               _s(f[22]), dba)


def pub78_rows(z):
    seen = set()
    for f in _lines(z):
        f += [""] * (6 - len(f))
        ein = _ein(f[0])
        if ein and ein not in seen:
            seen.add(ein)
            yield (ein, _s(f[1]), _s(f[2]), _s(f[3]), _s(f[4]), _s(f[5]))


def revocation_rows(z):
    seen = set()
    for f in _lines(z):
        f += [""] * (12 - len(f))
        ein, rev = _ein(f[0]), _d(f[9], "%d-%b-%Y")
        if not ein or not rev or (ein, rev) in seen:
            continue
        seen.add((ein, rev))
        yield (ein, _s(f[1]), _s(f[2]), _s(f[3]), _s(f[4]), _s(f[5]), _s(f[6]), _s(f[7]), _s(f[8]), rev,
               _d(f[10], "%d-%b-%Y"), _d(f[11], "%d-%b-%Y"))


TABLES = {
    "irs_bmf_detail": ["ein", "ico", "group_exemption", "subsection", "affiliation", "classification", "ruling",
                       "deductibility", "foundation", "activity", "organization", "status", "tax_period",
                       "filing_req", "asset_amt", "income_amt", "revenue_amt"],
    "irs_epostcard": ["ein", "tax_year", "legal_name", "small", "terminated", "period_begin", "period_end", "website",
                      "officer_name", "officer_city", "officer_state", "street", "city", "state", "zip", "country",
                      "dba"],
    "irs_pub78": ["ein", "name", "city", "state", "country", "codes"],
    "irs_revocations": ["ein", "legal_name", "dba", "street", "city", "state", "zip", "country", "exemption_type",
                        "revocation_date", "posting_date", "reinstatement_date"],
}


def load(status=print) -> dict:
    from app.funders import normalize_org
    sources = {"irs_bmf_detail": bmf_rows(), "irs_epostcard": epostcard_rows(_fetch("epostcard")),
               "irs_pub78": pub78_rows(_fetch("pub78")), "irs_revocations": revocation_rows(_fetch("revocation"))}
    counts = {}
    with db.connect() as conn:
        for table, rows in sources.items():
            cols = TABLES[table]
            conn.execute(f"DROP TABLE IF EXISTS {table}_new, {table}_old")
            conn.execute(f"CREATE TABLE {table}_new (LIKE {table} INCLUDING ALL)")
            with conn.cursor() as cur, cur.copy(f"COPY {table}_new ({', '.join(cols)}) FROM STDIN") as cp:
                n = 0
                for r in rows:
                    cp.write_row(r)
                    n += 1
            conn.commit()
            conn.execute(f"ANALYZE {table}_new")
            conn.commit()
            # The swap: two renames under a lock held for milliseconds (pages give up after 150 ms anyway).
            conn.execute("SET LOCAL lock_timeout = '10s'")
            conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
            conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
            conn.execute(f"DROP TABLE {table}_old")
            conn.commit()
            counts[table] = n
            status(f"irs status: {table}: {n:,} rows")
        # Organizations known only from these lists get a row (and so a page and search): the latest name and
        # address each list has, revocation first (the legal name), then the e-postcard, then Pub 78.
        missing = conn.execute("""
            SELECT DISTINCT ON (ein) ein, name, street, city, state, zip, subsection FROM (
                SELECT ein, legal_name AS name, street, city, state, zip, exemption_type AS subsection, 1 AS pri,
                       revocation_date AS d FROM irs_revocations
                UNION ALL SELECT ein, legal_name, street, city, state, zip, NULL, 2, period_end FROM irs_epostcard
                UNION ALL SELECT ein, name, NULL, city, state, NULL, NULL, 3, NULL FROM irs_pub78) u
            WHERE NOT EXISTS (SELECT 1 FROM organizations o WHERE o.ein = u.ein) AND name IS NOT NULL
            ORDER BY ein, pri, d DESC NULLS LAST""").fetchall()
        with conn.cursor() as cur:
            cur.execute("CREATE TEMP TABLE stage_new_orgs (ein text, name text, name_norm text, street text, city text, "
                        "state text, zip text, subsection text) ON COMMIT DROP")
            with cur.copy("COPY stage_new_orgs FROM STDIN") as cp:
                for e, n, st_, c, st, z, sub in missing:
                    cp.write_row((e, n, normalize_org(n), st_, c, st, z, sub))
            cur.execute("""INSERT INTO organizations (ein, name, name_norm, street, city, state, zip, subsection, in_bmf)
                           SELECT ein, name, name_norm, street, city, state, zip, subsection, false FROM stage_new_orgs
                           ON CONFLICT (ein) DO NOTHING""")
        conn.commit()
        counts["organizations_added"] = len(missing)
    status(f"irs status: {counts}")
    return counts


if __name__ == "__main__":
    load()
