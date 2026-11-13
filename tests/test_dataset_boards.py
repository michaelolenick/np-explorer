"""The leaderboards for the newer datasets (owner, 2026-11-13): IPO registrations (app/ipo_boards.py), Form 5500
benefit plans (app/form5500_boards.py), Form ADV private funds (app/fund_boards.py) and the food recall boards
(app/recall_boards.py). Each is registered with its group, its SQL runs against the database, its page has the
standard menu and width, and the Leaderboards list shows the group. Database tests skip without DATABASE_URL."""

import re

import pytest

from app import boards

IPO = {"ipo-most-amended", "ipo-longest-withdrawn", "ipo-serial-registrants", "ipo-federal-awards", "ipo-lobbying",
       "ipo-nonprofit-insiders", "ipo-benefit-plans"}
F5500 = {"f5500-most-plans", "f5500-nonprofit-plans", "f5500-gone-quiet", "f5500-federal-awards", "f5500-lobbying"}
FUNDS = {"sec-adv-biggest-funds", "sec-adv-fastest-growing", "sec-adv-most-investors", "sec-adv-highest-minimum",
         "sec-adv-top-advisers", "sec-adv-pension-backed"}
RECALLS = {"recalls-most", "recalls-class1", "recalls-connected", "recalls-repeat-years", "recalls-federal-food",
           "recalls-lobbying"}
EXPECTED = {"ipos": IPO, "benefit-plans": F5500, "funds": FUNDS, "recalls": RECALLS}


def _public(group: str) -> bool:
    from app import corporate, form5500, ipos, recalls
    return {"ipos": ipos.PUBLIC, "benefit-plans": form5500.PUBLIC, "funds": corporate.PUBLIC,
            "recalls": recalls.PUBLIC}[group]


def _boards(group: str) -> list:
    return [b for b in boards.BOARDS if b.group == group]


def _modules():
    from app import form5500_boards, fund_boards, ipo_boards, recall_boards
    return {"ipos": (ipo_boards.ipo_boards, ipo_boards.ALTERNATIVES),
            "benefit-plans": (form5500_boards.form5500_boards, form5500_boards.ALTERNATIVES),
            "funds": (fund_boards.fund_boards, fund_boards.ALTERNATIVES),
            "recalls": (recall_boards.recall_boards, recall_boards.ALTERNATIVES)}


@pytest.mark.parametrize("group", sorted(EXPECTED))
def test_boards_are_registered_with_their_group(group):
    make, alternatives = _modules()[group]
    if not _public(group):
        assert make() == []
        pytest.skip(f"{group} boards are not public here")
    slugs = {b.slug for b in make()}
    assert slugs == EXPECTED[group]
    assert slugs <= {b.slug for b in boards.BOARDS} and slugs <= {b.slug for b in boards.visible()}
    assert group in boards.GROUPS and boards.GROUPS[group]["title"] and boards.GROUPS[group]["definition"]
    assert {b.slug for b in boards.group_members(group)} == slugs
    assert set(alternatives) == slugs
    seen = set()
    for b in _boards(group):
        assert b.per_org and not b.forms and b.search and b.kind != "990", b.slug
        assert b.definition and b.formula.startswith("Value = "), b.slug
        assert "subject_url" in b.sql and "subject_norm" in b.sql and "org_pos" in b.sql, b.slug
        assert b.subtitle == alternatives[b.slug][0] and b.subtitle not in seen, b.slug
        seen.add(b.subtitle)
        assert boards.get(b.slug) is b
    # the Leaderboards list shows a group once, under its first board
    listed = [b.slug for b in boards.listed() if b.group == group]
    assert len(listed) == 1


def test_slugs_name_their_refresh():
    """IPO and benefit plan boards are refreshed from scripts/nightly.sh by slug; fund boards start with sec- so
    loader.sec_bulk's boards step (every slug starting with sec-) picks them up; recall boards by group."""
    import pathlib
    nightly = (pathlib.Path(__file__).resolve().parent.parent / "scripts" / "nightly.sh").read_text()
    for slug in IPO | F5500:
        assert slug in nightly, slug
    assert all(s.startswith("sec-adv-") for s in FUNDS)


def _db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        return psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")


@pytest.mark.parametrize("group", sorted(EXPECTED))
def test_board_sql_runs(group):
    if not _public(group):
        pytest.skip(f"{group} boards are not public here")
    conn = _db()
    try:
        conn.execute("SET statement_timeout = '60s'")
        for b in _boards(group):
            plan = conn.execute("EXPLAIN " + b.sql).fetchall()      # every table and column the SQL names exists
            assert plan, b.slug
    finally:
        conn.close()


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    return TestClient(main.app)


def _body(html: str) -> str:
    return re.search(r"<body[^>]*>", html).group(0)


@pytest.mark.parametrize("group", sorted(EXPECTED))
def test_board_pages_have_the_standard_width_and_the_list_shows_the_group(group, client):
    if not _public(group):
        pytest.skip(f"{group} boards are not public here")
    _db().close()
    lst = client.get("/boards")
    assert lst.status_code == 200 and _body(lst.text) == '<body class="wide contained">'
    assert boards.GROUPS[group]["title"] in lst.text
    for b in _boards(group):
        r = client.get(f"/boards/{b.slug}")
        assert r.status_code == 200, b.slug
        assert _body(r.text) == '<body class="wide contained">', b.slug
        assert b.title in r.text and b.definition[:40] in r.text, b.slug
        r = client.get(f"/boards/{b.slug}.csv")
        assert r.status_code == 200, b.slug
