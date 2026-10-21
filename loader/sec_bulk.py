"""SEC structured data: insider filings (Forms 3, 4, 5), Form D private offerings, and executive pay from proxy
statements' XBRL.

Sources (SEC fair-access rules: a User-Agent naming us, at most a few requests a second):
- Insider Transactions Data Sets, quarterly since 2006 (https://www.sec.gov/dera/data/form-345):
  sec_insider_filings, sec_insider_owners, sec_insider_trans (non-derivative transactions).
- Form D Data Sets, quarterly since 2009 (https://www.sec.gov/dera/data/form-d-data-sets):
  sec_formd (one row per filing, issuer and offering) and sec_formd_people (related persons).
- Executive pay: the pay-versus-performance table every proxy (DEF 14A) has tagged in XBRL since 2023, via the
  XBRL frames API: total compensation of the principal executive officer (ecd:PeoTotalCompAmt) and the average for
  the other named executives (ecd:NonPeoNeoAvgTotalCompAmt), by company and fiscal year: sec_exec_pay. (The full
  Summary Compensation Table is not tagged; parsing it from HTML is left for later.)

Every row keeps its accession number, so pages link to the filing on EDGAR (filing_url()).
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, datetime
from pathlib import Path

from loader import db

UA = "Strategy Studio info@strategystudio.org"
BASE = "https://www.sec.gov/files/structureddata/data/"
RAW = Path("/data/raw/sec_bulk")
csv.field_size_limit(10_000_000)


def filing_url(cik: str | int | None, accession: str) -> str:
    """The filing's index page on EDGAR."""
    acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik or 0)}/{acc}/{accession}-index.htm"


def _get(url: str) -> bytes | None:
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                time.sleep(0.3)
                return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"SEC kept failing: {url}")


def quarters(first: int) -> list[str]:
    today = date.today()
    out = []
    for y in range(first, today.year + 1):
        for q in range(1, 5):
            if (y, q) <= (today.year, (today.month - 1) // 3 + 1):
                out.append(f"{y}q{q}")
    return out


def _tsv(z: zipfile.ZipFile, name: str):
    info = next((i for i in z.infolist() if i.filename.upper().endswith("/" + name) or i.filename.upper() == name), None)
    if info is None:
        return
    with z.open(info) as raw:
        r = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""), delimiter="\t",
                       quoting=csv.QUOTE_NONE)
        head = next(r)
        for row in r:
            yield dict(zip(head, row))


def _d(v: str | None):
    v = (v or "").strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def _n(v: str | None):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _s(v: str | None, limit: int = 500):
    v = (v or "").strip()
    return v[:limit] or None


def owner_name_norm(raw: str) -> str:
    """EDGAR writes reporting owners last name first without a comma ("Smith John A"): put a comma after the
    first word so normalize_name reads it as "Last, First Middle"."""
    from app.names import normalize_name
    raw = (raw or "").strip()
    if "," not in raw and " " in raw:
        last, rest = raw.split(" ", 1)
        raw = f"{last}, {rest}"
    return normalize_name(raw)


# --- insider filings (Forms 3, 4, 5) --------------------------------------------------------------

