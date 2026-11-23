"""Consolidate duplicate people within an organization (owner, 2026-11-23).

The same person is listed under different spellings across filings: "Bronwyn Blake" / "Blake Bronwyn", "Mike Marcin" /
"Michael Marcin", "Jon" / "Jonathan", "Matt Matthews" / "Matt Mathews", "Kalunde Wambua" / "Kalunde Wambua-Weaver",
a married name. loader/cluster.py already groups rows by normalized name (case, punctuation, honorifics and trailing
credentials such as JD or CPA are dropped by app.names.normalize_name; raw names are never changed) and merges
variants that differ only by a middle name. This module adds the other variants, inside one organization (EIN):

  rule         confidence  what
  swap         high        first and last name exchanged ("blake bronwyn" = "bronwyn blake")
  nickname     high        same last name, first names equivalent (app/nicknames.py: mike = michael, katie = kathleen)
  spelling     medium      equivalent first names, last names one edit apart (two for long names): "mathews" = "matthews"
  hyphenated   medium      equivalent first names; one last name is a middle/second token of the other
                           ("kalunde wambua" = "kalunde wambua weaver")
  name_change  low         same first name and the same full middle name, different last name, years that do not overlap

Guardrails: two names that are listed as separate people in the same filing are never merged, directly or through a
chain of merges; a pair the owner reverted (person_merge_blocks) is never merged again. Across organizations nothing
is loosened: people still link across EINs only by the existing evidence in loader/cluster.py (related organizations,
shared address, co-board overlap), so a consolidated person's organization count grows only through those links.

Every merge is written to person_merge_log (EIN, both names, rule, confidence, years, the person it became). A merge is
reversed with `python -m loader.consolidate revert EIN "name a" "name b"`: the pair goes on person_merge_blocks and
the next cluster rebuild keeps them apart. The rebuild recomputes merges each time, so the log is refreshed, not
appended to, and a blocked pair is marked reverted.

Usage:  .venv/bin/python -m loader.consolidate preview EIN        what would merge at one organization
        .venv/bin/python -m loader.consolidate revert EIN A B      keep two names apart from now on
        .venv/bin/python -m loader.consolidate report              counts by rule, samples by confidence
"""
from __future__ import annotations

import sys
from collections import defaultdict
from itertools import combinations

from app.names import name_parts
from app.nicknames import first_equiv, keys
from loader import db

RULES = ["swap", "nickname", "spelling", "hyphenated", "name_change"]
CONFIDENCE = {"swap": "high", "nickname": "high", "spelling": "medium", "hyphenated": "medium", "name_change": "low"}
RANK = {r: i for i, r in enumerate(RULES)}
NOT_SURNAMES = {"ttee", "trustee", "trustees", "warden", "chair", "chairman", "director", "president", "secretary",
                "treasurer", "officer", "member", "board", "emeritus", "former", "deceased", "resigned", "retired", "ex"}
BUCKET_MAX = 600          # a first-name bucket larger than this at one organization is skipped (counted)

DDL = """
CREATE TABLE IF NOT EXISTS person_merge_log (
    id bigserial PRIMARY KEY, ein text NOT NULL, name_a text NOT NULL, name_b text NOT NULL, rule text NOT NULL,
    confidence text NOT NULL, years_a text, years_b text, cluster_id bigint, merged_at timestamptz NOT NULL DEFAULT now(),
    last_seen timestamptz NOT NULL DEFAULT now(), status text NOT NULL DEFAULT 'active', reverted_at timestamptz,
    UNIQUE (ein, name_a, name_b));
CREATE INDEX IF NOT EXISTS person_merge_log_cluster ON person_merge_log (cluster_id);
CREATE INDEX IF NOT EXISTS person_merge_log_rule ON person_merge_log (rule, confidence);
CREATE TABLE IF NOT EXISTS person_merge_blocks (
    ein text NOT NULL, name_a text NOT NULL, name_b text NOT NULL, reason text, added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ein, name_a, name_b));
"""


class Unit:
    __slots__ = ("uid", "name", "first", "mid", "last", "suf", "y0", "y1", "n")

    def __init__(self, uid, name, y0=None, y1=None, n=1):
        self.uid, self.name, self.y0, self.y1, self.n = uid, name, y0, y1, n
        self.first, self.mid, self.last, self.suf = name_parts(name)


