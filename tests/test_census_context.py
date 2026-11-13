"""Census context with every result (owner, 2026-11-13: "make sure the census data is integrated into the results of
everything else ... make sure to show demographic data"): topic detection picks the measures, "The places behind
these results" renders under /ask and /search results, the short answer gets the facts, the deep-query planner and
the search planner know the census tables, measure-of-a-place questions resolve by rule, the API and MCP search
carry `areas`, and every page keeps the standard menu and width. No test reaches a real model: ask.parse is
replaced where a question would be read, and answer._call where an answer would be written."""

import re

import pytest
from starlette.testclient import TestClient

from app import answer as nl_answer, ask, census, deep


@pytest.fixture(scope="module")
def client():
    from app import db
    from app.main import app
    db.pool.open(wait=False)           # no `with`: the lifespan would close the pool for later test modules
    return TestClient(app)


def _body(html: str) -> str:
    return re.search(r"<body[^>]*>", html).group(0)


def _menu(html: str) -> list[str]:
    nav = html[html.index("site-nav"):html.index("</nav>")]
    return re.findall(r"<(?:a|summary)[^>]*>([^<]+)<", nav)


# --- pure logic ----------------------------------------------------------------------------------------------------

def test_topic_detection_picks_the_measures_that_fit():
    assert census.topic("colleges in Mississippi")["measures"][0] == "bachelors_share"
    assert census.topic("highest paid school superintendents")["topic"] == "education"
    h = census.topic("affordable housing nonprofits in Austin")
    assert h["topic"] == "housing" and {"median_rent", "renter_share", "owner_share", "median_home_value"} <= set(h["measures"])
    assert census.topic("habitat for humanity")["topic"] == "housing"
    assert census.topic("food banks in Texas")["measures"][:2] == ["poverty_rate", "median_hh_income"]
    assert census.topic("highest paid hospital executives in Ohio")["topic"] == "health"
    assert census.topic("refugee resettlement agencies")["measures"][0] == "foreign_born_share"
    assert census.topic("senior centers in Florida")["measures"][0] == "over_65_share"
    assert census.topic("youth sports leagues")["measures"][0] == "under_18_share"
    assert census.topic("job training programs in Detroit")["measures"][0] == "unemployment_rate"
    assert census.topic("civil rights organizations")["measures"] == ["white_share", "black_share", "hispanic_share", "asian_share", "native_share"]
    d = census.topic("who runs the Red Cross")
    assert d["topic"] == "general" and d["measures"] == ["population", "median_hh_income", "poverty_rate", "bachelors_share"]
    for t in census.TOPIC_MEASURES:
        assert all(k in census.MEASURE_INFO for k in t[2])


def test_census_question_patterns_resolve():
    q = census.question("median rent in Austin, TX")
    assert q == {"intent": "census_area", "place": "Austin, TX", "measure": "median_rent"}
    assert census.question("bachelor's degree share in Travis County")["measure"] == "bachelors_share"
    assert census.question("what is the foreign-born share in Queens")["measure"] == "foreign_born_share"
    assert census.question("How educated is Travis County?")["measure"] == "bachelors_share"
    assert census.question("Travis County poverty rate")["measure"] == "poverty_rate"
    assert census.question("Austin, TX median home value") == {"intent": "census_area", "place": "Austin, TX", "measure": "median_home_value"}
    r = census.question("poverty rate of Mississippi counties")
    assert r["place"] == "Mississippi" and r["measure"] == "poverty_rate" and r["children"] == "county"
    r = census.question("Mississippi counties by median income")
    assert r["place"] == "Mississippi" and r["measure"] == "median_hh_income" and r["children"] == "county"
    r = census.question("poorest counties in Mississippi")
    assert r["place"] == "Mississippi" and r["measure"] == "poverty_rate" and r["children"] == "county" and not r["lowest_first"]
    r = census.question("cheapest cities in Texas")
    assert r["measure"] == "median_home_value" and r["children"] == "place" and r["lowest_first"]
    assert census.question("commute time in Cook County, Illinois")["measure"] == "mean_commute"
    assert census.question("senior population in Florida")["measure"] == "over_65_share"
    assert census.question("demographics of Ohio")["measure"] is None
    # Charity searches are not census questions.
    for s in ("food banks in Texas", "children's hospitals in Ohio", "housing nonprofits in Austin", "who runs the Red Cross",
              "charities in Austin", "highest paid hospital executives in Ohio", "immigrants in Queens"):
        assert census.question(s) is None, s
    intent = ask.rule_parse("median rent in Austin, TX")
    assert intent["intent"] == "census_area" and intent["measure"] == "median_rent"
    assert "median gross rent" in ask.describe(intent).lower() and "Austin" in ask.describe(intent)
    assert "ranked by poverty rate" in ask.describe(census.question("poorest counties in Mississippi"))


