"""People and organizations named as related persons on Form D (loader/formd_parties.py): their pages, the links
from Form D pages, and the "Private fund roles" section on person pages.

An organization's page (/corporate/entity/<slug>-<id>) lists every Form D it's named on and the records with the
same business name elsewhere on the site (a Form D issuer, an investment adviser, a nonprofit). A person's page
(/corporate/fund-person/<slug>-<id>) is for someone not matched to a person on the site; those who are matched
link to their /person page, which carries the same "Private fund roles" section.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import db
from app.corporate import PUBLIC

router = APIRouter()
log = logging.getLogger("np.formd_parties")
PREFIX = {"entity": "/corporate/entity/", "person": "/corporate/fund-person/", "adviser": "/corporate/adviser-person/"}


def clean_text(s):
    from loader.formd_parties import clean_text as c
    return c(s)


def url(kind: str, party_id, name: str) -> str:
    from app.slugs import slug
    return f"{PREFIX[kind]}{slug(name)}-{party_id}"


def _roles(conn, where: str, params) -> list[dict]:
    rows = conn.execute(f"""
        SELECT d.accession, d.issuer_name, d.filing_date, d.amount_sold, d.offering_amount, d.offering_indefinite,
               p.relationships, p.clarification, p.city, p.state, x.party_id
        FROM sec_formd_people p JOIN sec_formd d USING (accession)
        LEFT JOIN sec_formd_people_party x ON x.accession = p.accession AND x.seq = p.seq
        WHERE {where} ORDER BY d.filing_date DESC NULLS LAST LIMIT 300""", params).fetchall()
    out, seen = [], set()
    for r in rows:
        r["relationships"], r["clarification"] = clean_text(r["relationships"]), clean_text(r["clarification"])
        k = (r["accession"], r["relationships"], r["clarification"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _adv_roles(conn, name_norm: str | None, state: str | None, cluster_id: int | None, crds=None) -> list[dict]:
    """Investment advisers listing this person as an owner or control person (Form ADV Schedules A and B)."""
    if crds and name_norm:
        cond, params = "o.name_norm = %s AND o.crd = ANY(%s)", (name_norm, list(crds))
    elif cluster_id:
        cond, params = "o.crd IN (SELECT crd FROM adv_person_links WHERE cluster_id = %s) AND o.name_norm IN " \
                       "(SELECT name_norm FROM adv_person_links WHERE cluster_id = %s)", (cluster_id, cluster_id)
    elif name_norm and state:
        cond, params = ("o.name_norm = %s AND EXISTS (SELECT 1 FROM adv_filings f WHERE f.crd = o.crd AND f.state = %s)",
                        (name_norm, state))
    else:
        return []
    return conn.execute(f"""
        SELECT o.crd, min(o.year) AS first, max(o.year) AS last, bool_or(o.control_person) AS control,
               (array_agg(o.title ORDER BY o.year DESC))[1] AS title,
               (SELECT coalesce(f.business_name, f.legal_name) FROM adv_filings f WHERE f.crd = o.crd
                ORDER BY f.submitted DESC NULLS LAST LIMIT 1) AS adviser,
               (SELECT count(DISTINCT a.fund_id) FROM adv_funds a WHERE a.crd = o.crd) AS funds
        FROM adv_owners o WHERE {cond} GROUP BY o.crd ORDER BY max(o.year) DESC LIMIT 30""", params).fetchall()


def private_fund_roles(cluster_id: int) -> dict | None:
    """The "Private fund roles" section of a /person page: Form D filings naming this person (linked by name and
    state) and investment advisers listing them as an owner or control person."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '4s'")
            keys = [r["key"] for r in conn.execute("SELECT key FROM sec_person_links WHERE cluster_id = %s AND "
                                                   "source = 'formd'", (cluster_id,)).fetchall()]
            parties = [r["id"] for r in conn.execute("SELECT id FROM sec_formd_parties WHERE cluster_id = %s",
                                                     (cluster_id,)).fetchall()]
            # Two indexed lookups (an OR across them scans every related person): rows linked one by one, and
            # rows of the people grouped under this person.
            pairs = [k.split(":") for k in keys]
            formd = (_roles(conn, "(p.accession, p.seq) IN (SELECT a, s::int FROM unnest(%s::text[], %s::text[]) AS t(a, s))",
                            ([a for a, _ in pairs], [s for _, s in pairs])) if pairs else []) + \
                (_roles(conn, "x.party_id = ANY(%s)", (parties,)) if parties else [])
            seen = set()
            formd = [r for r in sorted(formd, key=lambda r: r["filing_date"] or 0, reverse=True)
                     if (k := (r["accession"], r["relationships"], r["clarification"])) not in seen and not seen.add(k)]
            adv = _adv_roles(conn, None, None, cluster_id)
    except Exception:  # noqa: BLE001
        log.exception("private fund roles %s", cluster_id)
        return None
    return {"formd": formd, "adv": adv, "fuzzy": True} if formd or adv else None


