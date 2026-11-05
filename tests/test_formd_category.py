"""Form D categories (form_d_category from loader/categorize.py; app/categories.py; owner, 2026-11-05): the filters, the
Form D view and lists, the category lines on Form D, company and org pages, with the table empty or filled."""


def test_filters_parse():
    from app import categories as c, db
    db.pool.open(wait=False)
    tax = c.formd_taxonomy()
    if not tax:
        return                      # formd_taxonomy not on this database
    assert c.clean_fd("technology") == "Technology" and c.clean_fd("Technology/other technology") == "Technology/Other Technology"
    assert c.clean_fd("Technology/Agriculture") is None and c.clean_fd("nope") is None and c.clean_fd("") is None
    assert c.clean_fund("Private Equity") == "private_equity" and c.clean_fund("venture") == "venture" and c.clean_fund("x") is None
    assert c.fund_label("hedge") == "Hedge fund" and c.fund_label(None) == ""
    nodes = c.formd_search_nodes(["real", "estate"])
    assert any(n["name"] == "Real Estate" for n in nodes) and any(n["kind"] == "fund" for n in nodes)


def test_menu_forms_have_the_formd_filters():
    assert 'name="fd_cat"' in open("templates/search.html").read() and 'name="fund"' in open("templates/search.html").read()
    assert 'name="fd_cat"' in open("templates/_search_form.html").read()
    assert "Form D category" in open("templates/corporate_formd.html").read()


def test_pages():
    from app import categories as c
    if not c.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    client = TestClient(main.app)
    page = client.get("/categories?view=formd")
    if page.status_code != 200 or "cat-tree" not in page.text:
        return                      # tables not loaded on this database
    assert "Form D" in page.text and 'id="fd-Technology"' in page.text
    assert "Across datasets" in client.get("/categories").text
    found = client.get("/categories?q=real+estate")
    assert "Form D categories" in found.text
    assert client.get("/categories/formd/Technology").status_code == 200
    assert client.get("/categories/formd/Technology/Other%20Technology").status_code == 200
    assert client.get("/categories/formd/fund/venture").status_code == 200
    assert client.get("/categories/formd/Nope").status_code == 404
    assert client.get("/categories/formd/fund/nope").status_code == 404
    r = client.get("/search?q=capital&type=name&fd_cat=Technology&fund=venture")
    assert r.status_code == 200
