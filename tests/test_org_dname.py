from app.names import distinctive
from app.queries import dname_pick

GENERIC = frozenset({"the", "of", "foundation", "family", "inc", "fund", "trust", "community"})


def test_distinctive_drops_generic_words():
    assert distinctive("the smith family foundation inc", GENERIC) == "smith"
    assert distinctive("community foundation of utah", GENERIC) == "utah"
    assert distinctive("the foundation of a", GENERIC) == ""          # nothing left: exact match only


def test_pick_needs_both_scores_and_no_exact_tie():
    a = {"ein": "1", "name": "A", "score": 0.9, "dscore": 0.8}
    assert dname_pick([a]) == a
    assert dname_pick([{**a, "score": 0.55}]) is None                 # whole name too far
    assert dname_pick([{**a, "dscore": 0.3}]) is None                 # shares only generic words ("hers" vs "49ers")
    assert dname_pick([a, {**a, "ein": "2"}]) is None                 # two organizations tie exactly
    assert dname_pick([a, {**a, "ein": "2", "score": 0.7}]) == a
