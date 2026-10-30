"""Abbreviations and full names (name_aliases; owner, 2026-10-30), so a search for "IBM" also finds "International
Business Machines" and the reverse. Two kinds of rows:

  manual   MANUAL below: well-known abbreviations, hand-picked. Inserted when missing and never overwritten, so a row
           the owner edits or turns off (status 'off') stays that way. Rows the owner adds are 'manual' too.
  derived  Initials of names FURP already holds (first letters of the words, skipping "of", "the", "and"...), kept
           only with evidence that the short name means that full name, since bare initials are hopelessly ambiguous
           ("ABC" fits 150 firms registered in three or more states):
             org      a nonprofit whose own DBA, website or common short name (org_alt_names) is the initials of
                      its name ("aarp.org" for American Association of Retired Persons)
             dba      a registry entity whose other name (biz_names) is the initials of its name, or the reverse
             address  an entity named with the initials registered at the same street address and ZIP as one
                      with the full name, at an address with few entities (not a registered agent's office); two
                      or more such addresses for short names of two or three letters
           support is how many records back the pair; a short name keeps its best-supported full names only.

Rebuilt every night (scripts/nightly.sh): derived rows are replaced, manual and 'off' rows are left alone. The
registry pairs take a scan of every registry address (several minutes), so they are recomputed only when the registry
tables changed since the last build (--force recomputes them anyway).

Usage: .venv/bin/python -m loader.name_aliases [--force]
"""

from __future__ import annotations

import re
import time

from loader import db
from loader.recalls import core

# Well-known abbreviations (short, full name). Unambiguous ones only: an abbreviation that names several well-known
# organizations (USC, OSU) is left out.
MANUAL = [
    ("IBM", "International Business Machines"), ("3M", "Minnesota Mining and Manufacturing"),
    ("GE", "General Electric"), ("HP", "Hewlett-Packard"), ("AT&T", "American Telephone and Telegraph"),
    ("UPS", "United Parcel Service"), ("PPG", "Pittsburgh Plate Glass"), ("BMW", "Bayerische Motoren Werke"),
    ("GM", "General Motors"), ("AIG", "American International Group"), ("AMD", "Advanced Micro Devices"),
    ("ADM", "Archer Daniels Midland"), ("PwC", "PricewaterhouseCoopers"), ("EY", "Ernst & Young"),
    ("BP", "British Petroleum"), ("HSBC", "Hongkong and Shanghai Banking Corporation"),
    ("UBS", "Union Bank of Switzerland"), ("USAA", "United Services Automobile Association"),
    ("GEICO", "Government Employees Insurance Company"), ("NCR", "National Cash Register"),
    ("TI", "Texas Instruments"), ("FedEx", "Federal Express"), ("IHOP", "International House of Pancakes"),
    ("KFC", "Kentucky Fried Chicken"), ("RCA", "Radio Corporation of America"),
    ("CBS", "Columbia Broadcasting System"), ("NBC", "National Broadcasting Company"),
    ("ABC", "American Broadcasting Companies"), ("CNN", "Cable News Network"), ("HBO", "Home Box Office"),
    ("ESPN", "Entertainment and Sports Programming Network"), ("BET", "Black Entertainment Television"),
    ("EDS", "Electronic Data Systems"), ("CSC", "Computer Sciences Corporation"),
    ("SAIC", "Science Applications International Corporation"), ("CVS", "Consumer Value Stores"),
    ("AARP", "American Association of Retired Persons"), ("YMCA", "Young Mens Christian Association"),
    ("YWCA", "Young Womens Christian Association"),
    ("NAACP", "National Association for the Advancement of Colored People"),
    ("ACLU", "American Civil Liberties Union"), ("NRA", "National Rifle Association"),
    ("NPR", "National Public Radio"), ("PBS", "Public Broadcasting Service"),
    ("ASPCA", "American Society for the Prevention of Cruelty to Animals"),
    ("SPCA", "Society for the Prevention of Cruelty to Animals"), ("WWF", "World Wildlife Fund"),
    ("NWF", "National Wildlife Federation"), ("NRDC", "Natural Resources Defense Council"),
    ("EDF", "Environmental Defense Fund"), ("SPLC", "Southern Poverty Law Center"), ("ADL", "Anti-Defamation League"),
    ("AIPAC", "American Israel Public Affairs Committee"), ("CAIR", "Council on American-Islamic Relations"),
    ("MADD", "Mothers Against Drunk Driving"), ("NAMI", "National Alliance on Mental Illness"),
    ("PETA", "People for the Ethical Treatment of Animals"), ("HRC", "Human Rights Campaign"),
    ("MIT", "Massachusetts Institute of Technology"), ("UCLA", "University of California Los Angeles"),
    ("NYU", "New York University"), ("CUNY", "City University of New York"),
    ("SUNY", "State University of New York"), ("AEI", "American Enterprise Institute"),
    ("CFR", "Council on Foreign Relations"), ("CSIS", "Center for Strategic and International Studies"),
    ("ALEC", "American Legislative Exchange Council"), ("FFRF", "Freedom From Religion Foundation"),
    ("EFF", "Electronic Frontier Foundation"), ("IEEE", "Institute of Electrical and Electronics Engineers"),
    ("AAAS", "American Association for the Advancement of Science"), ("AMA", "American Medical Association"),
    ("ABA", "American Bar Association"),
    ("AFL-CIO", "American Federation of Labor and Congress of Industrial Organizations"),
    ("SEIU", "Service Employees International Union"), ("UAW", "United Auto Workers"),
    ("NEA", "National Education Association"), ("AFT", "American Federation of Teachers"),
    ("BSA", "Boy Scouts of America"), ("USO", "United Service Organizations"), ("VFW", "Veterans of Foreign Wars"),
    ("DAV", "Disabled American Veterans"), ("HHMI", "Howard Hughes Medical Institute"),
    ("MSKCC", "Memorial Sloan Kettering Cancer Center"), ("UPMC", "University of Pittsburgh Medical Center"),
    ("NFL", "National Football League"), ("NBA", "National Basketball Association"),
    ("MLB", "Major League Baseball"), ("NCAA", "National Collegiate Athletic Association"),
    ("PGA", "Professional Golfers Association"), ("USGA", "United States Golf Association"),
    ("MoMA", "Museum of Modern Art"), ("LACMA", "Los Angeles County Museum of Art"),
]
SKIP = {"the", "of", "and", "for", "a", "an", "in", "on", "at", "to", "de"}
SHORT = re.compile(r"^[a-z0-9]{2,6}$")
KEEP = 3                 # derived full names kept per short name, best supported first
CROWDED = 25             # an address with more entities than this is an agent's or a mail drop, not evidence


