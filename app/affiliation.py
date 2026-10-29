"""Is this person listed at this organization? (owner, 2026-10-29)

"Tony Yang Mucker" or "Tony Yang, Mucker Capital" in the search box, and "Is Tony Yang listed on any Form D or ADV
for Mucker?" as a question, restrict a person search to people linked to that organization in any source: 990
officers, directors and key employees; Form D related persons; Form ADV owners and executive officers (Schedules A
and B); SEC insider filings (Forms 3, 4 and 5); state business registrations. When none lists the person there, the
answer says so plainly: that negative is often the point of the search.

Organizations are matched by their distinctive words, each at the start of a word ("mucker" matches Mucker Early,
LLC and MuckerLab, LLC, never Smucker); generic words (capital, partners, fund, LLC...) count only when nothing else
is left. People are matched by name in every source: the exact name and the same name with a middle name or initial
(queries.variant_regex). Two people can share a name, so a listing is a lead, not proof it is the same person.
"""

from __future__ import annotations

import logging
import re

from app import db
from app.names import DROP, SUFFIXES, normalize_name, query_tokens

log = logging.getLogger("np.affiliation")

GENERIC = frozenset("""capital partners partner management managers manager fund funds ventures venture group holdings
    holding llc lp llp lllp inc incorporated co company corp corporation ltd limited the of and advisors advisers
    adviser advisor advisory investments investment associates gp trust foundation l p plc""".split())
SOURCES = ["990 officers, directors and key employees", "Form D related persons", "Form ADV owners and executive officers",
           "SEC insider filings (Forms 3, 4, 5)", "state business registrations"]
FUND_SOURCES = ("Form D", "Form ADV")
MAX_NAMES = 60
TIMEOUT = "8s"


def org_words(org: str) -> list[str]:
    """The words an organization must have: its distinctive words, else all of them."""
    words = [w for w in re.findall(r"[a-z0-9]+", (org or "").lower()) if w]
    keep = [w for w in words if w not in GENERIC]
    return keep or words


def _patterns(words: list[str]) -> list[str]:
    return [r"\m" + re.escape(w) for w in words]


def _like(words: list[str]) -> str:
    """A LIKE on the longest word, for the trigram indexes (regexes alone scan)."""
    return "%" + max(words, key=len) + "%"


def _name_params(person: str) -> dict | None:
    from app.queries import _tsq, variant_regex
    tokens = query_tokens(person)
    norm = normalize_name(person)
    if len(tokens) < 2 or not norm:
        return None
    return {"exact": _tsq(tokens, False), "norm": norm, "variant": variant_regex(tokens)}


def names(conn, person: str) -> dict:
    """Name forms of this person found anywhere: {name_norm: display name}, people on the site (cluster ids) and
    Form D or ADV people (fund_people)."""
    p = _name_params(person)
    if not p:
        return {"norms": {}, "clusters": []}
    T = db.search_table()   # noqa: N806
    clusters = conn.execute(f"""SELECT id, display_name, name_norm FROM {T}
                                WHERE name_tsv @@ to_tsquery('simple', %(exact)s) AND NOT is_institution
                                  AND (name_norm = %(norm)s OR name_norm ~ %(variant)s)
                                ORDER BY (name_norm = %(norm)s) DESC, n_filings DESC LIMIT 2000""", p).fetchall()
    norms = {}
    for c in clusters:
        norms.setdefault(c["name_norm"], c["display_name"])
    if db.has_table("fund_people"):
        for f in conn.execute("""SELECT DISTINCT ON (name_norm) name_norm, name FROM fund_people
                                 WHERE name_tsv @@ to_tsquery('simple', %(exact)s)
                                   AND (name_norm = %(norm)s OR name_norm ~ %(variant)s) LIMIT 500""", p).fetchall():
            norms.setdefault(f["name_norm"], f["name"])
    ordered = sorted(norms, key=lambda n: (n != p["norm"], n))[:MAX_NAMES]
    return {"norms": {n: norms[n] for n in ordered}, "clusters": clusters}


