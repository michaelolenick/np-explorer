"""Nearby + Similar (owner, 2026-10-29): organizations close to an organization or a description on two axes, where
they are and what they do. BETA. No language model is involved; tables from loader/similar.py.

Where: every organization sits at its ZIP code's center (org_geo, from the Census ZCTA gazetteer in geo_zips);
"within N miles" is a straight-line (haversine) distance between ZIP centers. A place is a ZIP, "City, ST" (geo_places),
an EIN or an organization's name.

What they do, two signals blended:
  words   the seed organization's most distinctive words in its own filings (research.org_text: name, mission, program
          descriptions, Schedule O, grant purposes, contractor services), weighted TF-IDF style (sim_lexeme_df), and
          every other organization scored by the weighted words it shares, scaled down for very long texts. A word with
          labeled senses (research.sense_defs: "space" outer, open or parking space ...) counts only when the other
          organization uses it in one of the seed's senses. Statistical: tagged Fuzzy.
  links   funders in common (grants filed with the recipient's EIN, sim_grant_edges), grantees in common, and board
          members in common (person clusters, matched by name: Fuzzy). Each shared funder or grantee counts less the
          more organizations it is linked to (a donor-advised fund that gives to everyone counts for little).
Each signal is scaled to its best match (1.0), then blended WORDS_WEIGHT : LINKS_WEIGHT.
"""

from __future__ import annotations

import logging
import math
import re

from app import db
from app.cache import ttl_lru

log = logging.getLogger("np.nearby")

SHOWN = 10                   # on the org page
MAX = 100                    # on /nearby
MILES = (10, 25, 50, 100, 250)
DEFAULT_MILES = 25
TERMS = 20                   # distinctive words per seed
DF_MIN, DF_MAX = 10, 40000   # words in fewer organizations are mostly typos; in more, too common to tell anything
CANDIDATES = 300             # per signal
WORDS_WEIGHT, LINKS_WEIGHT = 0.6, 0.4
FUNDER_MAX_GRANTEES = 2000   # funders with more grantees are left out (donor-advised funds, federated campaigns)
GRANTEE_MAX_FUNDERS = 500
BOARD_MAX_ORGS = 25          # a person cluster on more boards than this is likely several people with one name
EARTH_MILES = 3958.8
TIMEOUT = "8s"

TABLES = ("org_geo", "sim_lexeme_df", "sim_grant_edges", "sim_grant_degree")


@ttl_lru(ttl=600)
def ready() -> bool:
    try:
        with db.conn() as conn:
            return conn.execute("SELECT " + " AND ".join(f"to_regclass('{t}') IS NOT NULL" for t in TABLES)
                                + " AND to_regclass('research.org_text') IS NOT NULL AS ok").fetchone()["ok"]
    except Exception:  # noqa: BLE001
        return False


@ttl_lru(ttl=3600)
def _corpus() -> dict:
    """Organizations with text, their average number of distinct words, and the sense-labeled words."""
    with db.conn() as conn:
        n = conn.execute("SELECT count(*) AS n FROM research.org_text").fetchone()["n"]
        avg = conn.execute("SELECT avg(length(tsv)) AS a FROM research.org_text TABLESAMPLE SYSTEM (1)").fetchone()["a"]
        senses = {}
        if conn.execute("SELECT to_regclass('research.sense_defs') IS NOT NULL AS ok").fetchone()["ok"]:
            senses = {r["lexeme"]: r["topic"] for r in conn.execute(
                """SELECT DISTINCT topic, unnest(tsvector_to_array(to_tsvector('english', replace(tsq, '|', ' '))))
                          AS lexeme FROM research.sense_defs""").fetchall()}
    return {"n": max(int(n or 0), 1), "avg_len": float(avg or 150), "senses": senses}


# --- places -----------------------------------------------------------------------------------

def dist_sql(t: str) -> str:
    """Miles from %(lat)s, %(lon)s to table alias t's lat and lon (haversine)."""
    return (f"2 * {EARTH_MILES} * asin(sqrt(power(sin(radians(%(lat)s - {t}.lat) / 2), 2) + cos(radians(%(lat)s)) "
            f"* cos(radians({t}.lat)) * power(sin(radians(%(lon)s - {t}.lon) / 2), 2)))")


_ZIP = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")
_EIN = re.compile(r"^\s*(\d{2})-?(\d{7})\s*$")
_CITY = re.compile(r"^\s*(.+?)[,\s]+([A-Za-z]{2})\s*$")


