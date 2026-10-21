"""SQL behind the pages and the JSON API."""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

from app import address, db
from app.names import normalize_name, normalize_org, query_tokens

PAGE = 50
# Name search may run longer than other pages' 5 s limit: a common name should be slow, not an error.
SEARCH_TIMEOUT = "10s"
TIER_CAP = 1000
# Very common words ("john": 285K people) would make each candidate set sort every match.
# Each set scans at most this many matches, then keeps its top TIER_CAP by filings.
CANDIDATE_SCAN = 30000
TRGM_MIN_WORD = 5   # trigram candidates only when some query word has at least this many letters
CLOSE_SIMILARITY = 0.8   # word similarity for a "close match": typos score 0.81-0.89, other names under 0.76


def _tsq(tokens, prefix: bool) -> str:
    # One- and two-letter words ("of", "a") only ever match whole: as prefixes they match nearly everything.
    return " & ".join(f"{t}:*" if prefix and len(t) > 2 else t for t in tokens)


def _filters(f: dict, params: dict) -> str:
    sql = []
    if f.get("state"):
        sql.append("%(state)s = ANY(c.states)")
        params["state"] = f["state"].upper()
    if f.get("year_from"):
        sql.append("c.last_year >= %(year_from)s")
        params["year_from"] = f["year_from"]
    if f.get("year_to"):
        sql.append("c.first_year <= %(year_to)s")
        params["year_to"] = f["year_to"]
    if f.get("min_comp"):
        sql.append("c.max_comp >= %(min_comp)s")
        params["min_comp"] = f["min_comp"]
    if f.get("title"):
        sql.append("""EXISTS (SELECT 1 FROM person_cluster_members m JOIN people p ON p.id = m.person_id
                      WHERE m.cluster_id = c.id AND p.title ILIKE %(title)s)""")
        params["title"] = f"%{f['title']}%"
    if f.get("org"):
        sql.append("""EXISTS (SELECT 1 FROM person_cluster_members m JOIN people p ON p.id = m.person_id
                      JOIN filings fl ON fl.id = p.filing_id
                      WHERE m.cluster_id = c.id AND fl.org_name ILIKE %(org)s)""")
        params["org"] = f"%{f['org']}%"
    return (" AND " + " AND ".join(sql)) if sql else ""


def search_people(q: str, filters: dict, page: int = 1, institutions: bool = False) -> dict:
    """Trigram word similarity first; whole-word and prefix token matches as fallback.

    Candidates come from three capped sets: names trigram-similar to the query
    (pg_trgm `<%`, word similarity >= 0.5), names containing every query word,
    and names with a word starting with each query word ("mich olen"). All are
    ranked together: an exact full-name match first, then names whose words
    start with the query words in order ("mich olen" -> "michael olenick",
    not "olen michael brown"), then word similarity (boosted when the query
    words match whole or as prefixes), then number of filings, then overall
    similarity. Sounds-alike (Soundex) is consulted
    only when that finds almost nothing. Without pg_trgm, the token sets alone
    are used, ranked by closeness in length.
    """
    tokens = query_tokens(q)
    norm = normalize_name(q)
    if not tokens:
        return {"results": [], "total": 0, "capped": False, "did_you_mean": []}
    trgm = db.has_trgm()
    T = db.search_table()   # noqa: N806 - the table name, interpolated below
    params = {"exact": _tsq(tokens, False), "prefix": _tsq(tokens, True), "norm": norm or " ".join(tokens),
              "ordered": ordered_prefix_regex(tokens), "whole": ordered_words_regex(tokens),
              "close": CLOSE_SIMILARITY, "cap": TIER_CAP, "scan": CANDIDATE_SCAN, "limit": PAGE,
              "offset": (page - 1) * PAGE}
    # People and institutions (banks, trust companies...) are searched separately.
    where = _filters(filters, params) + (" AND c.is_institution" if institutions else " AND NOT c.is_institution")
    sets = [
        f"""(SELECT id FROM (SELECT c.id, c.n_filings FROM {T} c
                              WHERE c.name_tsv @@ to_tsquery('simple', %(exact)s){where} LIMIT %(scan)s) s
             ORDER BY n_filings DESC LIMIT %(cap)s)""",
        f"""(SELECT id FROM (SELECT c.id, c.n_filings FROM {T} c
                              WHERE c.name_tsv @@ to_tsquery('simple', %(prefix)s){where} LIMIT %(scan)s) s
             ORDER BY n_filings DESC LIMIT %(cap)s)""",
    ]
    # Trigram candidates need some substance: query words under five letters
    # ("mich olen") are mostly common trigrams, so those go to prefix matching.
    # When the query itself reads like an institution ("bank of america"), its trigram
    # neighbours are mostly institutions, which the people search would scan only to
    # discard; whole-word and prefix matches still find people.
    if trgm and max(len(t) for t in tokens) >= TRGM_MIN_WORD and (institutions or not looks_institutional(tokens)):
        sets.insert(0, f"""(SELECT c.id FROM {T} c WHERE %(norm)s <%% c.name_norm{where}
                            LIMIT %(cap)s)""")
        # Word similarity, boosted when every query word starts a name word (in
        # any order) or matches a whole word. Word order is a separate sort key.
        score = """word_similarity(%(norm)s, c.name_norm)
                   + 0.1 * (c.name_tsv @@ to_tsquery('simple', %(prefix)s))::int
                   + 0.1 * (c.name_tsv @@ to_tsquery('simple', %(exact)s))::int"""
        sim = "similarity(c.name_norm, %(norm)s)"
    else:
        score = "(c.name_tsv @@ to_tsquery('simple', %(exact)s))::int"
        sim = "(1.0 / (1 + abs(length(c.name_norm) - length(%(norm)s))))"
    # Result bands, shown as sections: 1 exact (every query word as a whole word, in
    # order), 2 close (words start with the query words in order, or nearly the same
    # spelling), 3 everything else.
    # Middle initials don't count against closeness ("renee mauborgen" ~ "renee a mauborgne").
    close_spelling = ("""OR greatest(word_similarity(%(norm)s, c.name_norm),
                                     word_similarity(%(norm)s, regexp_replace(c.name_norm, ' [a-z](?= )', '', 'g')))
                          >= %(close)s""" if trgm else "")
    band = f"""CASE WHEN c.name_norm ~ %(whole)s THEN 1
                    WHEN c.name_norm ~ %(ordered)s {close_spelling} THEN 2 ELSE 3 END"""
    sql = f"""
        WITH cand AS ({" UNION ".join(sets)})
        SELECT c.id, c.display_name, c.name_norm, c.n_filings, c.n_orgs, c.first_year, c.last_year,
               c.max_comp, c.states, c.orgs, c.latest_title,
               {score} AS score, {sim} AS sim, c.name_norm ~ %(ordered)s AS in_order,
               c.name_tsv @@ to_tsquery('simple', %(exact)s) AS exact_words, {band} AS band,
               count(*) OVER () AS total,
               count(*) FILTER (WHERE {band} = 1) OVER () AS n_band1,
               count(*) FILTER (WHERE {band} = 2) OVER () AS n_band2,
               count(*) FILTER (WHERE {band} = 3) OVER () AS n_band3,
               count(*) FILTER (WHERE c.name_tsv @@ to_tsquery('simple', %(exact)s)) OVER () AS exact_total
        FROM cand JOIN {T} c ON c.id = cand.id
        ORDER BY band, (c.name_norm = %(norm)s) DESC, in_order DESC, round(({score})::numeric, 2) DESC,
                 c.n_filings DESC, sim DESC, c.id
        LIMIT %(limit)s OFFSET %(offset)s
    """
    with db.conn(timeout=SEARCH_TIMEOUT, io_concurrency=db.SEARCH_IO_CONCURRENCY) as conn, conn.transaction():
        # For common names the planner expects many trigram matches and scans the whole table, computing
        # similarity on 15M names (0.6-3 s); the trigram index answers the same query in about 0.1 s.
        conn.execute("SET LOCAL enable_seqscan = off")
        rows = conn.execute(sql, params).fetchall()
        total = rows[0]["total"] if rows else 0
        exact_total = rows[0]["exact_total"] if rows else 0
        bands = {b: (rows[0][f"n_band{b}"] if rows else 0) for b in (1, 2, 3)}
        if total < 10 and page == 1 and not institutions:
            # Almost nothing matched: add names that sound alike, after everything else.
            sound = sound_query(tokens)
            if sound:
                params["sound"] = sound
                seen = [r["id"] for r in rows]
                extra = conn.execute(f"""
                    SELECT c.id, c.display_name, c.name_norm, c.n_filings, c.n_orgs, c.first_year, c.last_year,
                           c.max_comp, c.states, c.orgs, c.latest_title, {sim} AS sim, 3 AS band
                    FROM {T} c
                    WHERE c.sound_tsv @@ to_tsquery('simple', %(sound)s) AND NOT (c.id = ANY(%(seen)s)){where}
                    ORDER BY sim DESC, c.n_filings DESC LIMIT %(more)s""",
                    {**params, "seen": seen, "more": PAGE - len(rows)}).fetchall()
                rows = rows + extra
                total = len(rows)
                bands[3] += len(extra)
        if not rows and page > 1:
            total = conn.execute(f"SELECT count(*) AS n FROM ({sql.replace('LIMIT %(limit)s OFFSET %(offset)s', '')}) x",
                                 params).fetchone()["n"]
        dym = []
        if exact_total < 5 and not institutions:
            # Close names are already among the ranked candidates; query only if none matched.
            dym = list(dict.fromkeys(r["display_name"] for r in rows if r["name_norm"] != params["norm"]))[:8]
            if not dym:
                dym = did_you_mean(conn, tokens, params["norm"], trgm)
    if rows:
        _add_org_totals(rows)
    return {"results": rows, "total": total, "capped": total >= TIER_CAP, "did_you_mean": dym,
            "bands": {"exact": bands[1], "close": bands[2], "other": bands[3]}}


