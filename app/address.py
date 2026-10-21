"""Normalized names and street addresses, for matching vendors (990 contractor lists: name and address, no
EIN) to filing organizations, and for collapsing spelling variants of one address on a vendor page.

An address key is (zip5, street number, street name core): "300 FUNSTON AVENUE", "300 Funston Ave" and
"300 funstun ave" in 94118 or 94118-2116 all reduce to ("94118", "300", "funston"/"funstun"), and
same_street() treats cores one or two letters apart as the same street.
"""

from __future__ import annotations

import re
from collections import Counter

# Street types and directions: dropped from the core, so "Funston Ave" and "Funston Avenue" compare equal.
SUFFIXES = {
    "avenue", "ave", "av", "street", "st", "str", "road", "rd", "boulevard", "blvd", "drive", "dr", "lane", "ln",
    "court", "ct", "place", "pl", "parkway", "pkwy", "highway", "hwy", "way", "wy", "circle", "cir", "terrace",
    "ter", "square", "sq", "trail", "trl", "plaza", "plz", "suite", "center", "ctr", "turnpike", "tpke", "pike",
    "expressway", "expy", "freeway", "fwy", "route", "rte", "alley", "aly",
}
DIRECTIONS = {"n": "n", "north": "n", "s": "s", "south": "s", "e": "e", "east": "e", "w": "w", "west": "w",
              "ne": "ne", "northeast": "ne", "nw": "nw", "northwest": "nw", "se": "se", "southeast": "se",
              "sw": "sw", "southwest": "sw", "so": "s", "no": "n"}
# A unit designator ends the street part: "300 Funston Ave Suite 2" -> "300 Funston Ave".
UNIT = {"suite", "ste", "unit", "apt", "apartment", "fl", "floor", "flr", "rm", "room", "bldg", "building",
        "dept", "department", "po", "p", "box", "pmb", "mailstop", "ms", "attn", "suit", "tower", "lbby", "lobby"}
# Long street types, also caught when misspelled by one letter ("Avenye").
LONG_SUFFIXES = ("avenue", "street", "boulevard", "parkway", "highway", "terrace", "circle")
ORDINALS = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th",
            "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th", "eleventh": "11th",
            "twelfth": "12th"}
NAME_DROP = {"the", "inc", "incorporated", "llc", "corp", "corporation", "co", "company", "ltd", "limited", "pc",
             "pllc", "lp", "llp", "a", "an", "dba"}

_BOX = re.compile(r"\b(?:p\s*o|post\s+office)?\s*box\s*#?\s*(\d+)", re.I)


def zip5(z: str | None) -> str:
    d = re.sub(r"\D", "", z or "")
    return d[:5] if len(d) >= 5 else ""


_CARE_OF = re.compile(r"^\s*(c\s*/\s*o\b|co\s|%|care\s+of\b|attn\b|in\s+care\b)", re.I)


def is_care_of(s: str | None) -> bool:
    """A DBA or name line that is really a mailing instruction ("C/O Harrison & Held LLP", "% Bank")."""
    return bool(s and _CARE_OF.match(s))


def name_core(name: str | None) -> str:
    """Lowercase words without punctuation, "&" as "and", legal-form words dropped: "The Internet Archive, Inc."
    -> "internet archive"."""
    s = (name or "").lower().replace("&", " and ")
    words = re.sub(r"[^a-z0-9]+", " ", s).split()
    return " ".join(w for w in words if w not in NAME_DROP)


def street_parts(street: str | None) -> tuple[str, str]:
    """(number, core) of a street line. A PO box is ("box N", "po box"); no number gives ("", core)."""
    s = (street or "").lower()
    m = _BOX.search(s)
    if m and not re.match(r"\s*\d", s):
        return "box " + m.group(1), "po box"
    words = re.sub(r"[^a-z0-9]+", " ", s.replace("#", " # ")).split()
    if not words:
        return "", ""
    num = ""
    if re.fullmatch(r"\d+[a-z]?", words[0]):
        num, words = re.match(r"\d+", words[0]).group(0), words[1:]
    out = []
    for i, w in enumerate(words):
        if out and (w in UNIT or w == "#" or (w == "no" and i + 1 < len(words) and words[i + 1][:1].isdigit())):
            break
        if w in SUFFIXES or w in DIRECTIONS or (len(w) >= 6 and any(_distance(w, x, 1) <= 1 for x in LONG_SUFFIXES)):
            continue
        out.append(ORDINALS.get(w, w))
    # A bare unit number after the street name: "515 Post Oak Blvd 1000" -> "post oak".
    while len(out) > 1 and out[-1].isdigit():
        out.pop()
    return num, " ".join(out)


def key(street: str | None, z: str | None) -> tuple[str, str, str] | None:
    """(zip5, number, core), or None when the address lacks a zip, a number or a street name."""
    num, core = street_parts(street)
    z5 = zip5(z)
    if not (z5 and num and core):
        return None
    return z5, num, core


def _distance(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance, stopping early once it passes cap."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def same_street(a: str, b: str) -> bool:
    """Street cores that are equal, or a typo apart: one letter for names under 8 letters, two from 8 up
    ("funston" / "funson" / "funstun"). Numbered streets ("5th") must be equal."""
    if a == b:
        return True
    if not a or not b or re.search(r"\d", a + b):
        return False
    n = min(len(a), len(b))
    return n >= 4 and _distance(a, b, 2) <= (1 if n < 8 else 2)


def same_address(a: tuple | None, b: tuple | None) -> bool:
    return bool(a and b and a[0] == b[0] and a[1] == b[1] and same_street(a[2], b[2]))


def collapse(addresses: list[tuple[str, str, str, str]], counts: Counter | None = None) -> list[dict]:
    """Group (street, city, state, zip) variants of one address. Each group: "shown" (the most common spelling,
    ties to the longest zip), "variants" (every original, most common first). Addresses without a key stay
    alone. Groups keep the order of their most common member."""
    counts = counts or Counter()
    groups: list[dict] = []
    for a in sorted(addresses, key=lambda a: (-counts[a], -len(a[3] or ""), a)):
        k = key(a[0], a[3])
        for g in groups:
            if k and same_address(k, g["key"]):
                g["variants"].append(a)
                break
        else:
            groups.append({"key": k, "shown": a, "variants": [a]})
    return groups