def edit_distance(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def _mid_ok(u: Unit, v: Unit) -> bool:
    if not u.mid or not v.mid:
        return True
    if u.mid == v.mid:
        return True
    a, b = u.mid.replace(" ", ""), v.mid.replace(" ", "")
    return a[0] == b[0] and (len(a) == 1 or len(b) == 1)


def _suf_ok(u: Unit, v: Unit) -> bool:
    return not u.suf or not v.suf or u.suf == v.suf


def _disjoint_years(u: Unit, v: Unit) -> bool:
    if None in (u.y0, u.y1, v.y0, v.y1):
        return False
    return u.y1 < v.y0 or v.y1 < u.y0


def classify(u: Unit, v: Unit) -> str | None:
    """The rule that makes these two names one person at the same organization, or None."""
    if not u.first or not v.first or not u.last or not v.last:
        return None
    if not (u.first.isalpha() and v.first.isalpha() and u.last.isalpha() and v.last.isalpha()):
        return None                                   # digits and stray marks in a name: not a person's name
    if u.last in NOT_SURNAMES or v.last in NOT_SURNAMES:
        return None                                   # "mark anaeto ttee": a role, not a surname
    if (u.first, u.last, u.suf) == (v.first, v.last, v.suf):
        return None                                   # only the middle differs: loader/cluster.py already merges these
    if not _suf_ok(u, v):
        return None
    if u.first == v.last and u.last == v.first and u.first != u.last and _mid_ok(u, v):
        return "swap"
    if not first_equiv(u.first, v.first) or not _mid_ok(u, v):
        return None
    if u.last == v.last:
        return "nickname" if u.first != v.first else None
    lu, lv = u.last, v.last
    # one last name is a middle/second token of the other: "wambua" in "wambua weaver"
    for a, b in ((u, v), (v, u)):
        if not b.mid and len(b.last) >= 3 and b.last in a.mid.split() and b.last != a.last:
            return "hyphenated"
    if lu[0] == lv[0] and min(len(lu), len(lv)) >= 5:
        d = edit_distance(lu, lv, 2)
        if d == 1 or (d == 2 and min(len(lu), len(lv)) >= 8):
            return "spelling"
    if (u.mid and u.mid == v.mid and " " not in u.mid and len(u.mid) >= 3 and min(len(lu), len(lv)) >= 3
            and edit_distance(lu, lv, 3) > 3 and _disjoint_years(u, v)):
        return "name_change"                          # a changed surname is far from the old one; "kelnr" for "keltner" is a typo
    return None


def candidates(units: list[Unit]) -> tuple[list[tuple[int, int, str]], int]:
    """Candidate merging pairs among one organization's units: [(i, j, rule)], and how many buckets were skipped."""
    out: dict[tuple[int, int], str] = {}
    skipped = 0

    def add(i, j, rule):
        k = (i, j) if i < j else (j, i)
        if k not in out or RANK[rule] < RANK[out[k]]:
            out[k] = rule

    by_first = defaultdict(list)
    by_key = defaultdict(list)
    for i, u in enumerate(units):
        by_first[u.first].append(i)
        for k in keys(u.first):
            by_key[k].append(i)
    for i, u in enumerate(units):                                           # swap: A.last = B.first
        for j in by_first.get(u.last, ()):
            if j != i:
                r = classify(u, units[j])
                if r == "swap":
                    add(i, j, r)
    for k, idxs in by_key.items():
        if len(idxs) > BUCKET_MAX:
            skipped += 1
            continue
        for i, j in combinations(idxs, 2):
            r = classify(units[i], units[j])
            if r:
                add(i, j, r)
    return [(i, j, r) for (i, j), r in out.items()], skipped


def accept(units: list[Unit], cands, conflicts: set) -> list[tuple[int, int, str]]:
    """Merge candidates, best rule first, refusing any union that would put two names that appear together in one
    filing into one person. `conflicts` holds unit-index pairs (i, j), i < j, that share a filing."""
    parent = list(range(len(units)))
    members = {i: [i] for i in range(len(units))}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    done = []
    for i, j, rule in sorted(cands, key=lambda c: (RANK[c[2]], c[0], c[1])):
        ri, rj = find(i), find(j)
        if ri == rj:
            done.append((i, j, rule))
            continue
        if any((min(a, b), max(a, b)) in conflicts for a in members[ri] for b in members[rj]):
            continue
        parent[rj] = ri
        members[ri] += members.pop(rj)
        done.append((i, j, rule))
    return done


# --- one organization, straight from the people table (preview, tests) ------------------------------------------------

def org_units(conn, ein: str) -> tuple[list[Unit], dict[str, set]]:
    rows = conn.execute("""SELECT name_norm, min(tax_year), max(tax_year), count(*), array_agg(DISTINCT filing_id)
                           FROM people WHERE ein = %s GROUP BY name_norm ORDER BY name_norm""", (ein,)).fetchall()
    units, filings = [], {}
    for i, (nm, y0, y1, n, fl) in enumerate(rows):
        units.append(Unit(i, nm, y0, y1, n))
        filings[nm] = set(fl)
    return units, filings


def preview(conn, ein: str) -> list[dict]:
    units, filings = org_units(conn, ein)
    blocked = {(a, b) for a, b in conn.execute(
        "SELECT name_a, name_b FROM person_merge_blocks WHERE ein = %s", (ein,))} if _has_blocks(conn) else set()
    cands, _ = candidates(units)
    cands = [c for c in cands if (units[c[0]].name, units[c[1]].name) not in blocked
             and (units[c[1]].name, units[c[0]].name) not in blocked
             and not (filings[units[c[0]].name] & filings[units[c[1]].name])]
    # conflicts for the chain check: every pair of names sharing a filing, among names in some candidate
    involved = sorted({x for c in cands for x in c[:2]})
    conflicts = {(a, b) for a, b in combinations(involved, 2) if filings[units[a].name] & filings[units[b].name]}
    return [{"a": units[i].name, "b": units[j].name, "rule": r, "confidence": CONFIDENCE[r],
             "years_a": f"{units[i].y0}-{units[i].y1}", "years_b": f"{units[j].y0}-{units[j].y1}"}
            for i, j, r in accept(units, cands, conflicts)]


def _has_blocks(conn) -> bool:
    return conn.execute("SELECT to_regclass('person_merge_blocks')").fetchone()[0] is not None


# --- the whole table, inside loader/cluster.py's rebuild --------------------------------------------------------------

def find_merges(conn, status) -> list[tuple[int, int, str, str, str, str, str]]:
    """Merges over every organization, from the cl_units table cluster.run builds (uid, name_norm, ein, y0, y1, n).
    Returns [(uid_a, uid_b, rule, ein, name_a, name_b, years)] and fills person_merge_log."""
    from app.institutions import candidate_regex
    conn.execute(DDL)
    conn.execute("DROP TABLE IF EXISTS cl_cand")
    conn.execute("""CREATE UNLOGGED TABLE cl_cand (ein text, ua bigint, ub bigint, na text, nb text, rule text,
                                                  ya text, yb text)""")
    status.phase = "cluster: consolidate candidates"
    n_cand = n_skipped = 0
    buf: list = []
    cur = conn.cursor()

    def flush():
        nonlocal buf
        if buf:
            db.copy_rows(cur, "cl_cand", ["ein", "ua", "ub", "na", "nb", "rule", "ya", "yb"], buf)
            buf = []

    with conn.cursor(name="cl_units_by_ein") as src:
        src.itersize = 50000
        src.execute(f"""SELECT ein, uid, name_norm, y0, y1, n FROM cl_units
                        WHERE array_length(string_to_array(name_norm, ' '), 1) BETWEEN 2 AND 6
                          AND NOT (name_norm ~ '{candidate_regex()}') ORDER BY ein""")
        cur_ein, units = None, []

        def handle():
            nonlocal n_cand, n_skipped
            if len(units) < 2:
                return
            cands, sk = candidates(units)
            n_skipped += sk
            for i, j, r in cands:
                u, v = units[i], units[j]
                buf.append((cur_ein, u.uid, v.uid, u.name, v.name, r, f"{u.y0}-{u.y1}", f"{v.y0}-{v.y1}"))
            n_cand += len(cands)
            if len(buf) > 100000:
                flush()

        for ein, uid, nm, y0, y1, n in src:
            if ein != cur_ein:
                handle()
                cur_ein, units = ein, []
            units.append(Unit(uid, nm, y0, y1, n))
        handle()
    flush()
    conn.commit()
    status.emit(f"cluster: consolidation candidates {n_cand:,} ({n_skipped:,} oversized name groups skipped)")
    # guardrails in SQL: reverted pairs, and any pair that appears together in one filing
    status.phase = "cluster: consolidate guardrails"
    conn.execute("CREATE INDEX ON cl_cand (ein, na, nb)")
    conn.execute("""DELETE FROM cl_cand c USING person_merge_blocks b WHERE b.ein = c.ein
                    AND ((b.name_a = c.na AND b.name_b = c.nb) OR (b.name_a = c.nb AND b.name_b = c.na))""")
    conn.execute("""DELETE FROM cl_cand c WHERE EXISTS (
                        SELECT 1 FROM people p1 JOIN people p2 ON p2.filing_id = p1.filing_id
                        WHERE p1.ein = c.ein AND p1.name_norm = c.na AND p2.ein = c.ein AND p2.name_norm = c.nb)""")
    conn.commit()
    n_ok = conn.execute("SELECT count(*) FROM cl_cand").fetchone()[0]
    status.emit(f"cluster: consolidation candidates after the same-filing guardrail {n_ok:,}")
    # chains: connected groups of 3+ names need every pair checked for a shared filing
    edges = defaultdict(list)
    for ein, ua, ub, na, nb, rule, ya, yb in conn.execute("SELECT ein, ua, ub, na, nb, rule, ya, yb FROM cl_cand ORDER BY ein"):
        edges[ein].append((ua, ub, na, nb, rule, ya, yb))
    accepted = []
    conflicts_by_ein = _chain_conflicts(conn, edges)
    for ein, es in edges.items():
        uids = sorted({x for e in es for x in e[:2]})
        index = {u: i for i, u in enumerate(uids)}
        names = {}
        for ua, ub, na, nb, rule, ya, yb in es:
            names[ua], names[ub] = na, nb
        units = [Unit(u, names[u]) for u in uids]
        conf = {(min(index[a], index[b]), max(index[a], index[b])) for a, b in conflicts_by_ein.get(ein, ())}
        cands = [(index[ua], index[ub], rule) for ua, ub, na, nb, rule, ya, yb in es]
        years = {(index[ua], index[ub]): (ya, yb) for ua, ub, na, nb, rule, ya, yb in es}
        for i, j, rule in accept(units, cands, conf):
            ya, yb = years.get((min(i, j), max(i, j)), years.get((i, j), ("", "")))
            accepted.append((units[i].uid, units[j].uid, rule, ein, units[i].name, units[j].name, f"{ya} / {yb}"))
    status.emit(f"cluster: {len(accepted):,} name merges accepted")
    return accepted


def _chain_conflicts(conn, edges) -> dict[str, set]:
    """{ein: {(uid_a, uid_b)}}: name pairs inside 3+ name groups that share a filing."""
    out: dict[str, set] = {}
    groups = []
    for ein, es in edges.items():
        parent: dict = {}

        def find(x):
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for ua, ub, *_ in es:
            parent[find(ua)] = find(ub)
        comp = defaultdict(set)
        for ua, ub, na, nb, *_ in es:
            comp[find(ua)].update(((ua, na), (ub, nb)))
        for members in comp.values():
            if len(members) >= 3:
                groups.append((ein, sorted(members)))
    if not groups:
        return out
    conn.execute("DROP TABLE IF EXISTS cl_chain")
    conn.execute("CREATE TEMP TABLE cl_chain (gid int, ein text, uid bigint, name text)")
    cur = conn.cursor()
    db.copy_rows(cur, "cl_chain", ["gid", "ein", "uid", "name"],
                 ((g, ein, uid, nm) for g, (ein, ms) in enumerate(groups) for uid, nm in ms))
    conn.execute("ANALYZE cl_chain")
    for ein, ua, ub in conn.execute("""
            SELECT a.ein, a.uid, b.uid FROM cl_chain a JOIN cl_chain b ON a.gid = b.gid AND a.uid < b.uid
            WHERE EXISTS (SELECT 1 FROM people p1 JOIN people p2 ON p2.filing_id = p1.filing_id
                          WHERE p1.ein = a.ein AND p1.name_norm = a.name AND p2.ein = a.ein AND p2.name_norm = b.name)"""):
        out.setdefault(ein, set()).add((ua, ub))
    return out


def write_log(conn, accepted, status) -> None:
    """person_merge_log: every accepted merge; pairs not seen this run go inactive; blocked pairs show reverted."""
    cur = conn.cursor()
    conn.execute("CREATE TEMP TABLE cl_log (ein text, name_a text, name_b text, rule text, confidence text, ya text, yb text)")
    db.copy_rows(cur, "cl_log", ["ein", "name_a", "name_b", "rule", "confidence", "ya", "yb"],
                 ((ein, *sorted((na, nb)), rule, CONFIDENCE[rule], *(yrs.split(" / ") if na <= nb else yrs.split(" / ")[::-1]))
                  for _a, _b, rule, ein, na, nb, yrs in accepted))
    conn.execute("""INSERT INTO person_merge_log (ein, name_a, name_b, rule, confidence, years_a, years_b)
                    SELECT ein, name_a, name_b, rule, confidence, ya, yb FROM cl_log
                    ON CONFLICT (ein, name_a, name_b) DO UPDATE SET rule = excluded.rule, confidence = excluded.confidence,
                        years_a = excluded.years_a, years_b = excluded.years_b, last_seen = now(),
                        status = CASE WHEN person_merge_log.status = 'reverted' THEN 'active' ELSE person_merge_log.status END""")
    conn.execute("""UPDATE person_merge_log l SET status = 'inactive'
                    WHERE l.status = 'active' AND NOT EXISTS (SELECT 1 FROM cl_log c WHERE c.ein = l.ein
                          AND c.name_a = l.name_a AND c.name_b = l.name_b)""")
    conn.commit()


FUNCTIONS = r"""
CREATE OR REPLACE FUNCTION np_cred_case(w text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT c FROM unnest(ARRAY['MD','PhD','DDS','DMD','JD','Esq','CPA','RN','MBA','LCSW','EdD','DVM','CFP','CFA','MSW',
                               'PharmD','PsyD','LMFT','LPC','DNP','MSN','BSN','MPH','CAE','CFRE','FAIA','AIA']) c
    WHERE lower(c) = lower(regexp_replace(w, '[.,]', '', 'g')) LIMIT 1
$$;
CREATE OR REPLACE FUNCTION np_credentials(raw text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT coalesce((SELECT string_agg(np_cred_case(w), ' ' ORDER BY i)
                     FROM unnest(string_to_array(btrim(regexp_replace(substring(raw from
        '(?i)(?:[ ,]+(?:md|phd|dds|dmd|jd|esq|cpa|rn|mba|lcsw|edd|dvm|cfp|cfa|msw|pharmd|psyd|lmft|lpc|dnp|msn|bsn|mph|cae|cfre|faia|aia)\.?)+\s*$'),
        '[ ,]+', ' ', 'g')), ' ')) WITH ORDINALITY AS t(w, i)), '')
$$;
CREATE OR REPLACE FUNCTION np_display_name(raw text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN raw = upper(raw) AND raw ~ '[A-Z]' THEN
        (SELECT string_agg(coalesce(np_cred_case(w), CASE WHEN lower(regexp_replace(w, '[.,]', '', 'g')) IN ('ii','iii','iv')
                                                           THEN upper(w) ELSE w END), ' ' ORDER BY i)
         FROM unnest(string_to_array(initcap(raw), ' ')) WITH ORDINALITY AS t(w, i))
        ELSE raw END
$$;
"""


def ensure_functions(conn) -> None:
    conn.execute(FUNCTIONS)


def build_aliases(conn, status) -> int:
    """After person_clusters_new and person_cluster_members_new exist: person_aliases_new (one row per name a merged
    person is listed under), the person's display name (most recent, most complete form, first-last order, with the
    credential), and the alias words added to the search vector so "mike marcin" still finds "Michael Marcin"."""
    status.phase = "cluster: aliases"
    conn.execute("DROP TABLE IF EXISTS person_aliases_new")
    conn.execute("""
        CREATE TABLE person_aliases_new AS
        WITH multi AS (SELECT c.cluster_id FROM cl_cluster c JOIN person_clusters_new pc ON pc.id = c.cluster_id
                       WHERE NOT pc.is_institution GROUP BY c.cluster_id HAVING count(DISTINCT c.name_norm) > 1),
        rows AS (SELECT m.cluster_id, p.name_norm, p.name_raw, p.tax_year, p.id
                 FROM multi JOIN person_cluster_members_new m USING (cluster_id) JOIN people p ON p.id = m.person_id)
        SELECT cluster_id, name_norm,
               (array_agg(name_raw ORDER BY tax_year DESC NULLS LAST, id DESC))[1] AS name_raw,
               coalesce(max(NULLIF(np_credentials(name_raw), '')), '') AS credentials,
               min(tax_year) AS first_year, max(tax_year) AS last_year, count(*)::int AS n_rows
        FROM rows GROUP BY cluster_id, name_norm""")
    conn.execute("ALTER TABLE person_aliases_new ADD PRIMARY KEY (cluster_id, name_norm)")
    conn.execute("ANALYZE person_aliases_new")
    conn.commit()
    n = conn.execute("SELECT count(DISTINCT cluster_id) FROM person_aliases_new").fetchone()[0]
    status.emit(f"cluster: {n:,} people are listed under more than one name")
    conn.execute("DROP TABLE IF EXISTS cl_orient")
    conn.execute("""CREATE UNLOGGED TABLE cl_orient AS
                    SELECT tok, sum(f)::bigint AS f, sum(l)::bigint AS l FROM (
                        SELECT first_name AS tok, 1 AS f, 0 AS l FROM person_clusters_new WHERE first_name IS NOT NULL
                        UNION ALL SELECT last_name, 0, 1 FROM person_clusters_new WHERE last_name IS NOT NULL) x GROUP BY tok""")
    conn.execute("ALTER TABLE cl_orient ADD PRIMARY KEY (tok)")
    conn.execute("""
        WITH scored AS (
            SELECT a.cluster_id, a.name_norm, a.name_raw, a.last_year, a.credentials,
                   array_length(string_to_array(a.name_norm, ' '), 1) AS ntok,
                   ln((coalesce(f1.f, 0) + 1.0) / (coalesce(f1.l, 0) + 1.0))
                     + ln((coalesce(l1.l, 0) + 1.0) / (coalesce(l1.f, 0) + 1.0)) AS orient
            FROM person_aliases_new a
            LEFT JOIN cl_orient f1 ON f1.tok = split_part(a.name_norm, ' ', 1)
            LEFT JOIN cl_orient l1 ON l1.tok = np_last_name(a.name_norm)),
        ranked AS (SELECT *, max(orient) OVER (PARTITION BY cluster_id) AS best_orient FROM scored),
        best AS (SELECT DISTINCT ON (cluster_id) cluster_id, name_raw FROM ranked WHERE orient >= best_orient - 2
                 ORDER BY cluster_id, last_year DESC NULLS LAST, ntok DESC, length(name_norm) DESC),
        cred AS (SELECT cluster_id, (array_agg(credentials ORDER BY last_year DESC NULLS LAST)
                                     FILTER (WHERE credentials <> ''))[1] AS credentials FROM person_aliases_new GROUP BY 1)
        UPDATE person_clusters_new c
        SET display_name = np_display_name(b.name_raw)
                           || CASE WHEN np_credentials(b.name_raw) = '' AND cr.credentials IS NOT NULL
                                   THEN ' ' || cr.credentials ELSE '' END
        FROM best b LEFT JOIN cred cr USING (cluster_id) WHERE c.id = b.cluster_id AND NOT c.is_institution""")
    conn.execute("""UPDATE person_clusters_new c SET name_tsv = c.name_tsv || to_tsvector('simple', a.words)
                    FROM (SELECT cluster_id, string_agg(name_norm, ' ') AS words FROM person_aliases_new GROUP BY 1) a
                    WHERE c.id = a.cluster_id AND NOT c.is_institution""")
    conn.execute("DROP TABLE cl_orient")
    conn.commit()
    return n


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        if cmd == "preview":
            for m in preview(conn, sys.argv[2]):
                print(f"{m['confidence']:6} {m['rule']:12} {m['a']!r} ({m['years_a']})  =  {m['b']!r} ({m['years_b']})")
        elif cmd == "revert":
            ein, a, b = sys.argv[2], *sorted(sys.argv[3:5])
            conn.execute("INSERT INTO person_merge_blocks (ein, name_a, name_b, reason) VALUES (%s, %s, %s, 'owner revert') "
                         "ON CONFLICT DO NOTHING", (ein, a, b))
            conn.execute("UPDATE person_merge_log SET status = 'reverted', reverted_at = now() WHERE ein = %s AND name_a = %s AND name_b = %s",
                         (ein, a, b))
            conn.commit()
            print("blocked; the pair stays apart from the next cluster rebuild on")
        elif cmd == "report":
            for r in conn.execute("""SELECT rule, confidence, status, count(*) FROM person_merge_log
                                     GROUP BY 1, 2, 3 ORDER BY 2, 1, 3"""):
                print(r)
        else:
            print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
