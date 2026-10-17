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