def _add_org_totals(rows: list[dict]) -> None:
    """Per-organization pay for a page of search results, newest organization first.

    Adds `org_totals` (name, ein, total, first/last year) and `total_comp` (the sum,
    excluding superseded returns) to each result row.
    """
    ids = [r["id"] for r in rows]
    with db.conn() as conn:
        agg = conn.execute("""
            SELECT m.cluster_id, p.ein, (array_agg(coalesce(o.name, f.org_name) ORDER BY p.tax_year DESC NULLS LAST))[1] AS name,
                   sum(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0))
                       FILTER (WHERE NOT f.superseded) AS total,
                   min(p.tax_year) AS first_year, max(p.tax_year) AS last_year
            FROM person_cluster_members m
            JOIN people p ON p.id = m.person_id
            JOIN filings f ON f.id = p.filing_id
            LEFT JOIN organizations o ON o.ein = p.ein
            WHERE m.cluster_id = ANY(%s) AND NOT p.is_duplicate
            GROUP BY m.cluster_id, p.ein""", (ids,)).fetchall()
    by_cluster: dict[int, list] = {}
    for a in agg:
        by_cluster.setdefault(a["cluster_id"], []).append(a)
    for r in rows:
        orgs = sorted(by_cluster.get(r["id"], []), key=lambda a: (-(a["last_year"] or 0), -(a["total"] or 0)))
        r["org_totals"] = [{"ein": a["ein"], "name": a["name"], "total": a["total"] or 0,
                            "first_year": a["first_year"], "last_year": a["last_year"]} for a in orgs]
        r["total_comp"] = sum(a["total"] or 0 for a in orgs)


def looks_institutional(tokens) -> bool:
    from app.institutions import is_institution
    return is_institution(" ".join(tokens), given_names=set())


def ordered_words_regex(tokens) -> str:
    """Regex: each token is a whole name word, in order. ["renee", "mauborgne"] -> (^| )renee( | .* )mauborgne( |$)"""
    return "(^| )" + "( | .* )".join(tokens) + "( |$)"


def ordered_prefix_regex(tokens) -> str:
    """Regex: each token starts a name word, in order. ["mich", "olen"] -> (^| )mich[^ ]* (.* )?olen"""
    return "(^| )" + "[^ ]* (.* )?".join(tokens)


def soundex(word: str) -> str:
    """Python twin of the np_soundex SQL function (migration 0002)."""
    codes = {**dict.fromkeys("AEIOUY", "0"), **dict.fromkeys("HW", "9"), **dict.fromkeys("BFPV", "1"),
             **dict.fromkeys("CGJKQSXZ", "2"), **dict.fromkeys("DT", "3"), "L": "4", "M": "5", "N": "5", "R": "6"}
    s = "".join(ch for ch in word.upper() if "A" <= ch <= "Z")
    if not s:
        return ""
    out, prev = s[0], codes[s[0]]
    for ch in s[1:]:
        code = codes[ch]
        if code == "9":
            continue
        if code != "0" and code != prev:
            out += code
            if len(out) == 4:
                break
        prev = code
    return out.ljust(4, "0")


def sound_query(tokens) -> str:
    # Words with no letters (numbers, an EIN) have no sound code: leave them out.
    return " & ".join(code for code in (soundex(t).lower() for t in tokens if len(t) > 1) if code)


def search_institutions(q: str, limit: int = 10) -> list[dict]:
    """Institutions matching the query, one row per name.

    The same bank appears as a separate cluster
    at each organization it serves (nothing in the filings links them), so rows
    are grouped by normalized name; the link goes to the record with most filings.
    """
    tokens = query_tokens(q)
    if not tokens:
        return []
    trgm = db.has_trgm()
    params = {"prefix": _tsq(tokens, True), "norm": normalize_name(q) or " ".join(tokens),
              "ordered": ordered_prefix_regex(tokens), "limit": limit}
    score = "max(word_similarity(%(norm)s, name_norm))" if trgm else "0"
    # Word/prefix matches first; trigram neighbours (typos like "wels fargo") only if those find little.
    with db.conn() as conn:
        rows = _institution_rows(conn, params, "i.name_tsv @@ to_tsquery('simple', %(prefix)s)", score)
        if len(rows) < 3 and trgm:
            rows = _institution_rows(conn, params, "(i.name_tsv @@ to_tsquery('simple', %(prefix)s) "
                                                   "OR %(norm)s <%% i.name_norm)", score)
        return rows


