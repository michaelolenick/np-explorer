"""Organization page data: each tax year counted once when a return was amended (the Dell
Foundation's 2021 and 2022 pattern), grants per year with summary lines and returned grants,
donors, and the reconciliation note. Hand-made rows in a throwaway schema (needs DATABASE_URL)."""

import os
import uuid
from contextlib import contextmanager

import pytest

from app import queries
from loader.parser import SUMMARY_LINE

EIN = "364336415"
TABLES = ["organizations", "filings", "people", "person_cluster_members", "person_clusters", "contractors",
          "grants", "daf_stats", "expense_breakdown", "donors", "pf_payout"]

# Dell-like filings: 2021 and 2022 each have an original (superseded) and an amended return.
FILINGS = [  # id, year, superseded, amended
    (1, 2021, True, False), (2, 2021, False, True),
    (3, 2022, True, False), (4, 2022, False, True),
    (5, 2019, False, False),
]


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row
    from app.config import DATABASE_URL
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True, row_factory=dict_row)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"org_page_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    c.execute(f"CREATE SCHEMA {schema}")
    try:
        c.execute(f"SET search_path = {schema}, public")
        for t in TABLES:
            c.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)")
        c.execute("""INSERT INTO organizations (ein, name, name_norm, state, city) VALUES
                     (%s, 'MICHAEL AND SUSAN DELL FOUNDATION', 'michael and susan dell foundation', 'TX', 'AUSTIN'),
                     ('111111111', 'TEACH FOR AMERICA', 'teach for america', 'NY', 'NEW YORK'),
                     ('222222222', 'BILL & MELINDA GATES FOUNDATION', 'bill melinda gates foundation', 'WA', 'SEATTLE')""",
                  (EIN,))
        for fid, year, sup, amended in FILINGS:
            c.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, state, superseded, amended,
                         total_revenue, total_expenses, total_assets_eoy)
                         VALUES (%s, %s, %s, '990PF', %s, 'MICHAEL AND SUSAN DELL FOUNDATION', 'TX', %s, %s, 1, 2, 3)""",
                      (fid, EIN, 900 + fid, year, sup, amended))
        c.execute("INSERT INTO person_clusters (id, display_name, name_norm, n_orgs, is_institution) VALUES "
                  "(1, 'Janet Mountain', 'janet mountain', 1, false), (2, 'Unpaid Director', 'unpaid director', 1, false)")
        pid = 0
        for fid, year, *_ in FILINGS:
            for cid, pay in ((1, 500_000), (2, 0)):
                pid += 1
                c.execute("""INSERT INTO people (id, filing_id, ein, tax_year, source, name_raw, name_norm, title, comp_org)
                             SELECT %s, %s, %s, %s, '990PF-VIII', upper(display_name), name_norm, 'DIRECTOR', %s
                             FROM person_clusters WHERE id = %s""", (pid, fid, EIN, year, pay, cid))
                c.execute("INSERT INTO person_cluster_members (person_id, cluster_id) VALUES (%s, %s)", (pid, cid))
            c.execute("""INSERT INTO contractors (filing_id, ein, tax_year, source, name_raw, name_norm, compensation)
                         VALUES (%s, %s, %s, '990PF-VIII', 'ACME LAW', 'acme law', 200000)""", (fid, EIN, year))
            if year in (2021, 2022):
                c.execute("""INSERT INTO grants (filing_id, ein, tax_year, source, recipient_name, recipient_name_norm,
                             recipient_is_person, state, cash_amount, is_summary) VALUES
                             (%(f)s, %(e)s, %(y)s, '990PF-XV', 'TEACH FOR AMERICA', 'teach for america', false, 'NY', 1000000, false),
                             (%(f)s, %(e)s, %(y)s, '990PF-XV', NULL, NULL, true, 'TX', 5000, false),
                             (%(f)s, %(e)s, %(y)s, '990PF-XV', 'RETURNED', 'returned', false, 'TX', -2500, false)""",
                          {"f": fid, "e": EIN, "y": year})
                c.execute("""INSERT INTO donors (filing_id, ein, tax_year, contributor_num, name, name_norm, is_person, city,
                             state, total_amount, noncash_amount) VALUES
                             (%(f)s, %(e)s, %(y)s, 1, 'Michael Dell', 'michael dell', true, 'Austin', 'TX', 50000000, 50000000),
                             (%(f)s, %(e)s, %(y)s, 2, 'Bill & Melinda Gates Foundation', 'bill melinda gates foundation',
                              false, 'Seattle', 'WA', 2000000, NULL)""", {"f": fid, "e": EIN, "y": year})
                c.execute("""INSERT INTO expense_breakdown (filing_id, ein, tax_year, form_type, grants_total, lines)
                             VALUES (%s, %s, %s, '990PF', 1002500, '[]')""", (fid, EIN, year))
        # 2019: the grant list is an attachment; the XML only has program summary lines.
        c.execute("""INSERT INTO grants (filing_id, ein, tax_year, source, recipient_name, recipient_is_person, state,
                     cash_amount, purpose, is_summary) VALUES
                     (5, %s, 2019, '990PF-XV', 'Education', false, 'TX', 22253852, 'See Statement 26, pages 8-14', true)""",
                  (EIN,))
        c.execute("""INSERT INTO expense_breakdown (filing_id, ein, tax_year, form_type, grants_total, lines)
                     VALUES (5, %s, 2019, '990PF', 103700162, '[]')""", (EIN,))
        yield c
    finally:
        c.execute(f"DROP SCHEMA {schema} CASCADE")
        c.close()


@pytest.fixture
def use_db(conn, monkeypatch):
    @contextmanager
    def use(*a, **k):
        yield conn
    monkeypatch.setattr(queries.db, "conn", use)
    return conn


def test_amended_years_count_people_once(use_db):
    o = queries.org(EIN)
    for year in (2021, 2022):
        assert len(o["people_by_year"][year]) == 2       # Janet + the unpaid director, not 4
        ps = o["pay_summary"][year]
        assert (ps["listed"], ps["paid"], ps["total"]) == (2, 1, 500_000)
    everyone = {p["display_name"]: p for p in queries.org_people([EIN])[EIN]}
    assert everyone["Janet Mountain"]["total"] == 500_000 * 3      # 2019, 2021, 2022: once each


def test_amended_years_count_contractors_once(use_db):
    o = queries.org(EIN)
    assert [len(o["contractors_by_year"][y]) for y in (2022, 2021, 2019)] == [1, 1, 1]


def test_amended_years_count_grants_and_donors_once(use_db):
    o = queries.org(EIN)
    years = {y["tax_year"]: y for y in o["made"]["years"]}
    assert (years[2021]["n_orgs"], years[2021]["to_orgs"], years[2021]["n_people"]) == (1, 1_000_000, 1)
    assert len(queries.grants_year(EIN, 2022)) == 3
    donors = {y["tax_year"]: y for y in o["donors"]}
    assert len(donors[2022]["rows"]) == 2 and donors[2022]["total"] == 52_000_000


def test_returned_grants_are_labelled_and_last(use_db):
    rows = queries.grants_year(EIN, 2021)
    assert rows[-1]["kind"] == "returned or refunded grant" and rows[-1]["amount"] == -2500
    years = {y["tax_year"]: y for y in queries.org(EIN)["made"]["years"]}
    assert years[2021]["n_returned"] == 1 and years[2021]["to_orgs"] == 1_000_000     # not netted into paid


def test_summary_lines_are_not_individuals_and_reconcile(use_db):
    years = {y["tax_year"]: y for y in queries.org(EIN)["made"]["years"]}
    y = years[2019]
    assert (y["n_orgs"], y["n_people"], y["n_summary"]) == (0, 0, 1)
    assert y["mismatch"] and y["expense_line"] == 103_700_162           # the note shows
    assert not years[2021]["mismatch"]                                   # 1,000,000 + 5,000 - 2,500 = the line


def test_donor_links_are_fuzzy_with_a_score(use_db):
    rows = {r["name"]: r for y in queries.org(EIN)["donors"] for r in y["rows"]}
    gates = rows["Bill & Melinda Gates Foundation"]["match"]
    assert gates["kind"] == "FUZZY" and gates["ein"] == "222222222" and gates["score"] >= 0.6
    assert rows["Michael Dell"]["match"] is None                         # individuals are not linked


@pytest.mark.parametrize("text", ["See Statement 26, pages 1-7", "Address for e-filing purposes", "SEE ATTACHED",
                                  "Various recipients", "see attached list"])
def test_summary_line_detection(text):
    assert SUMMARY_LINE.search(text)


@pytest.mark.parametrize("text", ["General support", "Teach For America", "Scholarship", "Statewide education"])
def test_ordinary_grants_are_not_summaries(text):
    assert not SUMMARY_LINE.search(text)
