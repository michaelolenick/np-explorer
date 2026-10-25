"""Funders and similar organizations: tables precomputed for org pages and plain-text search.

Built by load.py funders (weekly cron, outside the nightly load window; it holds the loader
lock, so it never overlaps a data load). Work is done in batches with pauses so it doesn't
saturate the database, and each table is built beside the live one and swapped in, so pages
keep working throughout.

  grant_links         one row per grant whose recipient we could identify. Grants come from
                      the latest return per grantor and tax year (an amended return replaces
                      the original, so nothing is counted twice). The recipient is matched by
                      the EIN the grantor wrote (EXACT), else by name (FUZZY): the same
                      normalized name in the same state, or a near-identical name there.
  grant_name_matches  the name-to-organization matches, kept between builds so only new names
                      need the slow near-identical (trigram) pass.
  org_funders         per recipient and grantor: years, grant count, total, latest year's amount.
  org_profile         per organization with filings: NTEE, revenue, expenses, mission, top-paid
                      title and pay, and a text index for topic search.
"""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from loader import db

CHICAGO = ZoneInfo("America/Chicago")
QUIET_START, QUIET_END = (23, 30), (1, 30)   # the nightly load (00:00 Chicago) and its tail: don't run
BATCH_FILINGS = 20_000      # grantor returns per batch
NAME_BATCH = 500            # name pairs per trigram batch
PAUSE = 0.5                 # seconds between batches
FUZZY_MIN = 0.85            # trigram similarity for a near-identical name
FUZZY_MARGIN = 0.03         # the best match must beat the runner-up by this much

LATEST_RETURN_ORDER = "f.ein, f.tax_year, f.amended DESC, f.filed_date DESC NULLS LAST, f.id DESC"


class QuietWindow(Exception):
    """The nightly load window started: stop without swapping anything in."""


def in_quiet_window(now: datetime | None = None) -> bool:
    t = (now or datetime.now(CHICAGO)).astimezone(CHICAGO)
    hm = (t.hour, t.minute)
    return hm >= QUIET_START or hm < QUIET_END


def _guard(force: bool) -> None:
    if not force and in_quiet_window():
        raise QuietWindow("inside the nightly load window (23:30-01:30 Chicago); run later or pass --force")


def _schema(conn) -> str:
    return conn.execute("SELECT current_schema()").fetchone()[0]


def _drop(conn, name: str) -> None:
    """DROP TABLE IF EXISTS, qualified with the current schema (never falls through to public)."""
    conn.execute(f'DROP TABLE IF EXISTS "{_schema(conn)}".{name}')


def _swap(conn, name: str) -> None:
    conn.execute("SET lock_timeout = '30s'")
    _drop(conn, name)
    conn.execute(f"ALTER TABLE {name}__new RENAME TO {name}")
    for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", (name,)).fetchall():
        if "__new" in idx:
            conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{idx.replace("__new", "")}"')
    conn.execute(f"ANALYZE {name}")
    conn.execute("SET lock_timeout = 0")


# --- org_profile ---------------------------------------------------------------------------

PROFILE_SQL = f"""
CREATE TABLE org_profile__new AS
WITH lf AS (
    SELECT DISTINCT ON (f.ein) f.ein, f.id, f.tax_year, f.mission, f.total_revenue, f.total_expenses
    FROM filings f WHERE NOT f.superseded AND f.tax_year IS NOT NULL
    ORDER BY f.ein, f.tax_year DESC, f.amended DESC, f.filed_date DESC NULLS LAST, f.id DESC),
top AS (
    SELECT DISTINCT ON (p.filing_id) p.filing_id, p.title,
           coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS pay
    FROM people p JOIN lf ON lf.id = p.filing_id
    WHERE NOT coalesce(p.is_duplicate, false)
    ORDER BY p.filing_id, pay DESC, p.id)
SELECT o.ein, coalesce(o.name, '') AS name, coalesce(o.name_norm, '') AS name_norm, o.state,
       nullif(upper(left(o.ntee, 3)), '') AS ntee_code, nullif(upper(left(o.ntee, 1)), '') AS ntee_major,
       coalesce(o.latest_total_revenue, lf.total_revenue) AS revenue,
       coalesce(o.latest_total_expenses, lf.total_expenses) AS expenses,
       lf.tax_year AS latest_year, lf.id AS latest_filing_id, lf.mission,
       top.title AS top_title, top.pay AS top_pay,
       setweight(to_tsvector('english', coalesce(o.name, '')), 'A')
         || setweight(to_tsvector('english', left(coalesce(lf.mission, ''), 2000)), 'B') AS doc
FROM organizations o JOIN lf ON lf.ein = o.ein
LEFT JOIN top ON top.filing_id = lf.id
"""

