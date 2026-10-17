"""SQL behind the pages and the JSON API."""

from __future__ import annotations

from collections import defaultdict

from app import db
from app.names import normalize_name, normalize_org, query_tokens

PAGE = 50
TIER_CAP = 1000


def _tsq(tokens, prefix: bool) -> str:
    return " & ".join(f"{t}:*" if prefix else t for t in tokens)


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


def search_people(q: str, filters: dict, page: int = 1) -> dict:
    tokens = query_tokens(q)
    norm = normalize_name(q)
    if not tokens:
        return {"results": [], "total": 0, "capped": False, "did_you_mean": []}
    trgm = db.has_trgm()
    params = {"exact": _tsq(tokens, False), "prefix": _tsq(tokens, True), "norm": norm,
              "cap": TIER_CAP, "limit": PAGE, "offset": (page - 1) * PAGE}
    where = _filters(filters, params)
    # Without pg_trgm, rank by closeness in length to the query as a similarity proxy.
    sim = ("similarity(c.name_norm, %(norm)s)" if trgm
           else "(1.0 / (1 + abs(length(c.name_norm) - length(%(norm)s))))")
    tiers = [
        f"""(SELECT c.id, 1 AS tier FROM person_clusters c
             WHERE c.name_tsv @@ to_tsquery('simple', %(exact)s){where}
             ORDER BY (c.name_norm = %(norm)s) DESC, {sim} DESC, c.n_filings DESC LIMIT %(cap)s)""",
        f"""(SELECT c.id, 2 AS tier FROM person_clusters c
             WHERE c.name_tsv @@ to_tsquery('simple', %(prefix)s)
               AND NOT c.name_tsv @@ to_tsquery('simple', %(exact)s){where}
             ORDER BY {sim} DESC, c.n_filings DESC LIMIT %(cap)s)""",
    ]
    if trgm:
        tiers.append(f"""(SELECT c.id, 3 AS tier FROM person_clusters c
             WHERE c.name_norm %% %(norm)s AND NOT c.name_tsv @@ to_tsquery('simple', %(prefix)s){where}
             ORDER BY {sim} DESC, c.n_filings DESC LIMIT %(cap)s)""")
    # Sounds-alike (Soundex on every word): catches misspellings with or without pg_trgm.
    sound = sound_query(tokens)
    if sound:
        params["sound"] = sound
        trgm_guard = "AND NOT c.name_norm %% %(norm)s" if trgm else ""
        tiers.append(f"""(SELECT c.id, 4 AS tier FROM person_clusters c
             WHERE c.sound_tsv @@ to_tsquery('simple', %(sound)s)
               AND NOT c.name_tsv @@ to_tsquery('simple', %(prefix)s) {trgm_guard}{where}
             ORDER BY {sim} DESC, c.n_filings DESC LIMIT %(cap)s)""")
    sql = f"""
        WITH cand AS ({" UNION ALL ".join(tiers)})
        SELECT c.id, c.display_name, c.name_norm, c.n_filings, c.n_orgs, c.first_year, c.last_year,
               c.max_comp, c.states, c.orgs, c.latest_title, cand.tier, {sim} AS sim,
               count(*) OVER () AS total, count(*) FILTER (WHERE cand.tier = 1) OVER () AS exact_total
        FROM cand JOIN person_clusters c ON c.id = cand.id
        ORDER BY cand.tier, (c.name_norm = %(norm)s) DESC, sim DESC, c.n_filings DESC, c.id
        LIMIT %(limit)s OFFSET %(offset)s
    """
    with db.conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        total = rows[0]["total"] if rows else 0
        exact_total = rows[0]["exact_total"] if rows else 0
        if not rows and page > 1:
            total = conn.execute(f"SELECT count(*) AS n FROM ({sql.replace('LIMIT %(limit)s OFFSET %(offset)s', '')}) x",
                                 params).fetchone()["n"]
        dym = did_you_mean(conn, tokens, norm, trgm) if exact_total < 5 else []
    return {"results": rows, "total": total, "capped": total >= TIER_CAP, "did_you_mean": dym}


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