def has_person(conn, person: str) -> bool:
    p = _name_params(person)
    if not p:
        return False
    T = db.search_table()   # noqa: N806
    if conn.execute(f"""SELECT 1 FROM {T} WHERE name_tsv @@ to_tsquery('simple', %(exact)s) AND NOT is_institution
                        AND (name_norm = %(norm)s OR name_norm ~ %(variant)s) LIMIT 1""", p).fetchone():
        return True
    return db.has_table("fund_people") and conn.execute(
        """SELECT 1 FROM fund_people WHERE name_tsv @@ to_tsquery('simple', %(exact)s)
           AND (name_norm = %(norm)s OR name_norm ~ %(variant)s) LIMIT 1""", p).fetchone() is not None


def matching_orgs(conn, org: str, limit: int = 40) -> list[dict]:
    """Organizations whose names have the org's words: Form D issuers, investment advisers, nonprofits, public
    companies (insider filings)."""
    words = org_words(org)
    if not words:
        return []
    q = {"pats": _patterns(words), "like": _like(words), "lim": limit}
    out = []
    for r in conn.execute("""SELECT DISTINCT ON (cik) cik, issuer_name AS name, accession, filing_date FROM sec_formd
                             WHERE lower(issuer_name) LIKE %(like)s AND issuer_name ~* ALL(%(pats)s)
                             ORDER BY cik, filing_date DESC NULLS LAST LIMIT %(lim)s""", q).fetchall():
        out.append({"kind": "Form D issuer", "name": r["name"], "cik": r["cik"], "date": r["filing_date"],
                    "url": f"/corporate/form-d/{r['accession']}"})
    for r in conn.execute("""SELECT * FROM (SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name) AS name,
                                                  legal_name, submitted FROM adv_filings
                                           WHERE lower(coalesce(business_name, '') || ' ' || coalesce(legal_name, ''))
                                                 LIKE %(like)s
                                           ORDER BY crd, submitted DESC NULLS LAST) a
                             WHERE name ~* ALL(%(pats)s) OR legal_name ~* ALL(%(pats)s) LIMIT %(lim)s""", q).fetchall():
        out.append({"kind": "Investment adviser (Form ADV)", "name": r["name"], "crd": r["crd"], "date": r["submitted"],
                    "url": f"https://adviserinfo.sec.gov/firm/summary/{r['crd']}", "external": True})
    for r in conn.execute("""SELECT ein, name FROM organizations WHERE name ILIKE %(like)s AND name ~* ALL(%(pats)s)
                             ORDER BY latest_total_revenue DESC NULLS LAST LIMIT 10""", q).fetchall():
        out.append({"kind": "Nonprofit", "name": r["name"], "ein": r["ein"], "url": f"/org/{r['ein']}"})
    return out


