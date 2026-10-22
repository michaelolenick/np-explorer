"""The Schools menu: a dropdown with three pages of leaderboard-style suggestions, and topic views of the Report Card."""

import re

from starlette.testclient import TestClient

from app import boards, main, schools_hub

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def test_menu_has_schools_under_more_data():
    html = client.get("/about").text
    menu = html[html.index('<details class="nav-drop'):html.index("</details>")]
    assert "<summary>Browse</summary>" in menu and '<span class="nav-drop-head">Schools</span>' in menu
    links = re.findall(r'<a href="([^"]+)">([^<]+)</a>', menu)
    assert links[:4] == [("/schools/990s", "School 990s"), ("/schools/pay", "School pay data"),
                         ("/schools/student-loans", "Student loan data"), ("/schools", "All school data")]
    assert "<summary>Schools</summary>" not in html          # no separate top-level Schools menu
    assert "/static/nav.js" in html


def test_section_pages_list_suggestions():
    for key, sec in schools_hub.SECTIONS.items():
        r = client.get(sec.path)
        assert r.status_code == 200, key
        assert f"<h1>{sec.title}</h1>" in r.text
        for s in sec.suggestions:
            assert f'href="{s.href.replace("&", "&amp;")}"' in r.text, (key, s.title)
        assert '<details class="nav-drop active">' in r.text      # Schools is the current menu item
    assert client.get("/schools/nope").status_code == 404


def test_overview_and_old_links():
    r = client.get("/schools")
    assert r.status_code == 200 and all(sec.title in r.text for sec in schools_hub.SECTIONS.values())
    r = client.get("/schools?page=2&sort=org_revenue", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/boards/schools?page=2&sort=org_revenue"


def test_every_suggestion_points_at_a_real_board_and_column():
    for sec in schools_hub.SECTIONS.values():
        for s in sec.suggestions:
            b = boards.BY_SLUG[s.board]
            if s.sort:
                assert s.sort in boards.sortable(b), s.title
                assert s.sort in schools_hub.VIEWS[s.view], s.title
    card = boards.BY_SLUG["schools"]
    keys = {c.key for c in card.columns}
    for view, cols in schools_hub.VIEWS.items():
        assert set(cols) <= keys, view


def test_report_card_views_show_only_their_columns():
    full = client.get("/boards/schools").text
    v990 = client.get("/boards/schools?view=990").text
    assert "Affiliates&#39; revenue (990)" in v990 and "Avg. professor salary" not in v990
    assert "Avg. professor salary" in full
    assert '<a href="/schools/990s">School 990s</a></p>' in v990          # breadcrumb back to its Schools page


def test_rates_and_ratios_say_what_they_are():
    assert schools_hub.unit("ratio", "Default rate (%)") == "%"
    assert schools_hub.unit("ratio", "Change (points)") == " points"
    assert schools_hub.unit("ratio", "Admin median / faculty average") == "x"
    assert schools_hub.unit("money", "Pool balance") == ""
