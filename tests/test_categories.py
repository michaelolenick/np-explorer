"""Nonprofit categories (loader/ntee.py, app/categories.py; owner, 2026-11-05): the taxonomy constants, the prompt
text, the search filters, the menu and the pages."""

from loader import ntee


def test_taxonomy_constants_and_prompt():
    assert [b[0] for b in ntee.BROAD] == ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    assert "".join(b[2] for b in ntee.BROAD) == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    assert set(ntee.COMMON) == {"01", "02", "03", "05", "11", "12", "19"}
    majors = {"A": "Arts", "B": "Education"}
    s = ntee.system_prompt(majors, {"A01": "Alliance", "B82": "Scholarships"})
    assert "A01 Alliance" in s and "B82 Scholarships" in s and "JSON" in s
    assert "A01 Alliance" not in ntee.system_prompt(majors) and "A Arts" in ntee.system_prompt(majors)
    assert ntee._conf("0.9") == 0.9 and ntee._conf(2) == 1.0 and ntee._conf("x") is None
    assert ntee._date("20251115") == "2025-11-15" and ntee._date("") is None


def test_org_text():
    acts = {"001": ("Church,synagogue, etc", "X20 - X70")}
    o = {"name": "FIRST CHURCH", "city": "AUSTIN", "state": "TX", "subsection": "03", "ruling_year": 1980, "activity": "001000000"}
    text, has = ntee.org_text(o, acts)
    assert not has and "Name: FIRST CHURCH" in text and "501(c)(3)" in text and "Church,synagogue, etc (NTEE X20 - X70)" in text
    text, has = ntee.org_text({**o, "program_text": "Worship services " * 100, "schedule_o_text": "Expenses"}, acts)
    assert has and "Program services" in text and "Schedule O" not in text and len(text) < 1200


def test_filters_and_cleaning():
    from app import categories as c
    params = {}
    sql = c.filter_sql("o", "B82", "women:issues", params)
    assert "fn.ntee_code LIKE %(f_ntee)s" in sql and params["f_ntee"] == "B82" and params["f_furp"] == "women:issues"
    params = {}
    assert "ff.field LIKE" in c.filter_sql("o", "b", "shelter", params) and params == {"f_ntee": "B%", "f_furp": "shelter:%"}
    assert c.filter_sql("o", "bad code", "no good", {}) == ""
    assert c.clean_ntee(" b82 ") == "B82" and c.clean_ntee("1234") is None
    assert c.clean_furp("Women: issues".replace(": ", ":")) == "women:issues" and c.clean_furp("x y z!") is None
    assert c._roman("VIII") == 8 and c._roman("IX") == 9 and c._roman("X") == 10
    assert c.furp_label("girls_boys", "boy_scouts") == "girls boys: boy scouts"


def test_menu_home_and_more():
    base = open("templates/base.html").read()
    assert '<a href="/categories">Nonprofits by category</a>' in base
    home = open("templates/index.html").read()           # owner, 2026-11-06: one line, both indexes
    assert 'href="/categories?view=nonprofit"' in home and 'href="/categories?view=formd"' in home
    assert 'include "_org_ntee.html"' in open("templates/org.html").read()
    search = open("templates/search.html").read()
    assert 'name="ntee"' in search and 'name="furp"' in search


def test_pages():
    from app import categories as c
    if not c.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    client = TestClient(main.app)
    page = client.get("/categories")
    if page.status_code != 200 or "cat-tree" not in page.text:
        return                      # tables not loaded on this database
    assert "<h1>Nonprofit categories</h1>" in page.text and 'id="broad-I"' in page.text
    furp = client.get("/categories?view=furp")
    assert furp.status_code == 200 and "FURP topics" in furp.text
    found = client.get("/categories?q=scholar")
    assert "B82" in found.text and "FURP categories" in found.text and "Stated categories" in found.text
    assert "shelter" in client.get("/categories?q=shelter").text
    assert "Kingdom Gates Ministries" in page.text and 'id="caveat"' in page.text
    lst = client.get("/categories/ntee/B82")
    assert lst.status_code == 200 and "Scholarships" in lst.text
    assert client.get("/categories/ntee/zzzz").status_code == 404
    assert client.get("/categories/ntee/B").status_code == 200
    broad = client.get("/categories/broad/V")               # the ten broad categories have their own lists
    assert broad.status_code == 200 and "Human Services" in broad.text and "across its major groups" in broad.text
    assert client.get("/categories/broad/XI").status_code == 404
    assert 'href="/categories/broad/I"' in page.text and ">For-profit index</a>" in page.text   # owner, 2026-11-06: just a link
    assert "cat-formd-entry\"><strong>Form D issuers" not in page.text
    assert "View:" not in page.text and "Stated NTEE codes" not in page.text   # owner, 2026-11-07: no view line, no heading
    assert page.text.index("<h1>Nonprofit categories</h1>") < page.text.index("Open a line.") < page.text.index('id="broad-I"')
    client.get("/categories?view=furp")                      # the chosen view is remembered for the visit
    assert "FURP topics" in client.get("/categories").text
    client.get("/categories?view=ntee")
    assert 'id="broad-I"' in client.get("/categories").text
    # The home page's nonprofit link: the remembered nonprofit view, never Form D, and the cookie is left alone.
    client.get("/categories?view=formd")
    assert "Form D industry groups" in client.get("/categories").text
    r = client.get("/categories?view=nonprofit")
    assert 'id="broad-I"' in r.text and "set-cookie" not in r.headers
    assert "Form D industry groups" in client.get("/categories").text
    client.get("/categories?view=furp")
    assert "FURP topics" in client.get("/categories?view=nonprofit").text
    client.get("/categories?view=ntee")
    assert client.get("/more").status_code == 200 and '<a href="/categories">' in client.get("/more").text


def test_tree_open_state_is_kept_for_the_back_button():
    """Owner, 2026-11-06: Back from a category's list returns to the tree as it was (static/site.js, per index)."""
    js = open("static/site.js").read()
    assert '"cat-open:" + location.pathname + location.search' in js and 'addEventListener("toggle", save)' in js
    assert 'addEventListener("pageshow"' in js
    tpl = open("templates/categories.html").read()
    assert 'id="broad-{{ b.code }}"' in tpl and 'id="major-{{ m.code }}"' in tpl and 'id="topic-{{ t.code }}"' in tpl
    assert '/static/site.js' in tpl


def test_find_as_you_type():
    """Owner, 2026-11-07: a long box, no button; /categories/find answers each keystroke."""
    from app import categories as c
    if not c.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    client = TestClient(main.app)
    page = client.get("/categories").text
    if "cat-tree" not in page:
        return
    assert 'data-live="/categories/find"' in page and 'id="cat-live"' in page and "<button" not in page[page.index('id="cat-search"'):page.index("</form>", page.index('id="cat-search"'))]
    r = client.get("/categories/find?q=B82&view=ntee").json()
    assert r["items"] and r["items"][0]["label"].startswith("B82") and r["items"][0]["url"] == "/categories/ntee/B82"
    assert client.get("/categories/find?q=B").json()["items"] == []
    assert "cat-live" in open("static/site.js").read()