def _institution_rows(conn, params, match, score):
    return conn.execute(f"""
            WITH m AS (SELECT i.id, i.name_norm, i.display_name, i.n_orgs, i.n_filings, i.first_year, i.last_year,
                              i.max_comp, i.states
                       FROM person_clusters i
                       WHERE i.is_institution AND {match})
            SELECT name_norm, (array_agg(id ORDER BY n_filings DESC))[1] AS id,
                   (array_agg(display_name ORDER BY n_filings DESC))[1] AS display_name,
                   count(*) AS n_records, sum(n_orgs) AS n_orgs, sum(n_filings) AS n_filings,
                   min(first_year) AS first_year, max(last_year) AS last_year, max(max_comp) AS max_comp,
                   (SELECT array_agg(DISTINCT s ORDER BY s) FROM m m2, unnest(m2.states) s
                     WHERE m2.name_norm = m.name_norm) AS states,
                   {score} AS score, bool_or(name_norm ~ %(ordered)s) AS in_order
            FROM m GROUP BY name_norm
            ORDER BY (name_norm = %(norm)s) DESC, in_order DESC, round(({score})::numeric, 2) DESC,
                     sum(n_filings) DESC
            LIMIT %(limit)s""", params).fetchall()


def did_you_mean(conn, tokens, norm, trgm) -> list[str]:
    T = db.search_table()   # noqa: N806
    if trgm:
        rows = conn.execute(f"""
            SELECT name_norm, max(display_name) AS display_name,
                   max(greatest(similarity(name_norm, %(n)s), word_similarity(%(n)s, name_norm))) AS s,
                   sum(n_filings) AS n
            FROM (SELECT * FROM {T} WHERE %(n)s <%% name_norm LIMIT 2000) c
            WHERE name_norm <> %(n)s
            GROUP BY name_norm ORDER BY s DESC, n DESC LIMIT 8""", {"n": norm}).fetchall()
    else:
        # Without pg_trgm: names that sound alike, closest length first.
        sound = sound_query(tokens)
        if not sound:
            return []
        rows = conn.execute(f"""
            SELECT name_norm, max(display_name) AS display_name, sum(n_filings) AS n
            FROM {T} WHERE sound_tsv @@ to_tsquery('simple', %(q)s) AND name_norm <> %(n)s
            GROUP BY name_norm ORDER BY abs(length(name_norm) - length(%(n)s)), n DESC LIMIT 8""",
            {"q": sound, "n": norm}).fetchall()
    return [r["display_name"] for r in rows]


def search_contractors(q: str, limit: int = 10, offset: int = 0) -> list[dict]:
    tokens = query_tokens(q)
    if not tokens:
        return []
    norm = normalize_org(q)
    match = ("(name_tsv @@ to_tsquery('simple', %(prefix)s) OR %(norm)s <%% name_norm)" if db.has_trgm()
             else "name_tsv @@ to_tsquery('simple', %(prefix)s)")
    rank = "max(word_similarity(%(norm)s, name_norm)) DESC," if db.has_trgm() else ""
    with db.conn() as conn:
        return conn.execute(f"""
            WITH m AS (SELECT * FROM contractors WHERE {match} LIMIT 20000)
            SELECT min(id) AS id, max(name_raw) AS name, name_norm, count(DISTINCT ein) AS n_orgs,
                   min(tax_year) AS first_year, max(tax_year) AS last_year, sum(compensation) AS total_comp,
                   array_agg(DISTINCT state) FILTER (WHERE state IS NOT NULL) AS states,
                   (array_agg(service_description ORDER BY tax_year DESC) FILTER (WHERE service_description IS NOT NULL))[1] AS service
            FROM m GROUP BY name_norm
            ORDER BY (name_norm = %(norm)s) DESC, {rank} count(DISTINCT ein) DESC, sum(compensation) DESC NULLS LAST
            LIMIT %(limit)s OFFSET %(offset)s""",
            {"prefix": _tsq(tokens, True), "norm": norm, "limit": limit, "offset": offset}).fetchall()


def search_orgs(q: str, limit: int = 10, offset: int = 0, daf_only: bool = False,
                state: str | None = None, city: str | None = None) -> list[dict]:
    """Organizations by name, optionally only DAF sponsors and/or in a state or city. With no name
    but a place, every organization there, largest first."""
    tokens = query_tokens(q)
    if not tokens and not (state or city):
        return []
    trgm = db.has_trgm() and bool(tokens)
    rank = "word_similarity(%(norm)s, name_norm) DESC," if trgm else ""
    params = {"prefix": _tsq(tokens, True) if tokens else "", "norm": normalize_org(q) if tokens else "",
              "limit": limit, "offset": offset, "state": state, "city": (city or "").strip().upper()}
    where = (" AND daf_sponsor" if daf_only else "") + (" AND state = %(state)s" if state else "") \
        + (" AND upper(city) = %(city)s" if city else "")
    sql = """
            SELECT ein, name, name_norm, city, state, ntee, latest_filing_year, latest_total_revenue,
                   latest_total_assets, latest_num_employees, daf_sponsor, daf_last_year
            FROM (SELECT * FROM organizations WHERE ({match}){where} {inner}) o
            ORDER BY (name_norm = %(norm)s) DESC, {rank} (latest_filing_year IS NOT NULL) DESC,
                     latest_total_revenue DESC NULLS LAST, ein
            LIMIT %(limit)s OFFSET %(offset)s"""
    with db.conn() as conn:
        if not tokens:
            # A place alone: no name to match, so rank everything there by size.
            return conn.execute(sql.format(match="true", where=where, rank="", inner=""), params).fetchall()
        rows = conn.execute(sql.format(match="name_tsv @@ to_tsquery('simple', %(prefix)s)", rank=rank,
                                       where=where, inner="LIMIT 2000"), params).fetchall()
        if len(rows) < 3 and trgm:
            # Few word matches: add trigram neighbours (misspellings, run-together words).
            rows = conn.execute(sql.format(match="(name_tsv @@ to_tsquery('simple', %(prefix)s) "
                                                 "OR %(norm)s <%% name_norm)", rank=rank, where=where,
                                           inner="LIMIT 2000"), params).fetchall()
        return rows


