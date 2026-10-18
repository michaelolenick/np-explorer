"""Event classification for the two event boards: category, related to mission, and the reason.
Deterministic keyword rules (app/event_class.py, docs/event-classification.md)."""

import pytest

from app.event_class import classify, in_board_b, is_gala


@pytest.mark.parametrize("desc, org, ntee, cat, related", [
    ("Annual Spring Gala", "Heart Association", "E30", "gala/party", False),
    ("Black & White Ball", "Childrens Museum", "A52", "gala/party", False),
    ("2025 Ellis County Dinner", "Ducks Unlimited Inc", "D20", "gala/party", False),
    ("Charity Golf Classic", "Childrens Hospital Foundation", "E22", "sports outing", False),
    ("The Big Egg Hunt", "Coexistence Story Inc", "D12", "hospitality", False),   # a party game, not hunting
    ("Junior Golf Tournament", "Northern California Golf Association", "N6A", "sports outing", True),   # sports org
    ("Bass Fishing Tournament", "Anglers Club of Texas", "C30", "sports outing", True),   # its own sport: program
    ("Pheasant Hunt", "Pheasants Forever Inc", "D20", "sports outing", None),             # wildlife org hunt: unclear
    ("Sporting Clays Shoot", "Ducks Unlimited Inc", "D20", "sports outing", None),                       # unclear
    ("Heart Walk", "American Heart Association", "G43", "walk/run/ride", False),     # health walk: fundraising
    ("Relay For Life", "American Cancer Society", "G30", "walk/run/ride", False),
    ("Boston Marathon", "Boston Athletic Association", "N60", "walk/run/ride", True),   # running org: program
    ("Charity 5K", "Youth Soccer League", "N64", "walk/run/ride", None),              # sports org, not running: unclear
    ("Gun Raffle", "Volunteer Fire Company", "M24", "raffle/auction", False),
    ("Wine Auction", "Napa Valley Vintners", "S41", "raffle/auction", False),
    ("Summer Concert Series", "City Symphony Orchestra", "A69", "hospitality", True),   # arts org: program
    ("Hospitality Suite", "Hospital Foundation", "E11", "hospitality", False),
    ("Event 2023", "Food Bank", "K31", "other", False),
])
def test_classification(desc, org, ntee, cat, related):
    got_cat, got_related, reason = classify(desc, org, ntee)
    assert (got_cat, got_related) == (cat, related), reason
    assert reason and (reason.startswith("unclear") == (related is None))


def test_reason_names_the_rule():
    assert classify("Golf Tournament", "Junior Golf Association", "N6A")[2] == \
        "NTEE N6A sports or recreation org, tournament treated as program"
    assert classify("Golf Tournament", "Hospital", None)[2] == "no NTEE code, not a sports organization: fundraising outing"


@pytest.mark.parametrize("desc, gala", [("Spring Gala", True), ("Benefit Dinner", True), ("Oyster Roast", True),
                                        ("Golf Classic", False), ("Baseball Night", False), ("Heart Walk", False)])
def test_board_a_party_words(desc, gala):
    assert is_gala(desc) is gala


def test_board_b_is_a_superset_of_a():
    events = [("Spring Gala", "Food Bank", "K31"), ("Golf Classic", "Food Bank", "K31"),
              ("Junior Golf Tournament", "Golf Association", "N6A"), ("Sporting Clays", "Ducks Unlimited", "D20")]
    for desc, org, ntee in events:
        related = classify(desc, org, ntee)[1]
        if is_gala(desc):
            assert in_board_b(related)                 # every gala is also on board B
    assert not in_board_b(True) and in_board_b(False) and in_board_b(None)   # unclear calls stay visible on B
