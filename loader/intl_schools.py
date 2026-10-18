"""International schools: foreign universities with US nonprofits that file 990s, linked like domestic schools.

Input: data/international-schools.csv (one row per school and US organization, from
scripts/intl_schools_discover.py, reviewed in docs/international-schools.md) and
data/intl-grants-abroad.csv (Schedule F rows of the linked organizations, read from their returns).
Run by load.py colleges (step "intl", after "orgs"); rebuilt in place in one transaction.

Rules (the owner's review decisions, 2026-10-18):
  - EXACT links only; FUZZY candidates are never linked.
  - A school that files its own US return (an IRS 98- EIN, or the evidence says so) is linked as
    relation "self" and flagged files_own_return, not counted as a US affiliate.
  - US-chartered universities with campuses abroad (American University of Beirut ...) are international.
  - A US school named after a foreign one (Soka University of America) is a US school: when the EIN is
    already the IPEDS EIN of a US institution, the link is dropped.
  - Endowment, fund-management and pension entities are relation "endowment"; alumni clubs are "alumni"
    and are left out of the school's totals.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from loader import db

REPO = Path(__file__).resolve().parent.parent
LINKS_CSV = REPO / "data" / "international-schools.csv"
GRANTS_CSV = REPO / "data" / "intl-grants-abroad.csv"
FIRST_ID = 9_000_001          # IPEDS UNITIDs are six digits; foreign schools get ids from here up

ENDOWMENT = re.compile(r"\b(endowment|funds?|retirement|pension|investments?|master trust|holdings)\b", re.I)
ALUMNI = re.compile(r"\b(alumni|alumnae|alumnus|graduates|club)\b", re.I)
OWN_RETURN = re.compile(r"the school itself files a US return", re.I)


def _norm(s: str | None) -> str:
    s = (s or "").lower().replace("&", " and ").replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def relation(org_name: str, ein: str, evidence: str) -> str:
    # Endowment and pension entities first: some have foreign (98-) EINs too (The Oxford Funds).
    if ENDOWMENT.search(org_name or ""):
        return "endowment"
    if ein.startswith("98") or OWN_RETURN.search(evidence or ""):
        return "self"
    if ALUMNI.search(org_name or ""):
        return "alumni"
    return "foundation"


def read_links(path: Path = LINKS_CSV) -> list[dict]:
    """EXACT rows of the reviewed CSV, one per (school, EIN), with the relation decided."""
    out: dict = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("match") or "").strip().upper() != "EXACT":
                continue
            ein = re.sub(r"\D", "", r["ein"] or "").zfill(9)
            ror = (r["ror_id"] or "").strip()
            if not ror.startswith("https://ror.org/") or len(ein) != 9:
                continue
            out[(ror, ein)] = {"ror_id": ror, "school": r["school_name"].strip(), "country": r["country"].strip() or None,
                               "website": (r["website"] or "").strip() or None, "ein": ein,
                               "org_name": (r["org_name"] or "").strip(), "evidence": (r["evidence"] or "").strip(),
                               "relation": relation(r["org_name"], ein, r["evidence"])}
    return list(out.values())


def read_grants(path: Path = GRANTS_CSV) -> list[tuple]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [(r["ein"].zfill(9), int(r["tax_year"]) if r["tax_year"] else None, r["object_id"] or None, r["part"],
                 r["region"] or None, int(float(r["amount"])) if r["amount"] not in ("", None) else None,
                 r["description"] or None) for r in csv.DictReader(f)]


def build(conn, status, links_csv: Path = LINKS_CSV, grants_csv: Path = GRANTS_CSV) -> int:
    links = read_links(links_csv)
    us_self = {r[0] for r in conn.execute(
        "SELECT co.ein FROM college_orgs co JOIN colleges c USING (unitid) WHERE co.relation = 'self' AND NOT c.international")}
    have = {r[0] for r in conn.execute("SELECT ein FROM organizations WHERE ein = ANY(%s)", ([l["ein"] for l in links],))}
    dropped_us = [l for l in links if l["ein"] in us_self]
    links = [l for l in links if l["ein"] not in us_self and l["ein"] in have]
    schools: dict = {}
    for l in links:
        s = schools.setdefault(l["ror_id"], {"name": l["school"], "country": l["country"], "website": l["website"],
                                             "own": False})
        s["own"] = s["own"] or l["relation"] == "self"
    # A school needs at least one link that is the school or a US affiliate (not only an endowment or a club).
    keep = {ror for ror in schools if any(l["ror_id"] == ror and l["relation"] in ("self", "foundation") for l in links)}
    links = [l for l in links if l["ror_id"] in keep]
    ids = dict(conn.execute("SELECT ror_id, unitid FROM intl_schools").fetchall())
    nxt = max([FIRST_ID - 1, *ids.values()]) + 1
    for ror in sorted(keep):
        if ror not in ids:
            ids[ror] = nxt
            nxt += 1
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout = '60s'")
        # intl_schools keeps every id it ever gave out, so pages keep their address across rebuilds.
        for ror in sorted(keep):
            s = schools[ror]
            conn.execute("""INSERT INTO intl_schools (ror_id, unitid, name, country, website, files_own_return)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (ror_id) DO UPDATE SET name = excluded.name, country = excluded.country,
                                website = excluded.website, files_own_return = excluded.files_own_return""",
                         (ror, ids[ror], s["name"], s["country"], s["website"], s["own"]))
        conn.execute("DELETE FROM college_orgs WHERE unitid >= %s", (FIRST_ID,))
        conn.execute("DELETE FROM colleges WHERE international")
        for ror in sorted(keep):
            s = schools[ror]
            conn.execute("""INSERT INTO colleges (unitid, name, name_norm, core_norm, website, control, country,
                                                  international, ror_id, closed, name_tsv)
                            VALUES (%s, %s, %s, %s, %s, 'International', %s, true, %s, false,
                                    to_tsvector('simple', %s))""",
                         (ids[ror], s["name"], _norm(s["name"]), re.sub(r"^the ", "", _norm(s["name"])), s["website"],
                          s["country"], ror, s["name"]))
        with conn.cursor() as cur:
            db.copy_rows(cur, "college_orgs", ["unitid", "ein", "relation", "match", "evidence"],
                         [(ids[l["ror_id"]], l["ein"], l["relation"], "EXACT",
                           json.dumps({"rule": "intl", "ror_id": l["ror_id"], "school": l["school"],
                                       "country": l["country"], "evidence": l["evidence"]})) for l in links])
        grants = [g for g in read_grants(grants_csv) if g[0] in {l["ein"] for l in links}]
        conn.execute("TRUNCATE intl_grants_abroad")
        with conn.cursor() as cur:
            db.copy_rows(cur, "intl_grants_abroad", ["ein", "tax_year", "object_id", "part", "region", "amount",
                                                     "description"], grants)
    conn.execute("ANALYZE colleges")
    status.emit(f"international schools: {len(keep):,} schools, {len(links):,} EXACT links "
                f"({sum(s['own'] for r, s in schools.items() if r in keep):,} file their own US return), "
                f"{len(grants):,} Schedule F rows; {len(dropped_us)} links dropped as US schools")
    return len(keep)