def daf_sponsors(q: str = "", state: str | None = None, city: str | None = None, limit: int = 50) -> list[dict]:
    """Donor-advised fund sponsors (Schedule D Part I on their returns), optionally by name, state or city, with
    the latest return's DAF figures: funds held, contributions in, grants out, value at year end. Largest first."""
    norm = normalize_org(q) if q else ""
    where = ["o.daf_sponsor"]
    params: dict = {"limit": limit}
    if state:
        where.append("o.state = %(state)s"); params["state"] = state
    if city:
        where.append("upper(o.city) = %(city)s"); params["city"] = city.strip().upper()
    if norm:
        where.append("o.name_norm LIKE %(name)s"); params["name"] = f"%{norm}%"
    with db.conn() as conn:
        return conn.execute(f"""
            SELECT o.ein, o.name, o.city, o.state, d.tax_year, d.daf_count, d.daf_contributions, d.daf_grants,
                   d.daf_value_eoy, d.filing_id
            FROM organizations o
            LEFT JOIN LATERAL (SELECT d.* FROM daf_stats d JOIN filings f ON f.id = d.filing_id AND NOT f.superseded
                               WHERE d.ein = o.ein AND (d.maintains_dafs OR d.daf_count IS NOT NULL)
                               ORDER BY d.tax_year DESC NULLS LAST LIMIT 1) d ON true
            WHERE {" AND ".join(where)}
            ORDER BY d.daf_value_eoy DESC NULLS LAST, o.latest_total_revenue DESC NULLS LAST, o.ein
            LIMIT %(limit)s""", params).fetchall()


_ORG_SUFFIX = re.compile(r"\s+(inc|incorporated|corp|corporation|co|company|llc|ltd|foundation|fund|trust|"
                         r"association|assn|society)$")


def best_org(name: str, state: str | None = None, city: str | None = None) -> dict | None:
    """The one organization a name most likely means: the same name (give or take Inc, Foundation...),
    else one containing every word, else the same after dropping leading words ("Bill & Melinda Gates
    Foundation" -> "Gates Foundation", the current IRS name); ties go to the larger organization. A live
    alias ("INSEAD") wins outright."""
    from app import aliases
    al = aliases.lookup(name)
    if al:
        return {**al["primary"], "alias": al}
    words = normalize_org(name).split()
    while words:
        q = " ".join(words)
        cands = search_orgs(q, limit=25, state=state, city=city)
        whole = [c for c in cands if set(words) <= set((c["name_norm"] or "").split())]
        if whole:
            return max(whole, key=lambda c: (_ORG_SUFFIX.sub("", c["name_norm"] or "") == _ORG_SUFFIX.sub("", q),
                                             c["name_norm"] == q, c["latest_total_revenue"] or 0))
        words = words[1:]
    return None


# --- firms (organizations) and their people --------------------------------------

FIRM_PAGE = 20          # organizations per page of firm search
FIRM_PEOPLE = 10        # people shown under each organization in firm search


def org_people(eins: list[str], per_org: int | None = None) -> dict[str, list[dict]]:
    """Everyone who has served at each organization, newest first then best paid.

    Per person and organization: total pay from that organization (excluding
    superseded returns), pay in their latest year there, first/last year, latest
    title, and how many organizations they serve overall. With per_org, only the
    top rows for each organization are returned (plus the full count).
    """
    if not eins:
        return {}
    limit = "" if per_org is None else "WHERE rk <= %(per_org)s"
    with db.conn() as conn:
        rows = conn.execute(f"""
            WITH per AS (
                SELECT p.ein, m.cluster_id,
                       sum(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0))
                           FILTER (WHERE NOT f.superseded) AS total,
                       (array_agg(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0)
                                  ORDER BY p.tax_year DESC NULLS LAST, f.superseded))[1] AS latest_pay,
                       (array_agg(p.title ORDER BY p.tax_year DESC NULLS LAST))[1] AS latest_title,
                       (array_agg(p.avg_hours ORDER BY p.tax_year DESC NULLS LAST))[1] AS latest_hours,
                       bool_or(p.comp_org IS NOT NULL OR p.comp_related IS NOT NULL OR p.other_comp IS NOT NULL)
                           AS comp_reported,
                       min(p.tax_year) AS first_year, max(p.tax_year) AS last_year
                FROM people p
                JOIN filings f ON f.id = p.filing_id AND NOT f.superseded
                JOIN person_cluster_members m ON m.person_id = p.id
                WHERE p.ein = ANY(%(eins)s) AND NOT p.is_duplicate
                GROUP BY p.ein, m.cluster_id
            ), latest AS (
                SELECT per.*, max(last_year) OVER (PARTITION BY ein) AS org_last_year,
                       count(*) OVER (PARTITION BY ein) AS n_people
                FROM per
            ), ranked AS (
                SELECT latest.*,
                       row_number() OVER (PARTITION BY ein ORDER BY (last_year = org_last_year) DESC,
                                          total DESC NULLS LAST, last_year DESC NULLS LAST, cluster_id) AS rk
                FROM latest
            )
            SELECT r.*, pc.display_name, pc.n_orgs, pc.is_institution
            FROM ranked r JOIN person_clusters pc ON pc.id = r.cluster_id
            {limit}
            ORDER BY r.ein, r.rk""", {"eins": list(eins), "per_org": per_org}).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        r["current"] = r["last_year"] == r["org_last_year"]
        out.setdefault(r["ein"], []).append(r)
    return out


def search_firms(q: str, page: int = 1, daf_only: bool = False, state: str | None = None,
                 city: str | None = None) -> dict:
    """Organizations matching the query (only DAF sponsors, if asked; in a state or city, if given),
    each with its people and their pay."""
    orgs = search_orgs(q, limit=FIRM_PAGE + 1, offset=(page - 1) * FIRM_PAGE, daf_only=daf_only,
                       state=state, city=city)
    more = len(orgs) > FIRM_PAGE
    orgs = orgs[:FIRM_PAGE]
    people = org_people([o["ein"] for o in orgs], per_org=FIRM_PEOPLE)
    for o in orgs:
        o["people"] = people.get(o["ein"], [])
        o["n_people"] = o["people"][0]["n_people"] if o["people"] else 0
    return {"orgs": orgs, "more": more}


# --- person -------------------------------------------------------------------

def resolve_person(cluster_id: int) -> int | None:
    """A cluster id that was merged away: find the cluster its people now belong to."""
    with db.conn() as conn:
        r = conn.execute("SELECT cluster_id FROM person_cluster_members WHERE person_id = %s", (cluster_id,)).fetchone()
        return r["cluster_id"] if r else None


BIG_CLUSTER = 1000      # filings; above this a person page loads one year at a time
BIG_YEAR_ROWS = 500     # rows shown for one year of a big cluster unless "show all"
BIG_ALL_ROWS = 300      # most recent rows shown on a big cluster's "All years" tab

_PERSON_ROW = """
    SELECT p.id, p.tax_year, p.ein, p.title, p.avg_hours, p.avg_hours_related, p.comp_org, p.comp_related,
           p.other_comp, p.name_raw, p.is_officer, p.is_director, p.is_trustee, p.is_key_employee,
           p.is_highest_comp, p.is_former, p.source,
           coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total,
           f.id AS filing_id, f.object_id, f.form_type, f.tax_period_end, f.superseded,
           coalesce(o.name, f.org_name) AS org_name, f.state,
           sj.base_org, sj.base_related, sj.bonus_org, sj.bonus_related, sj.other_org, sj.other_related,
           sj.deferred_org, sj.deferred_related, sj.nontaxable_org, sj.nontaxable_related,
           sj.total_org, sj.total_related
    FROM person_cluster_members m
    JOIN people p ON p.id = m.person_id
    JOIN filings f ON f.id = p.filing_id
    LEFT JOIN organizations o ON o.ein = p.ein
    LEFT JOIN schedule_j sj ON sj.person_id = p.id
    WHERE m.cluster_id = %(id)s AND NOT p.is_duplicate"""


