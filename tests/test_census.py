"""Census cross-reference (loader/census.py, app/census.py, app/census_map.py, app/census_boards.py; owner,
2026-11-12): the GISJOIN codes, slugs and the facts SQL; the SVG maps without a database; the link table logic;
the pages (standard menu and width), their map exports, the API dataset, endpoint and MCP tool. The pages must
render whether or not the census tables have finished loading, so data checks are skipped while they are empty."""

import json
import re

import pytest

from app import census, census_map
from loader import census as lc


# --- pure logic --------------------------------------------------------------------------------------------------

def test_gisjoin_codes_round_trip():
    assert lc.gisjoin("state", "48") == "G480"
    assert lc.gisjoin("county", "48453") == "G4804530"
    assert lc.gisjoin("place", "4805000") == "G48005000"
    assert lc.gisjoin("tract", "48453001100") == "G4804530001100"
    for level, geoid in (("state", "48"), ("county", "48453"), ("place", "4805000"), ("tract", "48453001100")):
        assert lc.geoid_of(level, lc.gisjoin(level, geoid)) == geoid


def test_slugs_and_place_names():
    assert lc.slugify("Travis County") == "travis-county"
    assert lc.slugify("St. Louis city") == "st-louis-city"
    assert lc.place_short("Austin city") == "Austin"
    assert lc.place_short("Nashville-Davidson metropolitan government (balance)") == "Nashville-Davidson"
    assert lc.place_short("Oak Grove CDP") == "Oak Grove"


def test_facts_sql_uses_the_catalog_and_nulls_missing_tables():
    catalog = {"B01003": {"nhgis_code": "AUO6", "pg_table": "d_2020_2024_acs5a_b01003"},
               "B17001": {"nhgis_code": "AUXY", "pg_table": "d_2020_2024_acs5a_b17001"}}
    sql, filled = lc.facts_sql(catalog, have_dhc=True)
    assert "population" in filled and "poverty_rate" in filled and "median_hh_income" not in filled
    assert "t0.auo6e001" in sql and "100.0 * t1.auxye002 / nullif(t1.auxye001, 0)" in sql
    assert "NULL::numeric AS median_hh_income" in sql
    assert sql.count('LEFT JOIN nhgis."d_2020_2024_acs5a_b01003"') == 1
    assert "dhc.u7h001" in sql
    sql2, _ = lc.facts_sql({}, have_dhc=False)
    assert "NULL::numeric AS population" in sql2 and "dhc" not in sql2


def test_measures_are_described_and_catalogued():
    keys = [m[0] for m in lc.MEASURES]
    assert len(keys) == len(set(keys))
    for key, table, expr, label, fmt, note in lc.MEASURES:
        assert re.fullmatch(r"[BC]\d{5}[A-Z]?", table) and "{c}" in expr and label and note
        assert fmt in ("num", "money", "pct", "years")
        assert key in census.MEASURE_INFO


def _pool():
    from app import db
    db.pool.open(wait=False)


def test_census_questions_are_recognised():
    assert census.question("median income in Cook County") == {"intent": "census_area", "place": "Cook County", "measure": "median_hh_income"}
    assert census.question("What is the population of Austin, Texas?") == {"intent": "census_area", "place": "Austin, Texas", "measure": "population"}
    assert census.question("poverty rate in Detroit")["measure"] == "poverty_rate"
    assert census.question("charities in Austin, Texas") is None
    assert census.question("John Smith") is None


def test_url_and_display_names():
    county = {"level": "county", "stusab": "TX", "slug": "travis-county", "short_name": "Travis County", "name": "Travis County, Texas"}
    place = {"level": "place", "stusab": "TX", "slug": "austin", "short_name": "Austin city", "name": "Austin city, Texas"}
    tract = {"level": "tract", "stusab": "TX", "geoid": "48453001100", "name": "Census Tract 11, Travis County, Texas"}
    assert census.url_for(county) == "/census/tx/travis-county" and census.display_name(county) == "Travis County, TX"
    assert census.url_for(place) == "/census/tx/place/austin" and census.display_name(place) == "Austin, TX"
    assert census.url_for(tract) == "/census/tract/48453001100"
    assert census.census_gov_url({**county, "geoid": "48453"}, "B19013") == "https://data.census.gov/table/ACSDT5Y2024.B19013?g=0500000US48453"