def initials(norm: str) -> str:
    """First letters of a normalized name's words, skipping articles and joiners: "international business
    machines" gives "ibm"."""
    return "".join(w[0] for w in (norm or "").split() if w not in SKIP)


def pair_ok(short_norm: str, long_norm: str) -> bool:
    """A derived pair: a short name of 2 to 6 letters that is the initials of a full name of two or more words."""
    return bool(SHORT.match(short_norm or "")) and len(long_norm.split()) >= 2 and initials(long_norm) == short_norm


def _add(pairs: dict, s: str, n: str, short: str, long: str, support: int, evidence: str) -> None:
    if pair_ok(s, n):
        p = pairs.setdefault((s, n), {"short": short, "long": long, "support": 0, "evidence": evidence})
        p["support"] += support


def _org_pairs(conn) -> dict:
    """Nonprofits whose own DBA, website or common short name is the initials of their name."""
    pairs: dict = {}
    for alias, name in conn.execute("""SELECT a.alias, o.name FROM org_alt_names a JOIN organizations o ON o.ein = a.ein
                                       WHERE a.source IN ('dba', 'website', 'llm')"""):
        _add(pairs, core(alias).replace(" ", ""), core(name), alias.upper(), name, 1, "org")
    return pairs


def _registry_changes(conn) -> int:
    """Rows inserted, updated or deleted in the registry tables so far (the statistics collector's counters): the
    registry pairs are recomputed only when this moves, since the scan takes several minutes."""
    return conn.execute("""SELECT coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) FROM pg_stat_user_tables
                           WHERE relname IN ('biz_entities', 'biz_names')""").fetchone()[0]


