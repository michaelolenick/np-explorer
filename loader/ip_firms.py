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
- haiku_check(): USPTO-only trademark firms whose names have no business word (the hardest slice for the rules
  above) go to Claude Haiku in Message Batches, names only; a name it reads as a person's is hidden (ip_firms.hidden),
  not deleted. Answers are kept per name (ip_name_checks), so later runs only ask about new names. A hard dollar
  ceiling on the worst-case cost of what is sent (owner, 2026-10-24: $2.00).

Usage: .venv/bin/python -m loader.ip_firms [full | related]
"""

from __future__ import annotations

import json
import os
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
        _apply_checks(conn)                  # rebuilt firms keep their Haiku answers (hidden people stay hidden)
        only = conn.execute("SELECT count(*) FROM ip_firms WHERE match_kind IS NULL AND NOT hidden").fetchone()[0]
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
    """Possible related entities: firms and state registry entities at the same street address (full passes). Built
    in ip_firm_related_new and swapped in with a quick rename, so pages never wait on the build."""
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("DROP TABLE IF EXISTS ip_firm_related_new")
        conn.execute("CREATE TABLE ip_firm_related_new (LIKE ip_firm_related INCLUDING DEFAULTS)")
        conn.commit()
        n = conn.execute("""INSERT INTO ip_firm_related_new (firm_id, kind, key, name, how)
            SELECT a.firm_id, 'firm', b.firm_id, b.name, 'same street address (trademark filings)'
            FROM ip_firms a JOIN ip_firms b ON b.addr_norm = a.addr_norm AND b.firm_id <> a.firm_id
            WHERE a.addr_norm IS NOT NULL
              AND a.addr_norm IN (SELECT addr_norm FROM ip_firms WHERE addr_norm IS NOT NULL GROUP BY 1 HAVING count(*) <= 25)
            ON CONFLICT DO NOTHING""").rowcount
        conn.commit()
        # Registry entities: the same street, city and state (a registered-agent address shared by many firms isn't a
        # sign of anything, so more than 25 entities at one address are left out before the join, not after it).
        conn.execute(f"""CREATE TEMP TABLE fa AS SELECT firm_id, {NORM.format(x='street')} AS st, upper(city) AS city, state
                         FROM ip_firms WHERE street IS NOT NULL AND city IS NOT NULL AND state IS NOT NULL""")
        conn.execute("CREATE INDEX ON fa (city, state, st)")
        conn.execute("ANALYZE fa")
        conn.execute(f"""CREATE TEMP TABLE be AS SELECT key, name, st, city, state FROM (
                           SELECT e.state || ':' || e.entity_id AS key, e.name, {NORM.format(x='e.street')} AS st,
                                  upper(e.city) AS city, coalesce(e.addr_state, e.state) AS state,
                                  count(*) OVER (PARTITION BY {NORM.format(x='e.street')}, upper(e.city),
                                                 coalesce(e.addr_state, e.state)) AS n
                           FROM biz_entities e WHERE e.street IS NOT NULL AND e.city IS NOT NULL) x
                         WHERE n <= 25""")
        conn.execute("ANALYZE be")
        n += conn.execute("""INSERT INTO ip_firm_related_new (firm_id, kind, key, name, how)
            SELECT fa.firm_id, 'biz', be.key, be.name, 'same street address as a state registration'
            FROM be JOIN fa ON fa.city = be.city AND fa.state = be.state AND fa.st = be.st""").rowcount
        conn.execute("""DELETE FROM ip_firm_related_new r USING ip_firms f
                        WHERE r.kind = 'biz' AND f.firm_id = r.firm_id AND f.match_kind = 'biz' AND f.match_key = r.key""")
        conn.execute("""DELETE FROM ip_firm_related_new r USING
                        (SELECT firm_id FROM ip_firm_related_new WHERE kind = 'biz' GROUP BY 1 HAVING count(*) > 25) c
                        WHERE r.kind = 'biz' AND r.firm_id = c.firm_id""")
        # Duplicates (a firm and an entity can share more than one address row) go before the primary key.
        conn.execute("""DELETE FROM ip_firm_related_new a USING ip_firm_related_new b
                        WHERE a.firm_id = b.firm_id AND a.kind = b.kind AND a.key = b.key AND a.ctid > b.ctid""")
        conn.execute("ALTER TABLE ip_firm_related_new ADD PRIMARY KEY (firm_id, kind, key)")
        conn.execute("CREATE INDEX ON ip_firm_related_new (firm_id)")
        conn.execute("ANALYZE ip_firm_related_new")
        conn.commit()
        conn.execute("SET lock_timeout = '10s'")
        conn.execute("DROP TABLE IF EXISTS ip_firm_related")
        conn.execute("ALTER TABLE ip_firm_related_new RENAME TO ip_firm_related")
        for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'ip_firm_related'").fetchall():
            if "_new" in idx:
                conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{idx.replace("_new", "")}"')
        conn.commit()
    status(f"firms: {n:,} possible related entities by address")
    return n

# --- person or company: Claude Haiku for the names the rules can't settle -----------------------------------------

MODEL = os.environ.get("IP_FIRMS_MODEL", "claude-haiku-5-5")
API = "https://api.anthropic.com/v1/messages"
PRICE_IN, PRICE_OUT = 0.10 / 1e6, 0.50 / 1e6        # Haiku 5.5 per token; batches half, cache write 2x, read 0.1x
CEILING = 2.00
PER_REQUEST = 100
CHUNK = 500
SYSTEM = """You sort names from US trademark filings into people and organizations. Each line of the user's message is a number and a name an owner gave on a trademark application. For each, decide whether it is a natural person's name (p true) or a business, brand, group or other organization (p false).