def place(q: str) -> dict | None:
    """{"lat", "lon", "label", "ein"?} for a ZIP, "City, ST", an EIN or an organization's name; None if not found."""
    q = (q or "").strip()[:200]
    if not q:
        return None
    from app.geo import place_norm
    with db.conn() as conn:
        m = _ZIP.match(q)
        if m:
            r = conn.execute("SELECT lat, lon FROM geo_zips WHERE zip5 = %s", (m.group(1),)).fetchone()
            return {**r, "label": f"ZIP {m.group(1)}"} if r else None
        m = _EIN.match(q)
        ein = m.group(1) + m.group(2) if m else None
        if not ein:
            m = _CITY.match(q)
            if m:
                r = conn.execute("SELECT name, state, lat, lon FROM geo_places WHERE state = %s AND place_norm = %s",
                                 (m.group(2).upper(), place_norm(m.group(1)))).fetchone()
                if r:
                    name = re.sub(r"\s+(city|town|village|borough|CDP|municipality)$", "", r["name"])
                    return {"lat": r["lat"], "lon": r["lon"], "label": f"{name}, {r['state']}"}
    if not ein:
        from app import funders
        org, _ = funders.resolve_org(q)
        ein = org["ein"] if org else None
    return org_place(ein) if ein else None


def org_place(ein: str) -> dict | None:
    with db.conn() as conn:
        r = conn.execute("""SELECT g.lat, g.lon, g.zip5, o.name, o.city, o.state FROM org_geo g
                            JOIN organizations o USING (ein) WHERE g.ein = %s""", (ein,)).fetchone()
    if not r:
        return None
    return {"lat": r["lat"], "lon": r["lon"], "ein": ein, "label": r["name"] or ein}


def _zips_within(conn, center: dict, miles: float) -> list[str]:
    dlat = miles / 69.0
    dlon = miles / max(69.0 * abs(math.cos(math.radians(center["lat"]))), 1.0)
    return [r["zip5"] for r in conn.execute(
        f"""SELECT zip5 FROM geo_zips z WHERE lat BETWEEN %(lat)s - %(dlat)s AND %(lat)s + %(dlat)s
               AND lon BETWEEN %(lon)s - %(dlon)s AND %(lon)s + %(dlon)s AND {dist_sql('z')} <= %(miles)s""",
        {"lat": center["lat"], "lon": center["lon"], "dlat": dlat, "dlon": dlon, "miles": miles}).fetchall()]


# --- what an organization does: its distinctive words ------------------------------------------

def seed_terms(conn, ein: str | None = None, text: str | None = None) -> list[dict]:
    """The TERMS most distinctive word stems of an organization's filings (or of a description), each with its weight,
    the word as written, and the senses the organization uses it in (for sense-labeled words)."""
    c = _corpus()
    src = ("SELECT tsv, left(text, 200000) AS text FROM research.org_text WHERE ein = %(ein)s" if ein else
           "SELECT to_tsvector('english', %(text)s) AS tsv, %(text)s AS text")
    rows = conn.execute(f"""
        WITH s AS ({src})
        SELECT u.lexeme, coalesce(array_length(u.positions, 1), 1) AS tf, d.df
        FROM s, unnest(s.tsv) u JOIN sim_lexeme_df d ON d.lexeme = u.lexeme
        WHERE d.df BETWEEN %(lo)s AND %(hi)s AND u.lexeme ~ '^[a-z][a-z-]*[a-z]$' AND length(u.lexeme) > 2""",
        {"ein": ein, "text": (text or "")[:5000], "lo": DF_MIN if ein else 2, "hi": DF_MAX}).fetchall()
    terms = sorted(({"lexeme": r["lexeme"], "w": (1 + math.log(r["tf"])) * math.log(c["n"] / r["df"])} for r in rows),
                   key=lambda t: -t["w"])[:TERMS]
    if not terms:
        return []
    lex = [t["lexeme"] for t in terms]
    words = {r["s"]: r["w"] for r in conn.execute(f"""
        SELECT DISTINCT ON (s) s, w FROM (
            SELECT w, (ts_lexize('english_stem', w))[1] AS s, count(*) AS n
            FROM ({src}) x, regexp_split_to_table(lower(x.text), '[^a-z-]+') w
            WHERE length(w) > 2 GROUP BY w) y
        WHERE s = ANY(%(lex)s) ORDER BY s, n DESC""", {"ein": ein, "text": (text or "")[:5000], "lex": lex}).fetchall()}
    codes = {}
    if ein and c["senses"] and any(t["lexeme"] in c["senses"] for t in terms):
        codes = {r["topic"]: re.sub(r"[^A-Z]", "", r["codes"]) for r in conn.execute(
            "SELECT topic, codes FROM research.org_codes WHERE ein = %s AND codes <> ''", (ein,)).fetchall()}
    for t in terms:
        t["word"] = words.get(t["lexeme"], t["lexeme"])
        topic = c["senses"].get(t["lexeme"])
        t["topic"], t["codes"] = (topic, codes.get(topic) or None) if topic else (None, None)
    return terms