PROFILE_INDEXES = [
    "CREATE UNIQUE INDEX ON org_profile__new (ein)",
    "CREATE INDEX ON org_profile__new (ntee_code, revenue)",
    "CREATE INDEX ON org_profile__new (ntee_major, revenue)",
    "CREATE INDEX ON org_profile__new (state)",
    "CREATE INDEX ON org_profile__new USING gin (doc)",
    "CREATE INDEX ON org_profile__new USING gin (name_norm gin_trgm_ops)",
]


def build_profile(conn, status, force: bool = False) -> int:
    _guard(force)
    status.phase = "funders: org_profile"
    _drop(conn, "org_profile__new")
    conn.execute(PROFILE_SQL)
    for ddl in PROFILE_INDEXES:
        conn.execute(ddl)
    _guard(force)
    _swap(conn, "org_profile")
    n = conn.execute("SELECT count(*) FROM org_profile").fetchone()[0]
    status.emit(f"funders: org_profile {n:,} organizations")
    return n


# --- grant_links -----------------------------------------------------------------------------

LINK_COLS = """grant_id bigint, grantor_ein text, grantor_filing_id bigint, grantor_form text, grantor_kind text,
               source text, tax_year integer, recipient_ein text, match text, filed_name text, filed_state text,
               amount bigint, purpose text"""

GRANTOR_RETURNS = f"""
CREATE TEMP TABLE gr AS
SELECT DISTINCT ON (f.ein, f.tax_year) f.id, f.ein, f.tax_year, f.form_type
FROM filings f
WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND f.id IN (SELECT DISTINCT filing_id FROM grants)
ORDER BY {LATEST_RETURN_ORDER}
"""

KIND = """CASE WHEN gr.form_type = '990PF' THEN 'Private foundation'
               WHEN d.maintains_dafs THEN 'DAF sponsor' ELSE 'Public charity' END"""

EXACT_BATCH = f"""
INSERT INTO grant_links__new
SELECT g.id, gr.ein, gr.id, gr.form_type, {KIND}, g.source, g.tax_year, o.ein, 'EXACT', g.recipient_name, g.state,
       coalesce(g.cash_amount, 0) + coalesce(g.noncash_amount, 0), g.purpose
FROM gr JOIN grants g ON g.filing_id = gr.id
JOIN organizations o ON o.ein = g.recipient_ein
LEFT JOIN daf_stats d ON d.filing_id = gr.id
WHERE gr.id > %(lo)s AND gr.id <= %(hi)s AND o.ein <> gr.ein AND NOT coalesce(g.is_summary, false)
"""

NAMES_BATCH = f"""
INSERT INTO grant_names
SELECT g.id, gr.ein, gr.id, gr.form_type, {KIND}, g.source, g.tax_year, g.recipient_name_norm, g.state,
       g.recipient_name, coalesce(g.cash_amount, 0) + coalesce(g.noncash_amount, 0), g.purpose
FROM gr JOIN grants g ON g.filing_id = gr.id
LEFT JOIN organizations o ON o.ein = g.recipient_ein
LEFT JOIN daf_stats d ON d.filing_id = gr.id
WHERE gr.id > %(lo)s AND gr.id <= %(hi)s AND o.ein IS NULL
  AND NOT coalesce(g.recipient_is_person, false) AND NOT coalesce(g.is_summary, false)
  AND coalesce(g.recipient_name_norm, '') <> ''
"""

# Same normalized name in the same state (or nationally when no state was given), and only one
# organization has it: FUZZY, because the grantor gave a name, not an EIN.
EXACT_NAME_MATCHES = """
INSERT INTO grant_name_matches (name_norm, state, ein, how, similarity)
SELECT p.name_norm, p.state, min(o.ein), 'same name', 1.0
FROM (SELECT DISTINCT name_norm, coalesce(state, '') AS state FROM grant_names) p
JOIN organizations o ON o.name_norm = p.name_norm AND (p.state = '' OR o.state = p.state)
LEFT JOIN grant_name_matches m ON m.name_norm = p.name_norm AND m.state = p.state
WHERE m.name_norm IS NULL
GROUP BY p.name_norm, p.state HAVING count(*) = 1
ON CONFLICT DO NOTHING
"""

