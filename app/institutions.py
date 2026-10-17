"""Telling institutions (banks, trust companies, firms) apart from people.

Form 990s list institutional trustees in the same officer tables as people,
so "Bank of America N A" shows up as one "person" on thousands of returns.
The IRS's own institutional-trustee checkbox is unreliable (filers tick it for
individuals), so names decide:

- a STRONG word (N.A., trust company, LLC, Inc, foundation, ...) always marks
  an institution;
- a WEAK word (church, bank, trust, alliance, ...) does too, unless the name
  is short (three words or fewer), has only one such word, and starts with a
  common given name: "William Church" and "Wade Alliance" are people; "First
  Presbyterian Church", "Frost Bank Trustee" and "Noel Memorial Methodist
  Church" are not.

Given names come from the data (first words common among names with no
institution words); see migration 0005 and loader/cluster.py. The SQL function
np_institution() is generated from these same lists.
"""

from __future__ import annotations

import re

STRONG = [
    "national association", "national assn", "natl assn", "fsb",
    "bancorp", "banc", "banking", "bank of", "trust company", "trust co", "tr co", "trust services",
    "trust department", "trust dept", "fiduciary", "wealth management", "asset management",
    "investment management", "capital management", "wells fargo", "jpmorgan", "j p morgan", "jp morgan",
    "bny mellon", "northern trust", "inc", "incorporated", "llc", "l l c", "ltd", "corp", "corporation",
    "lp", "llp", "plc", "foundation", "association", "assn", "university", "hospital", "diocese",
    "ministries", "city of", "state of", "estate of", "cpas", "federation",
]
WEAK = [
    "bank", "church", "parish", "county", "council", "committee", "institute", "college", "society",
    "alliance", "partnership", "partners", "associates", "services", "consulting", "group", "holdings",
    "enterprises", "trust", "trusts", "fund", "department", "company",
]
# "N A" / "NA" (national association) counts only at the end of a name that also
# has a bank-like word: "Na" is a surname and "n a" can be middle initials.
_NA_CONTEXT = r"(\w*bank|trust|mellon|chase|morgan|bancorp)"
# First words common in institution names that must never count as given names.
NOT_GIVEN = [
    "first", "state", "national", "american", "united", "citizens", "community", "peoples", "people",
    "farmers", "union", "central", "security", "city", "county", "the", "us", "new", "north", "south",
    "east", "west", "mid", "great", "old", "bank", "trust", "saint", "st", "mount", "mt", "merchants",
    "commerce", "commercial", "savings", "home", "heritage", "legacy", "pacific", "atlantic", "alta",
    "fidelity", "liberty", "pioneer", "premier", "capital", "summit", "frontier", "midwest", "western",
    "eastern", "northern", "southern", "noel",
]
LONG_NAME_WORDS = 4   # weak-word names this long are institutions even after a given name
_NA_TAIL = r"\s(n\sa|na)$"


def _alternation(words) -> str:
    return "|".join(sorted((w.replace(" ", r"\s") for w in words), key=len, reverse=True))


def sql_strong_regex() -> str:
    return rf"\y({_alternation(STRONG)})\y|\y{_NA_CONTEXT}\y.*{_NA_TAIL}"


def sql_weak_regex() -> str:
    return rf"\y({_alternation(WEAK)})\y"


_STRONG_RE = re.compile(rf"\b({_alternation(STRONG)})\b|\b{_NA_CONTEXT}\b.*{_NA_TAIL}")
_WEAK_RE = re.compile(rf"\b({_alternation(WEAK)})\b")


def is_institution(name_norm: str, given_names: set[str]) -> bool:
    """Python twin of the np_institution() SQL function, for tests."""
    if _STRONG_RE.search(name_norm):
        return True
    weak = {m.group(1) for m in _WEAK_RE.finditer(name_norm)}
    if not weak:
        return False
    words = name_norm.split(" ")
    return len(weak) >= 2 or len(words) >= LONG_NAME_WORDS or words[0] not in given_names


def _q(sql: str) -> str:
    return sql.replace("'", "''")


def function_sql() -> str:
    """CREATE OR REPLACE for np_institution(name_norm)."""
    strong, weak = _q(sql_strong_regex()), _q(sql_weak_regex())
    return f"""
    CREATE OR REPLACE FUNCTION np_institution(n text) RETURNS boolean LANGUAGE sql STABLE PARALLEL SAFE AS $$
        SELECT n ~ '{strong}'
            OR (n ~ '{weak}' AND (
                (SELECT count(DISTINCT m[1]) FROM regexp_matches(n, '{weak}', 'g') m) >= 2
                OR array_length(string_to_array(n, ' '), 1) >= {LONG_NAME_WORDS}
                OR NOT EXISTS (SELECT 1 FROM given_names g WHERE g.name = split_part(n, ' ', 1))))
    $$;
    """


