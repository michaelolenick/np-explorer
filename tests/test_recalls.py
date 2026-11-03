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


def test_recall_questions_go_to_the_model():
    assert not ask.is_plain_name("kroger food recalls") and not ask.is_plain_name("recalled cheese")
    assert ask.is_plain_name("kroger")


def test_category_pages_and_the_menu_submenu():
    """Food recall categories (owner, 2026-11-02): a submenu under Food safety in the site menu, one page each."""
    from app import recalls as app_recalls
    assert set(app_recalls.MENU_CATEGORIES) <= set(app_recalls.CATEGORIES)
    assert {"fda", "usda", "public-health-alerts", "class-1"} <= set(app_recalls.MENU_CATEGORIES)
    base = open("templates/base.html").read()
    food = base[base.index('nav-drop-head">Food safety'):base.index('nav-drop-head">By email')]
    assert '<a href="/recalls">Food recalls</a>' in food and 'class="nav-drop-sub" href="/recalls/{{ slug }}"' in food
    if not app_recalls.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    html = c.get("/recalls/usda").text
    assert "<h1>USDA FSIS meat, poultry and egg recalls</h1>" in html and "USDA FSIS&nbsp;&#8599;" in html
    assert '<a class="nav-drop-sub" href="/recalls/class-1">Class I food recalls</a>' in html
    assert c.get("/recalls/no-such-category").status_code == 404
    hub = c.get("/recalls").text
    assert "<h2>By category</h2>" in hub and '<a href="/recalls/public-health-alerts">' in hub
