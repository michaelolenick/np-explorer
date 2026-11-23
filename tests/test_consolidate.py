"""Person consolidation rules (owner, 2026-11-23; loader/consolidate.py, app/nicknames.py, app/titles.py)."""
import pytest

from app.nicknames import first_equiv
from app.titles import clean_title
from loader.consolidate import Unit, accept, candidates, classify


def U(name, y0=2015, y1=2020, uid=0):
    return Unit(uid, name, y0, y1)


@pytest.mark.parametrize("a,b,rule", [
    ("bronwyn blake", "blake bronwyn", "swap"),
    ("mike marcin", "michael marcin", "nickname"),
    ("katie hausenfluck", "kathleen hausenfluck", "nickname"),
    ("jon andrews", "jonathan andrews", "nickname"),
    ("matt matthews", "matt mathews", "spelling"),
    ("kalunde wambua", "kalunde wambua weaver", "hyphenated"),
])
def test_rules(a, b, rule):
    assert classify(U(a), U(b)) == rule


def test_name_change_needs_non_overlapping_years_and_the_same_middle():
    assert classify(U("sarah melton swartzendruber", 2022, 2022), U("sarah melton shrewsbury", 2021, 2021)) == "name_change"
    assert classify(U("sarah melton swartzendruber", 2020, 2022), U("sarah melton shrewsbury", 2021, 2023)) is None
    assert classify(U("sarah anne smith", 2010, 2012), U("sarah beth jones", 2015, 2016)) is None


def test_things_that_must_not_merge():
    assert classify(U("christopher smith"), U("christine smith")) is None
    assert classify(U("james smith"), U("jason smith")) is None
    assert classify(U("john smith"), U("jonathan smith")) is None
    assert classify(U("mark anaeto ttee"), U("mark anaeto warden")) is None       # roles are not surnames
    assert classify(U("kevin scarrozzo to 12020"), U("kevin scarrozzo to 0318")) is None
    assert classify(U("john smith jr"), U("john smith sr")) is None


def test_same_filing_guardrail_blocks_a_chain():
    units = [U("mike smith", uid=0), U("michael smith", uid=1), U("mickey smith", uid=2)]
    cands, _ = candidates(units)
    assert len(cands) == 3
    # mike and mickey are listed together in one filing: no chain may join them
    done = accept(units, cands, {(0, 2)})
    joined = {frozenset((i, j)) for i, j, _ in done}
    assert frozenset((0, 2)) not in joined or not ({frozenset((0, 1)), frozenset((1, 2))} <= joined)


def test_nicknames():
    assert first_equiv("liz", "elizabeth") and first_equiv("bob", "robert") and first_equiv("bill", "william")
    assert not first_equiv("christopher", "christine")


def test_title_typos():
    assert clean_title("BAORD MEMBER") == "BOARD MEMBER"
    assert clean_title("Baord Member") == "Board Member"
    assert clean_title("Presdient & Secratary") == "President & Secretary"
    assert clean_title("Treasury Dept") == "Treasury Dept"
    assert clean_title(None) is None
