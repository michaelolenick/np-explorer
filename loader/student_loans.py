"""Load student loan ABS trusts and their monthly servicing reports from SEC EDGAR.

  python -m loader.student_loans trusts            # write student_loan_trusts from ~/sla-data/trusts.json
  python -m loader.student_loans months [family]   # download + parse monthly reports (throttled; hours)
  python -m loader.student_loans stats             # recompute student_loan_trust_stats / _years
  python -m loader.student_loans parties           # parties + 990 matching
  python -m loader.student_loans all [family]
  python -m loader.student_loans refresh           # weekly (cron np-student-loans): new reports for every
                                                   # loaded trust, then stats and the boards; logged in
                                                   # student_loan_runs, and a failed run keeps the old data

Discovery (scripts/sla_index.py, scripts/sla_trusts.py) finds the trusts; this file decides
which are trusts, which family each belongs to, finds each monthly report's servicing
exhibit, parses it with the family's parser (loader/sla_parse.py) and stores one row per
trust-month. Downloads go through loader/sec.py (at most 4 requests a second, cached
under ~/sla-data). Memory stays small: one report at a time, rows written as they parse.
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from psycopg.types.json import Jsonb

from loader import db, sec
from loader import sla_parse as P

# (family, name pattern). First match wins. Corporate parents and unrelated companies whose
# names matched the discovery pattern (Collegiate Pacific, Brazos Sportswear, ...) match nothing.
FAMILY_RULES = [
    ("slm", r"^SLM (Student Loa?n?t? Trust|Private Credit Student Loan Trust|Private Education Loan Trust)"),
    ("slm", r"^Navient (Student Loan Trust|Private Education)"),
    ("smb", r"^SMB Private Education Loan Trust"),
    ("nelnet", r"^Nelnet (Student Loan Trust|Education Loan Funding|Private Education)"),
    ("ncslt", r"^National Collegiate (Student Loan|Master Student Loan|Trust)"),
    ("keycorp", r"^Key ?corp Student Loan Trust"),
    ("slc", r"^SLC Student Loan (Trust|Asset Backed)"),
    ("goal", r"^Goal Capital Funding Trust"),
    ("collegeloan", r"^College Loan Corp(oration)? Trust"),
    ("cfs", r"^Collegiate Funding Services Education Loan Trust"),
    ("edlinc", r"^Education Loans Inc"),
    ("gco", r"^GCO Education Loan Funding Trust"),
    ("access", r"^Access Group"),
    ("efc", r"^Education Funding Capital Trust"),
    ("pheaa", r"^PHEAA Student Loan Trust"),
    ("wachovia", r"^Wachovia Student Loan Trust"),
    ("chase", r"^Chase Education Loan Trust"),
    ("pnc", r"^PNC Student Loan Trust"),
    ("gmac", r"^GMAC Education Loan Funding Trust"),
    ("hef", r"^Higher Education Funding I"),
    ("other", r"Student Loan Trust|Education Loan Trust|Student Loan Asset[- ]Backed|Education Loan Funding Trust"),
]
PRIVATE_FAMILIES = {"smb", "ncslt"}
REPORT_FORMS = {"10-D", "10-D/A"}
EARLY_FORMS = {"8-K", "8-K/A"}          # monthly reports before Reg AB (2006) came on 8-K
LAST_8K_REPORT = "2006-07-01"           # Form 10-D took over from 2006; later 8-Ks are notices, not reports
EXHIBIT = re.compile(r"ex[-_]?v?99|exhibit[-_ ]?99", re.I)    # ex99_1.htm, exv99w1.htm, dex991.htm


def family_of(name: str) -> str | None:
    for fam, pat in FAMILY_RULES:
        if re.search(pat, name, re.I):
            return fam
    return None


def program_of(name: str, fam: str) -> str | None:
    if re.search(r"refi", name, re.I):
        return "refi"
    if fam in PRIVATE_FAMILIES or re.search(r"private", name, re.I):
        return "private"
    return None          # decided from the reports (FFELP language) in months()


def _now():
    return datetime.now(timezone.utc)


# --- trusts ----------------------------------------------------------------------------------

def trusts(status=print) -> int:
    data = json.loads((sec.CACHE / "trusts.json").read_text())
    n = 0
    with db.connect() as conn:
        for cik, t in data.items():
            fam = family_of(t["name"])
            if not fam:
                continue
            reports = t["forms"].get("10-D", 0) + t["forms"].get("10-D/A", 0)
            if not reports and t["forms"].get("8-K", 0) < 6:
                continue
            conn.execute("""
                INSERT INTO student_loan_trusts (cik, name, family, program_type, n_filings, filing_url, edgar_state,
                                                 retrieved_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cik) DO UPDATE SET name = excluded.name, family = excluded.family,
                    program_type = coalesce(student_loan_trusts.program_type, excluded.program_type),
                    n_filings = excluded.n_filings, filing_url = excluded.filing_url,
                    edgar_state = excluded.edgar_state, retrieved_at = excluded.retrieved_at""",
                (int(cik), t["name"], fam, program_of(t["name"], fam), reports or t["forms"].get("8-K", 0),
                 f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(cik):010d}&type=10-D",
                 t.get("biz_state") if re.fullmatch(r"[A-Z]{2}", t.get("biz_state") or "") else None, _now()))
            n += 1
        conn.commit()
    status(f"trusts: {n}")
    return n


# --- months ----------------------------------------------------------------------------------

def submissions(cik: int, refresh: bool = False) -> list[dict]:
    """Every filing of a trust. refresh=True re-reads the current list from the SEC (new reports); the older
    pages it points to never change, so they come from the cache."""
    d = json.loads(sec.fetch(f"{sec.DATA}/submissions/CIK{cik:010d}.json", refresh=refresh))
    blocks = [d["filings"]["recent"]] + [json.loads(sec.fetch(f"{sec.DATA}/submissions/{f['name']}"))
                                         for f in d["filings"].get("files", [])]
    out = []
    for b in blocks:
        for i in range(len(b["form"])):
            out.append({k: b[k][i] for k in ("form", "filingDate", "accessionNumber", "primaryDocument", "reportDate")})
    return out


def exhibit_url(cik: int, acc: str, primary: str) -> tuple[str | None, str]:
    """The servicing report document in a filing: the EX-99 exhibit, else the primary document."""
    base = f"{sec.WWW}/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
    idx = json.loads(sec.fetch(base + "/index.json"))
    items = [i for i in idx["directory"]["item"] if i["name"].lower().endswith((".htm", ".html", ".txt"))
             and not i["name"].startswith(acc) and i["name"] != primary]
    docs = [i["name"] for i in items]
    ex = [d for d in docs if EXHIBIT.search(d)] or [d for d in docs if re.search(r"99", d)]
    ex.sort(key=lambda d: (not re.search(r"99([._-]|w)?1(?!\d)", d), d))
    if not ex and items:      # no exhibit-style name: the largest attachment
        sized = [i for i in items if str(i.get("size") or "").isdigit()]
        ex = [max(sized, key=lambda i: int(i["size"]))["name"]] if sized else []
    doc = ex[0] if ex else (primary if primary and primary.lower().endswith((".htm", ".html", ".txt")) else None)
    return (f"{base}/{doc}" if doc else None), f"{base}/{acc}-index.htm"


def _period(parsed: dict, f: dict) -> date | None:
    d = parsed.get("collection_end")
    if not d and f.get("reportDate"):
        d = date.fromisoformat(f["reportDate"])
    if not d and parsed.get("distribution_date"):
        dd = parsed["distribution_date"]
        d = date(dd.year - (dd.month == 1), (dd.month - 2) % 12 + 1, 1)
    return P.period_of(d)


COLS = ["distribution_date", "collection_start", "collection_end", "period_months", "pool_balance", "loan_count", "borrower_count", "repayment_balance",
        "current_balance", "delinq_30_59", "delinq_60_89", "delinq_90_119", "delinq_120_plus", "delinq_total",
        "delinquency", "forbearance", "deferment", "school_grace", "claims_in_process", "defaults", "charge_offs",
        "recoveries", "cum_defaults", "cum_default_pct", "prepayment_rate", "wa_interest_rate"]


def _months_covered(parsed: dict) -> int:
    a, b = parsed.get("collection_start"), parsed.get("collection_end")
    if a and b and b > a:
        return max(1, round(((b - a).days + 1) / 30.44))
    return 1


def _save(conn, cik, period, parsed, f, doc, filing, fam):
    parsed = {**parsed, "period_months": _months_covered(parsed)}
    vals = {c: parsed.get(c) for c in COLS}
    vals["delinquency"] = Jsonb(vals["delinquency"]) if vals["delinquency"] is not None else None
    conn.execute(f"""
        INSERT INTO student_loan_trust_months (cik, period, {", ".join(COLS)}, form_type, accession, filing_date,
                                               filing_url, document_url, retrieved_at, parser, parse_notes)
        VALUES (%s, %s, {", ".join("%s" for _ in COLS)}, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (cik, period) DO UPDATE SET {", ".join(f"{c} = excluded.{c}" for c in COLS)},
            form_type = excluded.form_type, accession = excluded.accession, filing_date = excluded.filing_date,
            filing_url = excluded.filing_url, document_url = excluded.document_url,
            retrieved_at = excluded.retrieved_at, parser = excluded.parser, parse_notes = excluded.parse_notes
        WHERE student_loan_trust_months.filing_date IS NULL OR excluded.filing_date >= student_loan_trust_months.filing_date""",
        [cik, period, *vals.values(), f["form"], f["accessionNumber"], f["filingDate"], filing, doc, _now(), fam,
         parsed.get("parse_notes") or None])


PREFETCH_THREADS = 4     # downloads overlap; loader/sec.py still holds every thread to RATE requests a second


def prefetch(cik: int, reports: list[dict]) -> None:
    """Download each report's filing index and servicing exhibit into the cache, a few at a time."""
    def one(f):
        try:
            doc, _ = exhibit_url(cik, f["accessionNumber"], f["primaryDocument"])
            if doc:
                sec.fetch_path(doc)
        except Exception:  # noqa: BLE001 - the parse loop records the failure
            pass
    todo = [f for f in reports if not sec.cached(
        f"{sec.WWW}/Archives/edgar/data/{cik}/{f['accessionNumber'].replace('-', '')}/index.json")]
    if todo:
        with ThreadPoolExecutor(PREFETCH_THREADS) as pool:
            list(pool.map(one, todo))


def prospectus(conn, cik: int, fl: list[dict]) -> None:
    """Sponsor (and depositor, if the reports don't name one) from the trust's prospectus supplement cover."""
    pros = sorted((f for f in fl if f["form"] in ("424B5", "424B3", "424B2") and f["primaryDocument"]),
                  key=lambda f: (f["form"] != "424B5", f["filingDate"]))
    if not pros:
        return
    f = pros[0]
    url = f"{sec.WWW}/Archives/edgar/data/{cik}/{f['accessionNumber'].replace('-', '')}/{f['primaryDocument']}"
    try:
        parties = P.prospectus_parties(P.flatten(sec.fetch(url)))
    except Exception:  # noqa: BLE001 - the prospectus is a nice-to-have
        parties = {}
    conn.execute("""UPDATE student_loan_trusts SET prospectus_url = %s, sponsor = coalesce(%s, sponsor),
                        depositor = coalesce(depositor, %s), servicer = coalesce(servicer, %s),
                        administrator = coalesce(administrator, %s) WHERE cik = %s""",
                 (url, parties.get("sponsor"), parties.get("depositor"), parties.get("servicer"),
                  parties.get("administrator"), cik))


def trust_months(conn, cik: int, fam: str, status=print, refresh: bool = False) -> tuple[int, int, list[str]]:
    parser = P.PARSERS.get(fam) or P.PARSERS.get(P.ALIASES.get(fam, ""))
    if not parser:
        return 0, 0, ["no parser for this family yet"]
    fl = submissions(cik, refresh=refresh)
    early = fam in P.EARLY_8K
    reports = sorted((f for f in fl if f["form"] in REPORT_FORMS
                      or (early and f["form"] in EARLY_FORMS and f["filingDate"] < LAST_8K_REPORT)),
                     key=lambda f: (f["filingDate"], f["accessionNumber"]))
    prefetch(cik, reports)
    ok = bad = 0
    errors: list[str] = []
    ffelp = private = 0
    parties: dict = {}
    closing: dict = {}
    for f in reports:
        try:
            doc, filing = exhibit_url(cik, f["accessionNumber"], f["primaryDocument"])
            if not doc:
                raise ValueError("no servicing report document")
            text = P.flatten(sec.fetch(doc))
            if f["form"].startswith("8-K") and not P.looks_like_report(text):
                continue                     # an ordinary 8-K, not a monthly report
            parsed = parser(text)
            if parsed.get("error"):
                raise ValueError(parsed["error"])
            period = _period(parsed, f)
            if not period:
                raise ValueError("no reporting period")
            if re.search(r"Special Allowance|Guarantor Principal|Interest Subsidy", text, re.I):
                ffelp += 1
            elif re.search(r"private|charge[- ]?off", text, re.I):
                private += 1
            _save(conn, cik, period, parsed, f, doc, filing, fam)
            parties = parsed.get("parties") or parties          # the latest report's parties win
            if not closing and parsed.get("original_balance"):
                closing = {"date": parsed.get("closing_date"), "balance": parsed["original_balance"]}
            ok += 1
        except Exception as e:  # noqa: BLE001 - one bad report must not stop the trust
            bad += 1
            if len(errors) < 20:
                errors.append(f"{f['form']} {f['accessionNumber']}: {type(e).__name__}: {str(e)[:160]}")
        if (ok + bad) % 25 == 0:
            conn.commit()
    program = None
    if ffelp and private:
        program = "mixed"
    elif ffelp:
        program = "FFELP"
    elif private:
        program = "private"
    conn.execute("""UPDATE student_loan_trusts SET months_parsed = (SELECT count(*) FROM student_loan_trust_months WHERE cik = %(c)s),
                        months_failed = %(bad)s,
                        first_report = (SELECT min(period) FROM student_loan_trust_months WHERE cik = %(c)s),
                        last_report = (SELECT max(period) FROM student_loan_trust_months WHERE cik = %(c)s),
                        program_type = coalesce(program_type, %(prog)s),
                        closing_date = coalesce(%(cd)s, closing_date), original_balance = coalesce(%(ob)s, original_balance),
                        depositor = coalesce(%(dep)s, depositor), servicer = coalesce(%(svc)s, servicer),
                        administrator = coalesce(%(adm)s, administrator), trustee = coalesce(%(tru)s, trustee),
                        notes = %(notes)s, retrieved_at = now() WHERE cik = %(c)s""",
                 {"c": cik, "bad": bad, "prog": program, "notes": "; ".join(errors[:5]) or None,
                  "cd": closing.get("date"), "ob": closing.get("balance"),
                  "dep": parties.get("depositor"), "svc": parties.get("servicer"),
                  "adm": parties.get("administrator"), "tru": parties.get("trustee")})
    prospectus(conn, cik, fl)
    conn.commit()
    return ok, bad, errors


def months(only: str | None = None, status=print) -> None:
    """Every trust in a family (or one CIK), one at a time; progress lines flush as they go."""
    with db.connect() as conn:
        rows = conn.execute("""SELECT cik, name, family FROM student_loan_trusts
                               WHERE %s::text IS NULL OR family = %s OR cik::text = %s ORDER BY family, name""",
                            (only, only, only)).fetchall()
        for i, (cik, name, fam) in enumerate(rows):
            ok, bad, errors = trust_months(conn, cik, fam)
            status(f"[{i + 1}/{len(rows)}] {name} ({cik}, {fam}): {ok} parsed, {bad} failed"
                   + (f"; first error {errors[0]}" if errors else ""), flush=True)


# --- stats -----------------------------------------------------------------------------------

DELINQ_RATE = """CASE WHEN m.delinq_total IS NULL THEN NULL
                      WHEN m.current_balance IS NOT NULL AND m.current_balance + m.delinq_total > 0
                           THEN 100.0 * m.delinq_total / (m.current_balance + m.delinq_total)
                      WHEN m.pool_balance > 0 THEN 100.0 * m.delinq_total / m.pool_balance END"""
DELINQ_BASIS = """CASE WHEN m.delinq_total IS NULL THEN NULL WHEN m.current_balance IS NOT NULL THEN 'repayment'
                       WHEN m.pool_balance > 0 THEN 'pool' END"""

STATS_SQL = f"""
WITH m AS (
    SELECT m.*, {DELINQ_RATE} AS rate, {DELINQ_BASIS} AS basis,
           row_number() OVER (PARTITION BY cik ORDER BY period DESC) AS back
    FROM student_loan_trust_months m),
last12 AS (
    SELECT cik, count(*) AS n, avg(pool_balance) AS avg_bal, sum(coalesce(period_months, 1)) AS span,
           sum(defaults) AS defaults, sum(charge_offs) AS charge_offs
    FROM m WHERE back <= 12 GROUP BY cik)
INSERT INTO student_loan_trust_stats
SELECT a.cik, agg.months, agg.first_period, agg.last_period,
       greatest(0, extract(year FROM age(agg.last_period, agg.first_period)) * 12
        + extract(month FROM age(agg.last_period, agg.first_period)) - agg.covered)::int,
       a.pool_balance, a.loan_count, round(a.rate, 3), round(b.rate, 3), round(a.rate - b.rate, 3),
       CASE WHEN l.n >= 6 AND l.avg_bal > 0 AND l.defaults IS NOT NULL THEN round(100.0 * l.defaults / l.avg_bal * 12 / l.span, 3) END,
       CASE WHEN l.n >= 6 AND l.avg_bal > 0 AND l.charge_offs IS NOT NULL THEN round(100.0 * l.charge_offs / l.avg_bal * 12 / l.span, 3) END,
       agg.peak, b.pool_balance, now()
FROM m a
JOIN (SELECT cik, count(*) AS months, min(period) AS first_period, max(period) AS last_period,
             sum(coalesce(period_months, 1)) - (min(coalesce(period_months, 1)) FILTER (WHERE back = (SELECT max(back) FROM m m2 WHERE m2.cik = m.cik))) AS covered,
             max(pool_balance) AS peak FROM m GROUP BY cik) agg ON agg.cik = a.cik
LEFT JOIN m b ON b.cik = a.cik AND b.period = (a.period - interval '12 months')::date
LEFT JOIN last12 l ON l.cik = a.cik
WHERE a.back = 1"""

YEARS_SQL = f"""
WITH m AS (
    SELECT m.*, {DELINQ_RATE} AS rate, {DELINQ_BASIS} AS basis,
           row_number() OVER (PARTITION BY cik, extract(year FROM period) ORDER BY period DESC) AS back
    FROM student_loan_trust_months m),
y AS (
    SELECT cik, extract(year FROM period)::int AS year, count(*) AS months, avg(pool_balance) AS avg_bal,
           sum(coalesce(period_months, 1)) AS span,
           sum(defaults) AS defaults, sum(charge_offs) AS charge_offs, sum(recoveries) AS recoveries
    FROM m GROUP BY 1, 2)
INSERT INTO student_loan_trust_years
SELECT y.cik, y.year, y.months, a.period, a.pool_balance, a.loan_count, round(y.avg_bal, 2),
       y.defaults, y.charge_offs, y.recoveries,
       CASE WHEN y.avg_bal > 0 AND y.defaults IS NOT NULL THEN round(100.0 * y.defaults / y.avg_bal * 12 / y.span, 3) END,
       CASE WHEN y.avg_bal > 0 AND y.charge_offs IS NOT NULL THEN round(100.0 * y.charge_offs / y.avg_bal * 12 / y.span, 3) END,
       round(a.rate, 3), a.basis, round(b.rate, 3),
       CASE WHEN a.basis = b.basis THEN round(a.rate - b.rate, 3) END
FROM y
JOIN m a ON a.cik = y.cik AND extract(year FROM a.period) = y.year AND a.back = 1
LEFT JOIN m b ON b.cik = a.cik AND b.period = (a.period - interval '12 months')::date"""


def stats(status=print) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM student_loan_trust_stats")
        conn.execute(STATS_SQL)
        conn.execute("DELETE FROM student_loan_trust_years")
        conn.execute(YEARS_SQL)
        conn.commit()
        n = conn.execute("SELECT count(*) FROM student_loan_trust_years").fetchone()[0]
    status(f"stats: {n} trust-years")


# --- weekly refresh ----------------------------------------------------------------------------

def refresh(status=print, months_fn=None, stats_fn=None, boards_fn=None) -> bool:
    """New monthly reports for every loaded trust, then stats and the boards, logged in student_loan_runs.

    Months are upserted (a report is replaced only by a later filing for the same month), and stats are
    rebuilt in one transaction, so a run that stops part way leaves the previous figures in place; pages then
    show the last successful run's date and say the latest run failed."""
    months_fn = months_fn or _refresh_months
    stats_fn = stats_fn or stats
    boards_fn = boards_fn or _refresh_boards
    with db.connect(autocommit=True) as conn:
        run = conn.execute("INSERT INTO student_loan_runs DEFAULT VALUES RETURNING id").fetchone()[0]
        before = conn.execute("SELECT count(*) FROM student_loan_trust_months").fetchone()[0]
    try:
        n_trusts = months_fn(status)
        stats_fn(status)
        boards_fn(status)
    except Exception as e:  # noqa: BLE001 - recorded; the data from the last good run stays
        with db.connect(autocommit=True) as conn:
            conn.execute("UPDATE student_loan_runs SET finished_at = now(), ok = false, message = %s WHERE id = %s",
                         (f"{type(e).__name__}: {str(e)[:300]}", run))
        status(f"refresh failed: {type(e).__name__}: {e}")
        return False
    with db.connect(autocommit=True) as conn:
        after = conn.execute("SELECT count(*) FROM student_loan_trust_months").fetchone()[0]
        conn.execute("""UPDATE student_loan_runs SET finished_at = now(), ok = true, trusts = %s, new_months = %s
                        WHERE id = %s""", (n_trusts, after - before, run))
    status(f"refresh: {n_trusts} trusts, {after - before} new months")
    return True


def _refresh_months(status=print) -> int:
    with db.connect() as conn:
        rows = conn.execute("SELECT cik, name, family FROM student_loan_trusts ORDER BY family, name").fetchall()
        for cik, name, fam in rows:
            ok, bad, errors = trust_months(conn, cik, fam, refresh=True)
            status(f"{name} ({cik}): {ok} parsed, {bad} failed", flush=True)
    return len(rows)


def _refresh_boards(status=print) -> None:
    from app import boards as B
    from loader import boards as LB
    with db.connect() as conn:
        LB._prepare(conn)
        for b in B.BOARDS:
            if b.kind == "sla":
                LB.refresh_board(conn, b)
        conn.commit()


if __name__ == "__main__":
    cmd, arg = (sys.argv[1:] + [None, None])[:2]
    if cmd == "refresh":
        ok = refresh()
        try:            # average tuition (NCES Digest Table 330.10): a new edition yearly; never fails this job
            from loader import tuition
            tuition.refresh()
        except Exception as e:  # noqa: BLE001
            print(f"tuition refresh failed: {type(e).__name__}: {e}", flush=True)
        sys.exit(0 if ok else 1)
    if cmd in ("trusts", "all"):
        trusts()
    if cmd in ("months", "all"):
        months(arg)
    if cmd in ("stats", "all"):
        stats()
    if cmd in ("parties", "all"):
        from loader import sla_link
        sla_link.run()