def test_planner_system_and_tool_know_the_census():
    assert "census" in ask.SYSTEM.lower() and "census_area" in ask.SYSTEM
    tool = next(t for t in ask.TOOLS if t["name"] == "census_area")
    assert "median_rent" in tool["input_schema"]["properties"]["measure"]["enum"]
    v = ask.validate("census_area", {"place": "Austin, TX", "measure": "median_rent"})
    assert v == {"intent": "census_area", "place": "Austin, TX", "state": None, "measure": "median_rent"}
    v = ask.validate("census_area", {"place": "Mississippi", "measure": "poverty_rate", "children": "county", "lowest_first": True})
    assert v["children"] == "county" and v["lowest_first"] is True
    assert ask.validate("census_area", {"measure": "poverty_rate"})["intent"] == "unknown"
    assert "lowest_first=1" in ask.edit_url(v)


def test_deep_planner_prompt_describes_the_census_tables():
    assert "census_area" in deep.PLAN_SYSTEM and "census_links" in deep.PLAN_SYSTEM and "census_zip_county" in deep.PLAN_SYSTEM
    assert "poverty_rate" in deep.PLAN_SYSTEM and "JOIN census_area" in deep.PLAN_SYSTEM
    assert "census_measure" in deep.PLAN_TOOL["input_schema"]["properties"]
    p = deep.validate({"recipe": "topic", "title": "food banks", "terms": "food bank", "census_measure": "poverty_rate"})
    assert p["census_measure"] == "poverty_rate" and not p["unsupported"]
    assert deep.validate({"recipe": "topic", "title": "x", "terms": "y", "census_measure": "drop table"})["census_measure"] is None


def test_placement_reads_every_row_shape():
    assert census._placement({"ein": "943242767"}) == ("link", "org", "943242767")
    assert census._placement({"org_totals": [{"ein": "530196605"}], "id": 5}) == ("link", "org", "530196605")
    assert census._placement({"unitid": 228778}) == ("link", "college", "228778")
    assert census._placement({"subject_url": "/contractor/acme-62137"}) == ("link", "contractor", "62137")
    assert census._placement({"url": "https://furp.org/org/530196605"}) == ("link", "org", "530196605")
    assert census._placement({"zip": "78701-1234", "city": "Austin", "state": "TX"}) == ("addr", "78701", "AUSTIN", "TX")
    assert census._placement({"states": ["OH", "TX"]}) == ("addr", None, None, "OH")
    assert census._placement({"name": "nowhere"}) is None
    assert census._numbers({"latest_pay": 500000, "display_name": "Jane Doe", "latest_total_revenue": 1e7}, "org_people") == (500000.0, "Jane Doe", 1e7)
    assert census._numbers({"total_comp": 900000, "max_comp": 300000}, "people")[0] == 300000.0     # never a lifetime total
    assert census._numbers({"value": 250000, "subject_name": "A"}, "top_paid")[:2] == (250000.0, "A")


