"""Funders, similar organizations, and who funds organizations like this.

Read from tables precomputed by loader/funders.py (grant_links, org_funders, org_profile).
Every query here is bounded: an index lookup per organization, or at most a few thousand
candidate rows, so org pages and plain-text search stay fast. No language model is involved.
"""

from __future__ import annotations

import math
import re

from app import db
from app.cache import ttl_lru
from app.names import normalize_org

FUNDERS_SHOWN = 25          # on the org page; the full list is on /org/<ein>/funders
SIMILAR_SHOWN = 25
SIMILAR_MAX = 100
FUNDERS_LIKE_SHOWN = 15
FUNDERS_LIKE_MAX = 50
CANDIDATES_PER_SIDE = 300   # per NTEE level, above and below the organization's revenue
TOPIC_MAX = 100
FUNDING_KINDS = ("Private foundation", "DAF sponsor")
BANDS = [(math.log(2), "revenue within 2x"), (math.log(5), "revenue within 5x"), (math.log(10), "revenue within 10x")]


def available() -> bool:
    """False until loader/funders.py has built its tables (pages then say the section is being built)."""
    try:
        with db.conn() as conn:
            return conn.execute("SELECT to_regclass('org_funders') IS NOT NULL AND to_regclass('org_profile') IS NOT NULL "
                                "AS ok").fetchone()["ok"]
    except Exception:  # noqa: BLE001
        return False


# --- funders of one organization -------------------------------------------------------------

@ttl_lru()
def funders(ein: str, limit: int | None = FUNDERS_SHOWN, offset: int = 0) -> dict:
    with db.conn() as conn:
        tot = conn.execute("""SELECT count(*) AS n, sum(total) AS total, min(first_year) AS y0, max(last_year) AS y1
                              FROM org_funders WHERE recipient_ein = %s""", (ein,)).fetchone()
        rows = conn.execute(f"""SELECT * FROM org_funders WHERE recipient_ein = %s
                                ORDER BY total DESC NULLS LAST, last_year DESC, grantor_ein
                                {"LIMIT %s OFFSET %s" if limit else ""}""",
                            (ein, limit, offset) if limit else (ein,)).fetchall()
    return {"rows": rows, "n_total": tot["n"], "total": tot["total"], "first_year": tot["y0"], "last_year": tot["y1"]}


def funder_grants(ein: str, grantor_ein: str) -> list[dict]:
    """One grantor's grants to this organization, newest first."""
    with db.conn() as conn:
        return conn.execute("""SELECT l.*, f.object_id FROM grant_links l JOIN filings f ON f.id = l.grantor_filing_id
                               WHERE l.recipient_ein = %s AND l.grantor_ein = %s
                               ORDER BY l.tax_year DESC, l.amount DESC""", (ein, grantor_ein)).fetchall()


# --- similar organizations --------------------------------------------------------------------

def _profile(conn, ein: str) -> dict | None:
    return conn.execute("SELECT * FROM org_profile WHERE ein = %s", (ein,)).fetchone()


CANDIDATES = """
(SELECT ein FROM org_profile WHERE {level} = {key} {extra} AND revenue >= %(rev)s AND ein <> %(ein)s {st}
 ORDER BY revenue LIMIT {n})
UNION ALL
(SELECT ein FROM org_profile WHERE {level} = {key} {extra} AND revenue < %(rev)s AND ein <> %(ein)s {st}
 ORDER BY revenue DESC LIMIT {n})"""

SCORED = """
SELECT p.ein, p.name, p.state, p.ntee_code, p.ntee_major, p.revenue, p.expenses, p.top_title, p.top_pay,
       p.latest_year, similarity(p.name_norm, %(nn)s) AS name_sim,
       CASE WHEN %(mission)s <> '' AND p.mission IS NOT NULL
            THEN similarity(left(p.mission, 500), %(mission)s) ELSE 0 END AS mission_sim
FROM org_profile p WHERE p.ein = ANY(%(eins)s)"""