WORDS_SQL = """
WITH top AS (SELECT * FROM unnest(%(lex)s::text[], %(w)s::float8[], %(topic)s::text[], %(codes)s::text[])
             AS t(lexeme, w, topic, codes)),
hit AS (SELECT o.ein, top.lexeme, top.w, o.len FROM top,
        LATERAL (SELECT ein, length(tsv) AS len FROM research.org_text o
                 WHERE o.tsv @@ quote_literal(top.lexeme)::tsquery AND o.ein <> %(ein)s) o
        WHERE top.codes IS NULL OR EXISTS (SELECT 1 FROM research.org_codes c WHERE c.topic = top.topic AND c.ein = o.ein
                                           AND c.codes ~ ('[' || top.codes || ']'))),
agg AS (SELECT ein, sum(w) / sqrt(greatest(1, max(len) / %(avg)s)) AS score, array_agg(lexeme ORDER BY w DESC) AS shared
        FROM hit GROUP BY ein HAVING count(*) >= %(min)s)
SELECT a.* FROM agg a {geo} ORDER BY a.score DESC LIMIT %(lim)s"""


def _words(conn, terms: list[dict], ein: str | None, zips: list[str] | None) -> dict:
    if not terms:
        return {}
    geo = "JOIN org_geo g USING (ein) WHERE g.zip5 = ANY(%(zips)s)" if zips is not None else ""
    rows = conn.execute(WORDS_SQL.format(geo=geo), {
        "lex": [t["lexeme"] for t in terms], "w": [t["w"] for t in terms], "topic": [t["topic"] for t in terms],
        "codes": [t["codes"] for t in terms], "ein": ein or "", "avg": _corpus()["avg_len"],
        "min": min(2, len(terms)), "lim": CANDIDATES, "zips": zips}).fetchall()
    return {r["ein"]: r for r in rows}


# --- who they are linked to: funders, grantees and board members in common ----------------------

LINKS_SQL = f"""
WITH funders AS (SELECT e.funder, 1 / ln(2 + d.n_out) AS w FROM sim_grant_edges e JOIN sim_grant_degree d ON d.ein = e.funder
                 WHERE e.recipient = %(ein)s AND d.n_out <= {FUNDER_MAX_GRANTEES}),
cofund AS (SELECT e.recipient AS ein, 'funder' AS kind, f.funder AS via, f.w / sqrt(d.n_in) AS w FROM funders f
           JOIN sim_grant_edges e ON e.funder = f.funder JOIN sim_grant_degree d ON d.ein = e.recipient
           WHERE e.recipient <> %(ein)s),
grantees AS (SELECT e.recipient, 1 / ln(2 + d.n_in) AS w FROM sim_grant_edges e JOIN sim_grant_degree d ON d.ein = e.recipient
             WHERE e.funder = %(ein)s AND d.n_in <= {GRANTEE_MAX_FUNDERS}),
cogrant AS (SELECT e.funder AS ein, 'grantee' AS kind, g.recipient AS via, g.w / sqrt(d.n_out) AS w FROM grantees g
            JOIN sim_grant_edges e ON e.recipient = g.recipient JOIN sim_grant_degree d ON d.ein = e.funder
            WHERE e.funder <> %(ein)s AND d.n_out <= {FUNDER_MAX_GRANTEES}),
cl AS (SELECT DISTINCT m.cluster_id FROM people p JOIN person_cluster_members m ON m.person_id = p.id
       JOIN person_clusters pc ON pc.id = m.cluster_id
       WHERE p.ein = %(ein)s AND NOT p.is_duplicate AND pc.is_institution IS NOT TRUE AND pc.n_orgs <= {BOARD_MAX_ORGS}),
clo AS (SELECT cl.cluster_id, p.ein FROM cl JOIN person_cluster_members m USING (cluster_id) JOIN people p ON p.id = m.person_id
        GROUP BY 1, 2),
cln AS (SELECT cluster_id, count(*) AS n FROM clo GROUP BY 1 HAVING count(*) BETWEEN 2 AND {BOARD_MAX_ORGS}),
board AS (SELECT clo.ein, 'board' AS kind, clo.cluster_id::text AS via, 1 / ln(1 + cln.n) AS w
          FROM clo JOIN cln USING (cluster_id) WHERE clo.ein <> %(ein)s),
allh AS (SELECT * FROM cofund UNION ALL SELECT * FROM cogrant UNION ALL SELECT * FROM board)
SELECT a.ein, sum(a.w) AS score,
       array_agg(a.via ORDER BY a.w DESC) FILTER (WHERE a.kind = 'funder') AS funders,
       array_agg(a.via ORDER BY a.w DESC) FILTER (WHERE a.kind = 'grantee') AS grantees,
       array_agg(a.via ORDER BY a.w DESC) FILTER (WHERE a.kind = 'board') AS board
FROM allh a {{geo}} GROUP BY a.ein ORDER BY sum(a.w) DESC LIMIT %(lim)s"""