def test_answer_payload_carries_the_census_facts(monkeypatch):
    places = {"topic": "poverty", "placed": 9, "total": 10,
              "measures": [census.MEASURE_INFO["poverty_rate"], census.MEASURE_INFO["median_hh_income"]],
              "areas": [{"gisjoin": "G4802010", "name": "Harris County, TX", "level": "county", "url": "/census/tx/harris-county",
                         "n": 6, "share": 67, "vals": {"poverty_rate": 15.8, "median_hh_income": 71234},
                         "fmt": {"poverty_rate": "15.8%", "median_hh_income": "$71,234"}, "table_urls": {"poverty_rate": "x", "median_hh_income": "y"}}],
              "compare": ["The 6 nonprofits listed in Harris County, TX report $12,000,000 in revenue together."],
              "reference": {"name": "Texas", "url": "/census/tx", "level": "state", "n": None, "vals": {"poverty_rate": 14.0, "median_hh_income": 75000},
                            "fmt": {"poverty_rate": "14.0%", "median_hh_income": "$75,000"}, "table_urls": {}},
              "states": ["TX"], "how": "by ZIP"}
    facts = census.places_facts(places)
    assert facts["areas"][0]["Poverty rate"] == "15.8%" and facts["areas"][0]["rows_here"] == 6
    assert facts["state_for_comparison"]["area"] == "Texas" and facts["comparisons"]
    assert nl_answer.key_for("/ask?intent=org_lookup&name=x", [{"label": "Revenue"}], places).endswith("#first=Revenue#census")
    assert nl_answer.key_for("/ask?intent=org_lookup&name=x", [{"label": "Revenue"}], None).endswith("#first=Revenue")
    seen = {}

    def fake_call(question, data):
        seen.update(data)
        return "Harris County, TX has 15.8% of residents in poverty and Food Bank One reports $12,000,000."
    monkeypatch.setattr(nl_answer, "_call", fake_call)
    monkeypatch.setattr(nl_answer, "cached", lambda key: None)
    from app import db
    monkeypatch.setattr(db, "conn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no cache write in this test")))
    result = {"kind": "orgs", "total": 1, "rows": [{"ein": "943242767", "name": "Food Bank One", "city": "Houston", "state": "TX",
                                                    "latest_total_revenue": 12000000}]}
    html = nl_answer.answer("food banks in Texas", "/ask?test=census-context", result, lead="Revenue", places=places)
    assert seen["census"]["areas"][0]["area"] == "Harris County, TX" and seen["census"]["topic"] == "poverty"
    assert 'href="/census/tx/harris-county"' in html and "15.8%" in html
    assert "census" in nl_answer.SYSTEM and "bear on the question" in nl_answer.SYSTEM


# --- the pages (the shared database; skipped while the census is not loaded) -----------------------------------------

def _loaded():
    if not census.ready():
        pytest.skip("census_area not loaded yet")


def test_places_panel_for_an_orgs_result(client, monkeypatch):
    _loaded()
    about = client.get("/about").text
    monkeypatch.setattr(ask, "parse", lambda q, ip, trusted=False: {"intent": "org_lookup", "name": "food bank", "city": None,
                                                                    "state": "TX", "daf_only": False, "how": "test", "parse_ms": 0})
    r = client.get("/ask?q=food+banks+in+Texas")
    assert r.status_code == 200
    assert _body(r.text) == '<body class="wide contained">' and _menu(r.text) == _menu(about)
    assert "The places behind these results" in r.text
    assert re.search(r'href="/census/tx/[a-z-]+-county(\?[^"]*)?"', r.text), "a county link (it may carry the question: ?q=, ?topic=; 2026-11-13)"
    assert "Poverty rate" in r.text and re.search(r">\d{1,2}\.\d%<", r.text), "a formatted poverty rate"
    assert re.search(r'href="/census/tx(\?[^"]*)?">Texas</a> <span class="muted">state, for comparison', r.text)   # may carry ?q= (2026-11-13)
    assert "data.census.gov" in r.text
    # The same panel as data for the short answer and the API.
    res = ask.run({"intent": "org_lookup", "name": "food bank", "state": "TX", "limit": 25})
    places = census.places_for_result("food banks in Texas", res)
    assert places and places["topic"] == "poverty" and places["measures"][0]["key"] == "poverty_rate"
    assert places["areas"][0]["n"] >= 1 and places["areas"][0]["url"].startswith("/census/tx/")
    assert any("per resident" in c for c in places["compare"])
    out = census.places_out(places)
    assert out["areas"][0]["measures"]["poverty_rate"]["table"] == "B17001" and out["citation"].startswith("Jonathan Schroeder")