def did_you_mean(conn, tokens, norm, trgm) -> list[str]:
    if trgm:
        rows = conn.execute("""
            SELECT name_norm, max(display_name) AS display_name, max(similarity(name_norm, %(n)s)) AS s,
                   sum(n_filings) AS n
            FROM person_clusters WHERE name_norm %% %(n)s AND name_norm <> %(n)s
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
    with db.conn() as conn:
        return conn.execute("""
            WITH m AS (SELECT * FROM contractors WHERE name_tsv @@ to_tsquery('simple', %(prefix)s))
            SELECT min(id) AS id, max(name_raw) AS name, name_norm, count(DISTINCT ein) AS n_orgs,
                   min(tax_year) AS first_year, max(tax_year) AS last_year, sum(compensation) AS total_comp,
                   array_agg(DISTINCT state) FILTER (WHERE state IS NOT NULL) AS states,
                   (array_agg(service_description ORDER BY tax_year DESC) FILTER (WHERE service_description IS NOT NULL))[1] AS service
            FROM m GROUP BY name_norm
            ORDER BY (name_norm = %(norm)s) DESC, count(DISTINCT ein) DESC, sum(compensation) DESC NULLS LAST
            LIMIT %(limit)s OFFSET %(offset)s""",
            {"prefix": _tsq(tokens, True), "norm": normalize_org(q), "limit": limit, "offset": offset}).fetchall()


def search_orgs(q: str, limit: int = 10) -> list[dict]:
    tokens = query_tokens(q)
    if not tokens:
        return []
    with db.conn() as conn:
        return conn.execute("""
            SELECT ein, name, city, state, ntee, latest_filing_year, latest_total_revenue
            FROM organizations WHERE name_tsv @@ to_tsquery('simple', %(prefix)s)
            ORDER BY (name_norm = %(norm)s) DESC, (latest_filing_year IS NOT NULL) DESC,
                     latest_total_revenue DESC NULLS LAST
            LIMIT %(limit)s""", {"prefix": _tsq(tokens, True), "norm": normalize_org(q), "limit": limit}).fetchall()


# --- person -------------------------------------------------------------------

def resolve_person(cluster_id: int) -> int | None:
    """A cluster id that was merged away: find the cluster its people now belong to."""
    with db.conn() as conn:
        r = conn.execute("SELECT cluster_id FROM person_cluster_members WHERE person_id = %s", (cluster_id,)).fetchone()
        return r["cluster_id"] if r else None


def person(cluster_id: int) -> dict | None:
    with db.conn() as conn:
        c = conn.execute("SELECT * FROM person_clusters WHERE id = %s", (cluster_id,)).fetchone()
        if not c:
            return None
        rows = conn.execute("""
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
            WHERE m.cluster_id = %s
            ORDER BY p.tax_year DESC NULLS LAST, org_name, p.id""", (cluster_id,)).fetchall()
        alongside = conn.execute("""
            WITH mine AS (SELECT DISTINCT p.filing_id FROM person_cluster_members m
                          JOIN people p ON p.id = m.person_id WHERE m.cluster_id = %(id)s)
            SELECT m2.cluster_id AS id, pc.display_name, count(DISTINCT p2.filing_id) AS n_shared,
                   count(DISTINCT p2.ein) AS n_orgs, min(p2.tax_year) AS first_year, max(p2.tax_year) AS last_year
            FROM mine JOIN people p2 ON p2.filing_id = mine.filing_id
            JOIN person_cluster_members m2 ON m2.person_id = p2.id
            JOIN person_clusters pc ON pc.id = m2.cluster_id
            WHERE m2.cluster_id <> %(id)s
            GROUP BY m2.cluster_id, pc.display_name
            HAVING count(DISTINCT p2.filing_id) >= 2
            ORDER BY n_orgs DESC, n_shared DESC, pc.display_name LIMIT 100""", {"id": cluster_id}).fetchall()
        eins = {r["ein"] for r in rows}
        for e in c["evidence"] or []:
            eins.update(e.get("eins", []))
            if e.get("ein"):
                eins.add(e["ein"])
        names = {}
        if eins:
            names = {r["ein"]: r["name"] for r in conn.execute(
                "SELECT ein, name FROM organizations WHERE ein = ANY(%s)", (list(eins),))}
    by_year = defaultdict(lambda: {"comp_org": 0, "comp_related": 0, "other_comp": 0, "total": 0})
    lifetime = {"comp_org": 0, "comp_related": 0, "other_comp": 0, "total": 0}
    for r in rows:
        if r["superseded"]:
            continue
        y = by_year[r["tax_year"]]
        for k in lifetime:
            y[k] += r[k] or 0
            lifetime[k] += r[k] or 0
    return {"cluster": c, "rows": rows, "by_year": dict(sorted(by_year.items(), reverse=True)),
            "lifetime": lifetime, "alongside": alongside, "why": explain(c, rows, names), "org_names": names}


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
    for ein, u in sorted(units.items(), key=lambda kv: -max(kv[1]["years"] or {0})):
        org = names.get(ein, ein)
        ys = sorted(u["years"])
        span = f"{ys[0]}-{ys[-1]}" if len(ys) > 1 else (str(ys[0]) if ys else "")
        if u["n"] > 1:
            out.append(f"Same organization: {org}, {span} ({u['n']} filings).")
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
                   m.cluster_id, pc.n_orgs, f.id AS filing_id, f.superseded
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
                   c.state, c.zip, c.service_description, c.compensation, c.website, f.id AS filing_id
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


def stats() -> dict:
    with db.conn() as conn:
        r = conn.execute("""SELECT (SELECT count(*) FROM person_clusters) AS clusters,
                                   (SELECT min(tax_year) FROM filings) AS y0, (SELECT max(tax_year) FROM filings) AS y1
                         """).fetchone()
    return r
