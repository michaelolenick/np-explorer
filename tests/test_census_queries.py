"""Regression: the census questions the owner ran on 2026-11-13 ("list Counties with the highest share of
foreign-born residents" came back "No results" although the data was loaded: the planner was right, but
app/census.py had no nation-level area and ranked only a state's counties). Each question must resolve by rule
(no model), run to real rows from census_area, and render with the standard page. The intents the model produced
for them that day are pinned here too, so a planner change cannot break them silently. The broader retry and the
census suggestions on an empty result are covered at the end."""

import re

import pytest
from starlette.testclient import TestClient

from app import ask, census



@pytest.fixture(scope="module", autouse=True)
def _census_loaded(client):
    if not census.PUBLIC or not census.ready():
        pytest.skip("census tables not loaded")

OWNER_QUESTIONS = {
    "list Counties with the highest share of foreign-born residents":
        {"intent": "census_area", "place": "United States", "measure": "foreign_born_share", "children": "county", "lowest_first": False},
    "Which counties have the highest poverty rate?":
        {"intent": "census_area", "place": "United States", "measure": "poverty_rate", "children": "county", "lowest_first": False},
    "Which counties have the longest average commute?":
        {"intent": "census_area", "place": "United States", "measure": "mean_commute", "children": "county", "lowest_first": False},
    "Counties with the lowest share of foreign-born residents":
        {"intent": "census_area", "place": "United States", "measure": "foreign_born_share", "children": "county", "lowest_first": True},
    "Food banks in the poorest counties":
        {"intent": "orgs_in_topic", "keywords": "Food banks", "state": None, "min_revenue": None, "max_revenue": None,
         "area_measure": "poverty_rate", "area_lowest_first": False},
    "Foreign-born share in Travis County, Texas":
        {"intent": "census_area", "place": "Travis County, Texas", "measure": "foreign_born_share"},
    "Compare poverty rate in Monroe County, Indiana and Travis County, Texas":
        {"intent": "census_area", "place": "Monroe County, Indiana", "measure": "poverty_rate", "compare_with": "Travis County, Texas"},
}
# What the model planned for the one question the rules leave to it (2026-11-13), pinned.
MODEL_PLANS = {"Nonprofits in Monroe County, Indiana": {"intent": "census_area", "place": "Monroe County, Indiana", "state": "IN", "measure": None}}


@pytest.fixture(scope="module")
def client():
    from app import db
    from app.main import app
    db.pool.open(wait=False)           # no `with`: the lifespan would close the pool for later test modules
    return TestClient(app)


def test_every_owner_question_resolves_by_rule_without_a_model():
    for q, want in OWNER_QUESTIONS.items():
        got = ask.rule_parse(q)
        assert got, q
        for k, v in want.items():
            assert got.get(k) == v, (q, k, got)


def test_synonyms_resolve_to_the_measures():
    assert census.question("immigrants in Queens") is None          # an organization search, not a census question
    assert census.question("counties with the most immigrants")["measure"] == "foreign_born_share"
    assert census._measure_key("share of foreign-born residents") == "foreign_born_share"
    assert census._measure_key("born abroad") == "foreign_born_share"
    assert census._measure_key("average commute time") == "mean_commute"
    assert census._measure_key("poverty rates") == "poverty_rate"
    assert census.question("which cities have the most immigrants")["measure"] == "foreign_born_share"
    assert census.question("top 10 counties in Texas with the highest poverty rate") == {
        "intent": "census_area", "place": "Texas", "measure": "poverty_rate", "children": "county", "lowest_first": False, "limit": 10}
    assert census.question("counties with the shortest commutes")["lowest_first"] is True
    assert census.org_question("hospitals in the richest counties in Ohio") == {
        "intent": "orgs_in_topic", "keywords": "hospitals", "state": "OH", "min_revenue": None, "max_revenue": None,
        "area_measure": "median_hh_income", "area_lowest_first": False}
    assert census.is_nation("the United States") and census.is_nation("USA") and not census.is_nation("Texas")


def test_nationwide_rankings_return_real_counties_as_rates():
    res = census.answer(OWNER_QUESTIONS["list Counties with the highest share of foreign-born residents"])
    assert res["kind"] == "census" and res["nation"] and res["ranked_level"] == "county"
    names = [r["name"] for r in res["ranked"]]
    assert "Miami-Dade County, Florida" in names[:3], names[:5]
    assert all(0 <= float(r["foreign_born_share"]) <= 100 for r in res["ranked"])
    assert res["ranked"] == sorted(res["ranked"], key=lambda r: -float(r["foreign_born_share"]))
    assert all((r["population"] or 0) >= census.NATION_MIN_POP["county"] for r in res["ranked"])
    assert "10,000 or more residents" in res["ranked_note"] and res["map_url"].startswith("/census/map")
    lowest = census.answer(OWNER_QUESTIONS["Counties with the lowest share of foreign-born residents"])
    assert lowest["ranked"] == sorted(lowest["ranked"], key=lambda r: float(r["foreign_born_share"]))
    poverty = census.answer(OWNER_QUESTIONS["Which counties have the highest poverty rate?"])
    assert float(poverty["ranked"][0]["poverty_rate"]) > 30
    commute = census.answer(OWNER_QUESTIONS["Which counties have the longest average commute?"])
    assert 30 < float(commute["ranked"][0]["mean_commute"]) < 90
    res10 = census.answer({**OWNER_QUESTIONS["Which counties have the highest poverty rate?"], "limit": 10})
    assert len(res10["ranked"]) == 10