def _registry_pairs(conn, status) -> dict:
    pairs: dict = {}
    if not conn.execute("SELECT to_regclass('biz_entities') IS NOT NULL").fetchone()[0]:
        return pairs
    # Other names on the same entity (DBAs), either way round.
    for other, name, oc, nc in conn.execute("""
            SELECT n.name, e.name, n.name_core, e.name_core FROM biz_names n JOIN biz_entities e USING (state, entity_id)
            WHERE n.name_core ~ '^[a-z0-9]{2,6}$' OR e.name_core ~ '^[a-z0-9]{2,6}$'"""):
        _add(pairs, oc, nc, other, name, 1, "dba")
        _add(pairs, nc, oc, name, other, 1, "dba")
    status(f"name aliases: {len(pairs):,} pairs from registry other names")
    # The same street address and ZIP, at addresses with few entities.
    conn.execute("SET work_mem = '512MB'")
    conn.execute("""CREATE TEMP TABLE na_short AS
                    SELECT DISTINCT regexp_replace(upper(street), '[^A-Z0-9]', '', 'g') AS st, left(zip, 5) AS z
                    FROM biz_entities WHERE name_core ~ '^[a-z0-9]{2,6}$' AND length(street) > 3 AND zip ~ '^[0-9]{5}'""")
    conn.execute("ANALYZE na_short")
    conn.execute("""CREATE TEMP TABLE na_addr AS
                    SELECT e.name, e.name_core, s.st, s.z
                    FROM biz_entities e JOIN na_short s
                      ON left(e.zip, 5) = s.z AND regexp_replace(upper(e.street), '[^A-Z0-9]', '', 'g') = s.st""")
    for s, short, n, long, support in conn.execute("""
            WITH a AS (SELECT * FROM na_addr WHERE (st, z) IN (SELECT st, z FROM na_addr GROUP BY st, z
                                                                HAVING count(*) <= %s))
            SELECT s.name_core, min(s.name), l.name_core, min(l.name), count(DISTINCT (s.st, s.z))
            FROM a s JOIN a l USING (st, z)
            WHERE s.name_core ~ '^[a-z0-9]{2,6}$' AND l.name_core ~ ' ' AND left(l.name_core, 1) = left(s.name_core, 1)
            GROUP BY s.name_core, l.name_core""", (CROWDED,)):
        if support >= 2 or len(s) >= 4:     # one shared address is too thin for "cs" or "3m" ("33 Montauk LLC")
            _add(pairs, s, n, short, long, support, "address")
    conn.execute("DROP TABLE na_short, na_addr")
    return pairs


def _saved_registry_pairs(conn) -> dict:
    return {(s, n): {"short": short, "long": long, "support": support, "evidence": ev}
            for s, n, short, long, support, ev in conn.execute(
                """SELECT short_norm, long_norm, short, long, support, evidence FROM name_aliases
                   WHERE source = 'derived' AND evidence IN ('dba', 'address')""")}


def build(status=print, force: bool = False) -> dict:
    t0 = time.time()
    with db.connect() as conn:
        manual = [(core(s), core(lg), s, lg) for s, lg in MANUAL]
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO name_aliases (short_norm, long_norm, short, long, source, evidence)
                               VALUES (%s, %s, %s, %s, 'manual', 'hand-picked') ON CONFLICT DO NOTHING""", manual)
        conn.commit()
        pairs = _org_pairs(conn)
        status(f"name aliases: {len(pairs):,} pairs from nonprofits' own short names")
        changes = _registry_changes(conn)
        last = conn.execute("SELECT rows FROM loader_progress WHERE file = 'name_aliases:registry'").fetchone()
        if force or not last or last[0] != changes:
            registry = _registry_pairs(conn, status)
        else:
            registry = _saved_registry_pairs(conn)
            status("name aliases: registry unchanged since the last build; its pairs kept")
        for k, v in registry.items():
            if k in pairs:
                pairs[k]["support"] += v["support"]
            else:
                pairs[k] = v
        # Each short name keeps its best-supported full names.
        by_short: dict = {}
        for (s, n), v in pairs.items():
            by_short.setdefault(s, []).append((v["support"], n, v))
        # Shown as the bare initials ("NEON", not the website's "neon-inc" or a DBA's "NEON, Inc.").
        rows = [(s, n, s.upper(), v["long"], v["support"], v["evidence"])
                for s, lst in by_short.items() for _, n, v in sorted(lst, key=lambda x: (-x[0], x[1]))[:KEEP]]
        conn.execute("DELETE FROM name_aliases WHERE source = 'derived' AND status = 'live'")
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO name_aliases (short_norm, long_norm, short, long, source, support, evidence)
                               VALUES (%s, %s, %s, %s, 'derived', %s, %s) ON CONFLICT DO NOTHING""", rows)
        db.progress(conn, "name_aliases:registry", "done", kind="name_aliases", rows=changes)
        conn.commit()
        manual_n, derived_n = conn.execute("""SELECT count(*) FILTER (WHERE source = 'manual'),
                                                     count(*) FILTER (WHERE source = 'derived')
                                              FROM name_aliases WHERE status = 'live'""").fetchone()
    status(f"name aliases: {manual_n:,} hand-picked and {derived_n:,} derived pairs ({time.time() - t0:.0f}s)")
    return {"manual": manual_n, "derived": derived_n}


if __name__ == "__main__":
    import sys
    build(force="--force" in sys.argv)
