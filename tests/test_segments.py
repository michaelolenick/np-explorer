"""Segments from VSTRAT (owner, 2026-11-06): the reader, the matches, the question, the JSON and the page."""

import json

import pytest

from app import ask, corporate, queries, segments

TAX = {"ntee": {"B42": "Undergraduate College", "E22": "Hospital", "K31": "Food Bank"},
       "majors": {"B": "Education", "E": "Health", "K": "Food"},
       "formd": {"Health Care/Hospitals and Physicians": 10, "Technology/Other Technology": 5}}


class Resp:
    status_code = 200

    def __init__(self, obj):
        self.obj = obj

    def json(self):
        return {"content": [{"type": "text", "text": json.dumps(self.obj)}], "usage": {"input_tokens": 1, "output_tokens": 1}}


@pytest.fixture
def quiet(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(segments, "taxonomy", lambda: TAX)
    monkeypatch.setattr(ask, "enabled", lambda: True)
    monkeypatch.setattr(ask, "_usage", lambda **k: None)
    monkeypatch.setattr(ask, "_shared_get", lambda k: store.get(k))
    monkeypatch.setattr(ask, "_shared_put", lambda k, v: store.__setitem__(k, v))
    return store


def test_clean_keeps_only_real_codes_and_short_terms():
    r = segments.clean({"terms": ["Food Bank", "x" * 50, "a b c d e", "food bank"], "ntee": ["k31", "Z99", "K31"],
                        "formd": ["Technology/Other Technology", "Made Up/Thing", "Other/Other"], "wants": "customers", "confidence": 1.7}, {**TAX, "formd": {**TAX["formd"], "Other/Other": 1}})
    assert r == {"terms": ["food bank"], "ntee": ["K31"], "formd": ["Technology/Other Technology"], "wants": "customers", "confidence": 1.0}
    assert segments.clean({}, TAX)["wants"] == "unclear" and segments.clean({"confidence": "x"}, TAX)["confidence"] == 0.0


def test_parse_calls_once_and_caches(quiet, monkeypatch):
    calls = []
    monkeypatch.setattr(ask, "post", lambda body, timeout: calls.append(body) or Resp(
        {"terms": ["food bank"], "ntee": ["K31"], "formd": [], "wants": "funders", "confidence": 0.8}))
    r = segments.parse("food banks", "", "a grant program for hunger relief")
    assert r["how"] == "model" and r["ntee"] == ["K31"] and r["wants"] == "funders" and len(calls) == 1
    assert calls[0]["thinking"] == {"type": "disabled"} and calls[0]["model"] == segments.MODEL
    assert "K31 Food Bank" in calls[0]["system"] and "Technology/Other Technology" in calls[0]["system"]
    assert segments.parse("Food Banks", "", "A grant program for hunger relief")["how"] == "cache" and len(calls) == 1
    assert segments.parse("", "", "")["how"] == "off"
    monkeypatch.setattr(ask, "post", lambda body, timeout: Resp({"terms": [], "ntee": [], "formd": [], "wants": "unclear", "confidence": 0.1}))
    r = segments.parse("zzqx", "", "")
    assert r["how"] == "model" and not r["terms"] and segments.parse("zzqx", "", "")["how"] == "model"   # empty: not cached


def test_context_text_flattens_objects():
    assert segments.context_text({"offering": "SaaS", "industry": "health IT", "user": None}) == "offering: SaaS; industry: health IT"
    assert segments.context_text("plain words") == "plain words" and segments.context_text(None) == ""


def test_matches_rank_name_and_category_first(monkeypatch):
    monkeypatch.setattr(segments, "orgs_in_codes", lambda codes, limit, state=None: [
        {"ein": "1", "name": "BIG HOSPITAL", "latest_total_revenue": 900, "ntee_code": "E22", "city": "A", "state": "TX"},
        {"ein": "2", "name": "OTHER HEALTH SYSTEM", "latest_total_revenue": 500, "ntee_code": "E22", "city": "B", "state": "TX"}])
    monkeypatch.setattr(queries, "search_orgs", lambda q, limit, state=None: [
        {"ein": "2", "name": "OTHER HEALTH SYSTEM", "latest_total_revenue": 500, "ntee_code": "E22"},
        {"ein": "3", "name": "HEALTH SYSTEM FOUNDATION", "latest_total_revenue": 700, "ntee_code": "T30"}])
    rows = segments.nonprofits({"ntee": ["E22"], "terms": ["health system"]}, 10)
    assert [(r["ein"], r["matched"]) for r in rows] == [("2", "name and category"), ("1", "category"), ("3", "name")]
    assert rows[0]["url"].endswith("/org/2")

    def fake_formd(q, limit=10, fd_cat=None, fund=None):
        if fd_cat:
            return [{"cik": "9", "issuer_name": "MED LP", "amount_sold": 50, "accession": "a9", "category": "Health Care", "subcategory": "Hospitals and Physicians", "state": "CA"}]
        return [{"cik": "8", "issuer_name": "HEALTH SYSTEM INC", "amount_sold": 5, "accession": "a8", "category": "Technology", "subcategory": "Other Technology", "state": "CA"}]
    monkeypatch.setattr(corporate, "search_formd", fake_formd)
    f = segments.firms({"formd": ["Health Care/Hospitals and Physicians"], "terms": ["health system"]}, 10)
    assert [(r["cik"], r["matched"]) for r in f] == [("9", "category"), ("8", "name")] and f[0]["name"] == "MED LP"
    assert segments.firms({"formd": ["Health Care/Hospitals and Physicians"], "terms": []}, 10, state="NY") == []


def test_answer_asks_when_thin_and_api_and_page(quiet, monkeypatch):
    monkeypatch.setattr(ask, "post", lambda body, timeout: Resp({"terms": [], "ntee": [], "formd": [], "wants": "unclear", "confidence": 0.2}))
    r = segments.answer("northside widget buyers", "", "", "both", 25)
    assert r["status"] == "ask" and r["nonprofits"] == [] and r["firms"] == [] and r["question"].startswith("What is “northside widget buyers”?")
    assert r["page_url"].startswith(segments.SITE_URL + "/segments?segment=northside+widget+buyers")
    monkeypatch.setattr(ask, "post", lambda body, timeout: Resp({"terms": ["food bank"], "ntee": ["K31"], "formd": [], "wants": "funders", "confidence": 0.9}))
    monkeypatch.setattr(segments, "orgs_in_codes", lambda codes, limit, state=None: [
        {"ein": str(i), "name": f"FOOD BANK {i}", "latest_total_revenue": 100 - i, "ntee_code": "K31", "city": "X", "state": "TX"} for i in range(5)])
    monkeypatch.setattr(queries, "search_orgs", lambda q, limit, state=None: [])
    r = segments.answer("food banks", "", "a hunger grant program", "nonprofits", 3)
    assert r["status"] == "ok" and [x["ein"] for x in r["nonprofits"]] == ["0", "1", "2"] and r["firms"] == [] and r["question"] is None
    assert r["reading"]["ntee"] == [{"code": "K31", "name": "Food Bank"}]

    from starlette.testclient import TestClient
    from app import db, main
    try:
        db.pool.open(wait=False)
    except Exception:  # noqa: BLE001
        pass
    c = TestClient(main.app)
    j = c.post("/api/segments", json={"segment": "food banks", "context": {"offering": "grants"}, "kinds": "nonprofits", "limit": 2},
               headers={"Origin": "https://vstrat.ai"})
    assert j.status_code == 200 and j.headers["access-control-allow-origin"] == "https://vstrat.ai"
    assert len(j.json()["nonprofits"]) == 2 and j.json()["page_url"].endswith("kinds=nonprofits&limit=2")
    assert c.post("/api/segments", json={"segment": ""}).status_code == 400
    assert c.options("/api/segments", headers={"Origin": "https://vstrat.ai"}).status_code == 204
    assert c.get("/api/segments?segment=food+banks&kinds=nonprofits").json()["status"] == "ok"
    html = c.get("/segments?segment=food+banks&kinds=nonprofits&limit=2").text
    assert "<h1>Segment: food banks</h1>" in html and "FOOD BANK 0" in html and "Latest revenue" in html
    head = html[html.index("<thead>"):html.index("</thead>")]
    assert head.index("Name") < head.index("Latest revenue") < head.index("NTEE") < head.index("Location")
    assert "This answer as JSON" in html and 'class="site-nav"' in html or "site-nav" in html
    assert "<h1>Segments</h1>" in c.get("/segments").text
    monkeypatch.setattr(ask, "post", lambda body, timeout: Resp({"terms": [], "ntee": [], "formd": [], "wants": "unclear", "confidence": 0.1}))
    html = c.get("/segments?segment=northside+widget+buyers").text
    assert "were found with confidence" in html and 'name="description"' in html and "Describe the organizations in it" in html


def test_the_contract_file_matches_the_code():
    doc = open("docs/vstrat-segments.md").read()
    assert "/api/segments" in doc and "page_url" in doc and "window.open(page_url" in doc
    for field in ("segment", "description", "context", "kinds", "limit", "state"):
        assert f"`{field}`" in doc
    assert "X-FURP-Key" in doc and '"status": "ask"' in doc
