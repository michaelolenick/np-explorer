"""Common names and acronyms for organizations (org_aliases): "INSEAD" means the filer whose returns spell its
name "Institut Eupropeen d Administration des Affaires INSEAD". Only status 'live' rows are used; proposals wait
for review (scripts/propose_aliases.py)."""

from __future__ import annotations

import re

from app import db


def alias_norm(name: str) -> str:
    from app.funders import _core, normalize_org
    return _core(normalize_org(name or ""))


def lookup(name: str) -> dict | None:
    """{alias, note, primary: org, affiliates: [orgs]} for a live alias, else None. Orgs carry name, state and
    latest revenue so pages can show the size difference."""
    n = alias_norm(name)
    if not n:
        return None
    try:
        with db.conn() as conn:
            rows = conn.execute("""
                SELECT a.alias, a.role, a.note, o.ein, o.name, o.name_norm, o.city, o.state, o.latest_total_revenue,
                       o.latest_filing_year
                FROM org_aliases a JOIN organizations o ON o.ein = a.ein
                WHERE a.alias_norm = %s AND a.status = 'live'
                ORDER BY a.role = 'primary' DESC, o.latest_total_revenue DESC NULLS LAST""", (n,)).fetchall()
    except Exception:  # noqa: BLE001 - table missing: no aliases
        return None
    primary = next((r for r in rows if r["role"] == "primary"), None)
    if not primary:
        return None
    return {"alias": primary["alias"], "note": primary["note"], "primary": primary,
            "affiliates": [r for r in rows if r["role"] == "affiliate"],
            "evidence": f"“{primary['alias']}” is the common name for {primary['name']} (the name as filed)."}


SHOWN = 5          # an ambiguous short name shows this many organizations, largest first


def squash(n: str) -> str:
    """A normalized name without spaces: "red cross" and the website name "redcross" are the same short name
    (index org_alt_names_squash)."""
    return (n or "").replace(" ", "")


_ORG_COLS = """o.ein, o.name, o.name_norm, o.city, o.state, o.ntee, o.latest_filing_year, o.latest_total_revenue,
                o.latest_total_assets, o.latest_num_employees, o.daf_sponsor, o.daf_last_year"""


def orgs_for(name: str, limit: int = SHOWN) -> list[dict]:
    """The organizations a name is known as, largest first: a live alias's organization and its affiliates,
    else the alternate names (DBAs, website names, initials, common short names). Whole-name matches only."""
    al = lookup(name)
    try:
        with db.conn() as conn:
            if al:
                eins = [al["primary"]["ein"]] + [a["ein"] for a in al["affiliates"]]
                rows = conn.execute(f"SELECT {_ORG_COLS} FROM organizations o WHERE o.ein = ANY(%s)", (eins,)).fetchall()
                return sorted(rows, key=lambda r: eins.index(r["ein"]))[:limit]
            n = squash(alias_norm(name))
            if len(n) < 2:
                return []
            return conn.execute(f"""SELECT {_ORG_COLS} FROM organizations o WHERE o.ein IN (
                                        SELECT ein FROM org_alt_names WHERE replace(alias_norm, ' ', '') = %s)
                                     ORDER BY o.latest_total_revenue DESC NULLS LAST, o.ein LIMIT %s""",
                                (n, limit)).fetchall()
    except Exception:  # noqa: BLE001 - tables missing: no alternate names
        return []


# Words that are never a short name on their own, at either end of a span ("who runs uli" -> "uli").
HINT_SKIP = set("""who whom whose what which where when how why is are was were the a an of in at for on and or to from
does do did run runs pay paid make makes earn earns ceo cfo president board revenue revenues by year years highest
people top largest biggest funds fund funded funders leads lead led me show list find near its their much many most
s salary salaries grants grant give gave staff officers director directors trustees spending expenses assets
over time history all every any nonprofit nonprofits charity charities organization organizations""".split())