def _big_summary(conn, cluster_id: int) -> list[dict] | None:
    try:
        row = conn.execute("SELECT years FROM person_big_summary WHERE cluster_id = %s", (cluster_id,)).fetchone()
    except Exception:  # noqa: BLE001 - table not built yet: compute live
        return None
    return row["years"] if row else None


def person(cluster_id: int, full: bool = True, year: int | None = None, show_all: bool = False) -> dict | None:
    """A person's rows. full=False (the search popup) skips "serves alongside" and the evidence.

    Big clusters (mostly banks serving thousands of foundations) load one year at
    a time: totals still cover every row, but only the selected year's rows (or,
    on "All years", the most recent ones) are fetched and rendered.
    """
    with db.conn() as conn:
        c = conn.execute("SELECT * FROM person_clusters WHERE id = %s", (cluster_id,)).fetchone()
        if not c:
            return None
        big = (c["n_filings"] or 0) > BIG_CLUSTER
        params = {"id": cluster_id, "year": year}
        # Very large records: per-year totals and counts are precomputed (loader/search_table.py).
        summary = _big_summary(conn, cluster_id) if big else None
        if not big:
            rows = conn.execute(_PERSON_ROW + " ORDER BY p.tax_year DESC NULLS LAST, org_name, p.id", params).fetchall()
            n_rows = len(rows)
        else:
            if year:
                limit = "" if show_all else f" LIMIT {BIG_YEAR_ROWS}"
                rows = conn.execute(_PERSON_ROW + " AND p.tax_year = %(year)s ORDER BY total DESC, org_name, p.id"
                                    + limit, params).fetchall()
                n_rows = next((y["n_rows"] for y in summary if y["tax_year"] == year), 0) if summary else \
                    conn.execute("""SELECT count(*) FROM person_cluster_members m JOIN people p ON p.id = m.person_id
                                    WHERE m.cluster_id = %(id)s AND p.tax_year = %(year)s""", params).fetchone()["count"]
            else:
                rows = conn.execute(_PERSON_ROW + f" ORDER BY p.tax_year DESC NULLS LAST, total DESC, p.id LIMIT {BIG_ALL_ROWS}",
                                    params).fetchall()
                n_rows = sum(y["n_rows"] for y in summary) if summary else conn.execute(
                    "SELECT count(*) FROM person_cluster_members WHERE cluster_id = %(id)s", params).fetchone()["count"]
        # Year and lifetime totals over every row, excluding superseded returns.
        totals = [y for y in summary if y["n"]] if summary else conn.execute("""
            SELECT p.tax_year, sum(coalesce(p.comp_org, 0)) AS comp_org, sum(coalesce(p.comp_related, 0)) AS comp_related,
                   sum(coalesce(p.other_comp, 0)) AS other_comp,
                   sum(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0)) AS total,
                   count(*) AS n
            FROM person_cluster_members m JOIN people p ON p.id = m.person_id JOIN filings f ON f.id = p.filing_id
            WHERE m.cluster_id = %(id)s AND NOT f.superseded AND NOT p.is_duplicate
            GROUP BY p.tax_year ORDER BY p.tax_year DESC NULLS LAST""", params).fetchall()
        skip_alongside = not full or big or c.get("is_institution")
        alongside = [] if skip_alongside else conn.execute("""
            WITH mine AS (SELECT DISTINCT p.filing_id FROM person_cluster_members m
                          JOIN people p ON p.id = m.person_id WHERE m.cluster_id = %(id)s)
            SELECT m2.cluster_id AS id, pc.display_name, pc.is_institution, count(DISTINCT p2.filing_id) AS n_shared,
                   count(DISTINCT p2.ein) AS n_orgs, min(p2.tax_year) AS first_year, max(p2.tax_year) AS last_year
            FROM mine JOIN people p2 ON p2.filing_id = mine.filing_id
            JOIN person_cluster_members m2 ON m2.person_id = p2.id
            JOIN person_clusters pc ON pc.id = m2.cluster_id
            WHERE m2.cluster_id <> %(id)s
            GROUP BY m2.cluster_id, pc.display_name, pc.is_institution
            HAVING count(DISTINCT p2.filing_id) >= 2
            ORDER BY n_orgs DESC, n_shared DESC, pc.display_name LIMIT 100""", params).fetchall()
        names = {}
        if full:
            eins = {r["ein"] for r in rows}
            for e in c["evidence"] or []:
                eins.update(e.get("eins", []))
                if e.get("ein"):
                    eins.add(e["ein"])
            if eins:
                names = {r["ein"]: r["name"] for r in conn.execute(
                    "SELECT ein, name FROM organizations WHERE ein = ANY(%s)", (list(eins),))}
    keys = ("comp_org", "comp_related", "other_comp", "total")
    by_year = {t["tax_year"]: {k: t[k] for k in keys} for t in totals}
    lifetime = {k: sum(t[k] or 0 for t in totals) for k in keys}
    years = [t["tax_year"] for t in totals if t["tax_year"]]
    return {"cluster": c, "rows": rows, "years": years, "by_year": by_year, "lifetime": lifetime,
            "alongside": alongside, "alongside_skipped": skip_alongside and full,
            "big": big, "n_rows": n_rows, "show_all": show_all,
            "why": explain(c, rows, names) if full else [], "org_names": names}


