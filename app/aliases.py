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
SOURCE_LABEL = {"dba": "doing-business-as name", "website": "website", "acronym": "initials of its name",
                "llm": "common short name"}


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
                    WHERE a.alias_norm = %s
                    GROUP BY o.ein, o.name, o.city, o.state, o.latest_total_revenue, o.latest_filing_year, o.daf_sponsor
                    ORDER BY o.latest_total_revenue DESC NULLS LAST, o.ein LIMIT %s""", (n, SHOWN)).fetchall()
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
