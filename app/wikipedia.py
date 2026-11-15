"""About (Wikipedia): short bios of the people and organizations on FURP pages that also have a Wikipedia article
(owner, 2026-11-14). Data: loader/wikipedia.py (schema `wiki`), from the official Wikidata (CC0) and English Wikipedia
(CC BY-SA 4.0) dumps; stored per entity: a short description and the first sentence or two of the lead (at most 300
characters), the article URL, the Wikidata QID, birth and death year, occupations, employers, website, founding year and
headquarters. Shown with visible attribution ("From Wikipedia, CC BY-SA 4.0", linked to the article and its history) on
every page that shows it, and on /data#wikipedia.

Only links whose method has a sampled precision high enough are shown (wiki.link.show, set by loader/wikipedia.py
publish). Living people: only what the lead already states (no years, occupations or employers from Wikidata), no photos."""

from __future__ import annotations

import os
from urllib.parse import quote, urlencode

from app import db
from app.cache import ttl_lru

PUBLIC = os.environ.get("WIKIPEDIA_PUBLIC", "1") == "1"
LICENSE_NAME = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
WD_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
KINDS = ("person", "org", "college", "sec", "sec_insider")
RANK = {"high": 0, "medium": 1, "low": 2}

# How each method made the link, in the words the page shows.
METHOD_TEXT = {
    "person_cik": "the same SEC filer number (CIK)",
    "person_org_ein": "Wikidata lists an employer or board seat that is an organization this person is on in the filings (IRS EIN match), and the name is the same",
    "person_org_ein_fl": "Wikidata lists an employer or board seat that is an organization this person is on in the filings (IRS EIN match), and the first and last name are the same",
    "person_org_name": "Wikidata lists an employer or board seat with the same name as an organization this person is on in the filings, and the name is the same",
    "person_org_name_fl": "Wikidata lists an employer or board seat with the same name as an organization this person is on in the filings, and the first and last name are the same",
    "insider_issuer": "Wikidata names a company (by its SEC CIK) as this person's employer, membership or board, and the insider filings at that company name the same person",
    "insider_issuer_fl": "Wikidata names a company (by its SEC CIK) as this person's employer, membership or board, and the insider filings at that company name a person with the same first and last name",
    "person_name_rare": "the same rare full name, the only one with it on Wikipedia and in the filings (no other signal; may be a different person)",
    "person_name_uncommon": "the same full name, an uncommon one, the only one with it on Wikipedia and in the filings (no other signal; may be a different person)",
    "person_name_only": "the same full name, the only one with it on Wikipedia and in the filings (no other signal; may be a different person)",
    "org_ein": "the same IRS employer identification number (EIN)",
    "org_website": "the same website address",
    "org_website_name": "the same website address and the same name",
    "org_name_city": "the same name and headquarters city",
    "org_name_citydesc": "the same name, the only organization with it on Wikipedia and in the filings, described by Wikidata in the same city and state",
    "org_name_state": "the same name, the only organization with it on Wikipedia and in the filings, described by Wikidata in the same state",
    "org_name_us": "the same name, the only organization with it on Wikipedia and in the filings, placed in the United States by Wikidata, with no state named",
    "org_name_only": "the same name, the only organization with it on Wikipedia and in the filings (no other signal)",
    "sec_cik": "the same SEC Central Index Key (CIK)",
    "college_ein": "the same IRS employer identification number (EIN)",
    "college_website_name": "the same website address and the same name",
    "college_website": "the same website address",
    "college_name": "the same name",
}


def article_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"), safe="_(),'!:;@$*-.~")


def history_url(title: str) -> str:
    return "https://en.wikipedia.org/w/index.php?" + urlencode({"title": title.replace(" ", "_"), "action": "history"})


def wikidata_url(qid: str) -> str:
    return f"https://www.wikidata.org/wiki/{qid}"


def gone_url(qid: str) -> str:
    """The English article for a Wikidata item, however its title changes (what the cross-references link to)."""
    return f"https://www.wikidata.org/wiki/Special:GoToLinkedPage/enwiki/{qid}"


def report_url(kind: str, key: str, title: str) -> str:
    return "/contact?" + urlencode({"topic": "Corrections", "subject": f"Wrong Wikipedia match: {title} on {kind} {key}"})


def _ready(conn) -> bool:
    return conn.execute("SELECT to_regclass('wiki.link') IS NOT NULL AS t").fetchone()["t"]


def is_living(e: dict) -> bool:
    """A person with no death date who was born after 1900 (or whose birth year is unknown) counts as living."""
    if e.get("kind") != "person":
        return False
    if e.get("death_year"):
        return False
    by = e.get("birth_year")
    return by is None or by > 1900