def explain(c, rows, names) -> list[str]:
    """Plain-English reasons the rows in a cluster were linked."""
    out = []
    units = defaultdict(lambda: {"years": set(), "names": set(), "n": 0})
    for r in rows:
        u = units[r["ein"]]
        if r["tax_year"]:
            u["years"].add(r["tax_year"])
        u["names"].add(r["name_raw"])
        u["n"] += 1
    if c.get("is_institution") or len(units) > 25:
        # Many organizations (a bank serving thousands of foundations): one line, not one per organization.
        units = {}
    for ein, u in sorted(units.items(), key=lambda kv: -max(kv[1]["years"] or {0})):
        org = names.get(ein, ein)
        ys = sorted(u["years"])
        span = f"{ys[0]}-{ys[-1]}" if len(ys) > 1 else (str(ys[0]) if ys else "")
        if u["n"] > 1:
            out.append(f"Same organization: {org}, {span} ({u['n']} filings).")
    care = [e for e in (c["evidence"] or []) if e.get("r") == "care_of"]
    if care:
        listed = "; ".join(sorted({f'"{e.get("listed_as")}"' for e in care})[:4])
        banks = ", ".join(sorted({e.get("bank", "").title() for e in care}))
        out.append(f"An individual listed in care of {banks} on some filings ({listed}); shown under their own name.")
    for e in c["evidence"] or []:
        if e.get("r") == "same_institution":
            variants = "; ".join(n.title() for n in e.get("names", [])[:8])
            out.insert(0, f"One institution: {e.get('n', 0):,} records under the same name once suffixes like "
                          f"N.A. and Trustee are dropped ({variants}).")
    related, addr_org, addr_person, board, board_with, board_max = set(), set(), set(), set(), [], 0
    for e in c["evidence"] or []:
        r = e.get("r")
        if r == "variant":
            out.append(f"Name variants at the same organization ({names.get(e['ein'], e['ein'])}): "
                       f"\"{e['names'][0]}\" and \"{e['names'][1]}\".")
        elif r == "related_org":
            related.update(e["eins"])
        elif r == "address":
            (addr_person if e.get("kind") == "person" else addr_org).update(e["eins"])
        elif r == "co_board":
            board.update(e["eins"])
            board_max = max(board_max, e.get("n_shared", 0))
            board_with += [n for n in e.get("with", []) if n not in board_with]

    def orgs(eins):
        return "; ".join(sorted(names.get(x, x) for x in eins))

    if related:
        out.append(f"These organizations list each other as related on Schedule R: {orgs(related)}.")
    if addr_org:
        out.append(f"Same name at organizations that share a street address: {orgs(addr_org)}.")
    if addr_person:
        out.append(f"Same name and same personal address on filings of: {orgs(addr_person)}.")
    if board:
        sample = ", ".join(n.title() for n in board_with[:5])
        out.append(f"Serves alongside up to {board_max} of the same people ({sample}) at: {orgs(board)}.")
    if not out:
        out.append("One filing, so nothing to link.")
    return out


# --- organization -------------------------------------------------------------

def org(ein: str) -> dict | None:
    with db.conn() as conn:
        o = conn.execute("SELECT * FROM organizations WHERE ein = %s", (ein,)).fetchone()
        if not o:
            return None
        filings = conn.execute("""
            SELECT id, object_id, form_type, tax_year, tax_period_end, filed_date, total_revenue, total_expenses,
                   total_assets_eoy, total_liabilities_eoy, net_assets_eoy, contributions, program_service_revenue,
                   officer_comp_total, num_employees, num_volunteers, mission, amended, superseded, website
            FROM filings WHERE ein = %s ORDER BY tax_year DESC NULLS LAST, object_id DESC""", (ein,)).fetchall()
        people = conn.execute("""
            SELECT p.id, p.tax_year, p.name_raw, p.title, p.avg_hours, p.comp_org, p.comp_related, p.other_comp,
                   coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total,
                   m.cluster_id, pc.n_orgs, pc.is_institution, f.id AS filing_id, f.superseded
            FROM people p JOIN filings f ON f.id = p.filing_id AND NOT f.superseded
            LEFT JOIN person_cluster_members m ON m.person_id = p.id
            LEFT JOIN person_clusters pc ON pc.id = m.cluster_id
            WHERE p.ein = %s AND NOT p.is_duplicate ORDER BY p.tax_year DESC NULLS LAST, total DESC, p.id""", (ein,)).fetchall()
        contractors = conn.execute("""
            SELECT c.id, c.tax_year, c.name_raw, c.city, c.state, c.service_description, c.compensation,
                   f.id AS filing_id
            FROM contractors c JOIN filings f ON f.id = c.filing_id AND NOT f.superseded
            WHERE c.ein = %s ORDER BY c.tax_year DESC NULLS LAST, c.compensation DESC NULLS LAST""", (ein,)).fetchall()
        # This organization on other organizations' contractor lists (matched by name and address).
        as_vendor = conn.execute("""
            SELECT c.id, c.tax_year, c.ein, coalesce(po.name, f.org_name) AS payer, c.service_description,
                   c.compensation, f.id AS filing_id
            FROM vendor_org_links l JOIN contractors c ON c.id = l.contractor_id
            JOIN filings f ON f.id = c.filing_id AND NOT f.superseded
            LEFT JOIN organizations po ON po.ein = c.ein
            WHERE l.ein = %s ORDER BY c.tax_year DESC NULLS LAST, c.compensation DESC NULLS LAST
            LIMIT 500""", (ein,)).fetchall()
        daf = conn.execute("""
            SELECT d.*, f.id AS filing_id, f.object_id FROM daf_stats d JOIN filings f ON f.id = d.filing_id
            WHERE d.ein = %s AND NOT f.superseded
              AND (d.maintains_dafs OR d.daf_count IS NOT NULL OR d.daf_value_eoy IS NOT NULL)
            ORDER BY d.tax_year DESC NULLS LAST""", (ein,)).fetchall()
        received = grants_received(conn, o)
        expenses = conn.execute("""
            SELECT e.*, f.id AS filing_id FROM expense_breakdown e JOIN filings f ON f.id = e.filing_id
            WHERE e.ein = %s AND NOT f.superseded ORDER BY e.tax_year DESC NULLS LAST, f.object_id DESC""",
            (ein,)).fetchall()
        made = grants_made(conn, ein)
        donors = donors_by_year(conn, ein)
    mission = next((f["mission"] for f in filings if f["mission"]), None)
    people_by_year = defaultdict(list)
    for p in people:
        people_by_year[p["tax_year"]].append(p)
    contractors_by_year = defaultdict(list)
    for c in contractors:
        contractors_by_year[c["tax_year"]].append(c)
    return {"org": o, "filings": filings, "mission": mission, "people_by_year": dict(people_by_year),
            "contractors_by_year": dict(contractors_by_year), "as_vendor": as_vendor, "daf": daf, "received": received,
            "expenses": [_expense_view(e) for e in expenses], "made": made, "donors": donors,
            "pay_summary": _pay_summary(people, filings),
            "headline": next((f for f in filings if not f["superseded"]), None)}


def _expense_view(e: dict) -> dict:
    """An expense_breakdown row ready to show: lines biggest first, events marked, the total apart."""
    lines = [dict(zip(("key", "label", "desc", "total", "program", "management", "fundraising", "is_event"), ln))
             for ln in e["lines"] or []]
    detail = sorted((ln for ln in lines if ln["key"] != "total"), key=lambda ln: -(ln["total"] or 0))
    total = e["total_expenses"] or sum(ln["total"] or 0 for ln in detail)
    for ln in detail:
        ln["share"] = (ln["total"] or 0) / total if total else None
    events = (e["event_lines_total"] or 0) + (e["special_event_expenses"] or 0) + (e["conferences_total"] or 0)
    return {**e, "detail": detail, "total": total, "events": events, "has_columns": e["form_type"] == "990"}


def _pay_summary(people: list[dict], filings: list[dict]) -> dict:
    """Per tax year: people listed, how many were paid, total pay, employees, volunteers."""
    out: dict = {}
    for p in people:
        if p["superseded"]:
            continue
        y = out.setdefault(p["tax_year"], {"listed": 0, "paid": 0, "total": 0})
        y["listed"] += 1
        if p["total"]:
            y["paid"] += 1
            y["total"] += p["total"]
    for f in filings:
        if not f["superseded"] and f["tax_year"] in out:
            out[f["tax_year"]].setdefault("employees", f["num_employees"])
            out[f["tax_year"]].setdefault("volunteers", f["num_volunteers"])
    return out