def given_names_sql(min_count: int = 100) -> str:
    """Refill given_names: first words common among names with no institution words."""
    strong, weak = _q(sql_strong_regex()), _q(sql_weak_regex())
    excluded = ", ".join(f"'{w}'" for w in NOT_GIVEN)
    return f"""
    TRUNCATE given_names;
    INSERT INTO given_names
    SELECT first_name FROM person_clusters
    WHERE length(first_name) > 1 AND first_name NOT IN ({excluded})
      AND name_norm !~ '{strong}' AND name_norm !~ '{weak}'
    GROUP BY first_name HAVING count(*) >= {min_count};
    """


def candidate_regex() -> str:
    """Names that could be institutions at all (cheap pre-filter before np_institution)."""
    return f"({sql_strong_regex()})|({sql_weak_regex()})"


# --- One record per institution ------------------------------------------------
# The same bank is listed as "Bank Of America", "Bank Of America N A",
# "Bank of America NA Trustee"... Stripping these role and legal suffixes (and a
# leading "the") gives the key institution records are merged on.
KEY_SUFFIXES = [
    "n a", "na", "national association", "national assn", "natl assn", "trustee", "trustees", "ttee",
    "ttees", "tte", "co trustee", "cotrustee", "as trustee", "corporate trustee", "corp trustee",
    "agent", "as agent", "fbo", "former",
]
# Spellings of the same big names that differ only in spacing.
KEY_SPELLINGS = {
    "j p morgan": "jpmorgan", "jp morgan": "jpmorgan", "u s bank": "us bank", "key bank": "keybank",
    "b n y mellon": "bny mellon", "bank of new york mellon": "bny mellon", "m and t bank": "m t bank",
}
# Big trustee banks: any record whose name starts with the brand is that bank
# ("Wells Fargo Bank Texas N A", "Wells Fargo Advisors" -> "wells fargo").
# People listed "c/o" a bank ("Gary Worsham Wells Fargo") don't start with it.
KEY_BRANDS = [
    "wells fargo", "bank of america", "jpmorgan chase", "pnc bank", "us bank", "bny mellon", "northern trust",
    "truist bank", "keybank", "citibank", "fifth third bank", "regions bank", "comerica bank", "bmo harris bank",
    "td bank", "huntington national bank", "m t bank", "charles schwab", "morgan stanley",
]
_BRAND_RE = re.compile(rf"^({_alternation(KEY_BRANDS)})(\s|$)")
_SUFFIX_ALT = _alternation(KEY_SUFFIXES)
_KEY_TAIL_RE = re.compile(rf"(\s+({_SUFFIX_ALT}))+$")


def institution_key(name_norm: str) -> str:
    """Python twin of np_institution_key(): "bank of america n a trustee" -> "bank of america"."""
    key = re.sub(r"^the\s+", "", name_norm)
    for spelling, canonical in KEY_SPELLINGS.items():
        key = re.sub(rf"\b{spelling}\b", canonical, key)
    brand = _BRAND_RE.match(key)
    if brand:
        return brand.group(1)
    stripped = _KEY_TAIL_RE.sub("", key)
    return stripped or key


def key_function_sql() -> str:
    tail = _q(rf"(\s+({_SUFFIX_ALT}))+$")
    base = "regexp_replace(n, '^the\\s+', '')"
    for spelling, canonical in KEY_SPELLINGS.items():
        base = f"regexp_replace({base}, '\\y{spelling}\\y', '{canonical}', 'g')"
    brands = _q(rf"^({_alternation(KEY_BRANDS)})(\s|$)")
    return f"""
    CREATE OR REPLACE FUNCTION np_institution_key(n text) RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
        SELECT CASE WHEN {base} ~ '{brands}' THEN substring({base} from '{brands}')
                    ELSE coalesce(nullif(regexp_replace({base}, '{tail}', ''), ''), {base}) END
    $$;
    """