def test_one_place_and_a_comparison():
    res = census.answer(OWNER_QUESTIONS["Foreign-born share in Travis County, Texas"])
    assert res["kind"] == "census" and res["name"] == "Travis County, TX" and res["area"]["foreign_born_share"] is not None
    res = census.answer(OWNER_QUESTIONS["Compare poverty rate in Monroe County, Indiana and Travis County, Texas"])
    assert res["kind"] == "census" and res["total"] == 2 and res["compare"]["name_b"] == "Travis County, TX"
    assert res["compare"]["rows"][0]["key"] == "poverty_rate"
    assert res["compare"]["rows"][0]["va"] is not None and res["compare"]["rows"][0]["vb"] is not None
    res = census.answer(MODEL_PLANS["Nonprofits in Monroe County, Indiana"])
    assert res["kind"] == "census" and res["name"] == "Monroe County, IN" and len(res["top_orgs"]) >= 10
    assert any("INDIANA UNIVERSITY" in (o.get("name") or "") for o in res["top_orgs"])


def test_food_banks_ranked_by_their_countys_poverty_rate():
    res = ask.run(OWNER_QUESTIONS["Food banks in the poorest counties"])
    assert res["kind"] == "topic"
    t = res["t"]
    assert t["area_rank"]["measure"] == "poverty_rate" and t["area_rank"]["placed"] >= 10
    placed = [r for r in t["rows"] if r["area_value"] is not None]
    assert placed == t["rows"][:len(placed)]                      # placed rows first, then the unplaced
    assert placed == sorted(placed, key=lambda r: -float(r["area_value"]))
    assert placed[0]["county_url"].startswith("/census/") and placed[0]["county_name"]


def test_pages_render_each_question_with_rows_and_the_standard_page(client, monkeypatch):
    plans = {**OWNER_QUESTIONS, **MODEL_PLANS}
    for q, plan in plans.items():
        monkeypatch.setattr(ask, "parse", lambda question, ip, trusted=False, _p=plan: {**_p, "how": "rule"})
        r = client.get("/ask", params={"q": q})
        assert r.status_code == 200 and 'class="wide contained"' in r.text, q
        assert "No results" not in r.text, q
        assert "Met Museum" not in r.text, q
    def page(q):
        monkeypatch.setattr(ask, "parse", lambda question, ip, trusted=False, _p=plans[q]: {**_p, "how": "rule"})
        return client.get("/ask", params={"q": q}).text
    html = page("list Counties with the highest share of foreign-born residents")
    assert "Miami-Dade County, FL" in html and "Counties of United States by foreign born" in html
    html = page("Compare poverty rate in Monroe County, Indiana and Travis County, Texas")
    assert "compared with" in html and "Travis County, TX" in html
    html = page("Food banks in the poorest counties")
    assert "County poverty rate" in html and "Ranked by the poverty rate of each organization" in html


def test_broaden_widens_one_step_and_the_empty_page_suggests_census_questions(client, monkeypatch):
    assert ask.broaden({"intent": "census_area", "place": "Texas", "measure": "poverty_rate", "children": "county"})["place"] == "United States"
    assert ask.broaden({"intent": "census_area", "place": "United States", "measure": "poverty_rate", "children": "county"}) is None
    assert ask.broaden({"intent": "orgs_in_topic", "keywords": "x", "state": "TX", "area_measure": "poverty_rate"})["area_measure"] is None
    assert ask.broaden({"intent": "unknown"}) is None
    # a place nobody has: the broader plan (the country) answers instead of "No results"
    monkeypatch.setattr(ask, "parse", lambda question, ip, trusted=False: {
        "intent": "census_area", "place": "Nowhereville Zxq", "measure": "poverty_rate", "children": "county", "how": "rule"})
    r = client.get("/ask", params={"q": "poorest counties in Nowhereville Zxq"})
    assert r.status_code == 200 and "No results for" in r.text and "Showing" in r.text and "Counties of United States by poverty rate" in r.text
    # nothing to widen: the empty page offers census questions, never an unrelated idea
    monkeypatch.setattr(ask, "parse", lambda question, ip, trusted=False: {
        "intent": "census_area", "place": "Nowhereville Zxq", "measure": "poverty_rate", "how": "rule"})
    r = client.get("/ask", params={"q": "poverty rate in Nowhereville Zxq"})
    assert "No results." in r.text and "Which counties have the highest poverty rate?" in r.text
    assert "Met Museum" not in r.text and "related question" not in r.text
    assert [s["question"] for s in census.suggestions("mean_commute")][0] == "Which counties have the longest average commute?"


def test_the_planner_prompt_and_tools_carry_the_measures_and_synonyms():
    tool = next(t for t in ask.TOOLS if t["name"] == "census_area")
    assert "United States" in tool["description"] and "immigrants" in tool["description"] and "longest" in tool["description"]
    assert set(tool["input_schema"]["properties"]) >= {"place", "measure", "children", "lowest_first", "limit", "compare_with"}
    assert set(tool["input_schema"]["properties"]["measure"]["enum"]) >= {"poverty_rate", "foreign_born_share", "mean_commute"}
    topic = next(t for t in ask.TOOLS if t["name"] == "orgs_in_topic")
    assert "area_measure" in topic["input_schema"]["properties"]
    assert "poorest counties" in ask.SYSTEM and "place United States" in ask.SYSTEM
    v = ask.validate("census_area", {"place": "United States", "measure": "mean_commute", "children": "county", "limit": 500, "compare_with": "Ohio"})
    assert v["limit"] == 100 and v["compare_with"] == "Ohio"
    v = ask.validate("orgs_in_topic", {"keywords": "food bank", "area_measure": "poverty_rate", "area_lowest_first": True})
    assert v["area_measure"] == "poverty_rate" and v["area_lowest_first"] is True
    assert "ranked by their county's poverty rate" in ask.describe(v)