def hints(q: str, per: int = 3, most: int = 6) -> list[dict]:
    """Short names in a question that the site knows, for the model that reads questions: [{text, orgs}] with
    up to `per` organizations each, largest first ("uli in austin" -> "uli": Urban Land Institute, ...)."""
    words = [w[:-2] if w.endswith("'s") else w for w in re.findall(r"[a-z0-9&']+", (q or "").lower())]
    spans: dict[str, str] = {}
    for n in (4, 3, 2, 1):
        for i in range(len(words) - n + 1):
            span = words[i:i + n]
            if span[0] in HINT_SKIP or span[-1] in HINT_SKIP:
                continue
            key = squash(alias_norm(" ".join(span)))
            if len(key) >= 2:
                spans.setdefault(key, " ".join(span))
    if not spans:
        return []
    try:
        with db.conn() as conn:
            rows = conn.execute("""
                SELECT k, ein, name, city, state, rev FROM (
                    SELECT k, ein, name, city, state, rev,
                           row_number() OVER (PARTITION BY k ORDER BY pri DESC, rev DESC NULLS LAST, ein) AS rk
                    FROM (SELECT DISTINCT ON (k, ein) * FROM (
                        SELECT replace(a.alias_norm, ' ', '') AS k, o.ein, o.name, o.city, o.state,
                               o.latest_total_revenue AS rev, a.role = 'primary' AS pri
                        FROM org_aliases a JOIN organizations o ON o.ein = a.ein
                        WHERE a.status = 'live' AND replace(a.alias_norm, ' ', '') = ANY(%(k)s)
                        UNION ALL
                        SELECT replace(a.alias_norm, ' ', ''), o.ein, o.name, o.city, o.state, o.latest_total_revenue,
                               false
                        FROM org_alt_names a JOIN organizations o ON o.ein = a.ein
                        WHERE replace(a.alias_norm, ' ', '') = ANY(%(k)s)) u
                        ORDER BY k, ein, pri DESC) d) r
                WHERE rk <= %(per)s ORDER BY k, rk""", {"k": list(spans), "per": per}).fetchall()
    except Exception:  # noqa: BLE001 - an aid for the model; never fail a question
        return []
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["k"], {"text": spans[r["k"]], "orgs": []})["orgs"].append(r)
    # Longer spans first ("urban land institute" before "land"); the largest organization breaks ties.
    return sorted(out.values(), key=lambda h: (-len(h["text"]), -(h["orgs"][0]["rev"] or 0)))[:most]
SOURCE_LABEL = {"dba": "doing-business-as name", "website": "website", "acronym": "initials of its name",
                "llm": "common short name", "former": "earlier name on its returns"}


def alt_matches(q: str) -> dict | None:
    """Organizations known by the name typed (org_alt_names: DBAs, website names, acronyms, common short names),
    largest first: {alias, orgs, total, chapter}. When nothing matches the whole query but its first word or two
    is a short name ("ULI Austin"), the organizations for that short name are returned with chapter set to the
    rest of the query: a chapter or council that files no return of its own lands on its parent."""
    words = (q or "").split()
    tries = [(q, None)] + [(" ".join(words[:k]), " ".join(words[k:])) for k in (2, 1) if len(words) > k]
    try:
        with db.conn() as conn:
            for text, rest in tries:
                n = alias_norm(text)
                if not n or len(n) < 2:
                    continue
                rows = conn.execute("""
                    SELECT o.ein, o.name, o.city, o.state, o.latest_total_revenue, o.latest_filing_year,
                           o.daf_sponsor, array_agg(DISTINCT a.source) AS sources, min(a.alias) AS alias,
                           count(*) OVER () AS total
                    FROM org_alt_names a JOIN organizations o ON o.ein = a.ein
                    WHERE replace(a.alias_norm, ' ', '') = %s
                    GROUP BY o.ein, o.name, o.city, o.state, o.latest_total_revenue, o.latest_filing_year, o.daf_sponsor
                    ORDER BY o.latest_total_revenue DESC NULLS LAST, o.ein LIMIT %s""", (squash(n), SHOWN)).fetchall()
                if rows and rest and len(squash(n)) > 6 and not any({"llm", "acronym"} & set(r["sources"]) for r in rows):
                    # "Memorial Sloan Kettring": "memorial" is only some hospitals' DBA or website, not a short name
                    # with a chapter after it. Short prefixes (ULI, YMCA) and known short names still split.
                    continue
                if rows:
                    if rest:
                        # The chapter may file its own return under its full name ("YMCA of Greater Seattle" is
                        # "Young Mens Christian Association of Greater Seattle"): names with the rest of the query
                        # whose initials start with the short name. Those are the answer, not the parent.
                        from loader.alt_names import acronym_letters
                        like = "%" + "%".join(alias_norm(rest).split()) + "%"
                        cands = conn.execute("""SELECT ein, name, city, state, latest_total_revenue, latest_filing_year,
                                                     daf_sponsor FROM organizations WHERE name_norm LIKE %s
                                                     ORDER BY latest_total_revenue DESC NULLS LAST LIMIT 300""",
                                             (like,)).fetchall()
                        letters = re.sub(r"[^a-z0-9]", "", text.lower())
                        own = [c for c in cands if acronym_letters(c["name"]).startswith(letters)][:SHOWN]
                        if own:
                            for c in own:
                                c["how"] = f"initials of its name, plus “{rest}”"
                            return {"alias": text, "orgs": own, "total": len(own), "chapter": None}
                    for r in rows:
                        r["how"] = ", ".join(SOURCE_LABEL.get(s, s) for s in sorted(r["sources"]))
                    return {"alias": rows[0]["alias"], "orgs": rows, "total": rows[0]["total"], "chapter": rest}
    except Exception:  # noqa: BLE001 - table missing: no alternate names
        return None
    return None


