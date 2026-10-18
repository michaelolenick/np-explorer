#!/usr/bin/env python3
"""Propose common-name aliases for review (org_aliases, status 'proposed'); nothing goes live automatically.

  python scripts/propose_aliases.py propose     # write proposals + docs/alias-proposals.md
  python scripts/propose_aliases.py approve <alias> [<alias> ...]   # make reviewed aliases live
  python scripts/propose_aliases.py reject <alias> [<alias> ...]

Two sources of proposals:
  schools   A school whose own return is filed under another legal name ("President and Fellows of Harvard
            College"): the school's name, the aliases IPEDS lists for it ("MIT") and the short names the site
            already knows ("UT Austin") point to the school's own filer (EXACT school link), with its EXACT-linked
            foundations and associations as affiliates.
  same name Many organizations share one name and one is far larger than the rest (Ducks Unlimited and its
            chapters): the shared name points to the large one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.aliases import alias_norm  # noqa: E402
from app.colleges import NICKNAMES  # noqa: E402
from loader import db  # noqa: E402

DOC = Path(__file__).resolve().parent.parent / "docs" / "alias-proposals.md"
MIN_SCHOOL_REVENUE = 100_000_000     # schools: own filer's latest revenue
MIN_DOMINANT_REVENUE = 25_000_000    # same-name: the large organization's latest revenue
DOMINANT = 5                         # ... and at least this many times the next largest
MIN_SAME_NAME = 5                    # ... among at least this many organizations with the name
STATES = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida",
          "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
          "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska",
          "nevada", "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
          "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
          "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming"}
SCHOOLISH = re.compile(r"\b(universit|college|institute|school|academy|seminary|trustees|regents|governing|"
                       r"chancellor|president and fellows|polytechnic)", re.I)


def _school_aliases(conn) -> list[dict]:
    rows = conn.execute("""
        SELECT c.unitid, c.name AS school, c.alias AS ipeds_alias, o.ein, o.name AS filed, o.latest_total_revenue AS rev
        FROM colleges c JOIN college_orgs co ON co.unitid = c.unitid AND co.relation = 'self' AND co.match = 'EXACT'
        JOIN organizations o ON o.ein = co.ein
        WHERE NOT c.closed AND o.latest_total_revenue >= %s
        ORDER BY o.latest_total_revenue DESC""", (MIN_SCHOOL_REVENUE,)).fetchall()
    nick = {}
    for short, full in NICKNAMES.items():
        nick.setdefault(full, []).append(short)
    # "Harvard" for Harvard University: the name without University/College, if no other school shares it.
    shorts: dict = {}
    for (name,) in conn.execute("SELECT name FROM colleges WHERE NOT closed"):
        short = re.sub(r"(?i)^the |\b(university|college)\b|-main campus$|,.*$", "", name).strip(" -")
        shorts.setdefault(alias_norm(short), []).append(name)
    out = []
    for unitid, school, ipeds_alias, ein, filed, rev in rows:
        if not SCHOOLISH.search(filed or ""):
            continue                         # IPEDS lists a hospital system's EIN for its nursing school, etc.
        names = {re.sub(r"(?i)-main campus$", "", school).strip()}
        short = re.sub(r"(?i)^the |\b(university|college)\b|-main campus$|,.*$", "", school).strip(" -")
        if short and len(shorts.get(alias_norm(short), [])) == 1 and len(short) >= 4:
            names.add(short)
        names |= {a.strip() for a in re.split(r"[|,;]", ipeds_alias or "") if 2 <= len(a.strip()) <= 60}
        names |= {s.upper() if len(s) <= 5 else s.title() for s in nick.get(alias_norm(school), [])}
        affiliates = conn.execute("""SELECT co.ein FROM college_orgs co WHERE co.unitid = %s AND co.match = 'EXACT'
                                     AND co.relation IN ('foundation', 'athletic', 'alumni', 'research', 'hospital')""",
                                  (unitid,)).fetchall()
        for n in sorted(names):
            if not alias_norm(n) or alias_norm(n) == alias_norm(filed) or alias_norm(n) in STATES:
                continue                     # the filed name already says it, or a state name alone
            out.append({"alias": n, "primary": ein, "filed": filed, "rev": rev, "affiliates": [a[0] for a in affiliates],
                        "why": f"School: {school}; its own return is filed as “{filed}” (IPEDS EIN, EXACT school link)."})
    return out


def _same_name(conn) -> list[dict]:
    rows = conn.execute("""
        WITH n AS (
            SELECT regexp_replace(regexp_replace(name_norm, '^the ', ''),
                                  ' (inc|incorporated|corp|corporation|co|ltd|llc|foundation inc)$', '') AS core,
                   ein, name, latest_total_revenue AS rev
            FROM organizations WHERE name_norm IS NOT NULL),
        g AS (
            SELECT core, count(*) AS n,
                   (array_agg(ein ORDER BY rev DESC NULLS LAST))[1] AS top_ein,
                   (array_agg(name ORDER BY rev DESC NULLS LAST))[1] AS top_name,
                   (array_agg(rev ORDER BY rev DESC NULLS LAST))[1] AS top_rev,
                   (array_agg(rev ORDER BY rev DESC NULLS LAST))[2] AS next_rev
            FROM n GROUP BY core HAVING count(*) >= %s)
        SELECT core, n, top_ein, top_name, top_rev, next_rev FROM g
        WHERE top_rev >= %s AND top_rev >= %s * greatest(coalesce(next_rev, 0), 1)
        ORDER BY top_rev DESC LIMIT 300""", (MIN_SAME_NAME, MIN_DOMINANT_REVENUE, DOMINANT)).fetchall()
    return [{"alias": core.title(), "primary": ein, "filed": name, "rev": rev, "affiliates": [],
             "why": f"{n:,} organizations are named “{core}”; this one reports ${rev:,.0f}, "
                    f"{rev / max(nxt or 0, 1):,.0f} times the next largest (${(nxt or 0):,.0f})."}
            for core, n, ein, name, rev, nxt in rows]


def propose() -> None:
    with db.connect() as conn:
        live = {r[0] for r in conn.execute("SELECT DISTINCT alias_norm FROM org_aliases WHERE status <> 'proposed'")}
        props = [p for p in _school_aliases(conn) + _same_name(conn) if alias_norm(p["alias"]) not in live]
        seen, unique = set(), []
        for p in props:
            k = alias_norm(p["alias"])
            if k and k not in seen:
                seen.add(k)
                unique.append(p)
        conn.execute("DELETE FROM org_aliases WHERE status = 'proposed'")
        for p in unique:
            k = alias_norm(p["alias"])
            conn.execute("""INSERT INTO org_aliases (alias_norm, alias, ein, role, status, note)
                            VALUES (%s, %s, %s, 'primary', 'proposed', %s) ON CONFLICT DO NOTHING""",
                         (k, p["alias"], p["primary"], "Proposed (scripts/propose_aliases.py): " + p["why"]))
            for a in p["affiliates"]:
                if a != p["primary"]:
                    conn.execute("""INSERT INTO org_aliases (alias_norm, alias, ein, role, status, note)
                                    VALUES (%s, %s, %s, 'affiliate', 'proposed', %s) ON CONFLICT DO NOTHING""",
                                 (k, p["alias"], a, "Proposed affiliate: an EXACT-linked organization of the school."))
        conn.commit()
    lines = ["# Proposed aliases (for review; none are live)", "",
             "Generated by `scripts/propose_aliases.py propose`. Each alias would make the common name resolve to the",
             "primary organization (shown as EXACT, \"common name for <filed name>\") with affiliates listed beneath.",
             "Approve with `scripts/propose_aliases.py approve \"<alias>\"`, reject with `reject`.", "",
             "| Alias | Primary (as filed) | EIN | Latest revenue | Affiliates | Why |", "|---|---|---|---:|---:|---|"]
    for p in unique:
        lines.append(f"| {p['alias']} | {p['filed']} | {p['primary']} | ${p['rev'] or 0:,.0f} | {len(p['affiliates'])} | "
                     f"{p['why']} |")
    DOC.write_text("\n".join(lines) + "\n")
    print(f"{len(unique)} proposals written to org_aliases (status proposed) and {DOC}")


def set_status(aliases: list[str], status: str) -> None:
    with db.connect() as conn:
        for a in aliases:
            n = conn.execute("UPDATE org_aliases SET status = %s WHERE alias_norm = %s AND status = 'proposed'",
                             (status, alias_norm(a))).rowcount
            print(f"{a}: {n} row(s) {status}")
        conn.commit()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "propose"
    if cmd == "propose":
        propose()
    elif cmd in ("approve", "reject"):
        set_status(sys.argv[2:], "live" if cmd == "approve" else "rejected")
    else:
        sys.exit(__doc__)
