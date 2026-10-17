"""SQL behind the pages and the JSON API."""

from __future__ import annotations

import time
from collections import defaultdict

from app import db
from app.names import normalize_name, normalize_org, query_tokens

PAGE = 50
TIER_CAP = 1000
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
    params = {"exact": _tsq(tokens, False), "prefix": _tsq(tokens, True), "norm": norm or " ".join(tokens),
              "ordered": ordered_prefix_regex(tokens), "whole": ordered_words_regex(tokens),
              "close": CLOSE_SIMILARITY, "cap": TIER_CAP, "limit": PAGE, "offset": (page - 1) * PAGE}
    # People and institutions (banks, trust companies...) are searched separately.
    where = _filters(filters, params) + (" AND c.is_institution" if institutions else " AND NOT c.is_institution")
    sets = [
        f"""(SELECT c.id FROM person_clusters c WHERE c.name_tsv @@ to_tsquery('simple', %(exact)s){where}
             ORDER BY c.n_filings DESC LIMIT %(cap)s)""",
        f"""(SELECT c.id FROM person_clusters c WHERE c.name_tsv @@ to_tsquery('simple', %(prefix)s){where}
             ORDER BY c.n_filings DESC LIMIT %(cap)s)""",
    ]
    # Trigram candidates need some substance: query words under five letters
    # ("mich olen") are mostly common trigrams, so those go to prefix matching.
    # When the query itself reads like an institution ("bank of america"), its trigram
    # neighbours are mostly institutions, which the people search would scan only to
    # discard; whole-word and prefix matches still find people.
    if trgm and max(len(t) for t in tokens) >= TRGM_MIN_WORD and (institutions or not looks_institutional(tokens)):
        sets.insert(0, f"""(SELECT c.id FROM person_clusters c WHERE %(norm)s <%% c.name_norm{where}
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
        FROM cand JOIN person_clusters c ON c.id = cand.id
        ORDER BY band, (c.name_norm = %(norm)s) DESC, in_order DESC, round(({score})::numeric, 2) DESC,
                 c.n_filings DESC, sim DESC, c.id
        LIMIT %(limit)s OFFSET %(offset)s
    """
    with db.conn() as conn:
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
                    FROM person_clusters c
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
            WHERE m.cluster_id = ANY(%s)
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
    return " & ".join(soundex(t).lower() for t in tokens if len(t) > 1)


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
    if trgm:
        rows = conn.execute("""
            SELECT name_norm, max(display_name) AS display_name,
                   max(greatest(similarity(name_norm, %(n)s), word_similarity(%(n)s, name_norm))) AS s,
                   sum(n_filings) AS n
            FROM (SELECT * FROM person_clusters WHERE %(n)s <%% name_norm LIMIT 2000) c
            WHERE name_norm <> %(n)s
            GROUP BY name_norm ORDER BY s DESC, n DESC LIMIT 8""", {"n": norm}).fetchall()
    else:
        # Without pg_trgm: names that sound alike, closest length first.
        sound = sound_query(tokens)
        if not sound:
            return []
        rows = conn.execute("""
            SELECT name_norm, max(display_name) AS display_name, sum(n_filings) AS n
            FROM person_clusters WHERE sound_tsv @@ to_tsquery('simple', %(q)s) AND name_norm <> %(n)s
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


def search_orgs(q: str, limit: int = 10) -> list[dict]:
    tokens = query_tokens(q)
    if not tokens:
        return []
    trgm = db.has_trgm()
    rank = "word_similarity(%(norm)s, name_norm) DESC," if trgm else ""
    params = {"prefix": _tsq(tokens, True), "norm": normalize_org(q), "limit": limit}
    sql = """
            SELECT ein, name, city, state, ntee, latest_filing_year, latest_total_revenue
            FROM (SELECT * FROM organizations WHERE {match} LIMIT 2000) o
            ORDER BY (name_norm = %(norm)s) DESC, {rank} (latest_filing_year IS NOT NULL) DESC,
                     latest_total_revenue DESC NULLS LAST
            LIMIT %(limit)s"""
    with db.conn() as conn:
        rows = conn.execute(sql.format(match="name_tsv @@ to_tsquery('simple', %(prefix)s)", rank=rank),
                            params).fetchall()
        if len(rows) < 3 and trgm:
            # Few word matches: add trigram neighbours (misspellings, run-together words).
            rows = conn.execute(sql.format(match="(name_tsv @@ to_tsquery('simple', %(prefix)s) "
                                                 "OR %(norm)s <%% name_norm)", rank=rank), params).fetchall()
        return rows


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
           coalesce(o.name, f.org_name) AS org_name, f.state, m.evidence,
           sj.base_org, sj.base_related, sj.bonus_org, sj.bonus_related, sj.other_org, sj.other_related,
           sj.deferred_org, sj.deferred_related, sj.nontaxable_org, sj.nontaxable_related,
           sj.total_org, sj.total_related
    FROM person_cluster_members m
    JOIN people p ON p.id = m.person_id
    JOIN filings f ON f.id = p.filing_id
    LEFT JOIN organizations o ON o.ein = p.ein
    LEFT JOIN schedule_j sj ON sj.person_id = p.id
    WHERE m.cluster_id = %(id)s"""


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
        if not big:
            rows = conn.execute(_PERSON_ROW + " ORDER BY p.tax_year DESC NULLS LAST, org_name, p.id", params).fetchall()
            n_rows = len(rows)
        else:
            if year:
                limit = "" if show_all else f" LIMIT {BIG_YEAR_ROWS}"
                rows = conn.execute(_PERSON_ROW + " AND p.tax_year = %(year)s ORDER BY total DESC, org_name, p.id"
                                    + limit, params).fetchall()
                n_rows = conn.execute("""SELECT count(*) FROM person_cluster_members m JOIN people p ON p.id = m.person_id
                                         WHERE m.cluster_id = %(id)s AND p.tax_year = %(year)s""", params).fetchone()["count"]
            else:
                rows = conn.execute(_PERSON_ROW + f" ORDER BY p.tax_year DESC NULLS LAST, total DESC, p.id LIMIT {BIG_ALL_ROWS}",
                                    params).fetchall()
                n_rows = conn.execute("SELECT count(*) FROM person_cluster_members WHERE cluster_id = %(id)s",
                                      params).fetchone()["count"]
        # Year and lifetime totals over every row, excluding superseded returns.
        totals = conn.execute("""
            SELECT p.tax_year, sum(coalesce(p.comp_org, 0)) AS comp_org, sum(coalesce(p.comp_related, 0)) AS comp_related,
                   sum(coalesce(p.other_comp, 0)) AS other_comp,
                   sum(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0)) AS total,
                   count(*) AS n
            FROM person_cluster_members m JOIN people p ON p.id = m.person_id JOIN filings f ON f.id = p.filing_id
            WHERE m.cluster_id = %(id)s AND NOT f.superseded
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
            FROM people p JOIN filings f ON f.id = p.filing_id
            LEFT JOIN person_cluster_members m ON m.person_id = p.id
            LEFT JOIN person_clusters pc ON pc.id = m.cluster_id
            WHERE p.ein = %s ORDER BY p.tax_year DESC NULLS LAST, total DESC, p.id""", (ein,)).fetchall()
        contractors = conn.execute("""
            SELECT c.id, c.tax_year, c.name_raw, c.city, c.state, c.service_description, c.compensation,
                   f.id AS filing_id
            FROM contractors c JOIN filings f ON f.id = c.filing_id
            WHERE c.ein = %s ORDER BY c.tax_year DESC NULLS LAST, c.compensation DESC NULLS LAST""", (ein,)).fetchall()
    mission = next((f["mission"] for f in filings if f["mission"]), None)
    people_by_year = defaultdict(list)
    for p in people:
        people_by_year[p["tax_year"]].append(p)
    contractors_by_year = defaultdict(list)
    for c in contractors:
        contractors_by_year[c["tax_year"]].append(c)
    return {"org": o, "filings": filings, "mission": mission, "people_by_year": dict(people_by_year),
            "contractors_by_year": dict(contractors_by_year)}


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
    addresses = sorted({(r["street"] or "", r["city"] or "", r["state"] or "", r["zip"] or "") for r in rows})
    website = next((r["website"] for r in rows if r["website"]), None)
    return {"contractor": c, "rows": rows, "addresses": addresses, "website": website,
            "total": sum(r["compensation"] or 0 for r in rows)}


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