_SQL = """
SELECT l.method, l.confidence, l.evidence, e.qid, e.kind, e.label, e.title, e.wd_desc, e.short_desc, e.lead, e.birth_year,
       e.death_year, e.inception, e.dissolved, e.website, e.ein,
       (SELECT array_agg(x.label) FROM (SELECT lb.label FROM unnest(e.occ_q) WITH ORDINALITY u(q, o) JOIN wiki.label lb ON lb.qid = u.q ORDER BY u.o LIMIT 4) x) AS occupations,
       (SELECT array_agg(x.label) FROM (SELECT lb.label FROM unnest(coalesce(e.emp_q, '{}') || coalesce(e.mem_q, '{}')) WITH ORDINALITY u(q, o) JOIN wiki.label lb ON lb.qid = u.q ORDER BY u.o LIMIT 4) x) AS affiliations,
       (SELECT array_agg(x.label) FROM (SELECT lb.label FROM unnest(coalesce(e.hq_q, '{}')) WITH ORDINALITY u(q, o) JOIN wiki.label lb ON lb.qid = u.q ORDER BY u.o LIMIT 2) x) AS hq,
       (SELECT array_agg(x.label) FROM (SELECT lb.label FROM unnest(coalesce(e.p31_q, '{}')) WITH ORDINALITY u(q, o) JOIN wiki.label lb ON lb.qid = u.q ORDER BY u.o LIMIT 3) x) AS types
FROM wiki.link l JOIN wiki.entity e ON e.qid = l.qid
WHERE l.kind = %s AND l.key = %s AND l.show
ORDER BY CASE l.confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, l.method, e.qid LIMIT 1"""


@ttl_lru(ttl=300, maxsize=4096)
def about(kind: str, key: str) -> dict | None:
    """The "About (Wikipedia)" block of one page, or None. Never fails the page."""
    if not PUBLIC or kind not in KINDS or not key:
        return None
    try:
        with db.conn() as conn:
            if not _ready(conn):
                return None
            e = conn.execute(_SQL, (kind, str(key))).fetchone()
    except Exception:  # noqa: BLE001 - an extra section
        return None
    if not e or not e["title"]:
        return None
    e = dict(e)
    living = is_living(e)
    desc = e["short_desc"] or e["wd_desc"]
    out = {
        "qid": e["qid"], "kind": e["kind"], "title": e["title"], "label": e["label"] or e["title"], "url": article_url(e["title"]),
        "history_url": history_url(e["title"]), "wikidata_url": wikidata_url(e["qid"]), "description": desc, "lead": e["lead"],
        "living": living, "method": e["method"], "confidence": e["confidence"], "evidence": e["evidence"],
        "how": METHOD_TEXT.get(e["method"], e["method"]), "name_only": e["method"].endswith(("name_only", "name_rare", "name_uncommon")),
        "report_url": report_url(kind, str(key), e["title"]), "license": LICENSE_NAME, "license_url": LICENSE_URL,
        "years": None, "occupations": [], "affiliations": [], "facts": [],
    }
    if e["kind"] == "person" and not living:
        if e["birth_year"] or e["death_year"]:
            out["years"] = f"{e['birth_year'] or '?'}\u2013{e['death_year']}" if e["death_year"] else f"born {e['birth_year']}"
        out["occupations"] = e["occupations"] or []
        out["affiliations"] = e["affiliations"] or []
    if e["kind"] != "person":
        if e["inception"]:
            out["facts"].append(("Founded", str(e["inception"])))
        if e["dissolved"]:
            out["facts"].append(("Dissolved", str(e["dissolved"])))
        if e["hq"]:
            out["facts"].append(("Headquarters", ", ".join(e["hq"])))
        if e["types"]:
            out["facts"].append(("Type", ", ".join(e["types"])))
        if e["website"]:
            out["facts"].append(("Website", e["website"]))
    return out


def api_about(kind: str, key: str) -> dict | None:
    """The API and MCP view: the same short bio with its licence, for kinds that carry one."""
    a = about(kind, key)
    if not a:
        return None
    keep = ("qid", "title", "url", "history_url", "wikidata_url", "description", "lead", "method", "confidence", "how", "name_only",
            "years", "occupations", "affiliations", "facts")
    return {k: a[k] for k in keep} | {"attribution": f"From Wikipedia, {LICENSE_NAME}", "license_url": LICENSE_URL,
                                       "wikidata_license": "CC0", "living_person": a["living"]}


def summary() -> dict | None:
    """The /data#wikipedia numbers: entities, shown links by method with the sampled precision."""
    if not PUBLIC:
        return None
    try:
        with db.conn() as conn:
            if not _ready(conn):
                return None
            ent = conn.execute("""SELECT kind, count(*) AS n, count(lead) AS leads FROM wiki.entity GROUP BY kind""").fetchall()
            links = conn.execute("""SELECT l.kind, l.method, count(*) AS n, count(*) FILTER (WHERE l.show) AS shown,
                                           p.judged, p.correct FROM wiki.link l LEFT JOIN wiki.precision p USING (method)
                                    GROUP BY l.kind, l.method, p.judged, p.correct ORDER BY l.kind, l.method""").fetchall()
            dump = conn.execute("SELECT max(dump_date) AS d FROM wiki.entity").fetchone()["d"]
            return {"entities": {r["kind"]: r for r in ent}, "links": links, "dump": dump,
                    "shown": sum(r["shown"] for r in links)}
    except Exception:  # noqa: BLE001
        return None
