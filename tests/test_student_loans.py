"""Student loan ABS: report parsers, "Not reported" handling, monthly gaps, stats and boards.

Parser tests run on real servicing reports from EDGAR (flattened text, tests/fixtures/slabs_*).
The stats and board tests run the loader's SQL over hand-made rows in a throwaway schema
(the same table definitions as migration 0027) and need DATABASE_URL.
"""

import gzip
import importlib.util
import os
import sys
import types
import uuid
from datetime import date
from pathlib import Path

import pytest

from app import student_loans as SL
from loader import sla_parse as P

FIX = Path(__file__).parent / "fixtures"


def text(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode()


# --- NCSLT: the worked example ---------------------------------------------------------------

def test_ncslt_worked_example():
    """National Collegiate Student Loan Trust 2007-4, collection period May 2008 (10-D filed 2008-06-06)."""
    r = P.parse_ncslt(text("slabs_ncslt_2007-4_2008-05.txt.gz"))
    assert r["collection_end"] == date(2008, 5, 31) and r["distribution_date"] == date(2008, 6, 25)
    assert r["pool_balance"] == 1_048_230_393.14           # I.A.3, current column
    assert (r["loan_count"], r["borrower_count"]) == (69_702, 67_599)
    assert [b["label"] for b in r["delinquency"]] == ["31-60 days", "61-90 days", "91-120 days",
                                                     "121-150 days", "151-180 days", "> 180 days"]
    assert r["delinq_30_59"] == 5_671_686.91 and r["delinq_90_119"] == 1_048_764.88
    assert round(r["delinq_120_plus"], 2) == round(1_072_833.07 + 331_688.78 + 1_159_568.77, 2)
    assert r["current_balance"] == 119_484_482.93 and r["forbearance"] == 12_991_597.79
    # TERI claims are cumulative; the month's defaults are the change.
    assert r["cum_defaults"] == 1_993_565.76 and round(r["defaults"], 2) == 269_924.69
    assert r["cum_default_pct"] == 0.20 and r["prepayment_rate"] == 2.43
    assert r["deferment"] is None                           # this report has no deferment row
    assert (r["closing_date"], r["original_balance"]) == (date(2007, 9, 20), 989_697_216.24)


# --- SLM / Navient: three table layouts, FFELP and private -------------------------------------

def test_navient_2014_layout():
    r = P.parse_slm(text("slabs_navient_2014-4_2017-10.txt.gz"))
    assert r["collection_end"] == date(2017, 10, 31) and r["pool_balance"] == 195_805_035.36
    assert (r["loan_count"], r["borrower_count"]) == (8_483, 4_838)
    assert (r["delinq_30_59"], r["delinq_120_plus"]) == (5_522_662.31, 5_996_684.67)
    assert (r["defaults"], r["charge_offs"]) == (336_861.70, 8_110.13)   # guarantor principal; non-reimbursable
    assert r["prepayment_rate"] == 5.61                                   # current period, not the prior one
    assert r["parties"]["depositor"] == "Navient Funding, LLC"
    assert r["parties"]["trustee"] == "Deutsche Bank National Trust Company"
    assert "recoveries" not in r                                          # FFELP: not reported
    assert (r["closing_date"], r["original_balance"]) == (date(2014, 8, 14), 258_980_803.38)


def test_slm_2010_single_period_layout():
    r = P.parse_slm(text("slabs_slm_2010-1_2010-04.txt.gz"))
    assert r["pool_balance"] == 1_204_391_509.00 and r["loan_count"] == 489_355
    assert r["current_balance"] == 514_532_946.44 and r["deferment"] == 264_425_019.33
    assert r["delinq_30_59"] == 63_384_320.62 and r["prepayment_rate"] == -5.97


def test_slm_2006_two_period_layout_reads_the_current_column():
    r = P.parse_slm(text("slabs_slm_2006-1_2006-03.txt.gz"))
    assert r["pool_balance"] == 2_392_503_947.95 and r["loan_count"] == 767_540
    assert r["delinq_30_59"] == 93_562_290.31                # not the prior period's 114,020,462.89
    assert r["defaults"] == 698_423.13


def test_slm_private_credit():
    r = P.parse_slm(text("slabs_slm_private_2003-c_2015-11.txt.gz"))
    assert r["pool_balance"] == 382_704_539.85
    assert r["defaults"] == 1_564_544.97                     # change in gross defaults, not the cumulative 212M
    assert r["recoveries"] == 1_009_662.48
    assert {b["label"] for b in r["delinquency"]} >= {"121-150 days", "151-180 days"}


def test_nelnet_quarterly_with_split_rows():
    """Nelnet Student Loan Trust 2008-2, quarter ending November 2008: deferment and forbearance are each
    split into subsidized and unsubsidized rows; the current quarter is the second column."""
    r = P.parse_nelnet(text("slabs_nelnet_2008-2_2008-11.txt.gz"))
    assert (r["collection_start"], r["collection_end"]) == (date(2008, 9, 1), date(2008, 11, 30))
    assert r["pool_balance"] == 453_746_482.63 and r["loan_count"] == 115_959
    assert r["current_balance"] == 103_900_753.82                 # "0-30 days delinquent"
    assert round(r["deferment"], 2) == round(3_216_331.68 + 4_806_607.98, 2)
    assert round(r["forbearance"], 2) == round(1_765_043.03 + 2_071_374.48, 2)
    assert r["delinq_30_59"] == 852_053.06 and r["defaults"] == 135_290.61
    assert "recoveries" not in r


def test_prospectus_cover_parties():
    cover = ("424B5 PROSPECTUS SUPPLEMENT $1,000,000,000 SLM Student Loan Trust 2010-1 Issuing Entity SLM Funding LLC "
             "Depositor Sallie Mae, Inc. Sponsor, Servicer and Administrator Student Loan-Backed Notes")
    assert P.prospectus_parties(cover) == {"depositor": "SLM Funding LLC", "sponsor": "Sallie Mae, Inc.",
                                           "servicer": "Sallie Mae, Inc.", "administrator": "Sallie Mae, Inc."}
    slc = ("SLC Student Loan Trust 2010-1 Issuing Entity SLC Student Loan Receivables I, Inc. Depositor The Student "
           "Loan Corporation Sponsor Seller Servicer and Administrator $1,000 Notes")
    assert P.prospectus_parties(slc) == {"depositor": "SLC Student Loan Receivables I, Inc.",
                                         "sponsor": "The Student Loan Corporation"}


def test_decimal_comma_typo():
    # SLM Student Loan Trust 2011-3, April 2012 report prints "Guarantor Principal 1,904,607,71".
    assert P.money("1,904,607,71") == 1_904_607.71
    assert P.money("1,904,607") == 1_904_607 and P.money("(317.63 )") == -317.63


def test_numbers_after_reads_dashes_parentheses_and_percent():
    t = "Since Issued Constant Prepayment Rate (42.82)% (43.06)% Losses $ - Next"
    assert P.tokens_after(t, "Prepayment Rate", 2) == [(-42.82, True), (-43.06, True)]
    assert P.numbers_after(t, "Losses", 1) == [0.0]
    assert P.numbers_after(t, "Losses", 2) is None
    assert P.numbers_after(t, "Absent label", 1) is None


# --- display ---------------------------------------------------------------------------------

def test_unreported_is_never_zero():
    assert SL.fmt(None, "money") == "Not reported"
    assert SL.fmt(None, "pct") == "Not reported"
    assert SL.fmt(0, "money") == "$0"
    assert SL.fmt(12.345, "pct") == "12.35%"


def test_gaps_lists_missing_months():
    months = [{"period": date(2020, m, 1)} for m in (1, 2, 3, 6, 7)] + [{"period": date(2021, 1, 1)}]
    assert SL.gaps(months) == ["2020-04", "2020-05", "2020-08", "2020-09", "2020-10", "2020-11", "2020-12"]
    assert SL.gaps([]) == []
    quarterly = [{"period": date(2020, m, 1), "period_months": 3} for m in (3, 6, 12)]
    assert SL.gaps(quarterly) == ["2020-07", "2020-08", "2020-09"]


def test_delinq_rate_basis():
    assert SL.delinq_rate({"delinq_total": 10, "current_balance": 90, "pool_balance": 200}) == (10.0, "repayment")
    assert SL.delinq_rate({"delinq_total": 10, "current_balance": None, "pool_balance": 200}) == (5.0, "pool")
    assert SL.delinq_rate({"delinq_total": None, "pool_balance": 200}) == (None, None)


def test_spark_breaks_line_at_missing_months():
    pts = [(date(2020, m, 1), 100.0 - m) for m in (1, 2, 3, 6, 7, 8)]
    c = SL.spark(pts)
    assert len(c["lines"]) == 2 and c["first"] == date(2020, 1, 1)
    assert SL.spark([(date(2020, 1, 1), 5.0)]) is None


def test_trust_page_shows_not_reported(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    t = {"cik": 1, "name": "Example Student Loan Trust 2020-1", "family": "slm", "program_type": "FFELP",
         "sponsor": None, "depositor": "Example Funding LLC", "servicer": None, "administrator": None,
         "trustee": None, "closing_date": None, "original_balance": None, "filing_url": "https://www.sec.gov/x",
         "prospectus_url": None, "months_parsed": 2, "months_failed": 0}
    month = {c: None for c, _, _ in SL.FIELDS} | {
        "period": date(2020, 1, 1), "pool_balance": 1000, "delinq_total": 10, "current_balance": 90,
        "defaults": 5, "recoveries": None, "form_type": "10-D", "document_url": "https://www.sec.gov/d",
        "filing_url": None, "parse_notes": None, "delinquency": [{"label": "31-60 days", "balance": 10, "count": 1}]}
    months = [month, {**month, "period": date(2020, 3, 1)}]
    for m in months:
        m["delinq_rate"], m["delinq_basis"] = SL.delinq_rate(m)
    data = {"trust": t, "months": months, "stats": None, "gaps": SL.gaps(months), "parties": [], "fam": SL.family("slm")}
    monkeypatch.setattr(SL, "trust", lambda cik: data if cik == 1 else None)
    client = TestClient(main.app)
    page = client.get("/student-loans/trust/1").text
    assert "Example Student Loan Trust 2020-1" in page
    assert "Not reported" in page and "2020-02" in page              # recoveries; the missing month
    assert "Not named in the monthly reports" in page                # sponsor
    assert client.get("/student-loans/trust/2").status_code == 404


# --- stats, years and boards over a throwaway schema ----------------------------------------

def _migration():
    spec = importlib.util.spec_from_file_location(
        "m0027", Path(__file__).parents[1] / "migrations/versions/0027_student_loans.py")
    m = importlib.util.module_from_spec(spec)
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = types.SimpleNamespace(op=None)
    try:
        spec.loader.exec_module(m)
    finally:
        if saved is not None:
            sys.modules["alembic"] = saved
        else:
            del sys.modules["alembic"]
    return m


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"sla_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    try:
        conn.execute(f"SET search_path = {schema}, public")
        conn.execute(_migration().TABLES)
        conn.execute("""INSERT INTO student_loan_trusts (cik, name, family, program_type, depositor)
                        VALUES (1, 'Gap Trust 2019-1', 'slm', 'FFELP', 'Gap Funding LLC'),
                               (2, 'Steady Trust 2018-1', 'ncslt', 'private', 'Steady Funding LLC')""")
        rows = []
        # Trust 1: monthly, with July and August 2020 missing; delinquency rising; no recoveries reported.
        for i, (y, m) in enumerate([(2019, 7), (2019, 8), (2019, 9), (2019, 10), (2019, 11), (2019, 12),
                                    (2020, 1), (2020, 2), (2020, 3), (2020, 4), (2020, 5), (2020, 6),
                                    (2020, 9), (2020, 10), (2020, 11), (2020, 12)]):
            rows.append((1, date(y, m, 1), 1, 100_000_000 - i * 1_000_000, 900, 60_000_000, 2_000_000 + i * 300_000,
                         200_000, 10_000, None))
        # Trust 2: quarterly reports (period_months 3), private, recoveries reported.
        for q in range(8):
            rows.append((2, date(2019 + q // 4, 3 * (q % 4) + 1, 1), 3, 50_000_000, 400, 40_000_000, 1_000_000,
                         600_000, 300_000, 50_000))
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO student_loan_trust_months (cik, period, period_months, pool_balance,
                                   loan_count, current_balance, delinq_total, defaults, charge_offs, recoveries)
                               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", rows)
        from loader import student_loans as L
        conn.execute(L.STATS_SQL)
        conn.execute(L.YEARS_SQL)
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def q(db, sql, *a):
    cur = db.cursor(row_factory=__import__("psycopg").rows.dict_row)
    return cur.execute(sql, a).fetchall()


def test_missing_months_counted(db):
    s = q(db, "SELECT * FROM student_loan_trust_stats WHERE cik = 1")[0]
    assert (s["months"], s["missing_months"]) == (16, 2)
    assert (s["first_period"], s["last_period"]) == (date(2019, 7, 1), date(2020, 12, 1))


def test_quarterly_reports_are_not_gaps(db):
    s = q(db, "SELECT * FROM student_loan_trust_stats WHERE cik = 2")[0]
    assert (s["months"], s["missing_months"]) == (8, 0)


def test_rates_are_annualized_by_months_covered(db):
    one = q(db, "SELECT * FROM student_loan_trust_stats WHERE cik = 1")[0]
    two = q(db, "SELECT * FROM student_loan_trust_stats WHERE cik = 2")[0]
    # Trust 2: 600,000 per quarter on 50M = 4.8% a year, not 14.4% (quarterly reports cover 3 months).
    assert float(two["default_rate_12"]) == pytest.approx(4.8)
    assert float(two["chargeoff_rate_12"]) == pytest.approx(2.4)
    assert float(one["default_rate_12"]) > 0


def test_unreported_field_stays_null(db):
    y = q(db, "SELECT * FROM student_loan_trust_years WHERE cik = 1 AND year = 2020")[0]
    assert y["recoveries"] is None and y["defaults"] is not None
    assert q(db, "SELECT recoveries FROM student_loan_trust_years WHERE cik = 2 AND year = 2020")[0]["recoveries"] == 200_000


def test_delinquency_change_needs_the_month_a_year_back(db):
    y20 = q(db, "SELECT * FROM student_loan_trust_years WHERE cik = 1 AND year = 2020")[0]
    y19 = q(db, "SELECT * FROM student_loan_trust_years WHERE cik = 1 AND year = 2019")[0]
    assert y20["delinq_change_12"] is not None and float(y20["delinq_change_12"]) > 0
    assert y19["delinq_change_12"] is None                   # no December 2018 report


def test_boards_run_and_follow_the_contract(db):
    from app.student_loan_boards import student_loan_boards
    lead = ["pos", "rank", "org_pos", "subject_kind", "subject_key", "subject_name", "subject_norm", "subject_url",
            "match", "ein", "org_name", "state", "form_type", "tax_year", "filing_id", "object_id", "value"]
    for b in student_loan_boards():
        rows = q(db, f"SELECT * FROM ({b.sql}) v ORDER BY pos")
        assert rows, b.slug
        assert list(rows[0])[:len(lead)] == lead, b.slug
        assert all(r["subject_url"].startswith("/student-loans/trust/") for r in rows)
        assert {c.key for c in b.columns} <= set(rows[0]), b.slug
    largest = next(b for b in student_loan_boards() if b.slug == "student-loan-largest")
    top = q(db, f"SELECT * FROM ({largest.sql}) v WHERE org_pos = 1")[0]
    assert top["subject_name"] == "Gap Trust 2019-1" and top["tax_year"] == 2019
