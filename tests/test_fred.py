"""FRED (loader/fred.py, app/fred.py, app/fred_boards.py; owner, 2026-11-13): observation parsing from CSV and JSON
fixtures, the county-title-to-census_area matching, the CPI deflator, the sparkline, the boards' registration, the data
and developers pages, the API dataset, and the census pages keeping the standard menu and width with the block in.
The pages must render whether or not the fred tables are loaded, so data checks are skipped while they are empty."""

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from app import fred
from loader import fred as lf

FIX = Path(__file__).resolve().parent / "fixtures" / "fred"


# --- parsing -----------------------------------------------------------------------------------------------------------

def test_parse_csv_fixture_reads_dates_values_and_missing():
    rows = lf.parse_csv((FIX / "CPIAUCSL.csv").read_text())
    assert rows[0] == ("2019-01-01", 252.561) and rows[-1] == ("2020-02-01", 259.05)
    assert ("2020-01-01", None) in rows and len(rows) == 14


def test_parse_csv_accepts_the_old_date_header_and_rejects_html():
    assert lf.parse_csv("DATE,UNRATE\n2026-09-01,4.3\n") == [("2026-09-01", 4.3)]
    with pytest.raises(ValueError):
        lf.parse_csv("<html>not found</html>")


def test_parse_json_observations_fixture():
    obs = lf.parse_observations(json.loads((FIX / "observations.json").read_text()))
    assert obs == [("2026-06-01", 3.4), ("2026-07-01", 3.7), ("2026-08-01", None), ("2026-09-01", 3.5)]


# --- series ids to places ------------------------------------------------------------------------------------------------

AREAS = [
    {"gisjoin": "G4804530", "stusab": "TX", "short_name": "Travis County"},
    {"gisjoin": "G4201010", "stusab": "PA", "short_name": "Philadelphia County"},
    {"gisjoin": "G2905100", "stusab": "MO", "short_name": "St. Louis city"},
    {"gisjoin": "G2901890", "stusab": "MO", "short_name": "St. Louis County"},
    {"gisjoin": "G3500130", "stusab": "NM", "short_name": "Doña Ana County"},
    {"gisjoin": "G5107600", "stusab": "VA", "short_name": "Richmond city"},
    {"gisjoin": "G5101590", "stusab": "VA", "short_name": "Richmond County"},
]


def test_county_keys_normalize_accents_dots_and_types():
    assert lf.county_key("Doña Ana County") == ("dona ana", "county")
    assert lf.county_key("St. Louis city") == ("st louis", "city")
    assert lf.county_key("Philadelphia County/City") == ("philadelphia", "county/city")
    assert lf.county_key("Juneau City and Borough") == ("juneau", "city and borough")
    assert lf.county_key("Orleans Parish") == ("orleans", "parish")


def test_discovered_titles_match_census_counties():
    index = lf.county_index(AREAS)
    tag_rows = json.loads((FIX / "tags_series.json").read_text())["seriess"]
    _, id_re, title_re = lf.DISCOVER["county"]["unemployment_rate"]
    found = {}
    for s in tag_rows:
        assert id_re.match(s["id"]) and title_re.match(s["title"])
        name, st = title_re.match(s["title"]).groups()
        a = lf.match_county(index, name, st)
        found[s["id"]] = a and a["gisjoin"]
    assert found == {"TXTRAV3URN": "G4804530", "PAPHIL5URN": "G4201010", "MOSSURN": "G2905100", "NMDONA5URN": "G3500130"}
    # Virginia's Richmond city and Richmond County stay apart; an unknown county is None.
    assert lf.match_county(index, "Richmond City", "VA")["gisjoin"] == "G5107600"
    assert lf.match_county(index, "Richmond County", "VA")["gisjoin"] == "G5101590"
    assert lf.match_county(index, "Nowhere County", "TX") is None


def test_fips_patterns_and_prefix_kinds():
    pats = dict(lf.COUNTY_PATTERNS)
    assert pats["per_capita_income"].format(fips="48453", st="TX") == "PCPI48453"
    assert pats["hpi"].format(fips="48453", st="TX") == "ATNHPIUS48453A"
    assert pats["median_hh_income"].format(fips="48453", st="TX") == "MHITX48453A052NCEN"
    assert dict(lf.STATE_PATTERNS)["unemployment_rate"].format(st="TX") == "TXUR"
    assert "TXTRAV3URN"[:-3] + dict(lf.PREFIX_KINDS)["population"] == "TXTRAV3POP"
    assert fred.area_gisjoin({"level": "place", "state_fips": "48", "county_fips": "453"}) == "G4804530"
    assert fred.area_gisjoin({"level": "tract", "state_fips": "48", "county_fips": None}) == "G480"
    assert fred.area_gisjoin({"level": "county", "gisjoin": "G4804530"}) == "G4804530"


# --- the deflator, formats and the sparkline -------------------------------------------------------------------------------

CPI = {2019: 255.657, 2024: 313.689, 2025: 322.0}


def test_real_dollars_uses_cpi_annual_averages():
    assert round(fred.real_dollars(100_000, 2019, 2024, cpi=CPI)) == round(100_000 * 313.689 / 255.657)
    assert round(fred.real_dollars(100_000, 2019, cpi=CPI)) == round(100_000 * 322.0 / 255.657)   # to the latest year
    assert fred.real_dollars(100_000, 1950, 2024, cpi=CPI) is None and fred.real_dollars(None, 2019, cpi=CPI) is None
    assert fred.cpi_latest_year(CPI) == 2025
    assert fred.real_dollars(5, 2024, 2024, cpi=CPI) == 5


