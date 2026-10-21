"""Alternate names (loader/alt_names.py, app/aliases.alt_matches): sources, verification, and search behaviour."""

import pytest

from loader import alt_names as A


def test_sources():
    assert A.acronym("URBAN LAND INSTITUTE") == "ULI"
    assert A.acronym("THE FORD FOUNDATION") is None                      # too few significant words
    assert A.website_stem("WWW.ULI.ORG") == "uli" and A.website_stem("https://www.facebook.com/x") is None
    assert A.website_stem("[www.broken") is None
    assert A.dba_parts("ULI - THE URBAN LAND INSTITUTE") == ["ULI", "THE URBAN LAND INSTITUTE"]
    assert A.dba_parts("C/O SMITH & JONES LLP") == []


def test_model_suggestions_must_be_supported_by_the_organizations_own_data():
    assert A.verified("ULI", "URBAN LAND INSTITUTE", None, None)
    assert A.verified("ASPCA", "AMERICAN SOCIETY FOR THE PREVENTION OF CRUELTY TO ANIMALS", None, None)
    assert A.verified("Red Cross", "AMERICAN NATIONAL RED CROSS", None, None)
    assert A.verified("Smithsonian", "SMITHSONIAN INSTITUTION", None, "si.edu") is False
    assert not A.verified("XYZ", "URBAN LAND INSTITUTE", None, None)


def test_uli_search_finds_the_urban_land_institute_first():
    from app import aliases, db
    db.pool.open(wait=True)
    m = aliases.alt_matches("ULI")
    if not m:
        pytest.skip("alternate names not built")
    assert m["orgs"][0]["ein"] == "530159845" and m["alias"].upper() == "ULI"
    c = aliases.alt_matches("ULI Austin")
    assert c and c["chapter"] == "Austin" and c["orgs"][0]["ein"] == "530159845"
