"""Drill-down keeps the question (owner, 2026-11-13: "when there's a deep dive, e.g. a list of counties for a specific
purpose like homelessness, clicking a county must keep the second part (homelessness) for a list of charities").
app/census.py drill_url builds every place link with ?q=, ?topic=, ?kind= and ?measure=; the ranked census table, the
topic results, the places panel, the API `areas` and deep-query county tables use it; the county, place, state and
tract pages read the parameters and show the matching records in the area first (templates/_census_drill.html),
with a "Back to" link, and are unchanged without them."""

import re

import pytest
from starlette.testclient import TestClient

from app import ask, census

COUNTY = {"level": "county", "stusab": "TX", "slug": "travis-county", "short_name": "Travis County", "name": "Travis County, Texas",
          "gisjoin": "G4804530", "geoid": "48453"}
Q = "Food banks in the poorest counties"


@pytest.fixture(scope="module")
def client():
    from app import db
    from app.main import app
    db.pool.open(wait=False)           # no `with`: the lifespan would close the pool for later test modules
    return TestClient(app)


def _loaded():
    if not census.PUBLIC or not census.ready():
        pytest.skip("census tables not loaded")


def _menu(html: str) -> list[str]:
    nav = html[html.index("site-nav"):html.index("</nav>")]
    return re.findall(r"<(?:a|summary)[^>]*>([^<]+)<", nav)


# --- the helper, no database ---------------------------------------------------------------------------------------

def test_drill_url_builds_links_that_keep_the_context():
    ctx = {"q": Q, "topic": "food banks", "kind": "org", "measure": "poverty_rate"}
    assert census.drill_url(COUNTY, ctx) == "/census/tx/travis-county?q=Food+banks+in+the+poorest+counties&topic=food+banks&kind=org&measure=poverty_rate"
    assert census.drill_url(COUNTY, {}) == "/census/tx/travis-county" and census.drill_url(COUNTY) == "/census/tx/travis-county"
    assert census.drill_url("/census/tx?m=poverty_rate", q="x") == "/census/tx?m=poverty_rate&q=x"
    assert census.drill_url(COUNTY, {"kind": "nope", "measure": "nope", "q": "  "}) == "/census/tx/travis-county"
    assert census.drill_url(COUNTY, {"q": "a"}, q="b") == "/census/tx/travis-county?q=b"      # explicit values win
    assert census.drill_url(None, ctx) is None
    long = census.drill_url(COUNTY, {"q": "x" * 1000})
    assert len(long) < 400


def test_drill_ctx_and_the_subject_of_a_question():
    assert census.drill_ctx(Q, measure="poverty_rate") == {"q": Q, "topic": "food banks", "measure": "poverty_rate"}
    assert census.topic_from_question("counties with the most homelessness charities") == "homelessness"
    assert census.topic_from_question("Which counties have the highest poverty rate?") == ""
    assert census.topic_from_question("hospitals in the richest counties in Ohio") == "hospitals"
    assert census.drill_ctx("Which counties have the highest poverty rate?", measure="poverty_rate") == {
        "q": "Which counties have the highest poverty rate?", "measure": "poverty_rate"}
    assert census.drill_ctx("", kind="person") == {"kind": "person"} and census.drill_ctx("", kind="zzz") == {}
    assert census.drill_section(COUNTY, {}) is None            # no parameters: the plain page


# --- the area pages ------------------------------------------------------------------------------------------------

def test_county_page_shows_the_topic_first_then_the_usual_page(client):
    _loaded()
    url = census.drill_url(COUNTY, {"q": Q, "topic": "food bank", "kind": "org", "measure": "poverty_rate"})
    r = client.get(url)
    assert r.status_code == 200
    html = r.text
    assert 'class="wide contained"' in html and _menu(html) == _menu(client.get("/about").text)
    assert 'id="drill"' in html and "<h2>Food bank in Travis County, TX</h2>" in html
    assert html.index('id="drill"') < html.index("<h2>Census tracts</h2>") < html.index("FURP records in Travis County")
    assert "CENTRAL TEXAS FOOD BANK" in html.upper() and re.search(r'href="/org/[a-z0-9-]*\d{9}"', html[html.index('id="drill"'):])
    assert "Poverty rate in Travis County, TX:" in html and "B17001" in html
    assert 'Back to: <a href="/ask?q=Food+banks+in+the+poorest+counties">Food banks in the poorest counties</a>' in html
    assert 'href="/topics?q=food+bank&amp;area=G4804530"' in html
    # the rest of the page is what it always was
    plain = client.get("/census/tx/travis-county").text
    assert 'id="drill"' not in plain and "Back to:" not in plain
    for piece in ("<h2>Census tracts</h2>", "Places in the county", "FURP records in Travis County", "Cite:"):
        assert piece in html and piece in plain
    # a subject nothing here matches: one line, and the page still renders
    r = client.get("/census/tx/travis-county?topic=zzqqxxyy+wwvv&q=zzqqxxyy")
    assert r.status_code == 200 and "No nonprofits in Travis County, TX match" in r.text and "<h2>Census tracts</h2>" in r.text


