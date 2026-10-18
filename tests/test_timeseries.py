"""Natural-language year-by-year questions: the org_timeseries intent (fixed menus; all arithmetic in our SQL)."""

import os
import uuid

import pytest

from app import ask
from app import timeseries as T

EIN = "560000001"
# id, year, superseded, amended, filed, revenue, expenses, assets, fundraising (None = not reported)
FILINGS = [
    (1, 2018, False, False, "2019-05-01", 100, 90, 500, 10),
    (2, 2019, True, False, "2020-05-01", 999, 999, 999, 99),       # superseded: never used
    (3, 2019, False, True, "2020-09-01", 80, 95, 550, None),        # the amended return for 2019
    (4, 2020, False, False, "2021-05-01", 120, 100, 540, 12),
    (5, 2022, False, False, "2023-05-01", 110, 130, 600, 11),       # 2021 missing: no change computed for 2022
]


def test_validate_menus_and_conditions():
    v = ask.validate("org_timeseries", {"org": "INSEAD", "condition": "a_up_b_down", "metric_a": "assets",
                                        "metric_b": "revenue"})
    assert v["condition"] == "a_up_b_down" and v["yoy"] is True and v["metrics"] == ["assets", "revenue"]
    v = ask.validate("org_timeseries", {"org": "X", "condition": "above", "metric_a": "revenue"})   # no number
    assert v["condition"] is None and v["metrics"] == ["revenue"]
    v = ask.validate("org_timeseries", {"org": "Harvard", "condition": "deficit"})
    assert v["metrics"] == ["surplus"]
    v = ask.validate("org_timeseries", {"org": "X", "metrics": ["revenue", "DROP TABLE", "net_assets"]})
    assert v["metrics"] == ["revenue", "net_assets"]
    assert ask.validate("org_timeseries", {})["intent"] == "unknown"
    u = ask.validate("unknown", {"reason": "r", "understood": "u", "unsupported": "x", "suggestion": "Harvard revenue by year"})
    assert u["suggestion"] == "Harvard revenue by year" and u["understood"] == "u"


@pytest.fixture(scope="module")
def db(monkeypatch_module):
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"ts_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    conn.execute(f"SET search_path = {schema}, public")
    conn.execute("CREATE TABLE filings (LIKE public.filings INCLUDING DEFAULTS)")
    for fid, y, sup, amd, filed, rev, exp, assets, fr in FILINGS:
        conn.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, superseded, amended,
                        filed_date, total_revenue, total_expenses, total_assets_eoy, fundraising_expenses)
                        VALUES (%s,%s,%s,'990',%s,'x',%s,%s,%s,%s,%s,%s,%s)""",
                     (fid, EIN, 900000 + fid, y, sup, amd, filed, rev, exp, assets, fr))
    import contextlib
    from psycopg.rows import dict_row

    @contextlib.contextmanager
    def fake():
        c = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        c.execute(f"SET search_path = {schema}, public")
        try:
            yield c
        finally:
            c.close()
    monkeypatch_module.setattr("app.db.conn", fake)
    yield conn
    conn.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.close()


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


def rows(db, metrics, **kw):
    return T.series(EIN, metrics, **kw)


def test_one_return_per_year_newest_first_and_surplus(db):
    d = rows(db, ["revenue", "expenses", "surplus"])
    assert [r["tax_year"] for r in d["rows"]] == [2022, 2020, 2019, 2018]
    r2019 = next(r for r in d["rows"] if r["tax_year"] == 2019)
    assert (r2019["revenue"], r2019["surplus"], r2019["filing_id"]) == (80, -15, 3)     # the amended return


def test_yoy_needs_consecutive_years_and_cumulative(db):
    d = rows(db, ["revenue"], year_from=2019)
    by = {r["tax_year"]: r for r in d["rows"]}
    assert float(by[2019]["revenue_yoy"]) == -20.0                  # vs 2018, outside the range but still the prior year
    assert by[2022]["revenue_yoy"] is None                          # 2021 missing
    assert float(by[2020]["revenue_cum"]) == 200 and float(by[2022]["revenue_cum"]) == 310   # from 2019 on


def test_not_reported_never_zero(db):
    d = rows(db, ["fundraising_expenses"], cond={"condition": "below", "metric_a": "fundraising_expenses", "threshold": 11})
    assert [r["tax_year"] for r in d["rows"]] == [2018]             # 2019's missing value is not "below 11"
    full = {r["tax_year"]: r for r in rows(db, ["fundraising_expenses"], cumulative=True)["rows"]} \
        if False else {r["tax_year"]: r for r in rows(db, ["fundraising_expenses"])["rows"]}
    assert full[2019]["fundraising_expenses"] is None and full[2020]["fundraising_expenses_cum"] is None


def test_conditions(db):
    assert [r["tax_year"] for r in rows(db, ["revenue", "assets"], cond={
        "condition": "a_up_b_down", "metric_a": "assets", "metric_b": "revenue"})["rows"]] == [2019]
    assert [r["tax_year"] for r in rows(db, ["surplus"], cond={"condition": "deficit"})["rows"]] == [2022, 2019]
    assert [r["tax_year"] for r in rows(db, ["revenue"], cond={"condition": "rose_more_than", "metric_a": "revenue",
                                                                "percent": 25})["rows"]] == [2020]   # +50%
    assert T.condition_text({"condition": "fell_more_than", "metric_a": "revenue", "percent": 10}) == \
        "revenue fell more than 10% from the year before"


def test_program_expenses_not_loaded_note(db):
    d = rows(db, ["program_expenses"])
    assert all(r["program_expenses"] is None for r in d["rows"]) and d["notes"]


def test_intent_key_is_hashable_and_round_trips():
    from app import main
    intent = ask.validate("org_timeseries", {"org": "INSEAD", "metrics": ["revenue", "assets"], "yoy": True})
    key = main.intent_key({**intent, "how": "model", "parse_ms": 5})
    hash(key)
    back = {k: list(x) if isinstance(x, tuple) else x for k, x in key}
    assert back["metrics"] == ["revenue", "assets"] and "how" not in back