def grants_made(conn, ein: str) -> dict:
    """Per tax year, from the current return only: grants to organizations and to individuals,
    summary lines (a list kept in a separate attachment), returned grants, and the return's own
    "grants paid" expense line to reconcile against."""
    years = conn.execute("""
        WITH g AS (
            SELECT g.*, coalesce(g.cash_amount, 0) + coalesce(g.noncash_amount, 0) AS amount
            FROM grants g JOIN filings f ON f.id = g.filing_id AND NOT f.superseded WHERE g.ein = %(ein)s)
        SELECT tax_year,
               count(*) FILTER (WHERE NOT recipient_is_person AND NOT is_summary AND amount >= 0) AS n_orgs,
               sum(amount) FILTER (WHERE NOT recipient_is_person AND NOT is_summary AND amount >= 0) AS to_orgs,
               count(*) FILTER (WHERE recipient_is_person AND amount >= 0) AS n_people,
               sum(amount) FILTER (WHERE recipient_is_person AND amount >= 0) AS to_people,
               count(*) FILTER (WHERE is_summary) AS n_summary,
               sum(amount) FILTER (WHERE is_summary) AS summary_total,
               count(*) FILTER (WHERE amount < 0) AS n_returned,
               sum(amount) FILTER (WHERE amount < 0) AS returned,
               sum(amount) AS listed
        FROM g GROUP BY tax_year ORDER BY tax_year DESC NULLS LAST""", {"ein": ein}).fetchall()
    expense = {r["tax_year"]: r["grants_total"] for r in conn.execute("""
        SELECT e.tax_year, sum(e.grants_total) AS grants_total FROM expense_breakdown e
        JOIN filings f ON f.id = e.filing_id AND NOT f.superseded WHERE e.ein = %s GROUP BY e.tax_year""", (ein,))}
    for y in years:
        for k in ("to_orgs", "to_people", "summary_total", "returned", "listed"):
            y[k] = int(y[k]) if y[k] is not None else None
        line = expense.get(y["tax_year"])
        y["expense_line"] = int(line) if line is not None else None
        listed, line = y["listed"] or 0, y["expense_line"]
        # Reported apart when they differ by more than 1% (accruals, attachments, rounding).
        y["mismatch"] = bool(line) and abs(listed - line) > max(1000, 0.01 * abs(line))
    return {"years": years, "n_total": sum(y["n_orgs"] for y in years)}


def grants_year(ein: str, year: int) -> list[dict]:
    """Every grant this organization listed for one tax year (current return only), biggest first;
    returned or refunded grants (negative) last."""
    with db.conn() as conn:
        rows = conn.execute("""
            SELECT x.*, coalesce(r.ein, (SELECT min(o2.ein) FROM organizations o2
                                         WHERE x.recipient_ein IS NULL AND NOT x.recipient_is_person
                                           AND o2.name_norm = x.recipient_name_norm AND o2.state = x.state
                                         HAVING count(*) = 1)) AS recipient_org,
                   r.daf_sponsor AS recipient_daf
            FROM (SELECT g.*, coalesce(g.cash_amount, 0) + coalesce(g.noncash_amount, 0) AS amount,
                         f.id AS fid, f.form_type
                  FROM grants g JOIN filings f ON f.id = g.filing_id AND NOT f.superseded
                  WHERE g.ein = %s AND g.tax_year = %s) x
            LEFT JOIN organizations r ON r.ein = x.recipient_ein
            ORDER BY (x.amount < 0), x.is_summary DESC, x.amount DESC, x.recipient_name""", (ein, year)).fetchall()
    for r in rows:
        r["kind"] = ("returned or refunded grant" if r["amount"] < 0 else "summary line" if r["is_summary"]
                     else "individual" if r["recipient_is_person"] else "organization")
    return rows


DONOR_MATCH = 0.6   # trigram similarity for a FUZZY link from a business contributor to an organization


def donors_by_year(conn, ein: str) -> list[dict]:
    """Schedule B Part I contributors (990-PF), per tax year, current return only. Business
    contributors link to an organization only on name and state (FUZZY, with the score)."""
    rows = conn.execute("""
        SELECT d.*, f.id AS fid, f.form_type, f.object_id
        FROM donors d JOIN filings f ON f.id = d.filing_id AND NOT f.superseded
        WHERE d.ein = %s ORDER BY d.tax_year DESC NULLS LAST, d.total_amount DESC NULLS LAST, d.contributor_num""",
        (ein,)).fetchall()
    for r in rows:
        r["match"] = None
        if not r["is_person"] and r["name_norm"] and r["state"]:
            m = conn.execute("""
                SELECT ein, name, round(similarity(name_norm, %(n)s)::numeric, 2) AS score FROM organizations
                WHERE state = %(s)s AND name_norm %% %(n)s AND ein <> %(ein)s
                ORDER BY similarity(name_norm, %(n)s) DESC, latest_total_revenue DESC NULLS LAST LIMIT 1""",
                {"n": r["name_norm"], "s": r["state"], "ein": ein}).fetchone()
            if m and m["score"] >= DONOR_MATCH:
                r["match"] = {"ein": m["ein"], "name": m["name"], "score": float(m["score"]), "kind": "FUZZY"}
    years: dict = {}
    for r in rows:
        y = years.setdefault(r["tax_year"], {"tax_year": r["tax_year"], "rows": [], "total": 0, "fid": r["fid"],
                                             "form_type": r["form_type"]})
        y["rows"].append(r)
        y["total"] += r["total_amount"] or 0
    return list(years.values())


def org_name(ein: str) -> dict | None:
    with db.conn() as conn:
        return conn.execute("SELECT ein, name, city, state FROM organizations WHERE ein = %s", (ein,)).fetchone()


def org_exists(ein: str) -> bool:
    with db.conn() as conn:
        return conn.execute("SELECT 1 FROM organizations WHERE ein = %s", (ein,)).fetchone() is not None


GRANTS_SHOWN = 300


def grants_received(conn, o) -> dict:
    """Grants to this organization reported by other filers: Schedule I (matched by the EIN the
    grantor wrote down) and 990-PF grants paid (no EIN on that form: matched by exact name and state)."""
    params = {"ein": o["ein"], "norm": o["name_norm"] or "", "state": o["state"], "lim": GRANTS_SHOWN}
    found = """
        WITH g AS (
            SELECT g.id, g.filing_id, g.tax_year, g.cash_amount, g.noncash_amount, g.purpose, g.source,
                   'ein' AS matched_by
            FROM grants g WHERE g.recipient_ein = %(ein)s
            UNION ALL
            SELECT g.id, g.filing_id, g.tax_year, g.cash_amount, g.noncash_amount, g.purpose, g.source,
                   'name and state'
            FROM grants g
            WHERE g.source = '990PF-XV' AND %(norm)s <> '' AND g.recipient_name_norm = %(norm)s
              AND g.state = %(state)s)
        SELECT g.*, f.ein AS grantor_ein, f.form_type, f.org_name,
               coalesce(g.cash_amount, 0) + coalesce(g.noncash_amount, 0) AS amount
        FROM g JOIN filings f ON f.id = g.filing_id AND NOT f.superseded AND f.ein <> %(ein)s"""
    totals = conn.execute(f"SELECT count(*) AS n, sum(amount) AS total FROM ({found}) x", params).fetchone()
    rows = conn.execute(f"""
        SELECT x.*, coalesce(go.name, x.org_name) AS grantor_name, d.maintains_dafs
        FROM (SELECT * FROM ({found}) y ORDER BY tax_year DESC NULLS LAST, amount DESC LIMIT %(lim)s) x
        LEFT JOIN organizations go ON go.ein = x.grantor_ein
        LEFT JOIN daf_stats d ON d.filing_id = x.filing_id
        ORDER BY x.tax_year DESC NULLS LAST, x.amount DESC""", params).fetchall()
    for r in rows:
        r["grantor_kind"] = ("Private foundation" if r["form_type"] == "990PF"
                             else "DAF sponsor" if r["maintains_dafs"] else "Public charity")
    return {"rows": rows, "n_total": totals["n"], "total": totals["total"] or 0}


