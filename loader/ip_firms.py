"""Firms derived from USPTO data, for the business directory (owner, 2026-10-24): every company that holds patents
(PatentsView assignees that aren't individuals) or owns trademarks (trademark owners and applicants that aren't
individuals), one firm per name (legal endings aside, loader/recalls.core) and state, or country outside the US.

- Companies only: trademark owners who are people (by legal entity or by how the name reads, PERSON) are left
  out, and any firm built from them earlier is removed on the next run (drop_people).
- Patent and trademark records with the same core name and place become one firm: EXACT when their full names
  agree, FUZZY (medium) when only the core names do (merge_match).
- Each firm is matched to firms FURP already has, with the rules in loader/patents.org_links: state business
  registries (Florida included), Form D issuers, Form ADV advisers, nonprofits, colleges, SEC filers and federal
  lobbying clients (EXACT or FUZZY, with a confidence). The best match is the firm's home (match_kind, match_key):
  registries first. A matched firm gets a USPTO source line on that record's page (patents, trademarks, state of
  organization); the registry's own data is never changed. A firm with no match is a USPTO-only firm with its own
  page in the directory, /business/USPTO/<firm_id>, marked as derived from USPTO records only.
- State of organization: the trademark owner's nationality fields (owner.csv), the state or country the owner says
  it is organized under; it fills in Delaware and other entities state data lacks.
- Possible related entities: other firms and registry entities at the same street address (trademark owner
  addresses; PatentsView has city and state only), built on full passes.
- derive(scope) is idempotent: a part re-run recomputes its firms from the tables, nothing is duplicated. It runs
  after each patent or trademark part (loader/patents.load_part, loader/trademarks.load_part), in full after the
  backfills and with the weekly refresh (loader/uspto.py). Each run writes a FIRMS line to the status log.
  There's no SBIR data on FURP to match against.

Usage: .venv/bin/python -m loader.ip_firms [full | related]
"""

from __future__ import annotations

import sys
import time

from loader import db, uspto
from loader.uspto import log

KEY = "left(md5({core} || '|' || {place}), 12)"
NORM = "trim(regexp_replace(lower(replace({x}, '&', ' and ')), '[^a-z0-9]+', ' ', 'g'))"
# Best home for a matched firm: state registries first, then the other company records.
PRIORITY = {"biz": 1, "formd": 2, "adv": 3, "sec": 4, "org": 5, "college": 6, "lda": 7}
RANK = {("EXACT", "high"): 1, ("EXACT", "medium"): 2, ("FUZZY", "high"): 3, ("FUZZY", "medium"): 4,
        ("FUZZY", "low"): 5}
PAT_SRC = """SELECT a.name_core AS core, coalesce(a.state, a.country, '') AS place, a.name, a.city, a.state, a.country,
                    a.assignee_id, a.patent_id, p.granted
             FROM pat_assignees a JOIN pat_patents p USING (patent_id)
             WHERE NOT a.is_person AND a.name_core IS NOT NULL AND a.name_core <> '' AND a.assignee_type % 10 IN (2, 3)"""
# Business words: a name with one of these is a firm, whatever else it looks like.
BUSINESS = (r"\m(inc|incorporated|llc|l\.?l\.?c|ltd|limited|co|corp|corporation|company|companies|group|holdings?|"
            r"gmbh|ag|kg|sa|sas|sarl|srl|spa|s\.l|s\.a|bv|b\.v|nv|n\.v|plc|pty|lp|llp|pllc|pc|ab|oy|as|asa|bhd|sdn|kk|"
            r"kabushiki|kaisha|partners|associates|association|foundation|institute|university|college|club|studios?|"
            r"designs?|consulting|media|records|foods?|brands?|labs?|systems|technolog(y|ies)|industries|international|"
            r"enterprises?|services|solutions|products|trading|store|shop|ink|apparel|clothing|church|society|center|"
            r"centre|bank|capital|ventures|network|health|pharma|games|software|entertainment|productions?|films?|"
            r"music|publishing|press|works|farms?|wines?|winery|brewing|beauty|cosmetics|collective|team|the|of|and|"
            r"lda|ltda|societe|sociedad|cooperative|cooperativa|eirl|ug|kft|oyj|aps|cv|sp|zoo|spolka|sro|doo|ooo|"
            r"pte|jsc|gk|yk|ohg|gbr|ev|vzw|asbl|sca|scs|snc)\M")