# Biggest dollars first, so a time-boxed pass matches the names that matter most.
UNMATCHED_PAIRS = """
SELECT n.name_norm, coalesce(n.state, '') FROM grant_names n
LEFT JOIN grant_name_matches m ON m.name_norm = n.name_norm AND m.state = coalesce(n.state, '')
WHERE m.name_norm IS NULL AND coalesce(n.state, '') <> '' AND length(n.name_norm) >= 6
GROUP BY 1, 2 ORDER BY sum(n.amount) DESC NULLS LAST
"""

TRIGRAM_BATCH = """
SELECT p.nn, p.st, c.ein, c.sim, c.rn
FROM unnest(%(nn)s::text[], %(st)s::text[]) AS p(nn, st)
CROSS JOIN LATERAL (
    SELECT o.ein, similarity(o.name_norm, p.nn) AS sim, row_number() OVER (ORDER BY similarity(o.name_norm, p.nn) DESC) AS rn
    FROM organizations o WHERE o.state = p.st AND o.name_norm %% p.nn
    ORDER BY sim DESC LIMIT 2) c
"""


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS grant_name_matches (
                        name_norm text NOT NULL, state text NOT NULL, ein text,   -- ein NULL: tried, no match
                        how text NOT NULL, similarity real, PRIMARY KEY (name_norm, state))""")


def build_links(conn, status, force: bool = False) -> int:
    _guard(force)
    ensure_tables(conn)
    status.phase = "funders: grantor returns"
    conn.execute("DROP TABLE IF EXISTS pg_temp.gr")
    conn.execute(GRANTOR_RETURNS)
    conn.execute("CREATE INDEX ON gr (id)")
    conn.execute("ANALYZE gr")
    _drop(conn, "grant_links__new")
    conn.execute(f"CREATE TABLE grant_links__new ({LINK_COLS})")
    conn.execute("DROP TABLE IF EXISTS pg_temp.grant_names")
    conn.execute("""CREATE TEMP TABLE grant_names (grant_id bigint, grantor_ein text, grantor_filing_id bigint,
                    grantor_form text, grantor_kind text, source text, tax_year integer, name_norm text, state text,
                    filed_name text, amount bigint, purpose text)""")
    ids = [r[0] for r in conn.execute("SELECT id FROM gr ORDER BY id").fetchall()]
    status.emit(f"funders: {len(ids):,} grantor returns (latest per grantor and tax year)")
    bounds = [0] + ids[BATCH_FILINGS - 1::BATCH_FILINGS] + ([ids[-1]] if ids and len(ids) % BATCH_FILINGS else [])
    for lo, hi in zip(bounds, bounds[1:]):
        _guard(force)
        status.phase = f"funders: grants {hi:,}"
        conn.execute(EXACT_BATCH, {"lo": lo, "hi": hi})
        conn.execute(NAMES_BATCH, {"lo": lo, "hi": hi})
        conn.commit()
        time.sleep(PAUSE)
    conn.execute("CREATE INDEX ON grant_names (name_norm, state)")
    conn.execute("ANALYZE grant_names")

    status.phase = "funders: same-name matches"
    conn.execute(EXACT_NAME_MATCHES)
    conn.commit()
    match_near_identical(conn, status, force)

    status.phase = "funders: fuzzy links"
    conn.execute("""INSERT INTO grant_links__new
                    SELECT n.grant_id, n.grantor_ein, n.grantor_filing_id, n.grantor_form, n.grantor_kind, n.source,
                           n.tax_year, m.ein, 'FUZZY', n.filed_name, n.state, n.amount, n.purpose
                    FROM grant_names n
                    JOIN grant_name_matches m ON m.name_norm = n.name_norm AND m.state = coalesce(n.state, '')
                    WHERE m.ein IS NOT NULL AND m.ein <> n.grantor_ein""")
    for ddl in ("CREATE INDEX ON grant_links__new (recipient_ein, grantor_ein, tax_year)",
                "CREATE INDEX ON grant_links__new (grantor_ein)"):
        conn.execute(ddl)
    _guard(force)
    _swap(conn, "grant_links")
    conn.commit()
    n, fz = conn.execute("SELECT count(*), count(*) FILTER (WHERE match = 'FUZZY') FROM grant_links").fetchone()
    status.emit(f"funders: grant_links {n:,} grants with a known recipient ({fz:,} matched by name)")
    return n


def match_near_identical(conn, status, force: bool = False) -> int:
    """Trigram pass for names with no exact match, in small batches; results are cached."""
    pairs = conn.execute(UNMATCHED_PAIRS).fetchall()
    status.emit(f"funders: {len(pairs):,} names to try near-identical matching on")
    conn.execute(f"SET pg_trgm.similarity_threshold = {FUZZY_MIN}")
    found = 0
    for i in range(0, len(pairs), NAME_BATCH):
        _guard(force)
        status.phase = f"funders: near-identical names {i:,}/{len(pairs):,}"
        chunk = pairs[i:i + NAME_BATCH]
        rows = conn.execute(TRIGRAM_BATCH, {"nn": [p[0] for p in chunk], "st": [p[1] for p in chunk]}).fetchall()
        best: dict[tuple, list] = {}
        for nn, st, ein, sim, rn in rows:
            best.setdefault((nn, st), []).append((sim, ein))
        out = []
        for nn, st in chunk:
            cands = sorted(best.get((nn, st), []), reverse=True)
            ok = cands and cands[0][0] >= FUZZY_MIN and (len(cands) == 1 or cands[0][0] - cands[1][0] >= FUZZY_MARGIN)
            out.append((nn, st, cands[0][1] if ok else None, "near-identical name" if ok else "no match",
                        cands[0][0] if cands else None))
            found += bool(ok)
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO grant_name_matches (name_norm, state, ein, how, similarity)
                               VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""", out)
        conn.commit()
        time.sleep(PAUSE / 5)
    status.emit(f"funders: near-identical names matched {found:,} of {len(pairs):,}")
    return found


