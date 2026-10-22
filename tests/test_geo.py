"""Map-ready exports (app/geo.py, loader/geo.py): city names, ZIP-first for organizations and city-first for
individuals, districts, and the CSV and GeoJSON formats."""

import json

from starlette.testclient import TestClient

from app import geo, main
from loader.geo import place_norm

client = TestClient(main.app)            # no `with`: keeps the shared pool open


def test_place_names():
    assert place_norm("St. Louis city") == place_norm("SAINT LOUIS") == "saint louis"
    assert place_norm("Ft Worth") == "fort worth" and place_norm("Austin city") == "austin"
    assert place_norm("Nashville-Davidson metropolitan government (balance)") == "nashville davidson"


def test_locate_and_formats():
    if not geo.ready():
        return
    org, person = geo.locate([{"name": "A", "zip": "10022-1234", "city": "New York", "state": "NY"}]), \
        geo.locate([{"name": "B", "zip": "10022", "city": "New York", "state": "NY"}], individuals=True)
    assert org[0]["location_level"] == "ZIP" and org[0]["congressional_district"] == "NY-12"
    assert person[0]["location_level"] == "city" and person[0]["congressional_district"] == "NY-12"   # ZIP's district
    assert geo.locate([{"name": "C"}])[0]["latitude"] is None
    fields = geo.fields_for(org, ["name"])
    assert fields[0] == "name" and fields[-1] == "source" and "latitude" in fields
    csv_text = geo.to_csv(org, fields, "furp.org test")
    assert csv_text.splitlines()[0].startswith("name,") and "Source:" not in csv_text   # no footer row
    gj = json.loads(geo.to_geojson(org + geo.locate([{"name": "C"}]), fields, "furp.org test"))
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 1
    assert gj["metadata"]["rows_without_location"] == 1


def test_map_endpoints():
    if not geo.ready():
        return
    r = client.get("/search/map", params={"q": "urban land institute", "table": "orgs", "format": "geojson"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/geo+json")
    assert client.get("/search/map", params={"q": ""}).status_code == 404
    r = client.get("/ask/map", params={"intent": "food_recalls", "firm": "kroger"})
    assert r.status_code == 200 and r.text.splitlines()[0].endswith("location_level,source")
