"""Food recalls (loader/recalls.py, app/recalls.py): name matching, stable firm ids, readable URLs, the boards
and the plain-text search intent."""

from app import ask, boards, slugs
from loader import recalls


def test_core_names_match_across_spellings():
    assert recalls.core("WinCo Foods, LLC") == recalls.core("Winco Foods LLC") == "winco foods"
    assert recalls.core("The J.M. Smucker Company") == "j m smucker"
    assert recalls.core("Acme Inc. dba Fresh Farms") == "acme"
    assert recalls.firm_id("WinCo Foods, LLC", "ID") == recalls.firm_id("Winco Foods LLC", "id")
    assert recalls.firm_id("WinCo Foods, LLC", "ID") != recalls.firm_id("WinCo Foods, LLC", "WA")


def test_firm_urls():
    fid = recalls.firm_id("WinCo Foods, LLC", "ID")
    path = slugs.canonical("recallfirm", fid, "WinCo Foods, LLC")
    assert path == f"/recalls/firm/winco-foods-llc-{fid}" and slugs.parse("recallfirm", path.rsplit("/", 1)[1]) == fid


def test_boards_and_question():
    from app import recalls as app_recalls
    if app_recalls.PUBLIC:
        assert {"recalls-most", "recalls-class1", "recalls-connected"} <= {b.slug for b in boards.visible()}
    v = ask.validate("food_recalls", {"firm": "Kroger", "classification": "Class I", "year": 2024, "state": "oh"})
    assert v == {"intent": "food_recalls", "firm": "Kroger", "state": "OH", "classification": "Class I",
                 "year": 2024, "reason": None}
    assert ask.validate("food_recalls", {"classification": "Class IV"})["intent"] == "unknown"
    assert "food recalls by" in ask.describe(v)
