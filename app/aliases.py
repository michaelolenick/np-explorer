"""Common names and acronyms for organizations (org_aliases): "INSEAD" means the filer whose returns spell its
name "Institut Eupropeen d Administration des Affaires INSEAD". Only status 'live' rows are used; proposals wait
for review (scripts/propose_aliases.py)."""

from __future__ import annotations

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