def party(party_id: int) -> dict | None:
    from app.funders import normalize_org
    from loader.recalls import core
    with db.conn() as conn:
        p = conn.execute("SELECT * FROM sec_formd_parties WHERE id = %s", (party_id,)).fetchone()
        if not p:
            return None
        formd = _roles(conn, "x.party_id = %s", (party_id,))
        out = {"p": p, "formd": formd, "adv": [], "matches": [], "cluster": None, "fund_people": []}
        if p["kind"] == "person":
            link = conn.execute("""SELECT pc.id AS cluster_id, pc.display_name FROM person_clusters pc
                                   WHERE pc.id = coalesce(%s, (
                                       SELECT l.cluster_id FROM sec_formd_people_party x
                                       JOIN sec_person_links l ON l.source = 'formd' AND l.key = x.accession || ':' || x.seq
                                       WHERE x.party_id = %s LIMIT 1))""", (p.get("cluster_id"), party_id)).fetchone()
            out["cluster"] = link
            out["adv"] = _adv_roles(conn, p["name_norm"], p["state"], link["cluster_id"] if link else None)
            return out
        # An organization: the same business name as a Form D issuer, an investment adviser or a nonprofit; and the
        # people on the Form D filings it's named on.
        from app import affiliation
        out["fund_people"] = affiliation.fund_roster(accessions=[r["accession"] for r in formd])
        c = p["name_norm"]
        head = " ".join(c.split()[:2])
        for r in conn.execute("""SELECT DISTINCT ON (cik) latest_accession, issuer_name, cik FROM sec_formd_offerings
                                 WHERE lower(issuer_name) LIKE %s ORDER BY cik, latest_date DESC LIMIT 200""",
                              (head + "%",)).fetchall():
            if core(r["issuer_name"]) == c:
                out["matches"].append({"kind": "Form D issuer", "name": r["issuer_name"],
                                       "url": f"/corporate/form-d/{r['latest_accession']}"})
        for r in conn.execute("""SELECT DISTINCT ON (crd) crd, legal_name, business_name FROM adv_filings
                                 WHERE lower(legal_name) LIKE %s OR lower(business_name) LIKE %s
                                 ORDER BY crd, submitted DESC LIMIT 50""", (head + "%", head + "%")).fetchall():
            if c in (core(r["legal_name"]), core(r["business_name"])):
                out["matches"].append({"kind": "Investment adviser (Form ADV)", "name": r["business_name"] or r["legal_name"],
                                       "url": f"https://adviserinfo.sec.gov/firm/summary/{r['crd']}", "external": True})
        for r in conn.execute("SELECT ein, name FROM organizations WHERE name_norm = %s LIMIT 5",
                              (normalize_org(p["name"]),)).fetchall():
            out["matches"].append({"kind": "Nonprofit", "name": r["name"], "url": f"/org/{r['ein']}"})
        return out


def adviser_person(adv_id: int) -> dict | None:
    """A person on Form ADV with no Form D page (adv_people, loader/fund_people.py): the advisers listing them."""
    with db.conn() as conn:
        a = conn.execute("SELECT * FROM adv_people WHERE id = %s", (adv_id,)).fetchone()
        if not a:
            return None
        if a["formd_party_id"]:
            return {"redirect": url("person", a["formd_party_id"], a["name"])}
        cluster = conn.execute("SELECT id AS cluster_id, display_name FROM person_clusters WHERE id = %s",
                               (a["cluster_id"],)).fetchone() if a["cluster_id"] else None
        adv = _adv_roles(conn, a["name_norm"], a["state"], None, crds=a["crds"])
    p = {"id": a["id"], "kind": "person", "name": a["name"], "state": a["state"], "filings": 0, "last_date": None}
    return {"p": p, "formd": [], "adv": adv, "matches": [], "cluster": cluster, "fund_people": [], "adviser_only": True}


def _parse(key: str) -> int | None:
    m = re.search(r"(?:^|-)(\d+)$", key or "")
    return int(m.group(1)) if m else None


def _page(request: Request, kind: str, key: str):
    from app.corporate import _render
    pid = _parse(key)
    data = party(pid) if PUBLIC and pid else None
    if not data or data["p"]["kind"] != kind:
        raise HTTPException(404)
    want = url(kind, pid, data["p"]["name"])
    if request.url.path != want:
        return RedirectResponse(want, status_code=301)
    return _render(request, "formd_party.html", page_url=want, **data)


@router.get("/corporate/entity/{key}", response_class=HTMLResponse)
def entity_page(request: Request, key: str):
    return _page(request, "entity", key)


@router.get("/corporate/fund-person/{key}", response_class=HTMLResponse)
def person_page(request: Request, key: str):
    return _page(request, "person", key)


@router.get("/corporate/adviser-person/{key}", response_class=HTMLResponse)
def adviser_person_page(request: Request, key: str):
    from app.corporate import _render
    pid = _parse(key)
    data = adviser_person(pid) if PUBLIC and pid else None
    if not data:
        raise HTTPException(404)
    if data.get("redirect"):
        return RedirectResponse(data["redirect"], status_code=301)
    want = url("adviser", pid, data["p"]["name"])
    if request.url.path != want:
        return RedirectResponse(want, status_code=301)
    return _render(request, "formd_party.html", page_url=want, **data)
