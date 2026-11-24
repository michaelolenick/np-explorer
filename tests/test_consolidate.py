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


def test_name_change_rule_is_gone():
    assert classify(U("sarah melton swartzendruber", 2022, 2022), U("sarah melton shrewsbury", 2021, 2021)) is None


def test_titles_credentials_and_places_are_stripped_before_matching(monkeypatch):
    from loader import consolidate as C
    monkeypatch.setattr(C, "PLACES", {"nashville"})
    assert classify(U("chief thomas cox"), U("thomas cox")) == "clean"
    assert classify(U("pastor james buske"), U("pastor james kleist")) is None
    assert classify(U("daniel cage nashville"), U("daniel cage nsh")) == "clean"
    assert classify(U("beth reusch"), U("beth reusch chsp")) == "clean"
    assert classify(U("michael miller"), U("michael miller do")) == "clean"
    assert C.clean_name("rev dr jane smith") == "jane smith"
    assert C.clean_name("mary ann jackson") == "mary ann jackson"        # a surname is not a place


def test_spelling_needs_the_same_first_name_and_other_evidence_for_real_surnames(monkeypatch):
    from loader import consolidate as C
    assert classify(U("mark andrew"), U("mark andrews")) == "spelling_weak"          # plural
    monkeypatch.setattr(C, "SURN", {"baker": 900, "bakker": 60, "marschall": 40, "marshall": 5000})
    assert classify(U("tim baker"), U("tim bakker")) == "spelling_weak"
    assert classify(U("rich marschall"), U("rich marshall")) == "spelling_weak"
    assert classify(U("grace depompeo"), U("grace dipompeo")) == "spelling"          # a rare typo is still merged
    assert classify(U("ed gosicki"), U("edward goscicki")) is None                   # an equivalent first name is not enough


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