def test_places_panel_for_people_and_a_single_organization(client):
    _loaded()
    res = ask.run({"intent": "top_paid", "scope": "state", "state": "OH", "ntee": None, "org": None, "year": None,
                   "title_contains": None, "limit": 25, "per_person": True, "include_related": False})
    if res.get("rows"):
        places = census.places_for_result("highest paid hospital executives in Ohio", res)
        assert places and places["topic"] == "health" and places["areas"]
        assert any("times the median household income" in c for c in places["compare"]), places["compare"]
    org = census.link_for("org", "943242767")
    if org:
        res = ask.run({"intent": "org_people", "org": "Khan Academy", "state": None})
        if res.get("kind") == "org_people":
            places = census.places_for_result("who runs Khan Academy", res)
            assert places and len(places["areas"]) >= 1 and places["placed"] == 1


def test_classic_search_page_shows_the_places(client):
    _loaded()
    r = client.get("/search?q=habitat+for+humanity&nl=0")
    assert r.status_code == 200 and _body(r.text) == '<body class="wide contained">'
    assert "The places behind these results" in r.text and "Median gross rent" in r.text    # housing measures
    assert re.search(r'href="/census/[a-z]{2}/[a-z0-9-]+(\?[^"]*)?"', r.text)     # the link may carry the question (2026-11-13)


def test_census_question_pages(client):
    _loaded()
    r = client.get("/search?q=poverty+rate+of+Mississippi+counties")
    assert r.status_code == 200 and "Counties of Mississippi by poverty rate" in r.text
    assert 'href="/census/ms?m=poverty_rate"' in r.text and "Money first" in r.text
    r = client.get("/search?q=median+rent+in+Austin,+TX")
    assert r.status_code == 200 and "Median gross rent:" in r.text and "Housing first" in r.text
    r = client.get("/ask?intent=census_area&place=Texas&measure=median_hh_income&children=county&lowest_first=1")
    assert r.status_code == 200 and "lowest first" in r.text
    r = client.get("/census/of/org/943242767?state=CA", follow_redirects=False)
    assert r.status_code in (302, 404)
    if r.status_code == 302:
        assert r.headers["location"].startswith("/census/ca")
    r = client.get("/census/of/org/000000000?state=TX", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/census/tx"


def test_api_and_mcp_search_carry_areas(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    search = next(t for t in r.json()["result"]["tools"] if t["name"] == "search")
    assert "areas" in search["description"]
    assert "areas" in client.get("/developers").text
    _loaded()
    r = client.get("/api/v1/search?q=food+bank&type=organizations")
    assert r.status_code == 200
    body = r.json()
    assert "areas" in body
    if body["areas"]:
        a = body["areas"]["areas"][0]
        assert a["url"].startswith("http") and "/census/" in a["url"] and "poverty_rate" in a["measures"]
        assert body["areas"]["topic"] == "poverty"


def test_boards_offer_an_area_link(client):
    r = client.get("/boards/top-paid")
    assert r.status_code == 200 and _body(r.text) == '<body class="wide contained">'
    if census.PUBLIC and "/census/of/org/" not in r.text:
        assert 'href="/census/' in r.text          # rows without an EIN link to the state's page
