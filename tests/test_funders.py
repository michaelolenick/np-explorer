"""Funders, similar organizations and topics: the loader's SQL over hand-made rows in a throwaway
schema (same table definitions as the live database), plus the pure helpers. Needs DATABASE_URL for
the database tests."""

import contextlib
import os
import uuid

import pytest

from app import funders
from loader import funders as build

R_EIN, R_NAME, R_FUZZY, R_AMBIG_A, R_AMBIG_B, G_PF, G_DAF = (f"30000000{i}" for i in range(1, 8))

ORGS = [  # ein, name, state, ntee, revenue
    (R_EIN, "SPACE GIRLS ACADEMY", "TX", "B90", 2_000_000),
    (R_NAME, "STARLIGHT SCIENCE CENTER", "TX", "B90", 3_000_000),
    (R_FUZZY, "WOMEN IN ORBIT FOUNDATION", "CA", "B90", 2_500_000),
    (R_AMBIG_A, "RIVER CLINIC", "TX", "E32", 900_000),
    (R_AMBIG_B, "RIVER CLINIC", "TX", "E32", 800_000),
    (G_PF, "ACME FAMILY FOUNDATION", "NY", "T20", 50_000_000),
    (G_DAF, "BIG COMMUNITY FUND", "IL", "T30", 90_000_000),
]

FILINGS = [  # id, ein, form, year, superseded, amended, filed, mission
    (1, G_PF, "990PF", 2021, True, False, "2022-05-01", None),     # original, superseded by 2
    (2, G_PF, "990PF", 2021, False, True, "2022-09-01", None),
    (3, G_PF, "990PF", 2022, False, False, "2023-05-01", None),    # both current: the amended one (4) wins
    (4, G_PF, "990PF", 2022, False, True, "2023-10-01", None),
    (5, G_DAF, "990", 2022, False, False, "2023-05-01", "Donor advised funds"),
    (6, R_EIN, "990", 2022, False, False, "2023-05-01", "Sending girls to space camp and STEM programs"),
    (7, R_NAME, "990", 2022, False, False, "2023-05-01", "Science museum and planetarium"),
    (8, R_FUZZY, "990", 2022, False, False, "2023-05-01", "Women astronauts and orbit research"),
]

GRANTS = [  # filing, source, recipient name norm, state, recipient ein, person, summary, cash
    (1, "990PF-XV", "starlight science center", "TX", None, False, False, 50_000),     # superseded: not counted
    (2, "990PF-XV", "starlight science center", "TX", None, False, False, 60_000),
    (3, "990PF-XV", "starlight science center", "TX", None, False, False, 70_000),     # superseded in effect
    (4, "990PF-XV", "starlight science center", "TX", None, False, False, 80_000),
    (4, "990PF-XV", "women in orbits foundation", "CA", None, False, False, 10_000),   # near-identical name
    (4, "990PF-XV", "river clinic", "TX", None, False, False, 5_000),                  # two orgs: no link
    (4, "990PF-XV", "jane roe", "TX", None, True, False, 1_000),                       # a person
    (5, "990-I", "space girls academy", "TX", R_EIN, False, False, 100_000),          # by EIN
    (5, "990-I", "big community fund", "IL", G_DAF, False, False, 999_999),           # itself: excluded
    (5, "990-I", "see attached", "IL", None, False, True, 5_000_000),                 # summary line
]