def test_state_place_and_tract_pages_read_the_parameters_too(client):
    _loaded()
    r = client.get("/census/tx?topic=homeless&kind=org")
    assert r.status_code == 200 and "<h2>Homeless in Texas</h2>" in r.text and "homeless" in r.text.lower()
    r = client.get("/census/tx/place/austin?topic=homeless+shelter&q=homeless+shelters+in+Austin")
    assert r.status_code == 200 and "<h2>Homeless shelter in Austin, TX</h2>" in r.text and 'Back to: <a href="/ask?q=homeless+shelters+in+Austin">' in r.text
    r = client.get("/census/tx/travis-county?topic=university&kind=person")
    assert r.status_code == 200 and "Highest-paid people" in r.text and "/person/" in r.text[r.text.index('id="drill"'):]
    tract = census.children("tract", "48", "453", limit=1)
    if tract:
        r = client.get(census.url_for(tract[0]) + "?q=Food+banks+in+the+poorest+counties")
        assert r.status_code == 200 and "Back to:" in r.text


def test_topics_page_restricted_to_an_area_and_its_county_links(client):
    _loaded()
    r = client.get("/topics?q=food+bank&area=G4804530")
    assert r.status_code == 200 and "in <a href=\"/census/tx/travis-county\">Travis County, TX</a>" in r.text
    assert "CENTRAL TEXAS FOOD BANK" in r.text.upper()
    r = client.get("/topics?q=food+bank")
    assert r.status_code == 200 and "<th>County</th>" in r.text
    assert re.search(r'href="/census/[a-z]{2}/[a-z0-9-]+\?[^"]*topic=food\+bank', r.text)


# --- the result lists that lead to them ----------------------------------------------------------------------------

def test_result_lists_carry_the_parameters(client, monkeypatch):
    _loaded()
    plan = {"intent": "orgs_in_topic", "keywords": "Food banks", "state": None, "min_revenue": None, "max_revenue": None,
            "area_measure": "poverty_rate", "area_lowest_first": False, "how": "rule"}
    monkeypatch.setattr(ask, "parse", lambda question, ip, trusted=False: dict(plan))
    r = client.get("/ask", params={"q": Q})
    assert r.status_code == 200
    html = r.text
    link = re.search(r'href="(/census/[a-z]{2}/[a-z0-9-]+\?[^"]*)"', html)
    assert link and "topic=food+banks" in link.group(1) and "q=Food+banks+in+the+poorest+counties" in link.group(1) \
        and "measure=poverty_rate" in link.group(1), link.group(1) if link else html[:500]
    assert 'id="places"' in html
    panel = html[html.index('id="places"'):]
    assert re.search(r'href="/census/[^"]*\?[^"]*topic=food\+banks[^"]*"', panel)
    # the ranked census table
    ranked = {"intent": "census_area", "place": "United States", "measure": "poverty_rate", "children": "county", "lowest_first": False, "how": "rule"}
    monkeypatch.setattr(ask, "parse", lambda question, ip, trusted=False: dict(ranked))
    r = client.get("/ask", params={"q": "Which counties have the highest poverty rate?"})
    assert r.status_code == 200
    assert re.search(r'href="/census/[a-z]{2}/[a-z0-9-]+\?q=Which\+counties\+have\+the\+highest\+poverty\+rate%3F&amp;measure=poverty_rate"', r.text)


def test_places_panel_data_and_api_areas_carry_the_context():
    _loaded()
    from app import funders
    t = funders.topic("homeless shelters", "TX")
    if not t["rows"]:
        pytest.skip("no topic rows")
    places = census.places_for_rows("homeless shelters in Austin", t["rows"], "topic", subject="homeless shelters")
    assert places and places["areas"] and places["ctx"]["topic"] == "homeless shelters" and places["ctx"]["kind"] == "org"
    assert all("topic=homeless+shelters" in a["drill_url"] and "q=homeless+shelters+in+Austin" in a["drill_url"] for a in places["areas"])
    out = census.places_out(places)
    assert out["context"]["topic"] == "homeless shelters"
    assert out["areas"][0]["url"].startswith("http") and "topic=homeless+shelters" in out["areas"][0]["url"]
    assert out["areas"][0]["area_url"].startswith("http") and "?" not in out["areas"][0]["area_url"]
    # places_for_result passes a topic result's words along
    res = {"kind": "topic", "t": t}
    p2 = census.places_for_result("homeless shelters in Austin", res)
    assert p2 and p2["ctx"]["topic"] == "homeless shelters"


def test_deep_query_county_tables_link_with_the_question():
    _loaded()
    from app import db, deep
    rows = census.drill_rows("G4804530", "county", "food bank", "org")["rows"]
    assert rows and rows[0]["ein"]
    with db.conn() as conn:
        tables = deep._census_tables(conn, [r["ein"] for r in rows], "poverty_rate", "Food banks and local poverty", "food banks")
    assert tables and "county_page" in tables[0]["columns"]
    i = tables[0]["columns"].index("county_page")
    page = tables[0]["rows"][0][i]
    assert page.startswith("/census/tx/travis-county?") and "topic=food+banks" in page and "q=Food+banks+and+local+poverty" in page \
        and "measure=poverty_rate" in page
