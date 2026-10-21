"""Search interpretation: known short names go to the model, and an organization search never stops at nothing
when something close exists (app/ask.org_cascade). The search test set itself runs against the real database
before each deploy (scripts/search_eval.py); here only its shape is checked."""

import pathlib

import yaml

from app import aliases, ask, queries

ROOT = pathlib.Path(__file__).resolve().parents[1]
ULI = {"ein": "530159845", "name": "URBAN LAND INSTITUTE", "name_norm": "urban land institute", "city": "WASHINGTON",
       "state": "DC", "latest_total_revenue": 92_328_399, "latest_filing_year": 2024}


def test_known_names_reach_the_model(monkeypatch):
    monkeypatch.setattr(aliases, "hints", lambda q: [{"text": "uli", "orgs": [
        {"name": "URBAN LAND INSTITUTE", "city": "WASHINGTON", "state": "DC", "rev": 92328399}]}])
    text = ask._hint_text("uli in austin")
    assert "KNOWN NAMES" in text and '"uli": URBAN LAND INSTITUTE (Washington, DC; revenue $92,328,399)' in text
    monkeypatch.setattr(aliases, "hints", lambda q: [])
    assert ask._hint_text("who runs the ford foundation") == ""


def test_chapter_with_no_filer_shows_the_national_organization(monkeypatch):
    monkeypatch.setattr(aliases, "orgs_for", lambda name, limit=5: [ULI])
    monkeypatch.setattr(queries, "search_orgs", lambda q, limit=10, state=None, city=None, **k: [] if city else [ULI])
    r = ask.org_cascade("Urban Land Institute", "Austin", "TX")
    assert r["step"] == "b" and r["rows"][0]["ein"] == "530159845"
    assert r["note"] == ("No Urban Land Institute filer in Austin, TX. Showing the national Urban Land Institute "
                         "(Washington, DC); local chapters and councils usually file under it.")
    assert "—" not in r["note"]


def test_a_filer_in_the_place_is_shown_without_a_note(monkeypatch):
    local = {**ULI, "ein": "741193464", "name": "YOUNG MENS CHRISTIAN ASSOCIATION",
             "name_norm": "young mens christian association", "city": "AUSTIN", "state": "TX"}
    monkeypatch.setattr(aliases, "orgs_for", lambda name, limit=5: [])
    monkeypatch.setattr(queries, "search_orgs", lambda q, limit=10, state=None, city=None, **k: [local])
    r = ask.org_cascade("Young Mens Christian Association", "Austin", "TX")
    assert (r["step"], r["note"], r["rows"][0]["ein"]) == ("a", None, "741193464")


def test_misspelling_falls_back_to_the_closest_names(monkeypatch):
    msk = {**ULI, "ein": "912154267", "name": "MEMORIAL SLOAN-KETTERING CANCER CENTER",
           "name_norm": "memorial sloan kettering cancer center", "city": "NEW YORK", "state": "NY"}
    monkeypatch.setattr(aliases, "orgs_for", lambda name, limit=5: [])
    monkeypatch.setattr(queries, "search_orgs", lambda *a, **k: [])
    monkeypatch.setattr(queries, "fuzzy_orgs", lambda q, limit=10, state=None, city=None: [msk])
    r = ask.org_cascade("memorial sloan kettring", None, None)
    assert r["step"] == "d" and r["rows"][0]["ein"] == "912154267"
    assert r["note"] == "Nothing is filed under Memorial Sloan Kettring. Showing the closest names."


def test_search_test_set_shape():
    cases = yaml.safe_load((ROOT / "tests" / "search_cases.yml").read_text())
    assert len(cases) >= 50
    assert {"acronym", "chapter", "misspelling", "question"} <= {c["kind"] for c in cases}
    for c in cases:
        assert c["q"].strip() and (c.get("ein") or c.get("name")), c
    for q in ("uli", "aclu", "aarp", "ymca", "npr", "msk", "uli in austin"):
        assert q in {c["q"] for c in cases}