def _links(conn, ein: str | None, zips: list[str] | None) -> dict:
    if not ein:
        return {}
    geo = "JOIN org_geo g ON g.ein = a.ein WHERE g.zip5 = ANY(%(zips)s)" if zips is not None else ""
    rows = conn.execute(LINKS_SQL.format(geo=geo), {"ein": ein, "lim": CANDIDATES, "zips": zips}).fetchall()
    return {r["ein"]: r for r in rows}


# --- blending, and the one-line reason --------------------------------------------------------

def blend(words: dict, links: dict) -> list[tuple[float, str]]:
    """(score, ein), best first: each signal scaled to its best match, then WORDS_WEIGHT : LINKS_WEIGHT. With only one
    signal (no filings text, or no grants and no shared board members) that one alone."""
    tw = max((float(r["score"]) for r in words.values()), default=0) or 1
    lw = max((float(r["score"]) for r in links.values()), default=0) or 1
    ww, lk = (WORDS_WEIGHT, LINKS_WEIGHT) if words and links else (1.0, 1.0)
    out = []
    for ein in set(words) | set(links):
        s = ww * (float(words[ein]["score"]) / tw if ein in words else 0) \
            + lk * (float(links[ein]["score"]) / lw if ein in links else 0)
        out.append((s, ein))
    return sorted(out, key=lambda x: (-x[0], x[1]))


def _list(names: list[str], n: int = 3) -> str:
    more = len(names) - n
    return ", ".join(names[:n]) + (f" and {more} more" if more > 0 else "")


def why(w: dict | None, lk: dict | None, words: dict, orgs: dict, people: dict) -> list[dict]:
    """The reasons as parts: [{"text": ..., "fuzzy": bool}]: words in common, funders, grantees, board members."""
    parts = []
    if w:
        parts.append({"label": "Words", "text": ", ".join(words.get(x, x) for x in w["shared"][:5]), "fuzzy": True})
    if lk:
        if lk["funders"]:
            parts.append({"label": f"Funders in common ({len(lk['funders'])})",
                          "text": _list([orgs.get(e, e) for e in lk["funders"]]), "fuzzy": False})
        if lk["grantees"]:
            parts.append({"label": f"Grantees in common ({len(lk['grantees'])})",
                          "text": _list([orgs.get(e, e) for e in lk["grantees"]]), "fuzzy": False})
        if lk["board"]:
            parts.append({"label": f"Board members in common ({len(lk['board'])})",
                          "text": _list([people.get(int(c), c) for c in lk["board"]]), "fuzzy": True})
    return parts


