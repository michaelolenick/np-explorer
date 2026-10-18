"""Leaderboard sorting: one shared, server-side sort on raw numbers, blanks last, ties by name."""

import pytest

from app import boards as B

DAF = B.BY_SLUG["daf-sponsors"]


def test_only_numeric_columns_are_sortable():
    cols = B.sortable(DAF)
    assert set(cols) == {"value", "tax_year", "daf_count", "daf_contributions", "daf_grants"}
    assert B.sort_spec(DAF, "daf_grants", "asc") == ("daf_grants", "asc")
    assert B.sort_spec(DAF, "daf_grants", None) == ("daf_grants", "desc")         # default direction
    assert B.sort_spec(DAF, "subject_name", "asc") is None                          # text: not sortable
    assert B.sort_spec(DAF, 'value"; DROP TABLE x; --', "desc") is None             # never reaches SQL


def test_order_clause_puts_blanks_last_and_breaks_ties_by_name():
    assert B._order(DAF, {"sort": "value", "dir": "desc"}) == '"value" DESC NULLS LAST, subject_norm, pos'
    assert B._order(DAF, {"sort": "value", "dir": "asc"}) == '"value" ASC NULLS LAST, subject_norm, pos'
    assert B._order(DAF, {}) == "org_pos"                                           # the ranking, one row per org
    assert B._order(DAF, {"all": 1}) == "pos"


def test_daf_board_ranks_by_value_not_name():
    assert not DAF.alphabetical and DAF.per_org
    assert "value DESC NULLS LAST, subject_norm" in DAF.sql
    assert [b.slug for b in B.listed()].index("daf-sponsors") == 2   # after the event boards (B goes in ahead of it)


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    conn.execute("""CREATE TEMP TABLE t (pos int, value numeric, subject_norm text, daf_grants numeric, tax_year int)""")
    conn.execute("""INSERT INTO t VALUES (1, 10, 'beta', -5, 2022), (2, 9, 'alpha', 100, 2023), (3, 9, 'gamma', NULL, 2021),
                                         (4, -5, 'delta', 0, 2020), (5, NULL, 'epsilon', 7, 2024)""")
    yield conn
    conn.close()


def run(db, sort, d):
    return [r[0] for r in db.execute(f"SELECT subject_norm FROM t ORDER BY {B._order(DAF, {'sort': sort, 'dir': d})}")]


def test_numeric_not_text_negatives_and_blanks_last(db):
    assert run(db, "value", "desc") == ["beta", "alpha", "gamma", "delta", "epsilon"]   # 10 before 9 (text would put 9 first)
    assert run(db, "value", "asc") == ["delta", "alpha", "gamma", "beta", "epsilon"]    # -5 first; blank still last
    assert run(db, "daf_grants", "asc") == ["beta", "delta", "epsilon", "alpha", "gamma"]   # negative < 0 < 7 < 100, blank last
    assert run(db, "daf_grants", "desc")[-1] == "gamma"


def test_sort_survives_paging_and_canonicalizes():
    from starlette.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        r = c.get("/boards/daf-sponsors?sort=daf_grants&dir=asc&page=2")
    if r.status_code != 200 or "being built" in r.text:
        pytest.skip("board view not built here")
    assert "sort=daf_grants" in r.text and "dir=asc" in r.text                       # pager and headers keep the sort
    assert '<link rel="canonical" href="' in r.text and "/boards/daf-sponsors\"" in r.text   # canonical: the unsorted board
    assert "Sorted by Grants, lowest first" in r.text
