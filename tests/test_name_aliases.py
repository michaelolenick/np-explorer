"""Abbreviations and full names (loader/name_aliases.py, app/aliases.py; owner, 2026-10-30)."""

from app import aliases, queries
from loader import name_aliases
from loader.recalls import core


def test_initials_skip_joiners():
    assert name_aliases.initials("international business machines") == "ibm"
    assert name_aliases.initials("american society for the prevention of cruelty to animals") == "aspca"


def test_pair_ok_needs_initials_of_two_or_more_words():
    assert name_aliases.pair_ok("ibm", core("International Business Machines Corporation"))
    assert name_aliases.pair_ok("ge", core("General Electric Company"))
    assert not name_aliases.pair_ok("ibm", "informa")                  # one word
    assert not name_aliases.pair_ok("ibm", "general electric")         # other initials
    assert not name_aliases.pair_ok("abcdefg", "a b c d e f g")        # longer than six letters


def test_manual_list_has_the_owners_examples_and_no_duplicates():
    pairs = {(core(s), core(lg)) for s, lg in name_aliases.MANUAL}
    for s, lg in (("IBM", "International Business Machines"), ("3M", "Minnesota Mining and Manufacturing"),
                  ("GE", "General Electric"), ("HP", "Hewlett-Packard")):
        assert (core(s), core(lg)) in pairs
    assert len(pairs) == len(name_aliases.MANUAL)
    assert all(s and lg for s, lg in pairs)


def test_registry_key_matches_registry_names():
    assert aliases.name_key("3M Company") == aliases.name_key("3m") == "3m"
    assert aliases.name_key("Hewlett-Packard Co.") == "hewlett packard"


def test_short_names_skip_trigram_neighbours():
    assert queries._short("GE") and queries._short("3M") and queries._short("h.p.")
    assert not queries._short("IBM")