- A personal name, in any order or language, with or without initials, titles or suffixes (M.D., Jr., III), is a person: "Jaleel Miller", "THANDAR HLAING", "Omeed Ahadiat M.D.", "Garcia Zabala, Victor Javier", "LEE Deuk Woo", "Shijirbaatar Munkh Orgil".
- A trade name, brand, slogan or invented word is not a person, even when it contains a first name: "Emery Ink", "Countryside Kitchen", "Black Girls Crowned", "Casualtiezz of War", "Oak Grove Mercantile", "Veark".
- Two people together ("John and Mary Smith") are people (true). A trust, estate, school, church, club or band is not (false).
- When unsure, answer false.

Answer every number, in order, as JSON: {"r":[{"i":1,"p":true},{"i":2,"p":false}]}"""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["r"], "properties": {"r": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["i", "p"],
    "properties": {"i": {"type": "integer"}, "p": {"type": "boolean"}}}}}}


def _headers() -> dict:
    return {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"}


def _request(names: list[str]) -> dict:
    return {"model": MODEL, "max_tokens": 12 * len(names) + 40, "thinking": {"type": "disabled"},
            "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
            "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
            "messages": [{"role": "user", "content": "\n".join(f"{n} {x}" for n, x in enumerate(names, 1))}]}


def _worst(params: dict) -> float:
    """Upper bound at batch prices: every input token a cache write (about 3 characters a token), every output token."""
    chars = len(SYSTEM) + len(params["messages"][0]["content"])
    return 0.5 * (chars / 3 * 2 * PRICE_IN + params["max_tokens"] * PRICE_OUT)


def _cost(u: dict) -> float:
    return 0.5 * (u.get("input_tokens", 0) * PRICE_IN + u.get("cache_creation_input_tokens", 0) * 2 * PRICE_IN
                  + u.get("cache_read_input_tokens", 0) * 0.1 * PRICE_IN + u.get("output_tokens", 0) * PRICE_OUT)


def _apply_checks(conn, names: list[str] | None = None) -> int:
    """ip_firms.hidden from the cached answers (all firms, or those named)."""
    where = "AND c.name = ANY(%s)" if names is not None else ""
    n = conn.execute(f"""UPDATE ip_firms f SET hidden = c.is_person,
                            hidden_why = CASE WHEN c.is_person THEN 'name reads as a person''s (' || c.method || ', '
                                              || to_char(c.checked, 'YYYY-MM-DD') || ')' END
                         FROM ip_name_checks c WHERE c.name = f.name AND f.match_kind IS NULL AND f.n_patents = 0
                           AND f.hidden IS DISTINCT FROM c.is_person {where}""",
                     (names,) if names is not None else ()).rowcount
    conn.commit()
    return n


def haiku_check(max_dollars: float = CEILING, status=log) -> dict:
    """Ask Haiku about unchecked names in the hardest slice; hide the people. Each batch is saved as it ends."""
    import httpx
    with db.connect() as conn:
        _apply_checks(conn)                  # firms rebuilt since the last run get their cached answers back
        names = [r[0] for r in conn.execute(f"""
            SELECT DISTINCT f.name FROM ip_firms f
            WHERE f.match_kind IS NULL AND f.n_patents = 0 AND f.name !~* '{BUSINESS}' AND f.name !~ '[0-9]'
              AND NOT EXISTS (SELECT 1 FROM ip_name_checks c WHERE c.name = f.name)
            ORDER BY 1""").fetchall()]
    jobs, worst = [], 0.0
    for i in range(0, len(names), PER_REQUEST):
        part = names[i:i + PER_REQUEST]
        params = _request(part)
        w = _worst(params)
        if worst + w > max_dollars:
            status(f"firms haiku: ${max_dollars:.2f} ceiling reached at {sum(len(j[1]) for j in jobs):,} of {len(names):,} names; "
                   f"the rest wait for the next run")
            break
        jobs.append((params, part))
        worst += w
    out = {"checked": 0, "hidden": 0, "cost": 0.0, "worst": worst, "names": len(names)}
    if not jobs:
        uspto.status_line(uspto.current(), event="FIRMS (haiku): checked 0 | hidden 0 | cost $0.0000 (no new names)")
        return out
    ids = []
    for start in range(0, len(jobs), CHUNK):
        reqs = [{"custom_id": f"n{start + k}", "params": job[0]} for k, job in enumerate(jobs[start:start + CHUNK])]
        r = httpx.post(API + "/batches", timeout=300, headers=_headers(), json={"requests": reqs})
        r.raise_for_status()
        ids.append(r.json()["id"])
    status(f"firms haiku: {len(ids)} batches sent for {sum(len(j[1]) for j in jobs):,} names (worst case ${worst:.4f}): {', '.join(ids)}")
    pending, failed = list(ids), 0
    while pending:
        time.sleep(60)
        for bid in list(pending):
            b = httpx.get(f"{API}/batches/{bid}", timeout=60, headers=_headers()).json()
            if b["processing_status"] != "ended":
                continue
            pending.remove(bid)
            answers = []
            with httpx.stream("GET", b["results_url"], timeout=600, headers=_headers()) as rr:
                for line in rr.iter_lines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    part = jobs[int(row["custom_id"][1:])][1]
                    res = row["result"]
                    if res["type"] != "succeeded":
                        failed += 1
                        continue
                    out["cost"] += _cost(res["message"].get("usage") or {})
                    try:
                        items = json.loads("".join(c.get("text", "") for c in res["message"]["content"]
                                                   if c.get("type") == "text"))["r"]
                    except Exception:  # noqa: BLE001 - truncated or empty: these names wait for the next run
                        failed += 1
                        continue
                    for a in items:
                        if isinstance(a.get("i"), int) and 1 <= a["i"] <= len(part) and isinstance(a.get("p"), bool):
                            answers.append((part[a["i"] - 1], a["p"]))
            with db.connect() as conn:
                conn.execute("CREATE TEMP TABLE nc (name text, is_person boolean)")
                with conn.cursor() as cur, cur.copy("COPY nc FROM STDIN") as cp:
                    for nm, isp in answers:
                        cp.write_row((nm, isp))
                conn.execute("""INSERT INTO ip_name_checks (name, is_person, method)
                                SELECT DISTINCT ON (name) name, is_person, %s FROM nc
                                ON CONFLICT (name) DO UPDATE SET is_person = excluded.is_person, method = excluded.method,
                                    checked = now()""", (f"Claude Haiku ({MODEL})",))
                conn.commit()
                _apply_checks(conn, [nm for nm, _ in answers])
            out["checked"] += len(answers)
            out["hidden"] += sum(1 for _, isp in answers if isp)
            status(f"firms haiku: batch {bid} ended and saved ({b['request_counts']}); ${out['cost']:.4f} so far")
    uspto.status_line(uspto.current(), event=f"FIRMS (haiku): checked {out['checked']:,} | hidden {out['hidden']:,} | "
                                             f"cost ${out['cost']:.4f}" + (f" | failed requests {failed}" if failed else ""))
    return out


def counts() -> dict:
    with db.connect() as conn:
        out = {"firms": conn.execute("SELECT count(*) FROM ip_firms").fetchone()[0]}
        out["by_source"] = conn.execute("SELECT sources, count(*), count(match_kind) FROM ip_firms GROUP BY 1").fetchall()
        out["by_match"] = conn.execute("""SELECT coalesce(match_kind, 'USPTO only'), match, confidence, count(*)
                                          FROM ip_firms GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""").fetchall()
        out["with_org_state"] = conn.execute("SELECT count(*) FROM ip_firms WHERE org_state IS NOT NULL").fetchone()[0]
        out["hidden"] = conn.execute("SELECT count(*) FROM ip_firms WHERE hidden").fetchone()[0]
    return out


if __name__ == "__main__":
    arg = (sys.argv[1:] or ["full"])[0]
    if arg == "related":
        related()
    elif arg == "haiku":
        print(haiku_check())
    elif arg == "counts":
        print(counts())
    else:
        derive("full")
