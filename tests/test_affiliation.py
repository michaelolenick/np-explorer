"""Person search across Form D and ADV, a person at an organization, and the result bands (owner, 2026-10-29)."""

import re

from app import affiliation, ask
from app.queries import variant_regex
from loader.fund_people import display_name


def test_org_words_drop_generic_words():
    assert affiliation.org_words("Mucker Capital") == ["mucker"]
    assert affiliation.org_words("Acme Ventures, LLC") == ["acme"]
    assert affiliation.org_words("Capital Partners") == ["capital", "partners"]   # nothing else left: keep them


def test_org_pattern_matches_word_starts_only():
    pat = affiliation._patterns(["mucker"])[0].replace(r"\m", r"\b")         # Postgres \m is a word start
    assert re.search(pat, "MuckerLab, LLC", re.I) and re.search(pat, "Mucker Early, LLC", re.I)
    assert not re.search(pat, "The J. M. Smucker Company", re.I)


def test_split_with_a_comma():
    assert affiliation.split("Tony Yang, Mucker Capital") == ("Tony Yang", "Mucker Capital")
    assert affiliation.split("Yang, Tony") is None            # last name first, not an organization
    assert affiliation.split("Tony Yang, Jr.") is None
    assert affiliation.split("Tony Yang, MD") is None


def test_variant_regex_same_name_with_more_words():
    rx = re.compile(variant_regex(["tony", "yang"]))
    for name in ("tony k yang", "tahua tony yang", "tony yang jr"):
        assert rx.search(name), name
    for name in ("tony yang smith", "tom young", "anthony yang"):
        assert not rx.search(name), name


def test_listed_at_read_without_the_model():
    assert ask.rule_parse("Is Tony Yang listed on any Form D or ADV for Mucker Capital?") == \
        {"intent": "listed_at", "name": "Tony Yang", "org": "Mucker Capital"}
    assert ask.rule_parse("Does Jane Doe appear on any Form D for the Sequoia fund?")["org"] == "Sequoia fund"
    assert ask.rule_parse("Who runs Mucker Capital?") is None
    assert ask.validate("listed_at", {"name": "Tony Yang"})["intent"] == "unknown"


def test_comma_name_is_a_plain_search():
    assert ask.is_plain_name("Tony Yang, Mucker Capital")
    assert ask.is_plain_name("Smith, John")


def test_answer_says_no_explicitly():
    r = {"person": "Tony Yang", "org": "Mucker", "hits": [], "orgs": [{"name": "Mucker V, L.P."}], "error": False}
    assert affiliation.answer_text(r) == "No filing lists Tony Yang at an organization matching “Mucker”."
    assert affiliation.answer_text(r, fund_only=True).startswith("No. No Form D or Form ADV filing lists Tony Yang")
    r["hits"] = [{"source": "Form ADV", "org": "MUCKER EARLY, LLC"}]
    assert affiliation.answer_text(r, fund_only=True).startswith("Yes. Tony Yang is listed on 1 Form D or Form ADV")


def test_adv_display_names():
    assert display_name("HSU, WILLIAM") == "William Hsu"
    assert display_name("SMITH, JOHN, A") == "John A Smith"
    assert display_name("Hamoui, Omar") == "Omar Hamoui"


def test_when():
    import datetime
    assert affiliation.when(2018, 2024) == "2018-2024"
    assert affiliation.when(datetime.date(2020, 4, 21), datetime.date(2020, 9, 1)) == "2020"
    assert affiliation.when(None, None) == ""