def load_insider_quarter(q: str, status=print) -> int:
    data = _get(f"{BASE}insider-transactions-data-sets/{q}_form345.zip")
    if not data:
        return 0
    z = zipfile.ZipFile(io.BytesIO(data))
    subs = list(_tsv(z, "SUBMISSION.TSV"))
    accs = [s["ACCESSION_NUMBER"] for s in subs]
    with db.connect() as conn:
        for t in ("sec_insider_trans", "sec_insider_owners", "sec_insider_filings"):
            conn.execute(f"DELETE FROM {t} WHERE accession = ANY(%s)", (accs,))
        with conn.cursor() as cur:
            db.copy_rows(cur, "sec_insider_filings", ["accession", "quarter", "filing_date", "period", "form",
                                                      "issuer_cik", "issuer_name", "ticker"],
                         ((s["ACCESSION_NUMBER"], q, _d(s.get("FILING_DATE")), _d(s.get("PERIOD_OF_REPORT")),
                           _s(s.get("DOCUMENT_TYPE"), 20), _s(s.get("ISSUERCIK"), 20), _s(s.get("ISSUERNAME")),
                           _s(s.get("ISSUERTRADINGSYMBOL"), 20)) for s in subs))
            db.copy_rows(cur, "sec_insider_owners", ["accession", "owner_cik", "owner_name", "name_norm",
                                                     "relationship", "title", "city", "state"],
                         ((o["ACCESSION_NUMBER"], _s(o.get("RPTOWNERCIK"), 20), _s(o.get("RPTOWNERNAME")),
                           owner_name_norm(o.get("RPTOWNERNAME") or ""), _s(o.get("RPTOWNER_RELATIONSHIP"), 200),
                           _s(o.get("RPTOWNER_TITLE"), 300), _s(o.get("RPTOWNER_CITY"), 100),
                           _s(o.get("RPTOWNER_STATE"), 10)) for o in _tsv(z, "REPORTINGOWNER.TSV")))
            db.copy_rows(cur, "sec_insider_trans", ["accession", "sk", "security_title", "trans_date", "code",
                                                    "shares", "price", "acq_disp", "shares_after", "direct_indirect"],
                         ((t["ACCESSION_NUMBER"], int(t["NONDERIV_TRANS_SK"]), _s(t.get("SECURITY_TITLE"), 300),
                           _d(t.get("TRANS_DATE")), _s(t.get("TRANS_CODE"), 5), _n(t.get("TRANS_SHARES")),
                           _n(t.get("TRANS_PRICEPERSHARE")), _s(t.get("TRANS_ACQUIRED_DISP_CD"), 2),
                           _n(t.get("SHRS_OWND_FOLWNG_TRANS")), _s(t.get("DIRECT_INDIRECT_OWNERSHIP"), 2))
                          for t in _tsv(z, "NONDERIV_TRANS.TSV") if (t.get("NONDERIV_TRANS_SK") or "").isdigit()))
        conn.execute("INSERT INTO sec_runs (dataset, quarter, rows) VALUES ('form345', %s, %s)", (q, len(subs)))
        conn.commit()
    status(f"sec form345 {q}: {len(subs):,} filings")
    return len(subs)


# --- Form D -----------------------------------------------------------------------------------------

