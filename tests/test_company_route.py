"""Company or nonprofit routing (app/company_route.py) and annual-report support in the S-1 profile."""
import datetime as dt

import pytest

from app import company_route as C
from app import s1profile as S


@pytest.mark.parametrize("q,topic,entity", [
    ("who are competitors to avery dennison?", "competitors", "avery dennison"),
    ("avery dennison risks", "risks", "avery dennison"),
    ("competitors of jersey mike's", "competitors", "jersey mike's"),
    ("nike competitors", "competitors", "nike"),
    ("who competes with nike", "competitors", "nike"),
    ("nike swot", "strategy", "nike"),
])
def test_company_questions(q, topic, entity):
    r = C.question(q)
    assert r and r["topic"] == topic and r["entity"].lower() == entity


@pytest.mark.parametrize("q", ["avery dennison foundation grants", "avery dennison", "ford foundation risks", "top paid ceos", ""])
def test_not_company_questions(q):
    assert C.question(q) is None


def test_key_drops_suffixes():
    assert C.key("AVERY DENNISON Corp") == "avery dennison"
    assert C.key("Jersey Mike's Subs, Inc.") == "jersey mikes subs"


def _co(name, cik="1", how="exact"):
    return {"cik": cik, "name": name, "ticker": "X", "how": how}


def test_clear_intent_goes_to_the_company(monkeypatch):
    monkeypatch.setattr(C, "match_company", lambda n, fuzzy=True: _co("Avery Dennison Corp", "8818"))
    r = C.resolve("who are competitors to avery dennison?")
    assert r["go"].startswith("/s1/8818?topic=competitors")


def test_nonprofit_words_stay_and_offer_the_company(monkeypatch):
    monkeypatch.setattr(C, "match_company", lambda n, fuzzy=True: _co("Avery Dennison Corp", "8818"))
    r = C.resolve("avery dennison foundation grants")
    assert "go" not in r and "choose" not in r
    assert "public company" in r["alt"]["text"] and r["alt"]["url"].startswith("/s1/8818")


def test_bare_name_matching_both_asks(monkeypatch):
    monkeypatch.setattr(C, "match_company", lambda n, fuzzy=True: _co("FORD MOTOR CO", "37996", "prefix"))
    monkeypatch.setattr(C, "nonprofit_options", lambda e, limit=3, strict=False: [{"kind": "foundation", "name": "FORD FOUNDATION",
                                                                                      "ein": "1", "state": "NY", "revenue": 1}])
    monkeypatch.setattr(C, "school_options", lambda e, limit=2: [])
    r = C.resolve("ford")
    assert r["choose"]["company"]["name"] == "FORD MOTOR CO" and r["choose"]["nonprofits"]


def test_bare_name_with_one_reading_does_not_ask(monkeypatch):
    monkeypatch.setattr(C, "match_company", lambda n, fuzzy=True: None)
    monkeypatch.setattr(C, "nonprofit_options", lambda e, limit=3, strict=False: [])
    monkeypatch.setattr(C, "school_options", lambda e, limit=2: [])
    assert C.resolve("zzzz widgets") is None


def test_annual_report_preferred_when_the_s1_is_old():
    d = dt.date.today()
    fl = [{"accession": "a", "form": "10-K", "filed": d - dt.timedelta(days=30)},
          {"accession": "b", "form": "S-1/A", "filed": d - dt.timedelta(days=60)}]
    assert S.preferred(fl)[0]["accession"] == "a"
    fl2 = [{"accession": "b", "form": "S-1/A", "filed": d - dt.timedelta(days=30)},
           {"accession": "a", "form": "10-K", "filed": d - dt.timedelta(days=400)}]
    assert S.preferred(fl2)[0]["accession"] == "b"
    fl3 = [{"accession": "b", "form": "S-1/A", "filed": d - dt.timedelta(days=500)},
           {"accession": "a", "form": "10-K", "filed": d - dt.timedelta(days=400)}]
    assert S.preferred(fl3)[0]["accession"] == "a"