# --- contractor ---------------------------------------------------------------

def contractor(cid: int) -> dict | None:
    with db.conn() as conn:
        c = conn.execute("SELECT * FROM contractors WHERE id = %s", (cid,)).fetchone()
        if not c:
            return None
        rows = conn.execute("""
            SELECT c.id, c.tax_year, c.ein, coalesce(o.name, f.org_name) AS org_name, c.name_raw, c.street, c.city,
                   c.state, c.zip, c.service_description, c.compensation, c.website, f.id AS filing_id, f.object_id
            FROM contractors c JOIN filings f ON f.id = c.filing_id LEFT JOIN organizations o ON o.ein = c.ein
            WHERE c.name_norm = %s ORDER BY c.tax_year DESC NULLS LAST, c.compensation DESC NULLS LAST
            LIMIT 2000""", (c["name_norm"],)).fetchall()
        canonical_id = conn.execute("SELECT min(id) AS id FROM contractors WHERE name_norm = %s",
                                    (c["name_norm"],)).fetchone()["id"]
        # Filing organizations this vendor matched by name and address (loader/vendor_orgs.py).
        orgs = conn.execute("""
            SELECT l.ein, coalesce(o.name, l.ein) AS name, count(*) AS n
            FROM contractors c JOIN vendor_org_links l ON l.contractor_id = c.id
            LEFT JOIN organizations o ON o.ein = l.ein
            WHERE c.name_norm = %s GROUP BY 1, 2 ORDER BY n DESC, 1""", (c["name_norm"],)).fetchall()
    counts = Counter((r["street"] or "", r["city"] or "", r["state"] or "", r["zip"] or "") for r in rows)
    addresses = address.collapse([a for a in counts if any(a)], counts)
    website = next((r["website"] for r in rows if r["website"]), None)
    return {"contractor": c, "canonical_id": canonical_id, "rows": rows, "addresses": addresses, "website": website,
            "total": sum(r["compensation"] or 0 for r in rows), "orgs": orgs}


# --- filing -------------------------------------------------------------------

def filing(fid: int) -> dict | None:
    with db.conn() as conn:
        return conn.execute("""SELECT f.*, coalesce(o.name, f.org_name) AS name FROM filings f
                               LEFT JOIN organizations o ON o.ein = f.ein WHERE f.id = %s""", (fid,)).fetchone()


_coverage: dict = {}
COVERAGE_TTL = 900
COVERAGE_SHARE = 0.2   # a tax year counts as covered at 20%+ of the best-covered year's filings


def coverage() -> dict:
    """Tax years with substantial coverage, and whether the full backfill has finished.

    Cached per worker for five minutes. Late filers put a handful of returns in
    old tax years; those don't count until the year has real coverage.
    """
    now = time.monotonic()
    if _coverage and now - _coverage["at"] < COVERAGE_TTL:
        return _coverage["value"]
    with db.conn() as conn:
        counts = conn.execute("SELECT tax_year, n FROM filing_year_counts").fetchall()
        done = conn.execute("SELECT status FROM loader_progress WHERE file = 'all'").fetchone()
    peak = max((r["n"] for r in counts), default=0)
    covered = [r["tax_year"] for r in counts if peak and r["n"] >= peak * COVERAGE_SHARE]
    value = {"first": min(covered, default=None), "last": max(covered, default=None),
             "complete": bool(done and done["status"] == "done")}
    _coverage.update(at=now, value=value)
    return value


def stats() -> dict:
    with db.conn() as conn:
        r = conn.execute("""SELECT (SELECT count(*) FROM person_clusters) AS clusters,
                                   (SELECT min(tax_year) FROM filings) AS y0, (SELECT max(tax_year) FROM filings) AS y1
                         """).fetchone()
    return r


def org_connected(ein: str, filing_id: int | None, limit: int = 20) -> list[dict]:
    """Organizations tied to this one: those sharing people with its latest return (officers, directors, key
    employees listed on both), and the related organizations it lists on Schedule R. Largest ties first."""
    if not filing_id:
        return []
    with db.conn() as conn:
        shared = conn.execute("""
            WITH here AS (SELECT DISTINCT m.cluster_id FROM people p JOIN person_cluster_members m ON m.person_id = p.id
                          JOIN person_clusters c ON c.id = m.cluster_id AND NOT c.is_institution
                          WHERE p.filing_id = %(f)s LIMIT 400)
            SELECT p.ein, count(DISTINCT h.cluster_id) AS people, max(p.tax_year) AS last_year,
                   (array_agg(DISTINCT c.display_name))[1:3] AS names
            FROM here h JOIN person_cluster_members m ON m.cluster_id = h.cluster_id
            JOIN people p ON p.id = m.person_id JOIN person_clusters c ON c.id = h.cluster_id
            WHERE p.ein <> %(e)s
            GROUP BY p.ein ORDER BY people DESC, last_year DESC LIMIT %(n)s""", {"f": filing_id, "e": ein, "n": limit}).fetchall()
        related = conn.execute("""SELECT DISTINCT r.related_ein AS ein FROM related_orgs r
                                  WHERE r.filing_id = %s AND r.related_ein <> %s LIMIT %s""",
                               (filing_id, ein, limit)).fetchall()
        eins = list({r["ein"] for r in shared} | {r["ein"] for r in related})
        orgs = {r["ein"]: r for r in conn.execute("""SELECT ein, name, city, state, latest_total_revenue FROM organizations
                                                     WHERE ein = ANY(%s)""", (eins,)).fetchall()}
    out = {}
    for r in shared:
        if r["ein"] in orgs:
            out[r["ein"]] = {**orgs[r["ein"]], "people": r["people"], "names": r["names"], "related": False}
    for r in related:
        if r["ein"] in orgs:
            out.setdefault(r["ein"], {**orgs[r["ein"]], "people": 0, "names": [], "related": True})["related"] = True
    return sorted(out.values(), key=lambda o: (-(o["people"] or 0), -(o["latest_total_revenue"] or 0)))[:limit]