class Status:
    phase = ""

    def emit(self, m):
        pass


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"funders_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    conn.execute(f"SET search_path = {schema}, public")
    try:
        for t in ("filings", "grants", "organizations", "daf_stats", "people"):
            conn.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)")
        for ein, name, state, ntee, rev in ORGS:
            conn.execute("""INSERT INTO organizations (ein, name, name_norm, state, ntee, latest_total_revenue,
                            latest_total_expenses, latest_filing_year) VALUES (%s,%s,%s,%s,%s,%s,%s,2022)""",
                         (ein, name, name.lower(), state, ntee, rev, rev // 2))
        for fid, ein, form, year, sup, amd, filed, mission in FILINGS:
            conn.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, superseded, amended,
                            filed_date, mission) VALUES (%s,%s,%s,%s,%s,'x',%s,%s,%s,%s)""",
                         (fid, ein, 700000 + fid, form, year, sup, amd, filed, mission))
        conn.execute("INSERT INTO daf_stats (filing_id, ein, tax_year, maintains_dafs) VALUES (5, %s, 2022, true)", (G_DAF,))
        for i, (fid, src, nn, st, rein, person, summary, cash) in enumerate(GRANTS):
            conn.execute("""INSERT INTO grants (id, filing_id, ein, tax_year, source, recipient_name, recipient_name_norm,
                            recipient_ein, recipient_is_person, is_summary, state, cash_amount, purpose)
                            SELECT %s, id, ein, tax_year, %s, upper(%s), %s, %s, %s, %s, %s, %s, 'GENERAL SUPPORT'
                            FROM filings WHERE id = %s""", (i + 1, src, nn, nn, rein, person, summary, st, cash, fid))
        conn.commit()
        build.build_profile(conn, Status(), force=True)
        conn.commit()
        build.build_links(conn, Status(), force=True)
        build.build_funders(conn, Status(), force=True)
        yield conn
    finally:
        conn.rollback()
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.commit()
        conn.close()


@pytest.fixture
def app_db(db, monkeypatch):
    """Point app/funders.py at the test schema's connection."""
    from psycopg.rows import dict_row

    @contextlib.contextmanager
    def conn():
        db.row_factory = dict_row
        try:
            yield db
        finally:
            db.row_factory = __import__("psycopg").rows.tuple_row
    monkeypatch.setattr(funders.db, "conn", conn)
    return db


def links(db):
    return db.execute("SELECT grantor_filing_id, recipient_ein, match, amount FROM grant_links ORDER BY grant_id").fetchall()


def test_amended_returns_not_double_counted(db):
    got = [(f, a) for f, r, m, a in links(db) if r == R_NAME]
    assert got == [(2, 60_000), (4, 80_000)]          # 2021: the amendment, not the superseded original; 2022: the amended return


def test_ein_is_exact_name_is_fuzzy(db):
    by = {(r, m) for f, r, m, a in links(db)}
    assert (R_EIN, "EXACT") in by and (R_NAME, "FUZZY") in by and (R_FUZZY, "FUZZY") in by


def test_ambiguous_names_people_self_grants_and_summaries_are_left_out(db):
    recipients = {r for f, r, m, a in links(db)}
    assert R_AMBIG_A not in recipients and R_AMBIG_B not in recipients
    assert G_DAF not in recipients                     # an organization's grant to itself
    assert sum(a for f, r, m, a in links(db)) == 60_000 + 80_000 + 10_000 + 100_000   # no person, no summary line


def test_org_funders_rollup(db):
    from psycopg.rows import dict_row
    rows = db.cursor(row_factory=dict_row).execute("SELECT * FROM org_funders ORDER BY recipient_ein").fetchall()
    star = next(r for r in rows if r["recipient_ein"] == R_NAME)
    assert (star["grantor_ein"], star["total"], star["n_grants"], star["years"], star["last_year"], star["last_amount"],
            star["match"], star["grantor_kind"]) == (G_PF, 140_000, 2, [2021, 2022], 2022, 80_000, "FUZZY",
                                                     "Private foundation")
    assert star["fuzzy_names"] == ["STARLIGHT SCIENCE CENTER"]
    girls = next(r for r in rows if r["recipient_ein"] == R_EIN)
    assert (girls["match"], girls["grantor_kind"], girls["total"]) == ("EXACT", "DAF sponsor", 100_000)


def test_funders_query_and_not_reported(app_db):
    fu = funders.funders.__wrapped__(R_NAME)
    assert fu["n_total"] == 1 and fu["rows"][0]["total"] == 140_000
    none = funders.funders.__wrapped__(R_AMBIG_A)
    assert none["rows"] == [] and none["n_total"] == 0
    from app.main import templates
    html = templates.env.get_template("_funders_table.html").render(fu=none, fein=R_AMBIG_A, coverage_years="2010 to 2025")
    assert "Not reported" in html and "$0" not in html


def test_similar_is_deterministic_with_reasons(app_db):
    sim = funders.similar.__wrapped__(R_EIN)
    assert [r["ein"] for r in sim["rows"]][:2] == [R_NAME, R_FUZZY]     # same code; same state breaks the tie
    assert sim["rows"][0]["why"] == "Same NTEE code B90, revenue within 2x, same state"
    assert funders.similar.__wrapped__(R_EIN, state_only=True)["rows"][0]["ein"] == R_NAME
    assert all(r["state"] == "TX" for r in funders.similar.__wrapped__(R_EIN, state_only=True)["rows"])


def test_funders_like_ranks_foundations_and_daf_sponsors(app_db):
    like = funders.funders_like.__wrapped__(R_EIN)
    assert [(r["grantor_ein"], r["recipients"]) for r in like["rows"]] == [(G_PF, 2)]   # Starlight and Women in Orbit


def test_topic_words_codes_and_no_results(app_db):
    t = funders.topic.__wrapped__("women in orbit nonprofits")
    assert t["words"] == ["women", "orbit"] and [r["ein"] for r in t["rows"]] == [R_FUZZY]
    assert t["codes"] and t["codes"][0]["ntee_code"] == "B90"
    empty = funders.topic.__wrapped__("zzqxv qqqwv")
    assert empty["rows"] == [] and empty["total"] == 0


def test_resolve_org_never_guesses():
    two = [{"ein": "1", "name_norm": "river clinic"}, {"ein": "2", "name_norm": "river clinic"}]
    assert funders.resolve_org("River Clinic", search=lambda q, limit, state: two) == (None, two)
    one = [{"ein": "1", "name_norm": "river clinic"}, {"ein": "3", "name_norm": "river clinic of hope"}]
    assert funders.resolve_org("River Clinic Inc", search=lambda q, limit, state: one)[0]["ein"] == "1"
    assert funders.resolve_org("Nothing Here", search=lambda q, limit, state: []) == (None, [])


def test_nl_intents_validate_and_fall_back(monkeypatch):
    from app import ask
    assert ask.validate("funders_of", {"org": "Planned Parenthood", "state": "tx"}) == {
        "intent": "funders_of", "org": "Planned Parenthood", "state": "TX"}
    assert ask.validate("funders_of_similar", {"keywords": "women space"})["keywords"] == "women space"
    assert ask.validate("orgs_in_topic", {})["intent"] == "unknown"
    monkeypatch.setattr(funders, "available", lambda: True)
    monkeypatch.setattr(funders, "topic", lambda *a, **k: {"rows": [], "words": ["zzqxv"], "total": 0})
    assert ask.run({"intent": "orgs_in_topic", "keywords": "zzqxv"})["kind"] == "none"
    monkeypatch.setattr(funders, "resolve_org", lambda name, state: (None, [{"ein": "1"}, {"ein": "2"}]))
    assert ask.run({"intent": "funders_of", "org": "River Clinic", "state": None})["kind"] == "org_choices"
    from app.fmt import year_ranges
    assert year_ranges([2019, 2015, 2016, 2017, None]) == "2015-2017, 2019"