# A trademark owner that is a person, not a company (owner, 2026-10-24: companies only): the legal entity says so
# (individual, sole proprietorship, estate, trust, joint ownership, or code 19, which in this data is people), or
# the name reads as a person's: "Last, First" with no business word, or two to four words starting with a common
# given name (ip_given_names: inventors' first names) with no business word or digit; trustees and joint applicants
# ("A; B") too.
PERSON = rf"""(coalesce({{e}}, '') ~* '^(individual|sole propriet|estate|trust|joint or common|entity code 19$)'
    OR {{n}} ~* '^(the )?trustees? (of|for)' OR {{n}} ~ ';'
    OR ({{n}} !~* '{BUSINESS}' AND {{n}} !~ '[0-9]'
        AND (({{n}} ~ '^[^,]+, *[^,]+(, *[^,]+)?$'
              AND array_length(regexp_split_to_array(trim(split_part({{n}}, ',', 1)), '\s+'), 1) <= 3)
             OR (array_length(regexp_split_to_array(trim({{n}}), '\s+'), 1) BETWEEN 2 AND 4
                 AND lower(split_part(trim({{n}}), ' ', 1)) IN (SELECT n FROM ip_given_names)))))"""
TM_SRC = f"""SELECT o.name_core AS core, coalesce(o.state, o.country, '') AS place, o.name, o.city, o.state, o.country,
                   o.street, o.entity, o.org_state, o.org_country, o.owner_key, o.serial_no, m.filing_date, m.live
            FROM tm_owners o JOIN tm_marks m USING (serial_no)
            WHERE o.name_core IS NOT NULL AND o.name_core <> '' AND NOT {PERSON.format(e='o.entity', n='o.name')}"""


def given_names(conn) -> None:
    """ip_given_names: first names that at least 200 US patent inventor records carry (a person-name test)."""
    conn.execute("CREATE TABLE IF NOT EXISTS ip_given_names (n text PRIMARY KEY)")
    if conn.execute("SELECT count(*) FROM ip_given_names").fetchone()[0] == 0:
        conn.execute(f"""INSERT INTO ip_given_names
                         SELECT lower(split_part(trim(first_name), ' ', 1)) AS n FROM pat_inventors
                         WHERE first_name ~ '^[A-Za-z]{{2,}}' GROUP BY 1 HAVING count(*) >= 200
                           AND lower(split_part(trim(first_name), ' ', 1)) !~* '{BUSINESS}'
                         ON CONFLICT DO NOTHING""")
    conn.commit()


def drop_people(conn) -> int:
    """Firms that came only from trademark owners who are people (an earlier, looser filter), with their links:
    removed, so a re-run leaves companies only. Idempotent."""
    gone = conn.execute(f"""SELECT firm_id FROM ip_firms
                            WHERE n_patents = 0 AND {PERSON.format(e='entity_type', n='name')}""").fetchall()
    ids = [r[0] for r in gone]
    if ids:
        conn.execute("DELETE FROM ip_links WHERE src_kind = 'firm' AND src_key = ANY(%s)", (ids,))
        conn.execute("DELETE FROM ip_firm_related WHERE firm_id = ANY(%s) OR (kind = 'firm' AND key = ANY(%s))", (ids, ids))
        conn.execute("DELETE FROM ip_firms WHERE firm_id = ANY(%s)", (ids,))
    conn.commit()
    return len(ids)


def _scope_table(conn, scope: str, patents_where: str | None, marks_where: str | None) -> None:
    """scope_firms (core, place): every firm the part touches (all of their records are then recomputed)."""
    conn.execute("DROP TABLE IF EXISTS scope_firms")
    if scope == "full":
        conn.execute(f"""CREATE TEMP TABLE scope_firms AS
                         SELECT DISTINCT core, place FROM ({PAT_SRC}) x UNION SELECT DISTINCT core, place FROM ({TM_SRC}) y""")
    else:
        parts = []
        if patents_where:
            parts.append(f"SELECT DISTINCT core, place FROM ({PAT_SRC} AND {patents_where}) x")
        if marks_where:
            parts.append(f"SELECT DISTINCT core, place FROM ({TM_SRC} AND {marks_where}) y")
        conn.execute("CREATE TEMP TABLE scope_firms AS " + " UNION ".join(parts))
    conn.execute("CREATE INDEX ON scope_firms (core, place)")
    conn.execute("ANALYZE scope_firms")


