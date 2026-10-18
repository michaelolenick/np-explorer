"""Classify fundraising events from Schedule G Part II, deterministically (no AI).

Inputs: the event's own description, the organization's name and its NTEE code.
Outputs: a category, a "related to mission" flag (True, False, or None for unclear) and the
reason in plain words. The rules are written out in docs/event-classification.md; keep the
two in step.

Everything on Schedule G Part II is, by the form's own definition, a fundraising event, so
most events are not the charity's program. An event counts as the program only when the
organization's NTEE code or name says it is that kind of organization (a marathon run by a
running club, a concert by a music organization). Health-charity walks and runs are fundraising
events, not the program. Borderline calls are "unclear", not hidden.
"""

from __future__ import annotations

import re

CATEGORIES = ["gala/party", "raffle/auction", "sports outing", "walk/run/ride", "hospitality", "other"]

# Board A: the social, party-style events (the user's list plus close relatives).
GALA_WORDS = re.compile(
    r"\b(galas?|balls?|soir[eé]es?|part(?:y|ies)|dinners?|luncheons?|lunch|receptions?|benefits?|auctions?|"
    r"banquets?|cocktails?|brunch(?:es)?|f[eê]tes?|masquerades?|cabarets?|dances?|prom|tea|wine|tastings?|"
    r"oyster roast|crawfish|cookout|cook-?off|bbq|barbecue|fish fry|feast|casino night|derby party)\b", re.I)

RULES = [  # (category, pattern), first match wins
    ("raffle/auction", r"\b(raffles?|lotter(?:y|ies)|drawings?|bingo|casino|poker|50/50|sweepstakes|auctions?|"
                       r"calendar|split the pot)\b"),
    ("gala/party", GALA_WORDS.pattern),
    ("sports outing", r"\b(golf|tournaments?|classic|scramble|tee|fishing|fish|bass|anglers?|rodeo|shoot(?:out)?|"
                      r"clays|skeet|trap|hunts?|hunting|bowl(?:ing)?|tennis|pickleball|softball|baseball|"
                      r"basketball|volleyball|hockey|regatta|sailing|derby)\b"),
    ("walk/run/ride", r"\b(walks?|walkathon|runs?|5k|10k|half marathon|marathon|races?|relay|ride|rides|"
                      r"bike|biking|cycl(?:e|ing)|trek|climb|plunge|swim|triathlon|ruck|stair)\b"),
    ("hospitality", r"\b(hospitality|tailgates?|suites?|concerts?|festivals?|fairs?|shows?|tours?|cruises?|"
                    r"carnivals?|picnics?|socials?|mixers?|happy hour|parades?|exhibits?|performances?)\b"),
]
_RULES = [(c, re.compile(p, re.I)) for c, p in RULES]

SPORT_WORDS = re.compile(r"\b(golf|tennis|fishing|anglers?|bass|bowling|softball|baseball|basketball|volleyball|"
                         r"hockey|rodeo|sailing|yacht|soccer|athletic|sports?)\b", re.I)
RUN_ORG = re.compile(r"\b(run(?:ners?|ning)?|marathon|track|road runners|cycling|bicycle|bike|triathlon|"
                     r"swim(?:ming)?|athletic|sports?)\b", re.I)
HUNT_EVENT = re.compile(r"\b(hunts?|hunting|shoot(?:out)?|clays|skeet|trap|fishing|fish|bass|anglers?)\b", re.I)
ARTS_EVENT = re.compile(r"\b(concerts?|festivals?|shows?|performances?|exhibits?|tours?)\b", re.I)
FAIR_ORG = re.compile(r"\b(fair|exposition|agricultural|4-h|rodeo)\b", re.I)


# Not hunting: an egg, scavenger or treasure hunt is a party game.
GAME_HUNT = re.compile(r"\b(easter egg|egg|scavenger|treasure) hunts?\b", re.I)


def category(description: str | None) -> str:
    d = description or ""
    if GAME_HUNT.search(d):
        return "hospitality"
    return next((c for c, rx in _RULES if rx.search(d)), "other")


def is_gala(description: str | None) -> bool:
    """Board A: the description has a party-style word (a keyword match, shown as such)."""
    return bool(GALA_WORDS.search(description or ""))


def classify(description: str | None, org_name: str | None, ntee: str | None) -> tuple[str, bool | None, str]:
    """(category, related_to_mission, reason). related is None when the call is unclear."""
    cat = category(description)
    ntee = (ntee or "").upper()[:3]
    major = ntee[:1]
    name = org_name or ""
    code = f"NTEE {ntee}" if ntee else "no NTEE code"
    if cat == "sports outing":
        if major == "N":
            return cat, True, f"{code} sports or recreation org, tournament treated as program"
        if SPORT_WORDS.search(name) and SPORT_WORDS.search(description or ""):
            return cat, True, "organization's name is a sport the event is, treated as program"
        if HUNT_EVENT.search(description or "") and major in ("C", "D"):
            return cat, None, f"unclear: {code} conservation or wildlife org running a hunting, fishing or shooting event"
        return cat, False, f"{code}, not a sports organization: fundraising outing"
    if cat == "walk/run/ride":
        if major == "N" and RUN_ORG.search(name):
            return cat, True, f"{code} running, cycling or sports org, race treated as program"
        if major == "N":
            return cat, None, f"unclear: {code} sports org; the race may be its program"
        return cat, False, f"{code}: fundraising walk, run or ride, not the program"
    if cat == "hospitality":
        if major == "A" and ARTS_EVENT.search(description or ""):
            return cat, True, f"{code} arts or culture org, performance or exhibit treated as program"
        if FAIR_ORG.search(name) and re.search(r"\b(fairs?|rodeo|exposition)\b", description or "", re.I):
            return cat, True, "organization runs a fair or rodeo; the event is treated as program"
        return cat, False, f"{code}: fundraising hospitality or entertainment event"
    if cat in ("gala/party", "raffle/auction"):
        return cat, False, f"{code}: {cat} fundraising event"
    return cat, False, "listed as a fundraising event on Schedule G; the description says no more"


def in_board_b(related: bool | None) -> bool:
    """Board B: every event that is not the charity's program, including unclear calls (flagged)."""
    return related is not True
