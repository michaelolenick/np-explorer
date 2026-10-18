"""One organization's figures year by year, with derived columns and year filters (natural-language search).

The model only picks from fixed menus (metrics, a condition, numbers); every calculation is SQL written here:
surplus = revenue - expenses, year-over-year % change, a running total over the selected years, and the year
filters. One return per tax year: the latest (an amended return replaces the original). A missing value is
NULL, shown as Not reported; it is never treated as 0 in a calculation.
"""

from __future__ import annotations

import re

from app import db

# metric -> (label, SQL over the chosen filing f; NULL when not reported)
METRICS = {
    "revenue": ("Revenue", "f.total_revenue"),
    "expenses": ("Expenses", "f.total_expenses"),
    "assets": ("Total assets", "f.total_assets_eoy"),
    "liabilities": ("Total liabilities", "f.total_liabilities_eoy"),
    "net_assets": ("Net assets", "f.net_assets_eoy"),
    "surplus": ("Surplus or deficit (revenue minus expenses)", "f.total_revenue - f.total_expenses"),
    "program_expenses": ("Program expenses", "NULL::numeric"),
    "fundraising_expenses": ("Fundraising expenses", "f.fundraising_expenses"),
    "contributions": ("Contributions", "f.contributions"),
}
NOT_LOADED = {"program_expenses": "Program service expenses (Part IX, column B) are not loaded yet, so they show as "
                                  "Not reported."}
CONDITIONS = {
    "a_up_b_down": "{a} rose while {b} fell (from the year before)",
    "above": "{a} above {x}",
    "below": "{a} below {x}",
    "rose_more_than": "{a} rose more than {p}% from the year before",
    "fell_more_than": "{a} fell more than {p}% from the year before",
    "deficit": "a deficit (expenses more than revenue)",
}
DOMINANT = 5       # a same-named organization this many times larger than the next is taken as the one meant (FUZZY)


def condition_text(c: dict) -> str:
    if not c or not c.get("condition"):
        return ""
    lab = {k: v[0].lower() for k, v in METRICS.items()}
    return CONDITIONS[c["condition"]].format(a=lab.get(c.get("metric_a"), "?"), b=lab.get(c.get("metric_b"), "?"),
                                             x=f"${c.get('threshold') or 0:,.0f}", p=f"{c.get('percent') or 0:g}")


# --- which organization ------------------------------------------------------------------------------

def resolve(name: str, state: str | None = None) -> tuple[dict | None, list[dict]]:
    """(org with match + evidence, []) or (None, candidates). Order: an organization whose name is the one asked
    for; a school's own return or its one US affiliate (school links, EXACT); the one same-named organization far
    larger than the rest (FUZZY, with the reason); otherwise the candidates, never a guess."""
    from app import colleges, funders
    org, choices = funders.resolve_org(name, state)
    if org and org.get("alias"):
        al = org["alias"]
        return {**org, "match": "EXACT", "evidence": f"Common name for {al['primary']['name']}.",
                "affiliates": al["affiliates"]}, []
    if org:
        return {**org, "match": "EXACT", "evidence": "The organization's name is the name asked for."}, []
    inst, _ = colleges.resolve(name, state) if colleges.available() else (None, [])
    if inst:
        with db.conn() as conn:
            links = conn.execute("""SELECT co.ein, co.relation, o.name, o.state, o.latest_total_revenue
                                    FROM college_orgs co JOIN organizations o ON o.ein = co.ein
                                    WHERE co.unitid = %s AND co.match = 'EXACT' AND co.relation IN ('self', 'foundation')
                                    ORDER BY co.relation = 'self' DESC, o.latest_total_revenue DESC NULLS LAST""",
                                 (inst["unitid"],)).fetchall()
        selfs = [l for l in links if l["relation"] == "self"]
        pick = selfs[0] if len(selfs) == 1 else (links[0] if len(links) == 1 else None)
        if pick:
            how = ("files the school's own return" if pick["relation"] == "self"
                   else "is the school's only EXACT-linked US affiliate")
            return {"ein": pick["ein"], "name": pick["name"], "state": pick["state"], "match": "EXACT",
                    "evidence": f"“{name}” is the school {inst['name']}; {pick['name']} {how} (school links)."}, []
    cands = [c for c in choices if c.get("ein")]
    core = funders._core(funders.normalize_org(name))
    if core and len(cands) >= 2:
        # Every organization with exactly this name (the search shows ten; local chapters can crowd out the
        # national one), largest first.
        with db.conn() as conn:
            pattern = r"^(the )?" + re.escape(core).replace(r"\ ", " ") + r"( inc| incorporated| corp| corporation)?$"
            same = [r for r in conn.execute(
                """SELECT ein, name, name_norm, state, latest_total_revenue FROM organizations
                   WHERE name_norm ~ %s AND (%s::text IS NULL OR state = %s)
                   ORDER BY latest_total_revenue DESC NULLS LAST LIMIT 500""",
                (pattern, state, state)).fetchall() if funders._core(r["name_norm"] or "") == core]
            n_same = conn.execute("SELECT count(*) AS n FROM organizations WHERE name_norm ~ %s "
                                  "AND (%s::text IS NULL OR state = %s)", (pattern, state, state)).fetchone()["n"]
        if len(same) >= 2:
            cands = same
        with db.conn() as conn:
            rev = {r["ein"]: r["latest_total_revenue"] or 0 for r in conn.execute(
                "SELECT ein, latest_total_revenue FROM organizations WHERE ein = ANY(%s)", ([c["ein"] for c in cands],))}
        ranked = sorted(cands, key=lambda c: -rev.get(c["ein"], 0))
        top, nxt = rev.get(ranked[0]["ein"], 0), rev.get(ranked[1]["ein"], 0)
        words = set(re.sub(r"[^a-z0-9 ]", " ", name.lower()).split())
        if top > 0 and top >= DOMINANT * max(nxt, 1) and words <= set((ranked[0].get("name_norm") or "").split()):
            return {**ranked[0], "match": "FUZZY",
                    "evidence": f"{max(len(cands), locals().get('n_same') or 0):,} organizations match “{name}”; this one reports {top / max(nxt, 1):,.0f} "
                                f"times the revenue of the next largest (${top:,.0f} vs ${nxt:,.0f})."}, []
    return None, choices