def _hits(conn, nm: dict, words: list[str]) -> list[dict]:
    """Every record listing one of these names at an organization with these words."""
    pats, norms = _patterns(words), list(nm["norms"])
    q = {"pats": pats, "norms": norms, "ids": [c["id"] for c in nm["clusters"]]}
    hits = []
    if q["ids"]:
        for r in conn.execute("""
                SELECT m.cluster_id, max(c.display_name) AS name, coalesce(o.name, f.org_name) AS org, p.ein,
                       (array_agg(p.title ORDER BY p.tax_year DESC NULLS LAST))[1] AS role,
                       min(p.tax_year) AS first, max(p.tax_year) AS last
                FROM person_cluster_members m JOIN person_clusters c ON c.id = m.cluster_id
                JOIN people p ON p.id = m.person_id JOIN filings f ON f.id = p.filing_id
                LEFT JOIN organizations o ON o.ein = p.ein
                WHERE m.cluster_id = ANY(%(ids)s) AND coalesce(o.name, f.org_name) ~* ALL(%(pats)s)
                GROUP BY m.cluster_id, 3, p.ein ORDER BY max(p.tax_year) DESC LIMIT 50""", q).fetchall():
            hits.append({"source": "Form 990", "name": r["name"], "url": f"/person/{r['cluster_id']}", "role": r["role"],
                         "org": r["org"], "org_url": f"/org/{r['ein']}" if r["ein"] else None,
                         "first": r["first"], "last": r["last"]})
    if not norms:
        return hits
    for r in conn.execute("""
            SELECT p.name, p.relationships AS role, d.issuer_name AS org, d.accession, x.party_id,
                   min(d.filing_date) OVER w AS first, max(d.filing_date) OVER w AS last,
                   row_number() OVER (PARTITION BY d.cik, p.name_norm ORDER BY d.filing_date DESC) AS k
            FROM sec_formd_people p JOIN sec_formd d USING (accession)
            LEFT JOIN sec_formd_people_party x ON x.accession = p.accession AND x.seq = p.seq
            WHERE p.name_norm = ANY(%(norms)s) AND d.issuer_name ~* ALL(%(pats)s)
            WINDOW w AS (PARTITION BY d.cik, p.name_norm)
            ORDER BY d.filing_date DESC LIMIT 200""", q).fetchall():
        if r["k"] == 1:
            from app.formd_parties import url
            hits.append({"source": "Form D", "name": r["name"], "role": r["role"], "org": r["org"],
                         "url": url("person", r["party_id"], r["name"]) if r["party_id"] else None,
                         "org_url": f"/corporate/form-d/{r['accession']}", "first": r["first"], "last": r["last"]})
    for r in conn.execute("""
            SELECT o.name, o.name_norm, o.crd, n.name AS org, (array_agg(DISTINCT initcap(o.title)))[1:3] AS roles,
                   min(o.year) AS first, max(o.year) AS last, min(a.id) AS adv_id, min(a.formd_party_id) AS party_id,
                   min(a.cluster_id) AS cluster_id, min(a.name) AS shown
            FROM adv_owners o
            JOIN LATERAL (SELECT coalesce(f.business_name, f.legal_name) AS name, f.legal_name FROM adv_filings f
                          WHERE f.crd = o.crd ORDER BY f.submitted DESC NULLS LAST LIMIT 1) n ON true
            LEFT JOIN adv_people a ON a.name_norm = o.name_norm AND o.crd = ANY(a.crds)
            WHERE o.name_norm = ANY(%(norms)s) AND (n.name ~* ALL(%(pats)s) OR n.legal_name ~* ALL(%(pats)s))
            GROUP BY 1, 2, 3, 4 ORDER BY max(o.year) DESC LIMIT 50""", q).fetchall():
        from app.formd_parties import url
        shown = r["shown"] or nm["norms"].get(r["name_norm"]) or r["name"]
        hits.append({"source": "Form ADV", "name": shown,
                     "role": ", ".join(x for x in r["roles"] or [] if x), "org": r["org"],
                     "url": (f"/person/{r['cluster_id']}" if r["cluster_id"] else
                             url("person", r["party_id"], shown) if r["party_id"] else
                             url("adviser", r["adv_id"], shown) if r["adv_id"] else None),
                     "org_url": f"https://adviserinfo.sec.gov/firm/summary/{r['crd']}",
                     "org_external": True, "first": r["first"], "last": r["last"]})
    for r in conn.execute("""
            SELECT o.owner_name AS name, o.owner_cik, f.issuer_name AS org, f.issuer_cik,
                   (array_agg(coalesce(nullif(o.title, ''), o.relationship) ORDER BY f.filing_date DESC))[1] AS role,
                   min(f.filing_date) AS first, max(f.filing_date) AS last
            FROM sec_insider_owners o JOIN sec_insider_filings f USING (accession)
            WHERE o.name_norm = ANY(%(norms)s) AND f.issuer_name ~* ALL(%(pats)s)
            GROUP BY 1, 2, 3, 4 ORDER BY max(f.filing_date) DESC LIMIT 30""", q).fetchall():
        from app.slugs import canonical
        hits.append({"source": "SEC insider filings", "name": r["name"], "role": r["role"], "org": r["org"],
                     "url": canonical("insider", r["owner_cik"], r["name"]) if r["owner_cik"] else None,
                     "org_url": canonical("company", r["issuer_cik"], r["org"]) if r["issuer_cik"] else None,
                     "first": r["first"], "last": r["last"]})
    for r in conn.execute("""
            SELECT p.name, p.role, e.name AS org, e.state, e.entity_id, e.formed
            FROM biz_people p JOIN biz_entities e USING (state, entity_id)
            WHERE p.name_norm = ANY(%(norms)s) AND e.name ~* ALL(%(pats)s) LIMIT 30""", q).fetchall():
        hits.append({"source": "State business registration", "name": r["name"].title() if r["name"].isupper() else r["name"],
                     "role": r["role"], "org": f"{r['org']} ({r['state']})",
                     "org_url": f"/business/{r['state']}/{r['entity_id']}", "url": None,
                     "first": r["formed"], "last": None})
    return hits