def why_similar(me: dict, c: dict) -> tuple[tuple, str]:
    """(sort key, plain-English reason). Deterministic: NTEE code, then group; revenue band;
    same state; name and mission similarity; closest revenue."""
    reasons = []
    if me.get("ntee_code") and c.get("ntee_code") == me["ntee_code"]:
        level = 2
        reasons.append(f"Same NTEE code {c['ntee_code']}")
    elif me.get("ntee_major") and c.get("ntee_major") == me["ntee_major"]:
        level = 1
        reasons.append(f"Same NTEE group {c['ntee_major']}")
    else:
        level = 0
        reasons.append("Similar name")
    if me.get("revenue") and c.get("revenue"):
        dist = abs(math.log(max(c["revenue"], 1) / max(me["revenue"], 1)))
        band = next((i for i, (cut, _) in enumerate(BANDS) if dist <= cut), len(BANDS))
        reasons.append(BANDS[band][1] if band < len(BANDS) else "revenue differs more than 10x")
    else:
        dist, band = 99.0, len(BANDS) + 1
    same_state = bool(me.get("state")) and c.get("state") == me["state"]
    if same_state:
        reasons.append("same state")
    text = (c.get("name_sim") or 0) + (c.get("mission_sim") or 0)
    if (c.get("mission_sim") or 0) >= 0.3:
        reasons.append("similar mission")
    elif level and (c.get("name_sim") or 0) >= 0.4:
        reasons.append("similar name")
    return (-level, band, not same_state, -round(text, 3), dist, c["ein"]), ", ".join(reasons)


@ttl_lru()
def similar(ein: str, limit: int = SIMILAR_MAX, state_only: bool = False) -> dict:
    with db.conn() as conn:
        me = _profile(conn, ein)
        if not me:
            return {"me": None, "rows": []}
        params = {"ein": ein, "rev": me["revenue"] or 0, "nn": me["name_norm"] or "",
                  "mission": (me["mission"] or "")[:500], "state": me["state"]}
        st = "AND state = %(state)s" if state_only and me["state"] else ""
        parts = []
        if me["ntee_code"]:
            params["code"] = me["ntee_code"]
            parts.append(CANDIDATES.format(level="ntee_code", key="%(code)s", extra="", st=st, n=CANDIDATES_PER_SIDE))
        if me["ntee_major"]:
            params["major"] = me["ntee_major"]
            extra = "AND ntee_code IS DISTINCT FROM %(code)s" if me["ntee_code"] else ""
            parts.append(CANDIDATES.format(level="ntee_major", key="%(major)s", extra=extra, st=st,
                                           n=CANDIDATES_PER_SIDE))
        if not parts:     # no NTEE code: fall back to organizations with a near-identical name
            conn.execute("SET pg_trgm.similarity_threshold = 0.5")
            eins = [r["ein"] for r in conn.execute(
                f"SELECT ein FROM org_profile WHERE name_norm %% %(nn)s AND ein <> %(ein)s {st} LIMIT 300",
                params).fetchall()]
        else:
            eins = [r["ein"] for r in conn.execute(" UNION ALL ".join(parts), params).fetchall()]
        if not eins:
            return {"me": me, "rows": []}
        params["eins"] = list(dict.fromkeys(eins))
        cands = conn.execute(SCORED, params).fetchall()
    ranked = []
    for c in cands:
        key, why = why_similar(me, c)
        ranked.append((key, {**c, "why": why}))
    ranked.sort(key=lambda kv: kv[0])
    return {"me": me, "rows": [c for _, c in ranked[:limit]]}


# --- who funds organizations like this ----------------------------------------------------------

FUNDERS_LIKE = """
SELECT f.grantor_ein, max(f.grantor_name) AS grantor_name, max(f.grantor_kind) AS grantor_kind,
       sum(f.total) AS total, sum(f.n_grants) AS n_grants, count(DISTINCT f.recipient_ein) AS recipients,
       min(f.first_year) AS first_year, max(f.last_year) AS last_year,
       array_agg(f.recipient_ein ORDER BY f.total DESC) AS funded
FROM org_funders f
WHERE f.recipient_ein = ANY(%(eins)s) AND f.grantor_kind = ANY(%(kinds)s)
GROUP BY f.grantor_ein ORDER BY total DESC NULLS LAST, f.grantor_ein LIMIT %(lim)s"""


def funders_of_set(eins: list[str], names: dict[str, str], limit: int = FUNDERS_LIKE_MAX,
                   already: set[str] | None = None) -> list[dict]:
    if not eins:
        return []
    with db.conn() as conn:
        rows = conn.execute(FUNDERS_LIKE, {"eins": eins, "kinds": list(FUNDING_KINDS), "lim": limit}).fetchall()
    for r in rows:
        r["funded_names"] = [(e, names.get(e, e)) for e in r["funded"]]
        r["funds_this_org"] = bool(already) and r["grantor_ein"] in already
    return rows