# --- abbreviations and full names (name_aliases, loader/name_aliases.py; owner, 2026-10-30) -----------------------

PAIRS_SHOWN = 3          # full names (or abbreviations) searched per query, hand-picked first, then best supported


def name_key(q: str) -> str:
    """A query normalized the way registry names are (biz_entities.name_core): "3M Company" and "3m" are "3m"."""
    from loader.recalls import core
    return core(q or "")


def name_pairs(q: str) -> list[dict]:
    """The other names a query also stands for: "IBM" gives International Business Machines, and "International
    Business Machines" gives IBM. [{short, long, other, label, source}], other being the normalized name to look
    up and label the text shown with each result ("IBM = International Business Machines")."""
    k = name_key(q)
    if not k:
        return []
    try:
        with db.conn() as conn:
            rows = conn.execute("""
                SELECT short, long, CASE WHEN short_norm = %(k)s THEN long_norm ELSE short_norm END AS other, source
                FROM name_aliases
                WHERE status = 'live' AND (short_norm = %(k)s OR long_norm = %(k)s)
                ORDER BY source = 'manual' DESC, support DESC, long LIMIT %(n)s""",
                                {"k": k, "n": PAIRS_SHOWN}).fetchall()
    except Exception:  # noqa: BLE001 - table missing: no pairs
        return []
    return [{**r, "label": f"{r['short']} = {r['long']}"} for r in rows if r["other"] and r["other"] != k]


_SUFFIX = re.compile(r"\s+(inc|incorporated|corp|corporation|co|company|llc|ltd|foundation|fund|trust|"
                     r"association|assn|society)$")


def pair_orgs(pairs: list[dict], skip: set | None = None, limit: int = SHOWN) -> list[dict]:
    """Nonprofits whose whole name (give or take Inc, Foundation...) is one of the pairs' other names, largest
    first, each with via set to the pair's label."""
    from loader.recalls import core
    out, skip = [], set(skip or ())
    try:
        with db.conn() as conn:
            for p in pairs:
                words = p["other"].split()
                rows = conn.execute(f"""SELECT {_ORG_COLS} FROM organizations o
                                        WHERE o.name_tsv @@ to_tsquery('simple', %s)
                                        ORDER BY o.latest_total_revenue DESC NULLS LAST LIMIT 500""",
                                    (" & ".join(words),)).fetchall()
                for r in rows:
                    c = core(r["name"])
                    if r["ein"] not in skip and p["other"] in (c, _SUFFIX.sub("", c)):
                        skip.add(r["ein"])
                        out.append({**r, "via": p["label"]})
    except Exception:  # noqa: BLE001 - an extra; never fail a search
        return out[:limit]
    return out[:limit]