def roster(conn, orgs: list[dict], limit: int = 100) -> list[dict]:
    """Everyone named on Form D or Form ADV for these organizations, grouped by person."""
    ciks = [o["cik"] for o in orgs if o.get("cik")]
    crds = [o["crd"] for o in orgs if o.get("crd")]
    return people_for(conn, ciks=ciks, crds=crds, limit=limit)


def fund_roster(ciks=(), crds=(), accessions=(), limit: int = 200) -> list[dict]:
    """The People section of a fund or adviser page (owner, 2026-10-29): everyone on any Form D of these issuers
    (given directly, or as filings of theirs) and on Form ADV for these advisers and the advisers of these issuers'
    funds (adv_fund_links). Empty on any error: an extra on the page."""
    ciks, crds, accessions = [c for c in ciks if c], [c for c in crds if c], [a for a in accessions if a]
    if not (ciks or crds or accessions):
        return []
    try:
        with db.conn(timeout="4s") as conn:
            if accessions:
                ciks += [r["cik"] for r in conn.execute("SELECT DISTINCT cik FROM sec_formd WHERE accession = ANY(%s) "
                                                        "AND cik IS NOT NULL", (accessions,)).fetchall()]
            ciks = sorted(set(ciks))[:300]
            if ciks:
                crds += [r["crd"] for r in conn.execute("""
                    SELECT DISTINCT f.crd FROM sec_formd_offerings o JOIN adv_fund_links l USING (root_accession)
                    JOIN adv_funds f ON f.fund_id = l.fund_id WHERE o.cik = ANY(%s) AND f.crd IS NOT NULL""",
                    (ciks,)).fetchall()]
            return people_for(conn, ciks=ciks, crds=sorted(set(crds))[:20], accessions=accessions, limit=limit)
    except Exception:  # noqa: BLE001
        log.exception("fund roster")
        return []


