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

UA = "furp.org info@furp.org"
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
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):     # older Form D sets: "2019-03-29 17:29:14"
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

FORM345_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"


def form345_files() -> dict[str, str]:
    """{quarter: url} for every insider data set the SEC lists. From 2026q2 they live under a different path
    (/files/datastandardsinnovation/...), so take the links from the page."""
    import re as _re
    html = (_get(FORM345_PAGE) or b"").decode("utf-8", "replace")
    return {q: (h if h.startswith("http") else "https://www.sec.gov" + h)
            for h, q in sorted(set(_re.findall(r'href="([^"]*/(\d{4}q[1-4])_form345\.zip)"', html)))}


def load_insider_quarter(q: str, status=print, url: str | None = None) -> int:
    data = _get(url or f"{BASE}insider-transactions-data-sets/{q}_form345.zip")
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

FORMD_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets"


def formd_files() -> dict[str, str]:
    """{name: url} for every Form D data set the SEC lists (2008q1_d covers 2008 to 2011 and 2012q1_d 2012 to
    2013; quarterly after that). The newest live under a different path, so take the links from the page."""
    import re as _re
    html = (_get(FORMD_PAGE) or b"").decode("utf-8", "replace")
    out = {}
    for href in sorted(set(_re.findall(r'href="([^"]*/(\d{4}q[1-4])_d\.zip)"', html))):
        out[href[1]] = href[0] if href[0].startswith("http") else "https://www.sec.gov" + href[0]
    return out


def load_formd_quarter(q: str, status=print, url: str | None = None) -> int:
    data = _get(url or formd_files().get(q) or f"{BASE}form-d-data-sets/{q}_d.zip")
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
                         _s(o.get("AGGREGATENETASSETVALUERANGE"), 50),
                         (o.get("TOTALOFFERINGAMOUNT") or "").strip().lower().startswith("indefinite")))
        with conn.cursor() as cur:
            db.copy_rows(cur, "sec_formd", ["accession", "quarter", "filing_date", "form", "cik", "issuer_name",
                                            "entity_type", "street", "city", "state", "zip", "jurisdiction",
                                            "industry", "fund_type", "exemptions", "is_amendment", "previous_accession",
                                            "sale_date", "min_investment", "offering_amount", "amount_sold",
                                            "investors", "revenue_range", "nav_range", "offering_indefinite"], rows)
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
    """Every frame from 2019 to this year, upserted (COPY into a staging table, then one INSERT ... ON CONFLICT), so
    a value the SEC no longer returns stays and pages never see the table empty mid-load."""
    vals: dict[tuple, dict] = {}
    for year in range(2019, date.today().year + 1):
        for tag, col in (("PeoTotalCompAmt", "peo_total"), ("NonPeoNeoAvgTotalCompAmt", "neo_avg_total")):
            data = _get(f"https://data.sec.gov/api/xbrl/frames/ecd/{tag}/USD/CY{year}.json")
            if not data:
                continue
            for d in json.loads(data).get("data", []):
                if not d.get("end"):
                    continue
                v = vals.setdefault((str(d["cik"]), d["end"]), {"entity_name": d.get("entityName")})
                v[col], v[f"{col}_accn"] = d.get("val"), d.get("accn")
    with db.connect() as conn:
        conn.execute("CREATE TEMP TABLE ep (LIKE sec_exec_pay) ON COMMIT DROP")
        with conn.cursor() as cur:
            db.copy_rows(cur, "ep", ["cik", "entity_name", "period_end", "peo_total", "neo_avg_total", "accession"],
                         ((cik, v["entity_name"], end, v.get("peo_total"), v.get("neo_avg_total"),
                           v.get("neo_avg_total_accn") or v.get("peo_total_accn")) for (cik, end), v in vals.items()))
        conn.execute("""INSERT INTO sec_exec_pay SELECT * FROM ep
                        ON CONFLICT (cik, period_end) DO UPDATE SET entity_name = excluded.entity_name,
                            peo_total = coalesce(excluded.peo_total, sec_exec_pay.peo_total),
                            neo_avg_total = coalesce(excluded.neo_avg_total, sec_exec_pay.neo_avg_total),
                            accession = excluded.accession
                        WHERE (sec_exec_pay.entity_name, sec_exec_pay.peo_total, sec_exec_pay.neo_avg_total,
                               sec_exec_pay.accession) IS DISTINCT FROM
                              (excluded.entity_name, coalesce(excluded.peo_total, sec_exec_pay.peo_total),
                               coalesce(excluded.neo_avg_total, sec_exec_pay.neo_avg_total), excluded.accession)""")
        conn.commit()
    status(f"sec exec pay: {len(vals):,} company-years")
    return len(vals)


def load_all(status=print) -> None:
    listed = form345_files()
    for q in reversed(quarters(2006)):
        load_insider_quarter(q, status, listed.get(q))
    for q, url in sorted(formd_files().items(), reverse=True):
        load_formd_quarter(q, status, url)
    load_exec_pay(status)


def _newest(dataset: str) -> str | None:
    with db.connect() as conn:
        return conn.execute("SELECT max(quarter) FROM sec_runs WHERE dataset = %s", (dataset,)).fetchone()[0]


def refresh(status=print) -> dict:
    """Weekly (scripts/nightly.sh): every quarter after the newest one loaded (sec_runs), per data set; a quarter
    the SEC hasn't published yet is a 404 and is skipped (tried again next week). The newest appears a few weeks
    after quarter end. Then executive pay, the derived tables and the corporate leaderboards."""
    out = {"form345": [], "formd": []}
    last = _newest("form345")
    listed = form345_files()
    for q in quarters(2006):
        if last is None or q > last:
            if load_insider_quarter(q, status, listed.get(q)):
                out["form345"].append(q)
            else:
                status(f"sec form345 {q}: not published yet")
    last = _newest("formd")
    listed = formd_files()
    for q in quarters(2009):
        if last is None or q > last:
            if load_formd_quarter(q, status, listed.get(q) or f"{BASE}form-d-data-sets/{q}_d.zip"):
                out["formd"].append(q)
            else:
                status(f"sec formd {q}: not published yet")
    if out["formd"]:
        from loader import formd_parties
        formd_parties.build(status)
    from app import corporate
    if out["form345"] or out["formd"]:
        # Person links, sec_insider_sales; sec_formd_offerings only after a Form D load (its swap locks the table
        # for some seconds).
        corporate.build(status, offerings=bool(out["formd"]))
    if out["formd"]:
        from loader import formd_order
        formd_order.build(status)          # fund families and natural order (Haiku for every new or unclear family)
    if out["form345"]:
        from loader import buybacks
        buybacks.plans(status)             # 10b5-1 flags for the new quarters
        buybacks.sales(status)             # insider sales against buybacks
    out["exec_pay"] = load_exec_pay(status)
    boards(status)
    return out


def boards(status=print) -> None:
    """Refresh the SEC leaderboards in place (REFRESH CONCURRENTLY: pages keep reading them)."""
    from app import boards as B
    from loader import boards as LB
    with db.connect() as conn:
        LB._prepare(conn)
        for b in B.BOARDS:
            if b.slug.startswith("sec-"):
                status(f"board {b.slug}: {LB.refresh_board(conn, b):,} rows")
        LB.refresh_entries(conn)


if __name__ == "__main__":
    import sys
    # refresh (weekly): new quarters, exec pay, derived tables, boards. Or one step: exec_pay, boards, all.
    step = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    {"refresh": refresh, "exec_pay": load_exec_pay, "boards": boards, "all": load_all}[step]()