def derive(scope: str = "full", patents_where: str | None = None, marks_where: str | None = None,
           status=log) -> dict:
    """Recompute the firms in scope ('full', or a part with SQL conditions on p.* or m.*), match them, and log."""
    t0 = time.time()
    key = KEY.format(core="core", place="place")
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        given_names(conn)
        people = drop_people(conn)
        _scope_table(conn, scope, patents_where, marks_where)
        conn.execute("DROP TABLE IF EXISTS fp, ft, fn")
        conn.execute(f"""CREATE TEMP TABLE fp AS
            SELECT {key} AS firm_id, x.core, x.place, mode() WITHIN GROUP (ORDER BY x.name) AS name,
                   count(DISTINCT x.name) AS names, mode() WITHIN GROUP (ORDER BY x.city) AS city,
                   max(x.state) AS state, mode() WITHIN GROUP (ORDER BY x.country) AS country,
                   count(DISTINCT x.patent_id) AS n_patents, array_agg(DISTINCT x.assignee_id) AS assignee_ids,
                   min(x.granted) AS first_seen, max(x.granted) AS last_seen
            FROM ({PAT_SRC}) x JOIN scope_firms s USING (core, place) GROUP BY x.core, x.place""")
        conn.execute(f"""CREATE TEMP TABLE ft AS
            SELECT {key} AS firm_id, y.core, y.place, mode() WITHIN GROUP (ORDER BY y.name) AS name,
                   count(DISTINCT y.name) AS names, mode() WITHIN GROUP (ORDER BY y.city) AS city,
                   max(y.state) AS state, mode() WITHIN GROUP (ORDER BY y.country) AS country,
                   mode() WITHIN GROUP (ORDER BY y.street) AS street, mode() WITHIN GROUP (ORDER BY y.entity) AS entity,
                   mode() WITHIN GROUP (ORDER BY y.org_state) AS org_state,
                   mode() WITHIN GROUP (ORDER BY y.org_country) AS org_country,
                   count(DISTINCT y.serial_no) AS n_marks, count(DISTINCT y.serial_no) FILTER (WHERE y.live) AS n_live,
                   array_agg(DISTINCT y.owner_key) AS owner_keys, min(y.filing_date) AS first_seen,
                   max(y.filing_date) AS last_seen
            FROM ({TM_SRC}) y JOIN scope_firms s USING (core, place) GROUP BY y.core, y.place""")
        conn.execute(f"""CREATE TEMP TABLE fn AS
            SELECT coalesce(fp.firm_id, ft.firm_id) AS firm_id, coalesce(ft.name, fp.name) AS name,
                   coalesce(fp.core, ft.core) AS name_core, ft.street,
                   CASE WHEN ft.street IS NOT NULL THEN {NORM.format(x="concat_ws(' ', ft.street, ft.city, ft.state, ft.country)")} END AS addr_norm,
                   coalesce(ft.city, fp.city) AS city, coalesce(ft.state, fp.state) AS state,
                   coalesce(ft.country, fp.country) AS country, ft.entity AS entity_type, ft.org_state, ft.org_country,
                   coalesce(fp.n_patents, 0) AS n_patents, coalesce(ft.n_marks, 0) AS n_marks,
                   coalesce(ft.n_live, 0) AS n_live_marks, fp.assignee_ids, ft.owner_keys,
                   least(fp.first_seen, ft.first_seen) AS first_seen, greatest(fp.last_seen, ft.last_seen) AS last_seen,
                   CASE WHEN fp.firm_id IS NOT NULL AND ft.firm_id IS NOT NULL
                        THEN CASE WHEN {NORM.format(x="fp.name")} = {NORM.format(x="ft.name")} THEN 'EXACT' ELSE 'FUZZY' END
                        ELSE CASE WHEN coalesce(fp.names, ft.names) > 1 THEN 'FUZZY' ELSE 'EXACT' END END AS merge_match,
                   CASE WHEN fp.firm_id IS NOT NULL AND ft.firm_id IS NOT NULL
                        THEN 'patent assignee and trademark owner with the same name (legal endings aside) and place'
                        WHEN coalesce(fp.names, ft.names) > 1 THEN 'name variants with the same core name and place'
                        ELSE 'one name' END AS merge_how,
                   concat_ws(' and ', CASE WHEN fp.firm_id IS NOT NULL THEN 'PVGPATDIS' END,
                             CASE WHEN ft.firm_id IS NOT NULL THEN 'TRCFECO2' END) AS sources
            FROM fp FULL JOIN ft USING (firm_id)""")
        before = conn.execute("SELECT count(*) FROM ip_firms WHERE firm_id IN (SELECT firm_id FROM fn)").fetchone()[0]
        total = conn.execute("SELECT count(*) FROM fn").fetchone()[0]
        dates = ", ".join(f"{p} file of {uspto.file_date(p, f)}" for p, f in
                          (("PVGPATDIS", "g_assignee_disambiguated.tsv.zip"), ("TRCFECO2", "owner.csv.zip")))
        cols = ["firm_id", "name", "name_core", "street", "addr_norm", "city", "state", "country", "entity_type",
                "org_state", "org_country", "n_patents", "n_marks", "n_live_marks", "assignee_ids", "owner_keys",
                "first_seen", "last_seen", "merge_match", "merge_how", "sources"]
        stamp = conn.execute("SELECT now()").fetchone()[0]          # this transaction's time: the rows it writes
        conn.execute(f"""INSERT INTO ip_firms ({', '.join(cols)}, src_dates)
                         SELECT {', '.join(cols)}, %s FROM fn
                         ON CONFLICT (firm_id) DO UPDATE SET
                         {', '.join(f'{c} = excluded.{c}' for c in cols[1:])}, src_dates = excluded.src_dates,
                         updated = now()""", (dates,))
        conn.commit()
        # Matches to firms FURP already has (EXACT or FUZZY with a confidence), then each firm's best home.
        from loader import patents
        conn.execute("DELETE FROM ip_links WHERE src_kind = 'firm' AND src_key IN (SELECT firm_id FROM fn)")
        conn.commit()
        patents.org_links(conn, "firm", f"""SELECT firm_id, name, state FROM ip_firms
                                           WHERE updated = '{stamp.isoformat()}'::timestamptz""", status=lambda m: None)
        best = {}
        for fid, kind, k, match, conf, how in conn.execute(
                """SELECT src_key, target_kind, target_key, match, confidence, how FROM ip_links
                   WHERE src_kind = 'firm' AND src_key IN (SELECT firm_id FROM fn) AND target_kind <> 'person'""").fetchall():
            r = (RANK.get((match, conf), 9), PRIORITY.get(kind, 9))
            if fid not in best or r < best[fid][0]:
                best[fid] = (r, kind, k, match, conf, how)
        conn.execute("UPDATE ip_firms SET match_kind = NULL, match_key = NULL, match = NULL, confidence = NULL, how = NULL "
                     "WHERE firm_id IN (SELECT firm_id FROM fn)")
        conn.execute("DROP TABLE IF EXISTS fb")
        conn.execute("CREATE TEMP TABLE fb (firm_id text, kind text, key text, match text, confidence text, how text)")
        with conn.cursor() as cur, cur.copy("COPY fb FROM STDIN") as cp:
            for fid, (_, kind, k, match, conf, how) in best.items():
                cp.write_row((fid, kind, k, match, conf, how))
        conn.execute("""UPDATE ip_firms f SET match_kind = b.kind, match_key = b.key, match = b.match,
                               confidence = b.confidence, how = b.how FROM fb b WHERE b.firm_id = f.firm_id""")
        # A USPTO-only firm's own confidence: how sure the merge of its USPTO records is.
        conn.execute("""UPDATE ip_firms SET match = merge_match,
                               confidence = CASE WHEN merge_match = 'EXACT' THEN 'high' ELSE 'medium' END,
                               how = 'USPTO records only: ' || merge_how
                        WHERE firm_id IN (SELECT firm_id FROM fn) AND match_kind IS NULL""")
        only = conn.execute("SELECT count(*) FROM ip_firms WHERE match_kind IS NULL").fetchone()[0]
        n = {"new": total - before, "updated": before, "merged": len(best), "uspto_only": only, "total": total,
             "people_removed": people}
        conn.execute("INSERT INTO ip_firm_runs (scope, new, updated, merged, uspto_only) VALUES (%s, %s, %s, %s, %s)",
                     (scope, n["new"], n["updated"], n["merged"], only))
        conn.commit()
    if scope == "full":
        related(status)
    uspto.status_line(f"{uspto.current()}", event=f"FIRMS ({scope}): new {n['new']:,} | updated {n['updated']:,} | "
                                                   f"merged {n['merged']:,} | USPTO-only total {only:,}"
                                                   + (f" | people removed {people:,}" if people else ""))
    status(f"firms {scope}: {n} ({time.time() - t0:.0f}s)")
    return n