def test_comparisons_are_furp_style():
    a = {"level": "county", "stusab": "TX", "short_name": "Travis County", "population": 1_300_000, "median_hh_income": 90_000,
         "households": 500_000, "poverty_rate": 11.5}
    c = {x["kind"]: x for x in census.compare(a, {"revenue": 1_300_000_000, "pay": 900_000, "pay_name": "Jane Doe", "employees": 13_000})}
    assert c["pay_vs_income"]["value"] == 10 and "10.0 times the median household income" in c["pay_vs_income"]["text"]
    assert c["revenue_per_resident"]["value"] == 1000
    assert round(c["revenue_vs_income"]["value"], 2) == 2.89
    assert c["employees_per_1000"]["value"] == 10
    assert census.compare(a, {}) == []


# --- maps without a database -------------------------------------------------------------------------------------------

def _square(gj, name, x, y, size=1.0):
    return {"gisjoin": gj, "level": "county", "name": name, "geoid": gj[1:3] + gj[4:7], "lon": x + size / 2, "lat": y + size / 2,
            "geom": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]}


FEATURES = [_square("G4800010", "A County", -98, 30), _square("G4800030", "B County", -97, 30), _square("G4800050", "C County", -96, 30),
            _square("G4800070", "D County", -98, 31), _square("G4800090", "E County", -97, 31)]


def test_svg_map_renders_with_links_legend_and_points():
    values = {"G4800010": 10, "G4800030": 20, "G4800050": 30, "G4800070": 40, "G4800090": None}
    links = {f["gisjoin"]: f"/census/tx/{f['name'].lower().replace(' ', '-')}" for f in FEATURES}
    svg = str(census_map.render(FEATURES, values, "money", links, points=[{"lon": -97.5, "lat": 30.5, "n": 3, "label": "ZIP 78701: 3 nonprofits", "url": "/nearby?q=78701"}],
                                legend="Median household income", highlight={"G4800010"}))
    assert svg.startswith("<svg") and svg.endswith("</svg>") and re.search(r'viewBox="0 0 \d+ \d+"', svg)
    assert svg.count("<path") == 6                           # five areas plus the highlight outline
    assert '<a href="/census/tx/a-county">' in svg and "<title>A County: $10</title>" in svg
    assert "<title>E County: no data</title>" in svg and census_map.NO_DATA in svg
    assert "Median household income" in svg and "up to $10" in svg and "over $30" in svg
    assert "<circle" in svg and "ZIP 78701: 3 nonprofits" in svg and 'href="/nearby?q=78701"' in svg
    assert census_map.HIGHLIGHT in svg
    assert len(svg) < 6000


def test_svg_map_without_values_and_us_projection():
    svg = str(census_map.render(FEATURES, {}, "num", {}, legend="x"))
    assert svg.count("<path") == 5 and "<rect" not in svg
    us = [_square("G060", "California", -120, 36, 3), _square("G480", "Texas", -100, 30, 4), _square("G020", "Alaska", -150, 62, 8),
          _square("G150", "Hawaii", -157, 20, 1)]
    for f in us:
        f["level"] = "state"
    svg = str(census_map.render(us, {"G060": 1, "G480": 2, "G020": 3, "G150": 4}, "num", {"G480": "/census/tx"}, us=True))
    assert svg.count("<path") == 4 and '<a href="/census/tx">' in svg
    # Alaska and Hawaii land inside the frame as insets.
    for m in re.finditer(r'<path d="M(-?[\d.]+) (-?[\d.]+)', svg):
        assert 0 <= float(m.group(1)) <= 820 and 0 <= float(m.group(2)) <= 620