def load_formd_quarter(q: str, status=print) -> int:
    data = _get(f"{BASE}form-d-data-sets/{q}_d.zip")
    if not data or not data[:2] == b"PK":
        return 0
    z = zipfile.ZipFile(io.BytesIO(data))
    subs = {s["ACCESSIONNUMBER"]: s for s in _tsv(z, "FORMDSUBMISSION.TSV")}
    issuers = {i["ACCESSIONNUMBER"]: i for i in _tsv(z, "ISSUERS.TSV") if i.get("IS_PRIMARYISSUER_FLAG") == "YES"}
    offers = {o["ACCESSIONNUMBER"]: o for o in _tsv(z, "OFFERING.TSV")}
    accs = list(subs)
    with db.connect() as conn:
        conn.execute("DELETE FROM sec_formd_people WHERE accession = ANY(%s)", (accs,))
        conn.execute("DELETE FROM sec_formd WHERE accession = ANY(%s)", (accs,))
        rows = []
        for a, s in subs.items():
            i, o = issuers.get(a, {}), offers.get(a, {})
            rows.append((a, q, _d(s.get("FILING_DATE")), _s(s.get("SUBMISSIONTYPE"), 10), _s(i.get("CIK"), 20),
                         _s(i.get("ENTITYNAME")), _s(i.get("ENTITYTYPE"), 100), _s(i.get("STREET1")),
                         _s(i.get("CITY"), 100), _s(i.get("STATEORCOUNTRY"), 10), _s(i.get("ZIPCODE"), 20),
                         _s(i.get("JURISDICTIONOFINC"), 100), _s(o.get("INDUSTRYGROUPTYPE"), 100),
                         _s(o.get("INVESTMENTFUNDTYPE"), 100), _s(o.get("FEDERALEXEMPTIONS_ITEMS_LIST"), 200),
                         o.get("ISAMENDMENT") == "true", _s(o.get("PREVIOUSACCESSIONNUMBER"), 30),
                         _d(o.get("SALE_DATE")), _n(o.get("MINIMUMINVESTMENTACCEPTED")),
                         _n(o.get("TOTALOFFERINGAMOUNT")), _n(o.get("TOTALAMOUNTSOLD")),
                         _n(o.get("TOTALNUMBERALREADYINVESTED")), _s(o.get("REVENUERANGE"), 50),
                         _s(o.get("AGGREGATENETASSETVALUERANGE"), 50)))
        with conn.cursor() as cur:
            db.copy_rows(cur, "sec_formd", ["accession", "quarter", "filing_date", "form", "cik", "issuer_name",
                                            "entity_type", "street", "city", "state", "zip", "jurisdiction",
                                            "industry", "fund_type", "exemptions", "is_amendment", "previous_accession",
                                            "sale_date", "min_investment", "offering_amount", "amount_sold",
                                            "investors", "revenue_range", "nav_range"], rows)
            from app.names import normalize_name
            db.copy_rows(cur, "sec_formd_people", ["accession", "seq", "name", "name_norm", "relationships",
                                                   "clarification", "city", "state"],
                         ((p["ACCESSIONNUMBER"], int(p["RELATEDPERSON_SEQ_KEY"]),
                           _s(" ".join(x for x in (p.get("FIRSTNAME"), p.get("MIDDLENAME"), p.get("LASTNAME")) if x)),
                           normalize_name(" ".join(x for x in (p.get("FIRSTNAME"), p.get("MIDDLENAME"),
                                                               p.get("LASTNAME")) if x)),
                           _s(", ".join(x for x in (p.get("RELATIONSHIP_1"), p.get("RELATIONSHIP_2"),
                                                    p.get("RELATIONSHIP_3")) if x), 200),
                           _s(p.get("RELATIONSHIPCLARIFICATION"), 300), _s(p.get("CITY"), 100),
                           _s(p.get("STATEORCOUNTRY"), 10))
                          for p in _tsv(z, "RELATEDPERSONS.TSV")
                          if p["ACCESSIONNUMBER"] in subs and (p.get("RELATEDPERSON_SEQ_KEY") or "").isdigit()))
        conn.execute("INSERT INTO sec_runs (dataset, quarter, rows) VALUES ('formd', %s, %s)", (q, len(subs)))
        conn.commit()
    status(f"sec formd {q}: {len(subs):,} filings")
    return len(subs)


# --- executive pay (XBRL pay versus performance) ----------------------------------------------------

def load_exec_pay(status=print) -> int:
    n = 0
    with db.connect() as conn:
        conn.execute("DELETE FROM sec_exec_pay")
        for year in range(2019, date.today().year + 1):
            for tag, col in (("PeoTotalCompAmt", "peo_total"), ("NonPeoNeoAvgTotalCompAmt", "neo_avg_total")):
                data = _get(f"https://data.sec.gov/api/xbrl/frames/ecd/{tag}/USD/CY{year}.json")
                if not data:
                    continue
                for d in json.loads(data).get("data", []):
                    conn.execute(f"""INSERT INTO sec_exec_pay (cik, entity_name, period_end, {col}, accession)
                                     VALUES (%s, %s, %s, %s, %s)
                                     ON CONFLICT (cik, period_end) DO UPDATE SET {col} = excluded.{col},
                                         accession = excluded.accession""",
                                 (str(d["cik"]), d.get("entityName"), d.get("end"), d.get("val"), d.get("accn")))
                    n += 1
        conn.commit()
    status(f"sec exec pay: {n:,} values")
    return n


def load_all(status=print) -> None:
    for q in reversed(quarters(2006)):
        load_insider_quarter(q, status)
    for q in reversed(quarters(2009)):
        load_formd_quarter(q, status)
    load_exec_pay(status)


def refresh(status=print) -> None:
    """Quarterly data sets: reload the last two quarters (the newest appears a few weeks after quarter end)."""
    for q in quarters(2006)[-2:]:
        load_insider_quarter(q, status)
        load_formd_quarter(q, status)
    load_exec_pay(status)