def people_for(conn, ciks=(), crds=(), accessions=(), limit: int = 200) -> list[dict]:
    """The People section of fund and adviser pages: every person on any Form D of these issuers (or these filings)
    and any Form ADV of these advisers, with roles, the filings' organizations, and first and last dates."""
    from app.formd_parties import url
    from loader.formd_parties import classify
    people: dict[str, dict] = {}
    if ciks or accessions:
        for r in conn.execute("""
                SELECT p.name, p.name_norm, p.relationships, d.issuer_name, d.filing_date, x.party_id, pt.kind,
                       pt.cluster_id
                FROM sec_formd d JOIN sec_formd_people p USING (accession)
                LEFT JOIN sec_formd_people_party x ON x.accession = p.accession AND x.seq = p.seq
                LEFT JOIN sec_formd_parties pt ON pt.id = x.party_id
                WHERE d.cik = ANY(%s) OR d.accession = ANY(%s)
                ORDER BY d.filing_date""", (list(ciks), list(accessions))).fetchall():
            if r["kind"] == "entity" or (r["kind"] is None and classify(r["name"])[0] == "entity"):
                continue
            key = r["name_norm"] or r["name"]
            p = people.setdefault(key, {"name": r["name"], "roles": set(), "orgs": [], "first": None, "last": None,
                                        "sources": set(), "url": None})
            p["sources"].add("Form D")
            p["roles"].update(x.strip() for x in (r["relationships"] or "").split(",") if x.strip())
            if r["issuer_name"] not in p["orgs"]:
                p["orgs"].append(r["issuer_name"])
            _span(p, r["filing_date"])
            p["name"] = r["name"]
            if r["party_id"]:
                p["url"] = f"/person/{r['cluster_id']}" if r["cluster_id"] else url("person", r["party_id"], r["name"])
    if crds:
        from loader.fund_people import display_name
        for r in conn.execute("""
                SELECT o.name, o.name_norm, initcap(o.title) AS title, o.year, o.crd, a.id AS adv_id, a.cluster_id,
                       a.formd_party_id, (SELECT coalesce(f.business_name, f.legal_name) FROM adv_filings f
                                          WHERE f.crd = o.crd ORDER BY f.submitted DESC NULLS LAST LIMIT 1) AS adviser
                FROM adv_owners o
                LEFT JOIN adv_people a ON a.name_norm = o.name_norm AND o.crd = ANY(a.crds)
                WHERE o.crd = ANY(%s) AND o.entity_kind = 'I' ORDER BY o.year""", (list(crds),)).fetchall():
            key = r["name_norm"] or r["name"]
            p = people.setdefault(key, {"name": display_name(r["name"]), "roles": set(), "orgs": [], "first": None,
                                        "last": None, "sources": set(), "url": None})
            p["sources"].add("Form ADV")
            if r["title"]:
                p["roles"].add(r["title"])
            if r["adviser"] and r["adviser"] not in p["orgs"]:
                p["orgs"].append(r["adviser"])
            _span(p, r["year"])
            if not p["url"] and r["adv_id"]:
                p["url"] = (f"/person/{r['cluster_id']}" if r["cluster_id"] else
                            url("person", r["formd_party_id"], p["name"]) if r["formd_party_id"] else
                            url("adviser", r["adv_id"], p["name"]))
    out = sorted(people.values(), key=lambda p: (-(len(p["orgs"])), -_year(p["last"]), p["name"]))
    for p in out:
        p["roles"] = ", ".join(sorted(p["roles"]))
        p["sources"] = " and ".join(sorted(p["sources"]))
        p["orgs"] = list(reversed(p["orgs"]))         # newest first
        p["when"] = when(p["first"], p["last"])
    return out[:limit]


def when(first, last) -> str:
    """"2018-2024", "2020", or ""."""
    a, b = _year(first), _year(last)
    if not a and not b:
        return ""
    return str(a or b) if not (a and b) or a == b else f"{a}-{b}"


def _year(v) -> int:
    return v if isinstance(v, int) else (v.year if v else 0)


def _span(p: dict, v) -> None:
    if v is None:
        return
    if p["first"] is None or _year(v) < _year(p["first"]):
        p["first"] = v
    if p["last"] is None or _year(v) > _year(p["last"]):
        p["last"] = v