def test_formats_and_periods():
    assert fred.fmt(4.26, "pct") == "4.3%" and fred.fmt(78123.4, "money") == "$78,123"
    assert fred.fmt(1334.567, "people") == "1,334,567" and fred.fmt(0.5, "points") == "+0.5 pt"
    assert fred.period(dt.date(2026, 9, 1), "M") == "Sep 2026" and fred.period(dt.date(2024, 1, 1), "A") == "2024"
    assert fred.period(dt.date(2026, 4, 1), "Q") == "Q2 2026"


def test_sparkline_is_inline_svg_with_a_title():
    pts = [(dt.date(2016 + i // 12, i % 12 + 1, 1), 3 + (i % 7) / 2) for i in range(120)]
    svg = fred.sparkline(pts, label="Unemployment rate")
    assert svg.startswith("<svg") and "<polyline" in svg and "<title>Unemployment rate: 3.0% in Jan 2016" in svg
    assert fred.sparkline([(dt.date(2026, 1, 1), 3.0)]) == ""


def test_sentence_for_the_compact_block():
    econ = {"compact": [
        {"kind": "unemployment_rate", "short": "unemployment", "label": "Unemployment rate", "text": "3.4%", "period": "Sep 2026",
         "change_1y": {"value": 0.3}, "text_1y": "3.1%"},
        {"kind": "per_capita_income", "short": "per capita personal income", "label": "x", "text": "$78,000", "period": "2024",
         "change_5y": {"value": 23.4}, "real_change_5y": {"text": "+4.1%"}}]}
    assert fred.sentence(econ) == ("unemployment 3.4% in Sep 2026 (3.1% a year earlier); per capita personal income $78,000 in "
                                   "2024, up 23% in five years (+4.1% after inflation)")


# --- registration: boards, the API dataset, MCP ------------------------------------------------------------------------------

def test_fred_boards_are_registered():
    from app import boards
    from app.fred_boards import fred_boards
    slugs = {b.slug for b in fred_boards()}
    assert slugs == {"fred-income-down-nonprofits-up", "fred-unemployment-big-nonprofits", "fred-pay-vs-county-income"}
    assert slugs <= {b.slug for b in boards.BOARDS} and "fred" in boards.GROUPS
    for b in fred_boards():
        assert b.group == "fred" and "fred." in b.sql and "FRED" in b.formula
    assert "fred.real_dollars" in boards.BY_SLUG["fred-pay-vs-county-income"].sql


def test_fred_dataset_in_the_api_and_mcp():
    from app import mcp, public_api
    ds = {d["id"]: d for d in public_api.DATASETS}
    assert "fred" in ds and ds["fred"]["search"] and "Federal Reserve Bank of St. Louis" in ds["fred"]["source"]
    assert "fred" in mcp._DATASET_IDS


# --- pages ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient
    from app import main
    return TestClient(main.app)            # no `with`: keeps the shared pool open


def _body(html: str) -> str:
    return re.search(r"<body[^>]*>", html).group(0)


def _menu(html: str) -> list[str]:
    nav = html[html.index("site-nav"):html.index("</nav>")]
    return re.findall(r"<(?:a|summary)[^>]*>([^<]+)<", nav)


def test_data_and_developers_pages_credit_fred(client):
    html = client.get("/data").text
    assert "Source: FRED, Federal Reserve Bank of St. Louis" in html and 'id="fred"' in html
    assert _body(html) == '<body class="wide contained">'
    dev = client.get("/developers").text
    assert "/fred/" in dev and "fred" in [m for m in re.findall(r"<code>([a-z0-9_]+)</code>", dev)]
    assert _body(dev) == '<body class="wide contained">'
    r = client.get("/api/v1/datasets")
    assert r.status_code == 200 and "fred" in {d["id"] for d in r.json()["datasets"]}


def test_census_pages_keep_the_menu_and_width_with_the_economy_block(client):
    about = client.get("/about").text
    for path in ("/census/tx", "/census/tx/travis-county"):
        r = client.get(path)
        if r.status_code == 404:
            pytest.skip("census not loaded")
        assert r.status_code == 200, path
        assert _body(r.text) == '<body class="wide contained">' and _menu(r.text) == _menu(about)
        if fred.ready() and fred.economy("G4804530"):
            assert 'id="economy"' in r.text and "Source: FRED, Federal Reserve Bank of St. Louis" in r.text
            assert "fred.stlouisfed.org/series/" in r.text


def test_api_series_endpoint_is_well_behaved(client):
    assert client.get("/api/v1/fred/not-a-series!").status_code == 404
    if not fred.ready():
        pytest.skip("fred not loaded")
    r = client.get("/api/v1/fred/CPIAUCSL?since=2024-01-01")
    assert r.status_code == 200
    j = r.json()
    assert j["id"] == "CPIAUCSL" and j["observations"] and j["observations"][0]["date"] >= "2024-01-01"
    assert j["attribution"] == "Source: FRED, Federal Reserve Bank of St. Louis"
