"""Parties to student loan trusts, matched to 990 filers where they are nonprofits.

Every sponsor, depositor, servicer, administrator and trustee named in student_loan_trusts
becomes one student_loan_parties row (one per normalized name), with its own page slug.
Then each is looked up in organizations:

  EXACT  the same normalized name (legal suffixes dropped) and the same state (the party's
         EDGAR business address, or for a sponsor its trust's address)
  FUZZY  the same name in another state, or a trigram similarity of at least FUZZY_MIN on the
         normalized name in the same state (or where the filings give no state)

Banks and companies don't file 990s, so most parties match nothing; that's expected. A
party known from the filings to be a government agency (PHEAA) is labeled, not linked.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from loader import db, sec

FUZZY_MIN = 0.75
SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|llc|l l c|ltd|na|n a|lp|the)\b")
ROLES = ("sponsor", "depositor", "servicer", "administrator", "trustee")
ALL_ROLES = ROLES + ("securitizer",)
# Securitizers that file Form ABS-15G (Rule 15Ga-1 repurchase reports) for student loan deals. Their
# deals are private (Rule 144A) or municipal, so they file no monthly reports, but the filing names
# them as student loan securitizers. Names matched by the discovery pattern that aren't student loan
# securitizers (real estate, sporting goods, SPACs) are excluded here.
SECURITIZER = re.compile(r"student|education|educational|edvance|academic|lending|loan|sofi|navient|nelnet|"
                         r"sallie|smb |pheaa|college|accesslex|marblehead|dr bank|cit strategic", re.I)
NOT_SECURITIZER = re.compile(r"northstar (realty|real estate|healthcare|asset|20\d\d|spectrum|wireless)|n1 liquidating|"
                             r"brightspire|digitalbridge|sport supply|collegiate pacific|hockey|adapti|cslm|arctos",
                             re.I)
# Parties that are obviously for-profit or banks: never linked to a 990 filer.
NOT_NONPROFIT = re.compile(r"\b(bank|trust company|banc|national association|navient|sallie mae|slm|nelnet|"
                           r"wells fargo|citibank|keybank|key bank|first marblehead|funding,? llc|"
                           r"securities|capital markets|sofi)\b", re.I)
# What the filings and public record say about parties that are not ordinary 990 filers.
KNOWN = {
    "pennsylvania higher education assistance agency": "A Pennsylvania state agency (PHEAA); state agencies "
                                                        "don't file Form 990.",
}


def norm(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", SUFFIX.sub(" ", s)).strip()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:80]


def run(status=print) -> int:
    with db.connect() as conn:
        rows = conn.execute(f"SELECT {', '.join(ROLES)}, edgar_state FROM student_loan_trusts").fetchall()
        parties: dict[str, dict] = {}
        for r in rows:
            for role, name in zip(ROLES, r[:5]):
                if not name:
                    continue
                n = norm(name)
                p = parties.setdefault(n, {"party": name, "roles": set(), "state": None})
                p["roles"].add(role)
                # A trust's EDGAR business address is its sponsor's office, so it gives the sponsor's state.
                if role == "sponsor" and r[5] and not p["state"]:
                    p["state"] = r[5]
        for cik, t in _securitizers().items():
            n = norm(t["name"])
            p = parties.setdefault(n, {"party": t["name"], "roles": set(), "state": None})
            p["roles"].add("securitizer")
            p["state"] = p["state"] or t["state"]
            p["cik"] = cik
            p["abs15g"] = t["abs15g"]
        now = datetime.now(timezone.utc)
        linked = 0
        conn.execute("DELETE FROM student_loan_parties")
        used_slugs: set[str] = set()
        for n, p in sorted(parties.items()):
            ein = match = None
            evidence: list[dict] = []
            if n in KNOWN:
                evidence.append({"why": KNOWN[n]})
            elif not NOT_NONPROFIT.search(p["party"]):
                ein, match, evidence = _match(conn, n, p["state"])
            slug = slugify(p["party"])
            while slug in used_slugs:
                slug += "-2"
            used_slugs.add(slug)
            conn.execute("""INSERT INTO student_loan_parties (party, party_norm, slug, roles, state, ein, match,
                                                              evidence, sec_cik, abs15g, retrieved_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                         (p["party"], n, slug, sorted(p["roles"], key=ALL_ROLES.index), p["state"], ein, match,
                          Jsonb(evidence) if evidence else None, p.get("cik"),
                          Jsonb(p["abs15g"]) if p.get("abs15g") else None, now))
            linked += ein is not None
        conn.commit()
    status(f"parties: {len(parties)}, linked to 990 filers: {linked}")
    return linked


def _securitizers() -> dict[int, dict]:
    """{cik: {name, state, abs15g}} for student loan securitizers filing Form ABS-15G (from discovery)."""
    data = json.loads((sec.CACHE / "trusts.json").read_text())
    out = {}
    for cik, t in data.items():
        n15 = t["forms"].get("ABS-15G", 0) + t["forms"].get("ABS-15G/A", 0)
        if not n15 or not SECURITIZER.search(t["name"]) or NOT_SECURITIZER.search(t["name"]):
            continue
        st = t.get("biz_state") if re.fullmatch(r"[A-Z]{2}", t.get("biz_state") or "") else None
        out[int(cik)] = {"name": t["name"], "state": st,
                         "abs15g": {"filings": n15, "first": t.get("first_15g"), "last": t.get("last_15g")}}
    return out


def _match(conn, n: str, state: str | None):
    """(ein, 'EXACT' | 'FUZZY', evidence) or (None, None, [])."""
    cands = conn.execute("""
        SELECT ein, name, name_norm, state, latest_filing_year, similarity(name_norm, %(n)s) AS sim
        FROM organizations
        WHERE name_norm %% %(n)s AND similarity(name_norm, %(n)s) >= %(min)s
        ORDER BY sim DESC, latest_filing_year DESC NULLS LAST LIMIT 10""", {"n": n, "min": FUZZY_MIN - 0.25}).fetchall()
    best = None
    for ein, name, name_norm, st, year, sim in cands:
        exact = norm(name_norm) == n
        other_state = bool(state and st and st != state)
        if other_state and not exact:       # a similar name in another state is a different organization
            continue
        if exact or sim >= FUZZY_MIN:
            best = (ein, name, st, year, sim, exact, other_state)
            break
    if not best:
        return None, None, []
    ein, name, st, year, sim, exact, other_state = best
    why = (f"Same name after dropping legal suffixes: \"{name}\"" if exact
           else f"Similar name ({sim:.2f} trigram similarity): \"{name}\"")
    if st:
        why += f", {st}"
    if state and st == state:
        why += " (same state as the party's EDGAR business address)"
    elif other_state:
        why += f"; the party's EDGAR business address is in {state}, so this is tagged Fuzzy"
    elif not state:
        why += "; the filings don't give the party's state, so state was not compared"
    if year:
        why += f"; latest 990 tax year {year}"
    return ein, ("EXACT" if exact and state and not other_state else "FUZZY"), [{"why": why}]