def check(person: str, org: str) -> dict:
    """Is this person listed at this organization in any source? Hits (Form D and ADV first), the organizations
    matched, and who is listed there."""
    words = org_words(org)
    out = {"person": " ".join(person.split()), "org": " ".join(org.split()), "words": words, "hits": [], "orgs": [],
           "roster": [], "sources": SOURCES, "listed": False, "listed_fund": False, "error": False}
    if not words or not _name_params(person):
        return out
    try:
        with db.conn(timeout=TIMEOUT) as conn:
            nm = names(conn, person)
            out["hits"] = _hits(conn, nm, words)
            out["orgs"] = matching_orgs(conn, org)
            out["roster"] = roster(conn, out["orgs"])
    except Exception:  # noqa: BLE001 - say it could not be checked; never a 500
        log.exception("affiliation %r at %r", person, org)
        out["error"] = True
        return out
    out["hits"].sort(key=lambda h: (h["source"] not in FUND_SOURCES, -_year(h["last"] or h["first"])))
    for h in out["hits"]:
        h["when"] = when(h["first"], h["last"])
    out["listed"] = bool(out["hits"])
    out["listed_fund"] = any(h["source"] in FUND_SOURCES for h in out["hits"])
    return out


def split(q: str) -> tuple[str, str] | None:
    """A search for a person at an organization: "Tony Yang, Mucker Capital" (a comma after a full name) or
    "Tony Yang Mucker" (a known name followed by words that name an organization, when the whole is nobody's name
    and no organization's). None for anything else, including "Yang, Tony" and "Tony Yang, Jr."."""
    raw = " ".join((q or "").split())
    if "," in raw:
        a, b = (x.strip() for x in raw.split(",", 1))
        rest = re.findall(r"[a-z]+", b.lower())
        if len(a.split()) < 2 or not rest or all(w in SUFFIXES or w in DROP for w in rest):
            return None
        return (a, b) if org_words(b) else None
    words = raw.split()
    if len(words) < 3:
        return None
    try:
        with db.conn(timeout="3s") as conn:
            if has_person(conn, raw) or _is_org_name(conn, raw):
                return None
            for k in range(len(words) - 1, 1, -1):
                person, org = " ".join(words[:k]), " ".join(words[k:])
                if not [w for w in org_words(org) if w not in GENERIC]:
                    continue                    # "John Smith Foundation": an organization's name, not a person at one
                if has_person(conn, person) and matching_orgs(conn, org, limit=1):
                    return person, org
    except Exception:  # noqa: BLE001 - an extra; a plain name search still runs
        log.exception("affiliation split %r", q)
    return None


def _is_org_name(conn, q: str) -> bool:
    from app.names import normalize_org
    n = normalize_org(q)
    return bool(n) and conn.execute("SELECT 1 FROM organizations WHERE name_norm = %s LIMIT 1", (n,)).fetchone() is not None


def answer_text(r: dict, fund_only: bool = False) -> str:
    """Yes or no, from the filings. fund_only: the question asked about Form D and ADV (the AI query mode); other
    sources are then mentioned after the answer."""
    who, at = r["person"], r["org"]
    if r["error"]:
        return f"We couldn't check {who} at {at} just now; please try again."
    fund = [h for h in r["hits"] if h["source"] in FUND_SOURCES]
    if fund:
        names = sorted({h["org"] for h in fund})
        return (f"Yes. {who} is listed on {len(fund)} Form D or Form ADV record{'s' if len(fund) != 1 else ''} for "
                f"{', '.join(names[:3])}{' and others' if len(names) > 3 else ''}.")
    other = sorted({h["source"] for h in r["hits"]})
    if fund_only:
        no = f"No. No Form D or Form ADV filing lists {who} at an organization matching “{at}”."
        if other:
            no += f" {who} does appear with a matching organization in {', '.join(other)} (below)."
    elif other:
        return (f"Listed in {', '.join(other)}: {who} with an organization matching “{at}”. No Form D or Form ADV "
                f"filing lists them there.")
    else:
        no = f"No filing lists {who} at an organization matching “{at}”."
    if not r["orgs"]:
        no += f" No Form D issuer, investment adviser or nonprofit matching “{at}” was found either."
    return no