def test_item_prefix_is_stripped():
    assert S.ITEM_PREFIX.sub("", "Item 1A. Risk Factors") == "Risk Factors"
    assert S.ITEM_PREFIX.sub("", "ITEM 1B - Unresolved Staff Comments") == "Unresolved Staff Comments"


def test_common_surname_never_opens_the_chooser(monkeypatch):
    monkeypatch.setattr(C, "match_company", lambda n, fuzzy=True: _co("SMITH MICRO SOFTWARE", "1", "prefix"))
    monkeypatch.setattr(C, "nonprofit_options", lambda e, limit=3, strict=False: [{"kind": "foundation", "name": "SMITH FOUNDATION",
                                                                                      "ein": "1", "state": "NY", "revenue": 1}])
    monkeypatch.setattr(C, "school_options", lambda e, limit=2: [])
    assert C.resolve("smith") is None


@pytest.fixture
def majors(monkeypatch):
    import time
    def m(cik, name, ticker, *aliases):
        return {"cik": cik, "name": name, "ticker": ticker, "how": "exact", "major": True, "akeys": [a.split() for a in aliases]}
    rows = [m("56873", "Kroger", "KR", "kroger"), m("37996", "Ford Motor Company", "F", "ford motor"), m("104169", "Walmart", "WMT", "walmart"),
            m("27419", "Target Corporation", "TGT", "target")]
    alias = {a: r for r in rows for a in (" ".join(x) for x in r["akeys"])}
    monkeypatch.setitem(C._major, "t", time.time() + 1e6)
    monkeypatch.setitem(C._major, "rows", rows)
    monkeypatch.setitem(C._major, "alias", alias)
    monkeypatch.setitem(C._major, "ticker", {r["ticker"].lower(): r for r in rows})
    monkeypatch.setattr(C, "nonprofit_options", lambda e, limit=3, strict=False: [])
    monkeypatch.setattr(C, "school_options", lambda e, limit=2: [])
    return rows


@pytest.mark.parametrize("q,cik,topic", [
    ("kroger, the grocery store - tell me competitors", "56873", "competitors"),
    ("kroger competitors", "56873", "competitors"),
    ("KR risks", "56873", "risks"),
    ("walmart competitors", "104169", "competitors"),
    ("ford competitors", "37996", "competitors"),
    ("target competitors", "27419", "competitors"),
    ("kroger stock", "56873", ""),
    ("kroger earnings", "56873", ""),
])
def test_major_companies_are_recognized(majors, q, cik, topic):
    r = C.resolve(q)
    assert r and r["go"].startswith(f"/s1/{cik}?") and (f"topic={topic}" in r["go"])


def test_lowercase_ticker_is_not_a_ticker(majors):
    assert C.major_match("kr", prefix=False) is None


def test_foundation_words_keep_the_nonprofit(majors):
    r = C.resolve("kroger foundation grants")
    assert "go" not in r and r["alt"]["url"].startswith("/s1/56873")
    r = C.resolve("ford foundation")
    assert "go" not in r and r["alt"]["url"].startswith("/s1/37996")


def test_other_intents_are_not_taken(majors):
    assert C.question("kroger insider stock sales") is None


def test_risk_items_from_short_caps_headings():
    blocks = [{"t": "Risk Factors", "bold": True, "lead": "", "id": ""}]
    for h, body in (("COMPETITIVE ENVIRONMENT", "Competition from online retailers and mass merchants is intense and growing every year, " * 3),
                    ("PRODUCT SAFETY", "Customers count on us to provide safe food, drugs and other merchandise, and recalls hurt us. " * 3)):
        blocks += [{"t": h, "bold": True, "lead": "", "id": ""}, {"t": body, "bold": False, "lead": "", "id": ""}]
    blocks.insert(3, {"t": "Item 1A. Risk Factors (Continued)", "bold": True, "lead": "", "id": ""})
    items = S.risk_items(blocks, 0, len(blocks))
    assert [i["title"] for i in items] == ["Competitive environment", "Product safety"]