def _finish(conn, ranked, words_hits, link_hits, terms, center, limit) -> list[dict]:
    top = [e for _, e in ranked[:limit]]
    if not top:
        return []
    via = {v for e in top for k in ("funders", "grantees") for v in ((link_hits.get(e) or {}).get(k) or [])}
    clusters = {int(c) for e in top for c in ((link_hits.get(e) or {}).get("board") or [])}
    params = {"eins": top, "via": sorted(via), "cl": sorted(clusters),
              "lat": center["lat"] if center else 0, "lon": center["lon"] if center else 0}
    dist = f"CASE WHEN g.lat IS NOT NULL AND %(c)s THEN {dist_sql('g')} END"
    info = {r["ein"]: r for r in conn.execute(
        f"""SELECT o.ein, o.name, o.city, o.state, t.revenue, {dist} AS miles
            FROM organizations o LEFT JOIN org_geo g USING (ein) LEFT JOIN research.org_text t USING (ein)
            WHERE o.ein = ANY(%(eins)s)""", {**params, "c": bool(center)}).fetchall()}
    orgs = {r["ein"]: r["name"] or r["ein"] for r in conn.execute("SELECT ein, name FROM organizations WHERE ein = ANY(%(via)s)", params).fetchall()}
    people = {r["id"]: r["display_name"] for r in conn.execute(
        "SELECT id, display_name FROM person_clusters WHERE id = ANY(%(cl)s)", params).fetchall()} if clusters else {}
    wordmap = {t["lexeme"]: t["word"] for t in terms}
    best = ranked[0][0] or 1
    out = []
    for s, e in ranked[:limit]:
        i = info.get(e) or {"name": e, "city": None, "state": None, "revenue": None, "miles": None}
        parts = why(words_hits.get(e), link_hits.get(e), wordmap, orgs, people)
        out.append({"ein": e, "name": i["name"], "city": i["city"], "state": i["state"], "revenue": i["revenue"],
                    "miles": round(float(i["miles"]), 1) if i.get("miles") is not None else None,
                    "score": round(s / best, 2), "why": parts, "fuzzy": any(p["fuzzy"] for p in parts)})
    return out


def _timeout(conn):
    conn.execute(f"SET LOCAL statement_timeout = '{TIMEOUT}'")


@ttl_lru(ttl=3600)
def similar(ein: str, miles: int | None = None, near: str | None = None, limit: int = SHOWN) -> dict:
    """Organizations like this one, optionally within `miles` of `near` (default: this organization's own place)."""
    local = bool(miles or near)
    center = place(near) if near else org_place(ein)
    if local and not center:
        return {"error": "place", "rows": [], "terms": []}
    with db.conn() as conn:
        _timeout(conn)
        zips = _zips_within(conn, center, miles or DEFAULT_MILES) if local else None
        terms = seed_terms(conn, ein=ein)
        words_hits = _words(conn, terms, ein, zips)
        link_hits = _links(conn, ein, zips)
        rows = _finish(conn, blend(words_hits, link_hits), words_hits, link_hits, terms, center, limit)
    return {"rows": rows, "terms": [t["word"] for t in terms], "center": center,
            "miles": (miles or DEFAULT_MILES) if local else None, "has_links": bool(link_hits)}


@ttl_lru(ttl=3600)
def like_text(text: str, miles: int | None = None, near: str | None = None, limit: int = MAX) -> dict:
    """Organizations whose filings use the distinctive words of a description."""
    center = place(near) if near else None
    if near and not center:
        return {"error": "place", "rows": [], "terms": []}
    with db.conn() as conn:
        _timeout(conn)
        zips = _zips_within(conn, center, miles or DEFAULT_MILES) if center else None
        terms = seed_terms(conn, text=text)
        words_hits = _words(conn, terms, None, zips)
        rows = _finish(conn, blend(words_hits, {}), words_hits, {}, terms, center, limit)
    return {"rows": rows, "terms": [t["word"] for t in terms], "center": center,
            "miles": (miles or DEFAULT_MILES) if center else None}


@ttl_lru(ttl=3600)
def nearby(near: str, miles: int = DEFAULT_MILES, limit: int = MAX) -> dict:
    """Organizations within `miles` of a place, nearest first (larger ones first at the same distance)."""
    center = place(near)
    if not center:
        return {"error": "place", "rows": [], "n": 0}
    with db.conn() as conn:
        _timeout(conn)
        zips = _zips_within(conn, center, miles)
        p = {"zips": zips, "lat": center["lat"], "lon": center["lon"], "lim": limit, "self": center.get("ein") or ""}
        n = conn.execute("SELECT count(*) AS n FROM org_geo WHERE zip5 = ANY(%(zips)s) AND ein <> %(self)s",
                         p).fetchone()["n"]
        rows = conn.execute(f"""
            SELECT g.ein, o.name, o.city, o.state, o.latest_total_revenue AS revenue, round({dist_sql('g')}::numeric, 1)
                   AS miles
            FROM org_geo g JOIN organizations o USING (ein)
            WHERE g.zip5 = ANY(%(zips)s) AND g.ein <> %(self)s
            ORDER BY miles, o.latest_total_revenue DESC NULLS LAST, g.ein LIMIT %(lim)s""", p).fetchall()
    return {"rows": rows, "n": n, "center": center, "miles": miles}