# --- the figures -----------------------------------------------------------------------------------------

def series(ein: str, metrics: list[str], year_from: int | None = None, year_to: int | None = None,
           cond: dict | None = None) -> dict:
    """Rows (newest year first) with each metric, its year-over-year % change, and a running total over the
    selected years; the condition, if any, keeps only matching years."""
    metrics = [m for m in metrics if m in METRICS] or ["revenue", "expenses"]
    cond = cond or {}
    need = set(metrics) | {m for m in (cond.get("metric_a"), cond.get("metric_b")) if m in METRICS}
    if cond.get("condition") == "deficit":
        need.add("surplus")
    cols = sorted(need, key=list(METRICS).index)
    vals = ",\n               ".join(f"({METRICS[m][1]})::numeric AS {m}" for m in cols)
    lags = ",\n               ".join(
        f"CASE WHEN lag(tax_year) OVER w = tax_year - 1 AND lag({m}) OVER w IS NOT NULL AND lag({m}) OVER w <> 0 "
        f"AND {m} IS NOT NULL THEN round(100.0 * ({m} - lag({m}) OVER w) / abs(lag({m}) OVER w), 1) END AS {m}_yoy"
        for m in cols)
    cums = ",\n               ".join(
        f"CASE WHEN count({m}) OVER c = count(*) OVER c THEN sum({m}) OVER c END AS {m}_cum" for m in cols)
    where, params = [], {"ein": ein, "y0": year_from, "y1": year_to}
    c = cond.get("condition")
    a, b = cond.get("metric_a"), cond.get("metric_b")
    if c == "a_up_b_down" and a in METRICS and b in METRICS:
        where.append(f"{a}_yoy > 0 AND {b}_yoy < 0")
    elif c in ("above", "below") and a in METRICS and cond.get("threshold") is not None:
        where.append(f"{a} {'>' if c == 'above' else '<'} %(x)s")
        params["x"] = cond["threshold"]
    elif c in ("rose_more_than", "fell_more_than") and a in METRICS and cond.get("percent") is not None:
        where.append(f"{a}_yoy {'>' if c == 'rose_more_than' else '<'} %(p)s")
        params["p"] = cond["percent"] if c == "rose_more_than" else -cond["percent"]
    elif c == "deficit":
        where.append("surplus < 0")
    sql = f"""
        WITH f AS (
            SELECT DISTINCT ON (f.tax_year) f.tax_year, f.id AS filing_id, f.form_type, f.object_id,
                   {vals}
            FROM filings f
            WHERE f.ein = %(ein)s AND NOT f.superseded AND f.tax_year IS NOT NULL
            ORDER BY f.tax_year, f.amended DESC, f.filed_date DESC NULLS LAST, f.id DESC),
        d AS (
            SELECT f.*, {lags}
            FROM f WINDOW w AS (ORDER BY tax_year)),
        r AS (
            SELECT d.*, {cums}
            FROM d WHERE (%(y0)s::int IS NULL OR tax_year >= %(y0)s) AND (%(y1)s::int IS NULL OR tax_year <= %(y1)s)
            WINDOW c AS (ORDER BY tax_year ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW))
        SELECT * FROM r {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY tax_year DESC"""
    with db.conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        n_years = conn.execute("""SELECT count(DISTINCT tax_year) AS n FROM filings
                                  WHERE ein = %(ein)s AND NOT superseded AND tax_year IS NOT NULL
                                    AND (%(y0)s::int IS NULL OR tax_year >= %(y0)s)
                                    AND (%(y1)s::int IS NULL OR tax_year <= %(y1)s)""", params).fetchone()["n"]
    return {"rows": rows, "metrics": metrics, "labels": {m: METRICS[m][0] for m in METRICS},
            "notes": [NOT_LOADED[m] for m in metrics if m in NOT_LOADED], "n_years": n_years,
            "condition": condition_text(cond)}