def test_class_breaks_and_shading():
    cuts = census_map.breaks([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    assert len(cuts) == 4 and cuts == sorted(cuts)
    assert census_map.shade(None, cuts) == census_map.NO_DATA
    assert census_map.shade(1, cuts) == census_map.PALETTE[0] and census_map.shade(100, cuts) == census_map.PALETTE[-1]
    assert census_map.breaks([5]) == [] and census_map.breaks([]) == []


def test_locator_map_and_geojson():
    county = FEATURES[0]
    svg = str(census_map.locator(county, FEATURES[1], FEATURES[2], (-97.5, 30.5)))
    assert svg.count("<path") == 3 and "<circle" in svg and "<title>A County</title>" in svg
    assert census_map.locator(None, None, None, None) == ""
    fc = census_map.geojson(FEATURES[:2], {"G4800010": {"population": 5}})
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2
    assert fc["features"][0]["geometry"]["type"] == "Polygon" and fc["features"][0]["properties"]["population"] == 5
    json.dumps(fc)


# --- the database: the link logic, the pages, the API ------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)                      # as tests/test_attribution.py: no `with`, its lifespan closes the shared pool
    return TestClient(main.app)


def _body(html: str) -> str:
    return re.search(r"<body[^>]*>", html).group(0)


def _menu(html: str) -> list[str]:
    nav = html[html.index("site-nav"):html.index("</nav>")]
    return re.findall(r"<(?:a|summary)[^>]*>([^<]+)<", nav)


def test_census_pages_have_the_standard_menu_and_width(client):
    about = client.get("/about").text
    paths = ["/census", "/census/tables", "/census/area", "/census/area?q=Austin", "/census/tx", "/census/tx/travis-county",
             "/census/tx/place/austin", "/census/zz", "/census/tx/no-such-county"]
    for path in paths:
        r = client.get(path)
        assert r.status_code in (200, 404, 302), (path, r.status_code)
        if r.status_code == 200:
            assert _body(r.text) == '<body class="wide contained">', path
            assert _menu(r.text) == _menu(about), path
            assert "IPUMS" in r.text or "census" in r.text.lower()
    assert client.get("/census/zz").status_code == 404
    assert client.get("/census/tx/no-such-county").status_code == 404
    assert client.get("/census/tract/123").status_code == 404


def test_state_page_when_loaded(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    r = client.get("/census/tx")
    assert r.status_code == 200
    assert "<h1>Texas</h1>" in r.text and "Travis County" in r.text and 'href="/census/tx/travis-county"' in r.text
    assert "FURP records in Texas" in r.text
    assert "P1" in r.text and "data.census.gov/table/ACSDT5Y2024.B01003?g=0400000US48" in r.text
    if census_map.shapes("county", "48"):
        assert '<svg xmlns="http://www.w3.org/2000/svg"' in r.text and 'class="census-map"' in r.text
        assert 'href="/census/tx/travis-county"><path' in r.text
        assert "/census/tx/map?format=geojson" in r.text
    r = client.get("/census/tx?m=median_age&k=college")
    assert r.status_code == 200


def test_county_place_and_tract_pages_when_loaded(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    r = client.get("/census/tx/travis-county")
    assert r.status_code == 200 and "Travis County, TX" in r.text and 'href="/census/tx"' in r.text
    assert "All " in r.text and "tracts" in r.text
    r = client.get("/census/tx/place/austin")
    assert r.status_code == 200 and "<h1>Austin city, Texas</h1>" in r.text and "Travis County" in r.text
    tract = census.children("tract", "48", "453", limit=1)
    if tract:
        r = client.get(census.url_for(tract[0]))
        assert r.status_code == 200 and tract[0]["geoid"] in r.text and "holding most of the record" in r.text


def test_area_lookup_and_redirect(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    r = client.get("/census/area?q=Austin, TX", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/census/tx/place/austin"
    r = client.get("/census/area?q=Texas", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/census/tx"
    hits = census.lookup("Cook County, Illinois")
    assert hits and hits[0]["level"] == "county" and hits[0]["slug"] == "cook-county"
    assert census.lookup("78701")[0]["gisjoin"] == "G4804530"     # the ZIP's county


def test_link_for_address_uses_the_crosswalks(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    link = census.link_for_address("78701", "Austin", "TX")
    assert link and link["county_gj"] == "G4804530" and link["place_gj"] == "G48005000" and link["how"] == "zip+city"
    assert link["tract_gj"].startswith("G4804530") and link["state_gj"] == "G480"
    assert census.link_for_address(None, "Austin", "TX")["how"] == "city"
    assert census.link_for_address(None, "Nowhere Special", "TX")["how"] == "state"
    assert census.link_for_address(None, None, None) is None
    assert census.link_for_address("78701", None, None)["how"] == "zip"


def test_entity_section_and_org_page(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    sec = census.section("address", zip5="78701", city="Austin", state="TX", numbers={"revenue": 10_000_000, "pay": 500_000, "pay_name": "X"})
    assert sec and sec["finest_level"] == "tract" and sec["cols"][-1]["level"] == "state"
    assert any(c["kind"] == "revenue_per_resident" for c in sec["compare"])
    assert sec["rows"] and all(len(r["vals"]) == len(sec["cols"]) for r in sec["rows"])
    if census.link_for("org", "943242767"):
        r = client.get("/org/943242767")
        assert r.status_code == 200 and 'id="area"' in r.text and "The area" in r.text and "data.census.gov" in r.text


def test_map_exports_are_valid(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    r = client.get("/census/tx/map?format=geojson")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["metadata"]["source"].startswith("furp.org")
    if fc["features"]:
        f = fc["features"][0]
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon") and f["properties"]["url"].endswith(("/census/tx/" + f["properties"]["name"].lower().replace(" ", "-").replace(".", ""), f["properties"]["url"][-1]))
        assert "population" in f["properties"]
    r = client.get("/census/tx/map?format=csv")
    assert r.status_code == 200 and r.text.startswith("name,level,state,geoid,gisjoin,url,") and "Travis County" in r.text
    r = client.get("/census/map?format=geojson")
    assert r.status_code == 200 and r.json()["type"] == "FeatureCollection"
    r = client.get("/census/tx/travis-county/map?format=csv")
    assert r.status_code == 200 and "latitude,longitude,source" in r.text.splitlines()[0]


def test_map_rendering_does_not_query_per_path(monkeypatch):
    """Rendering reads the cached outlines once; no database call happens while the SVG is drawn."""
    calls = []
    from app import db
    real = db.conn
    monkeypatch.setattr(db, "conn", lambda *a, **k: calls.append(1) or real(*a, **k))
    census_map.render(FEATURES, {"G4800010": 1}, "num", {})
    assert calls == []


def test_api_dataset_endpoint_and_mcp_tool(client):
    from app import public_api as api
    ids = [d["id"] for d in api.datasets()]
    assert "census" in ids
    d = next(x for x in api.datasets() if x["id"] == "census")
    assert "IPUMS NHGIS" in d["source"] and "18128" in d["source_url"] + d.get("citation", "")
    r = client.get("/api/v1/datasets")
    assert r.status_code == 200 and any(x["id"] == "census" for x in r.json()["datasets"])
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = {t["name"] for t in r.json()["result"]["tools"]}
    assert "get_area" in tools
    assert "IPUMS NHGIS" in client.get("/llms.txt").text
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    r = client.get("/api/v1/area?zip=78701")
    assert r.status_code == 200
    body = r.json()
    assert body["level"] == "county" and body["name"] == "Travis County, TX" and "population" in body["facts"]
    assert body["facts"]["population"]["table"] == "B01003" and body["citation"].startswith("Jonathan Schroeder")
    assert body["url"].endswith("/census/tx/travis-county") and "furp_records" in body
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "get_area", "arguments": {"city": "Austin", "state": "TX"}}})
    res = r.json()["result"]
    assert not res["isError"] and res["structuredContent"]["level"] == "place"
    r = client.get("/api/v1/datasets/census?q=Cook County")
    assert r.status_code == 200 and r.json()["results"][0]["url"].endswith("/census/il/cook-county")
    org = api.organization("943242767")
    if census.link_for("org", "943242767"):
        assert org["census_area"]["level"] in ("place", "county") and "facts" in org["census_area"]


def test_census_boards_are_registered():
    from app import boards
    from app.census_boards import census_boards
    slugs = {b.slug for b in census_boards()}
    assert {"census-revenue-per-resident", "census-nonprofits-per-10k", "census-pay-vs-income",
            "census-poor-counties-rich-nonprofits", "census-places-revenue-per-resident", "census-federal-per-resident"} <= slugs
    assert slugs <= {b.slug for b in boards.BOARDS}
    assert "census" in boards.GROUPS
    for b in census_boards():
        assert "subject_url" in b.sql and "census_area" in b.sql and b.kind == "census"


def test_search_answers_a_census_question(client):
    _pool()
    if not census.ready():
        pytest.skip("census_area not loaded yet")
    from app import ask
    intent = ask.rule_parse("median income in Travis County, Texas")
    assert intent and intent["intent"] == "census_area"
    res = ask.run(intent)
    assert res["kind"] == "census" and res["area"]["slug"] == "travis-county" and res["url"] == "/census/tx/travis-county"
    assert "Travis County" in ask.describe(intent)
    r = client.get("/search?q=median+income+in+Travis+County,+Texas")
    assert r.status_code == 200 and "Travis County" in r.text and "data.census.gov" in r.text