# --- org_funders -------------------------------------------------------------------------------

FUNDERS_SQL = """
CREATE TABLE org_funders__new AS
WITH y AS (
    SELECT l.recipient_ein, l.grantor_ein, l.tax_year, sum(l.amount) AS amount, count(*) AS n,
           bool_or(l.match = 'EXACT') AS exact, max(l.grantor_kind) AS grantor_kind, max(l.grantor_form) AS grantor_form
    FROM grant_links l GROUP BY 1, 2, 3),
fz AS (
    SELECT recipient_ein, grantor_ein, (array_agg(DISTINCT filed_name))[1:3] AS fuzzy_names
    FROM grant_links WHERE match = 'FUZZY' GROUP BY 1, 2)
SELECT y.recipient_ein, y.grantor_ein,
       coalesce(max(o.name), '') AS grantor_name,
       (array_agg(y.grantor_kind ORDER BY y.tax_year DESC))[1] AS grantor_kind,
       (array_agg(y.grantor_form ORDER BY y.tax_year DESC))[1] AS grantor_form,
       CASE WHEN bool_or(y.exact) THEN 'EXACT' ELSE 'FUZZY' END AS match,
       max(fz.fuzzy_names) AS fuzzy_names,
       sum(y.n) AS n_grants, sum(y.amount) AS total, min(y.tax_year) AS first_year, max(y.tax_year) AS last_year,
       array_agg(y.tax_year ORDER BY y.tax_year) AS years,
       (array_agg(y.amount ORDER BY y.tax_year DESC))[1] AS last_amount
FROM y LEFT JOIN organizations o ON o.ein = y.grantor_ein
LEFT JOIN fz ON fz.recipient_ein = y.recipient_ein AND fz.grantor_ein = y.grantor_ein
GROUP BY y.recipient_ein, y.grantor_ein
"""


def build_funders(conn, status, force: bool = False) -> int:
    _guard(force)
    status.phase = "funders: org_funders"
    _drop(conn, "org_funders__new")
    conn.execute(FUNDERS_SQL)
    for ddl in ("CREATE UNIQUE INDEX ON org_funders__new (recipient_ein, grantor_ein)",
                "CREATE INDEX ON org_funders__new (grantor_ein)"):
        conn.execute(ddl)
    _guard(force)
    _swap(conn, "org_funders")
    conn.commit()
    n = conn.execute("SELECT count(*) FROM org_funders").fetchone()[0]
    status.emit(f"funders: org_funders {n:,} recipient-grantor pairs")
    return n


def build(status, only: list[str] | None = None, force: bool = False) -> None:
    steps = only or ["profile", "links", "funders"]
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.commit()
        try:
            if "profile" in steps:
                build_profile(conn, status, force)
                conn.commit()
            if "links" in steps:
                build_links(conn, status, force)
            if "funders" in steps:
                build_funders(conn, status, force)
        except QuietWindow as e:
            conn.rollback()
            for t in ("org_profile__new", "grant_links__new", "org_funders__new"):
                _drop(conn, t)
            conn.commit()
            status.emit(f"funders: stopped, {e}; live tables untouched")