def related(status=log) -> int:
    """Possible related entities: firms and state registry entities at the same street address (full passes)."""
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("TRUNCATE ip_firm_related")
        n = conn.execute("""INSERT INTO ip_firm_related (firm_id, kind, key, name, how)
            SELECT a.firm_id, 'firm', b.firm_id, b.name, 'same street address (trademark filings)'
            FROM ip_firms a JOIN ip_firms b ON b.addr_norm = a.addr_norm AND b.firm_id <> a.firm_id
            WHERE a.addr_norm IS NOT NULL
              AND (SELECT count(*) FROM ip_firms c WHERE c.addr_norm = a.addr_norm) <= 25
            ON CONFLICT DO NOTHING""").rowcount
        # Registry entities: the same street, city and state (a registered-agent address shared by thousands of
        # firms isn't a sign of anything, so addresses with more than 25 entities are left out).
        conn.execute(f"""CREATE TEMP TABLE fa AS SELECT firm_id, {NORM.format(x='street')} AS st, upper(city) AS city, state
                         FROM ip_firms WHERE street IS NOT NULL AND city IS NOT NULL AND state IS NOT NULL""")
        conn.execute("CREATE INDEX ON fa (city, state)")
        n += conn.execute(f"""INSERT INTO ip_firm_related (firm_id, kind, key, name, how)
            SELECT fa.firm_id, 'biz', e.state || ':' || e.entity_id, e.name, 'same street address as a state registration'
            FROM fa JOIN biz_entities e ON upper(e.city) = fa.city AND coalesce(e.addr_state, e.state) = fa.state
                                       AND {NORM.format(x='e.street')} = fa.st
            WHERE e.street IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM ip_firms f WHERE f.firm_id = fa.firm_id AND f.match_kind = 'biz'
                              AND f.match_key = e.state || ':' || e.entity_id)
            ON CONFLICT DO NOTHING""").rowcount
        conn.execute("""DELETE FROM ip_firm_related r WHERE r.kind = 'biz' AND r.firm_id IN
                        (SELECT firm_id FROM ip_firm_related WHERE kind = 'biz' GROUP BY 1 HAVING count(*) > 25)""")
        conn.commit()
    status(f"firms: {n:,} possible related entities by address")
    return n


def counts() -> dict:
    with db.connect() as conn:
        out = {"firms": conn.execute("SELECT count(*) FROM ip_firms").fetchone()[0]}
        out["by_source"] = conn.execute("SELECT sources, count(*), count(match_kind) FROM ip_firms GROUP BY 1").fetchall()
        out["by_match"] = conn.execute("""SELECT coalesce(match_kind, 'USPTO only'), match, confidence, count(*)
                                          FROM ip_firms GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""").fetchall()
        out["with_org_state"] = conn.execute("SELECT count(*) FROM ip_firms WHERE org_state IS NOT NULL").fetchone()[0]
    return out


if __name__ == "__main__":
    arg = (sys.argv[1:] or ["full"])[0]
    if arg == "related":
        related()
    elif arg == "counts":
        print(counts())
    else:
        derive("full")