@ttl_lru()
def funders_like(ein: str, limit: int = FUNDERS_LIKE_MAX) -> dict:
    sim = similar(ein, SIMILAR_MAX)
    names = {r["ein"]: r["name"] for r in sim["rows"]}
    with db.conn() as conn:
        mine = {r["grantor_ein"] for r in conn.execute(
            "SELECT grantor_ein FROM org_funders WHERE recipient_ein = %s", (ein,)).fetchall()}
    return {"me": sim["me"], "n_similar": len(sim["rows"]),
            "rows": funders_of_set(list(names), names, limit, already=mine)}


# --- topics --------------------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")


def topic_words(keywords: str) -> list[str]:
    stop = {"nonprofit", "nonprofits", "organization", "organizations", "charity", "charities", "foundation",
            "foundations", "group", "groups", "the", "a", "an", "of", "for", "in", "on", "and", "that", "with", "who",
            "fund", "funds", "funding", "working", "work", "works"}
    return [w for w in _WORD.findall((keywords or "").lower()) if w not in stop][:8]


@ttl_lru()
def topic(keywords: str, state: str | None = None, ntee: str | None = None,
          min_revenue: int | None = None, max_revenue: int | None = None, limit: int = TOPIC_MAX) -> dict:
    """Organizations whose name or mission matches every keyword (or, if none do, any keyword), with
    the NTEE codes most common among them so the reader can narrow. Deterministic."""
    words = topic_words(keywords)
    out = {"words": words, "rows": [], "codes": [], "total": 0, "mode": "all", "state": state, "ntee": ntee}
    if not words:
        return out
    filters, params = [], {"lim": limit}
    if state:
        filters.append("p.state = %(state)s")
        params["state"] = state
    if min_revenue:
        filters.append("p.revenue >= %(minr)s")
        params["minr"] = min_revenue
    if max_revenue:
        filters.append("p.revenue <= %(maxr)s")
        params["maxr"] = max_revenue
    with db.conn() as conn:
        for mode, joiner in (("all", " & "), ("any", " | ")):
            params["q"] = joiner.join(words)
            base = " AND ".join(["p.doc @@ to_tsquery('english', %(q)s)"] + filters)
            codes = conn.execute(f"""SELECT p.ntee_code, count(*) AS n FROM org_profile p WHERE {base}
                                     GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 12""", params).fetchall()
            total = sum(c["n"] for c in codes)
            if not total:
                continue
            where = base + (" AND p.ntee_code = %(ntee)s" if ntee else "")
            if ntee:
                params["ntee"] = ntee
            rows = conn.execute(f"""SELECT p.ein, p.name, p.state, p.ntee_code, p.revenue, p.expenses, p.top_title,
                                           p.top_pay, p.latest_year, ts_rank(p.doc, to_tsquery('english', %(q)s)) AS rank
                                    FROM org_profile p WHERE {where}
                                    ORDER BY rank DESC, p.revenue DESC NULLS LAST, p.ein LIMIT %(lim)s""",
                                params).fetchall()
            out.update(rows=rows, codes=codes, total=conn.execute(
                f"SELECT count(*) AS n FROM org_profile p WHERE {where}", params).fetchone()["n"], mode=mode,
                query=params["q"])
            break
    return out


@ttl_lru()
def topic_funders(keywords: str, state: str | None = None, ntee: str | None = None, limit: int = FUNDERS_LIKE_MAX):
    t = topic(keywords, state, ntee)
    names = {r["ein"]: r["name"] for r in t["rows"]}
    return {"topic": t, "rows": funders_of_set(list(names), names, limit)}


# --- resolving an organization named in plain text -----------------------------------------------

_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|llc|ltd|foundation|fund|trust|the)\b")


def _core(n: str) -> str:
    return " ".join(_SUFFIX.sub(" ", n or "").split())


def resolve_org(name: str, state: str | None = None, search=None) -> tuple[dict | None, list[dict]]:
    """(the organization, []) when the name points at one; (None, candidates) when it is ambiguous;
    (None, []) when nothing matches. Never guesses between several equally good matches."""
    from app import queries
    search = search or queries.search_orgs
    words = normalize_org(name).split()
    if not words:
        return None, []
    cands = search(" ".join(words), limit=10, state=state)
    if not cands:
        return None, []
    q = _core(" ".join(words))
    exact = [c for c in cands if _core(c.get("name_norm") or "") == q]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, exact
    whole = [c for c in cands if set(words) <= set((c.get("name_norm") or "").split())]
    if len(whole) == 1:
        return whole[0], []
    return None, (whole or cands)[:10]
