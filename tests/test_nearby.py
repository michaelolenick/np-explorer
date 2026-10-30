"""Nearby + Similar (app/nearby.py; owner, 2026-10-29): blending, the one-line reasons, place parsing."""

from app import nearby


def test_blend_scales_each_signal_to_its_best_match():
    words = {"a": {"score": 10}, "b": {"score": 5}}
    links = {"b": {"score": 2}, "c": {"score": 1}}
    ranked = dict((e, s) for s, e in nearby.blend(words, links))
    assert ranked["b"] > ranked["a"] > ranked["c"]          # b: half the words and all the links
    assert abs(ranked["a"] - nearby.WORDS_WEIGHT) < 1e-9


def test_blend_with_one_signal_uses_it_alone():
    ranked = nearby.blend({"a": {"score": 4}, "b": {"score": 2}}, {})
    assert ranked[0] == (1.0, "a") and ranked[1] == (0.5, "b")


def test_why_tags_words_and_board_fuzzy_and_ein_links_exact():
    w = {"shared": ["bird", "flyway"]}
    lk = {"funders": ["111111111", "222222222", "333333333", "444444444"], "grantees": None, "board": ["7"]}
    parts = nearby.why(w, lk, {"bird": "birds"}, {"111111111": "PACKARD"}, {7: "Jane Roe"})
    assert parts[0] == {"label": "Words", "text": "birds, flyway", "fuzzy": True}
    assert parts[1]["label"] == "Funders in common (4)" and not parts[1]["fuzzy"]
    assert parts[1]["text"] == "PACKARD, 222222222, 333333333 and 1 more"
    assert parts[2] == {"label": "Board members in common (1)", "text": "Jane Roe", "fuzzy": True}
    assert not any(p["fuzzy"] for p in nearby.why(None, {**lk, "board": None}, {}, {}, {}))


def test_place_patterns():
    assert nearby._ZIP.match("10027").group(1) == "10027"
    assert nearby._ZIP.match("10027-1234").group(1) == "10027"
    assert nearby._EIN.match("13-1624102").groups() == ("13", "1624102")
    assert nearby._CITY.match("Oakland, CA").groups() == ("Oakland", "CA")
    assert nearby._CITY.match("Saint Louis MO").groups() == ("Saint Louis", "MO")
    assert not nearby._ZIP.match("1002")