# --- People listed "care of" a bank ---------------------------------------------
# Filers write individuals as "Kristin Cupillari Co Wells Fargo", "John K Tran -
# Wells Fargo Bank", "Wells Fargo Bank - Dominic Clemente". The person's part is
# their name; the bank is only their address.
_CARE_BRANDS = sorted(set(KEY_BRANDS) | {"bank of america", "wells fargo", "jpmorgan"}, key=len, reverse=True)
_BRAND_ALT = "|".join(b.replace(" ", r"\s") for b in _CARE_BRANDS)
_BRAND_TAIL = r"(?:\s(?:bank|bk|b|na|n\sa|advisors?|foundation|financial|private\sbank|trust|co))*"
_CARE_WORDS = {"co", "c", "o", "care", "of", "attn", "at", "for", "via", "fbo", "tr", "ttee", "trustee"}
_TITLE_WORDS = {"pres", "president", "vp", "svp", "evp", "ceo", "cfo", "coo", "market", "regional", "manager",
                "mgr", "officer", "advisor", "esq", "trust", "sr", "vice", "director", "dir", "rep", "cha", "chas"}
# Words that never appear in a person's name here, and brokerages that read like names.
_NOT_PERSON_WORDS = {"dept", "department", "charitable", "comp", "bank", "bankna", "bk", "nat", "ass", "wm",
                     "trust", "trustee", "services", "group", "fund", "smit", "bar", "chase"}
_NOT_PERSON_WORDS |= {"see", "stmt", "statement", "note", "schedule", "sched", "attached", "mac", "na", "n",
                      "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
                      "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas",
                      "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota",
                      "mississippi", "missouri", "montana", "nebraska", "nevada", "ohio", "oklahoma", "oregon",
                      "pennsylvania", "tennessee", "texas", "utah", "vermont", "virginia", "washington",
                      "wisconsin", "wyoming"}
_FIRM_NAMES = {"merrill lynch", "dean witter", "smith barney", "smith bar", "morgan keegan", "raymond james",
               "edward jones", "charles schwab", "wells fargo"}


def _unglue(n: str) -> str:
    """Separate a brand run into a neighbouring word: "chapmanwells fargo" -> "chapman wells fargo"."""
    for b in _CARE_BRANDS:
        n = re.sub(rf"(?<=[a-z]){re.escape(b)}", f" {b}", n)
        n = re.sub(rf"{re.escape(b)}(?=[a-z])", f"{b} ", n)
    return re.sub(r"\s+", " ", n).strip()


def _person_words(words: list[str], given_names: set[str]) -> str | None:
    words = [w for w in words if not w.isdigit()]
    if any(any(ch.isdigit() for ch in w) for w in words):
        return None
    # "co" glued to the surname: "robert schoolfieldco wells fargo".
    if words and words[-1].endswith("co") and len(words[-1]) >= 7:
        words = words[:-1] + [words[-1][:-2]]
    while words and words[0] in _CARE_WORDS:
        words = words[1:]
    while words and (words[-1] in _CARE_WORDS or words[-1] in _TITLE_WORDS):
        words = words[:-1]
    if not 2 <= len(words) <= 4 or words[0] not in given_names:
        return None
    if any(w in _NOT_PERSON_WORDS for w in words):
        return None
    candidate = " ".join(words)
    if candidate in _FIRM_NAMES or _STRONG_RE.search(candidate) or _WEAK_RE.search(candidate):
        return None
    return candidate


def care_of_person(name_norm: str, given_names: set[str]) -> tuple[str, str] | None:
    """(person name, bank) when a name is an individual listed care of a bank, else None.

    "kristin cupillari co wells fargo" -> ("kristin cupillari", "wells fargo");
    "wells fargo bank dominic clemente" -> ("dominic clemente", "wells fargo");
    "wells fargo bank n a" -> None.
    """
    n = _unglue(name_norm)
    for spelling, canonical in KEY_SPELLINGS.items():
        n = re.sub(rf"\b{spelling}\b", canonical, n)
    m = re.search(rf"\b({_BRAND_ALT}){_BRAND_TAIL}\b", n)
    if not m:
        return None
    brand = m.group(1)
    before, after = n[:m.start()].split(), n[m.end():].split()
    suffix = [w for w in after if w in ("jr", "sr", "ii", "iii", "iv")]
    if before:
        person = _person_words(before, given_names)
        if person:
            return (" ".join([person] + suffix[:1]), brand)
        return None
    person = _person_words(after, given_names)
    return (person, brand) if person else None


def care_of_candidate_regex() -> str:
    """SQL regex for names that mention a brand at all (pre-filter for care_of_person)."""
    return "(" + "|".join(b.replace(" ", r"\s?") for b in _CARE_BRANDS) + ")"
