"""One NTEE code per organization everywhere (owner, 2026-11-08): the IRS's code when it lists one, otherwise the
inferred one (nonprofit_ntee), the same in name search, topic search, Similar, Funders like, the top-paid category
filter, the Dreamer and the categories index."""
import inspect

import pytest

from loader import dreamer as ld
from loader import funders as lf
from app import aliases, ask, colleges, queries, student_loans, uni_boards


def test_builds_and_queries_read_the_one_code():
    assert "nonprofit_ntee nn" in lf.PROFILE_SQL and "coalesce(nn.ntee_code, o.ntee)" in lf.PROFILE_SQL
    assert "nonprofit_ntee nn" in ld.SQL and "coalesce(nn.ntee_code, g.ntee)" in ld.SQL
    for mod in (ask, queries, aliases, colleges, uni_boards, student_loans):
        assert "nonprofit_ntee nn" in inspect.getsource(mod), mod.__name__
    src = inspect.getsource(ask.top_paid_rows)
    assert "o.ntee LIKE" not in src and "o.ntee ~" not in src and "NTEE_CODE" in src


@pytest.fixture(scope="module")
def db():
    from app import db as adb
    try:
        adb.pool.open(wait=True)        # no close: the shared pool (as tests/test_alt_names.py)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    return adb


def test_search_tables_agree_with_the_index(db):
    """org_profile and research.dream_orgs carry nonprofit_ntee's code (loader.ntee sync runs after every build)."""
    with db.conn(timeout="120s") as conn:
        if conn.execute("SELECT to_regclass('public.nonprofit_ntee') AS t").fetchone()["t"] is None:
            pytest.skip("no nonprofit_ntee")
        bad = conn.execute("""SELECT count(*) AS n FROM org_profile p JOIN nonprofit_ntee n ON n.ein = p.ein
                              WHERE p.ntee_code IS DISTINCT FROM n.ntee_code""").fetchone()["n"]
        assert bad == 0
        if conn.execute("SELECT to_regclass('research.dream_orgs') AS t").fetchone()["t"] is not None:
            bad = conn.execute("""SELECT count(*) AS n FROM research.dream_orgs d JOIN nonprofit_ntee n ON n.ein = d.ein
                                  WHERE NOT d.closed AND d.ntee_major IS DISTINCT FROM left(n.ntee_code, 1)""").fetchone()["n"]
            assert bad == 0


def test_topic_search_shows_inferred_code_when_the_irs_has_none(db):
    from app import funders
    with db.conn() as conn:
        row = conn.execute("""SELECT p.ein, p.name, p.state FROM org_profile p JOIN nonprofit_ntee n ON n.ein = p.ein
                              JOIN organizations o ON o.ein = p.ein
                              WHERE n.ntee_source = 'inferred' AND o.ntee IS NULL AND p.revenue > 10000000
                              ORDER BY p.revenue DESC LIMIT 1""").fetchone()
    if not row:
        pytest.skip("no large filer with an inferred code")
    t = funders.topic(row["name"], state=row["state"])
    me = [r for r in t["rows"] if r["ein"] == row["ein"]]
    assert me and me[0]["ntee_code"], "an organization with only an inferred code must still show it"
