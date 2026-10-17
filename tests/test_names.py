import pytest

from app.names import name_parts, normalize_name, normalize_org


@pytest.mark.parametrize("raw, norm", [
    ("SMITH, JOHN A. JR.", "john a smith jr"),
    ("Dr. Mar\u00eda O'Neil, PhD", "maria oneil"),
    ("JOHN SMITH (THRU 6/2024)", "john smith"),
    ("Michael F. Olenick", "michael f olenick"),
    ("YO-YO MA", "yo yo ma"),
    ("Jane Doe, MA", "jane doe"),
    ("Robert Jones III", "robert jones iii"),
    ("Jones, Robert, III", "robert jones iii"),
    ("JOHN SMITH JR MD", "john smith jr"),
    ("Sr. Mary Joseph", "mary joseph"),
    ("", ""),
])
def test_normalize_name(raw, norm):
    assert normalize_name(raw) == norm


def test_name_parts():
    assert name_parts("john a smith jr") == ("john", "a", "smith", "jr")
    assert name_parts("cher") == ("cher", "", "", "")


def test_normalize_org():
    assert normalize_org("St. Mary's Hospital, Inc.") == "st marys hospital inc"


def test_soundex_matches_reference_values():
    from app.queries import soundex
    assert [soundex(w) for w in ("Robert", "Rupert", "Tymczak", "Pfister", "Ashcraft", "Olenick", "Olenik")] == \
        ["R163", "R163", "T522", "P236", "A261", "O452", "O452"]


def test_ordered_prefix_regex():
    import re
    from app.queries import ordered_prefix_regex
    rx = re.compile(ordered_prefix_regex(["mich", "olen"]))
    assert rx.search("michael olenick") and rx.search("michael f olenick")
    assert not rx.search("olen michael brown") and not rx.search("mitch olson")
