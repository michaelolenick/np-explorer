"""Cross-links between the 2026-11-04 datasets (Form 5500, FARA, Open Payments, state and city payroll) and the rest
of the site (owner, 2026-11-04): people and name clusters, nonprofit filings, state business registries, FEC donors,
federal lobbying (clients, registrants, lobbyists) and SEC records (filers, Form D issuers, Form ADV advisers), in
one table, xlinks, read both ways (app/xlinks.py: the new records on each existing page, and the existing pages on
each new record).

Sources (src_kind, src_key):
  fara_registrant reg_number      fara_principal id           fara_person short-form id
  f5500_sponsor   sponsor EIN
  f5500_person    state:name_norm (signers and preparers)
  op_recipient    recipient key   op_payer      payer id
  payroll_person  state:employer:name_norm (gov_* sources only)
Targets (dst_kind, dst_key):
  person cluster id   org EIN   biz state:entity_id   fec_donor zip5:name_norm   lda_client id   lda_registrant id
  lda_lobbyist id     formd CIK   adv CRD   sec CIK
Rules, the site's usual ones: a person is the same normalized full name with a middle name or initial, held by
exactly one person page (or one FEC donor zip, or one lobbyist), in one of that person's states (FEC: the same
state); an organization is the same EIN (EXACT), or the same name core and state held by one record on each side
(SEC filers, which carry no state: a name core unique on both sides nationally).

Usage: .venv/bin/python -m loader.xlinks
"""

from __future__ import annotations

import datetime as dt
import sys

from app.names import normalize_name
from loader import db
from loader.recalls import core

PEOPLE_KINDS = ("preparer", "admin_signer", "sponsor_signer", "dfe_signer")
DDL = """
CREATE TABLE IF NOT EXISTS xlinks (
    src_kind text NOT NULL, src_key text NOT NULL, src_name text, src_state text,
    dst_kind text NOT NULL, dst_key text NOT NULL, dst_name text, how text NOT NULL,
    PRIMARY KEY (src_kind, src_key, dst_kind, dst_key));
CREATE INDEX IF NOT EXISTS xlinks_dst ON xlinks (dst_kind, dst_key);
CREATE TABLE IF NOT EXISTS xlink_counts (src_kind text NOT NULL, dst_kind text NOT NULL, n bigint NOT NULL,
                                         sources bigint NOT NULL, built timestamptz NOT NULL, PRIMARY KEY (src_kind, dst_kind));
"""


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (table,)).fetchone()[0]


def _copy(conn, table: str, cols: list[str], rows) -> int:
    with conn.cursor() as cur:
        return db.copy_rows(cur, table, cols, rows)


def people_sources(conn, status) -> None:
    """x_people: every person-like record of the new datasets, with its normalized name and state."""
    conn.execute("CREATE TEMP TABLE x_people (src_kind text, src_key text, src_name text, name_norm text, state text)")
    if _has(conn, "fara_short_forms"):
        conn.execute("""INSERT INTO x_people SELECT 'fara_person', id::text, name, name_norm, state FROM fara_short_forms
                        WHERE name_norm IS NOT NULL""")
        rows = conn.execute("""SELECT reg_number, name, state FROM fara_registrants
                               WHERE business_name IS NULL AND name LIKE '%%,%%'""").fetchall()
        _copy(conn, "x_people", ["src_kind", "src_key", "src_name", "name_norm", "state"],
              (("fara_registrant", n, name, normalize_name(name), st) for n, name, st in rows if normalize_name(name)))
    if _has(conn, "form5500_names"):
        conn.execute("""INSERT INTO x_people
                        SELECT 'f5500_person', state || ':' || name_norm, min(name), name_norm, state FROM form5500_names
                        WHERE kind = ANY(%s) AND name_norm IS NOT NULL AND state IS NOT NULL GROUP BY state, name_norm""",
                     (list(PEOPLE_KINDS),))
    if _has(conn, "op_recipients"):
        conn.execute("""INSERT INTO x_people SELECT 'op_recipient', key, name, name_norm, state FROM op_recipients
                        WHERE profile_id IS NOT NULL AND name_norm IS NOT NULL""")
    if _has(conn, "payroll_person_years"):
        conn.execute("""INSERT INTO x_people
                        SELECT 'payroll_person', state || ':' || label || ':' || name_norm, min(person_name), name_norm, state
                        FROM payroll_person_years WHERE source_key LIKE 'gov\\_%%' AND NOT withheld AND name_norm IS NOT NULL
                        GROUP BY state, label, name_norm""")
    conn.execute("CREATE INDEX ON x_people (name_norm)")
    conn.execute("ANALYZE x_people")
    status(f"xlinks: {conn.execute('SELECT count(*) FROM x_people').fetchone()[0]:,} person records to match")


def org_sources(conn, status) -> None:
    """x_orgs: every organization-like record of the new datasets, with its name core, state and EIN."""
    conn.execute("CREATE TEMP TABLE x_orgs (src_kind text, src_key text, src_name text, core text, state text, ein text)")
    if _has(conn, "fara_registrants"):
        conn.execute("""INSERT INTO x_orgs SELECT 'fara_registrant', reg_number, name, name_core, state, NULL FROM fara_registrants
                        WHERE length(name_core) >= 4""")
        conn.execute("""INSERT INTO x_orgs SELECT 'fara_principal', id::text, principal, principal_core, state, NULL FROM fara_principals
                        WHERE length(principal_core) >= 4 AND state ~ '^[A-Z]{2}$'""")
    if _has(conn, "form5500_filings"):
        rows = conn.execute("""SELECT DISTINCT ON (sponsor_ein) sponsor_ein, sponsor_name, sponsor_state FROM form5500_filings
                               WHERE sponsor_ein IS NOT NULL AND sponsor_name IS NOT NULL
                               ORDER BY sponsor_ein, plan_year DESC NULLS LAST""").fetchall()
        _copy(conn, "x_orgs", ["src_kind", "src_key", "src_name", "core", "state", "ein"],
              (("f5500_sponsor", ein, name, core(name), st, ein) for ein, name, st in rows))
    if _has(conn, "op_recipients"):
        rows = conn.execute("""SELECT key, name, state FROM op_recipients WHERE profile_id IS NULL AND name IS NOT NULL""").fetchall()
        _copy(conn, "x_orgs", ["src_kind", "src_key", "src_name", "core", "state", "ein"],
              (("op_recipient", k, name, core(name), st, None) for k, name, st in rows if len(core(name)) >= 4))
        rows = conn.execute("SELECT id, name, state FROM op_payers WHERE name IS NOT NULL").fetchall()
        _copy(conn, "x_orgs", ["src_kind", "src_key", "src_name", "core", "state", "ein"],
              (("op_payer", str(i), name, core(name), st, None) for i, name, st in rows if len(core(name)) >= 4))
    conn.execute("CREATE INDEX ON x_orgs (core, state)")
    conn.execute("CREATE INDEX ON x_orgs (ein)")
    conn.execute("ANALYZE x_orgs")
    status(f"xlinks: {conn.execute('SELECT count(*) FROM x_orgs').fetchone()[0]:,} organization records to match")


def org_targets(conn, status) -> None:
    """t_orgs: the site's organizations by name core and state (one per core+state), and by EIN."""
    conn.execute("CREATE TEMP TABLE t_orgs (dst_kind text, dst_key text, dst_name text, core text, state text, ein text)")
    rows = conn.execute("SELECT ein, name, state FROM organizations WHERE name IS NOT NULL").fetchall()
    _copy(conn, "t_orgs", ["dst_kind", "dst_key", "dst_name", "core", "state", "ein"],
          (("org", ein, name, core(name), st, ein) for ein, name, st in rows))
    if _has(conn, "biz_entities"):
        conn.execute("""INSERT INTO t_orgs SELECT 'biz', state || ':' || entity_id, name, name_core, addr_state, ein FROM biz_entities
                        WHERE name_core <> '' AND source <> 'form5500'""")
    if _has(conn, "lda_filings"):
        rows = conn.execute("""SELECT client_id, min(client_name), min(client_state), min(client_ein) FROM lda_filings
                               WHERE client_name IS NOT NULL GROUP BY 1""").fetchall()
        _copy(conn, "t_orgs", ["dst_kind", "dst_key", "dst_name", "core", "state", "ein"],
              (("lda_client", str(i), name, core(name), st, ein) for i, name, st, ein in rows))
        rows = conn.execute("""SELECT registrant_id, min(registrant_name), min(registrant_state), min(registrant_ein) FROM lda_filings
                               WHERE registrant_name IS NOT NULL GROUP BY 1""").fetchall()
        _copy(conn, "t_orgs", ["dst_kind", "dst_key", "dst_name", "core", "state", "ein"],
              (("lda_registrant", str(i), name, core(name), st, ein) for i, name, st, ein in rows))
    if _has(conn, "sec_formd_offerings"):
        rows = conn.execute("""SELECT DISTINCT ON (cik) cik, issuer_name, state FROM sec_formd_offerings
                               WHERE issuer_name IS NOT NULL ORDER BY cik, latest_date DESC""").fetchall()
        _copy(conn, "t_orgs", ["dst_kind", "dst_key", "dst_name", "core", "state", "ein"],
              (("formd", cik, name, core(name), st, None) for cik, name, st in rows))
    if _has(conn, "adv_filings"):
        rows = conn.execute("""SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name), state FROM adv_filings
                               WHERE crd IS NOT NULL ORDER BY crd, submitted DESC NULLS LAST""").fetchall()
        _copy(conn, "t_orgs", ["dst_kind", "dst_key", "dst_name", "core", "state", "ein"],
              (("adv", str(crd), name, core(name), st, None) for crd, name, st in rows if name))
    if _has(conn, "sec_fin_subs"):
        rows = conn.execute("SELECT DISTINCT ON (cik) cik, name FROM sec_fin_subs WHERE name IS NOT NULL ORDER BY cik, filed DESC").fetchall()
        _copy(conn, "t_orgs", ["dst_kind", "dst_key", "dst_name", "core", "state", "ein"],
              (("sec", str(cik), name, core(name), None, None) for cik, name in rows))
    conn.execute("DELETE FROM t_orgs WHERE length(core) < 4")
    conn.execute("CREATE INDEX ON t_orgs (dst_kind, core, state)")
    conn.execute("CREATE INDEX ON t_orgs (ein) WHERE ein IS NOT NULL")
    conn.execute("ANALYZE t_orgs")
    status(f"xlinks: {conn.execute('SELECT count(*) FROM t_orgs').fetchone()[0]:,} organization targets")


def build(status=print) -> dict:
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '1GB'")
        conn.commit()
        people_sources(conn, status)
        org_sources(conn, status)
        org_targets(conn, status)
        conn.execute("DROP TABLE IF EXISTS xlinks_new")
        conn.execute("CREATE TABLE xlinks_new (LIKE xlinks INCLUDING ALL)")
        # --- people -> person pages, FEC donors, lobbyists
        conn.execute("""
            CREATE TEMP TABLE t_people AS
            SELECT name_norm, min(id) AS id, min(states) AS states, min(display_name) AS display_name FROM person_clusters
            WHERE NOT coalesce(is_institution, false) GROUP BY name_norm HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON t_people (name_norm)")
        conn.execute("""
            INSERT INTO xlinks_new SELECT DISTINCT ON (x.src_kind, x.src_key, 'person', u.id::text)
                   x.src_kind, x.src_key, x.src_name, x.state, 'person', u.id::text, u.display_name,
                   'same full name with a middle name or initial, one person page, in that person''s states'
            FROM x_people x JOIN t_people u ON u.name_norm = x.name_norm
            WHERE array_length(string_to_array(x.name_norm, ' '), 1) >= 3 AND x.state IS NOT NULL AND x.state = ANY(u.states)""")
        if _has(conn, "fec_donor_totals"):
            conn.execute("""
                CREATE TEMP TABLE t_fec AS
                SELECT name_norm, state, min(zip5) AS zip5, min(name) AS name FROM
                     (SELECT DISTINCT name_norm, zip5, state, name FROM fec_donor_totals WHERE state IS NOT NULL AND zip5 IS NOT NULL) d
                GROUP BY name_norm, state HAVING count(DISTINCT zip5) = 1""")
            conn.execute("CREATE INDEX ON t_fec (name_norm, state)")
            conn.execute("""
                INSERT INTO xlinks_new SELECT DISTINCT ON (x.src_kind, x.src_key, 'fec_donor', f.zip5 || ':' || f.name_norm)
                       x.src_kind, x.src_key, x.src_name, x.state, 'fec_donor', f.zip5 || ':' || f.name_norm, f.name,
                       'same full name with a middle name or initial, one FEC donor in that state'
                FROM x_people x JOIN t_fec f ON f.name_norm = x.name_norm AND f.state = x.state
                WHERE array_length(string_to_array(x.name_norm, ' '), 1) >= 3""")
        if _has(conn, "lda_activity_lobbyists"):
            conn.execute("""
                CREATE TEMP TABLE t_lob AS
                SELECT name_norm, min(lobbyist_id) AS lobbyist_id, min(name) AS name FROM
                     (SELECT DISTINCT lobbyist_id, name_norm, name FROM lda_activity_lobbyists WHERE name_norm IS NOT NULL) l
                GROUP BY name_norm HAVING count(DISTINCT lobbyist_id) = 1""")
            conn.execute("CREATE INDEX ON t_lob (name_norm)")
            conn.execute("""
                INSERT INTO xlinks_new SELECT DISTINCT ON (x.src_kind, x.src_key, 'lda_lobbyist', l.lobbyist_id::text)
                       x.src_kind, x.src_key, x.src_name, x.state, 'lda_lobbyist', l.lobbyist_id::text, l.name,
                       'same full name with a middle name or initial, one registered lobbyist'
                FROM x_people x JOIN t_lob l ON l.name_norm = x.name_norm
                WHERE array_length(string_to_array(x.name_norm, ' '), 1) >= 3""")
        conn.commit()
        status("xlinks: people matched")
        # --- organizations: EIN exact, then name core and state (one on each side), SEC filers by unique core
        conn.execute("""
            INSERT INTO xlinks_new SELECT DISTINCT ON (x.src_kind, x.src_key, t.dst_kind, t.dst_key)
                   x.src_kind, x.src_key, x.src_name, x.state, t.dst_kind, t.dst_key, t.dst_name, 'EIN (EXACT)'
            FROM x_orgs x JOIN t_orgs t ON t.ein = x.ein WHERE x.ein IS NOT NULL ON CONFLICT DO NOTHING""")
        conn.execute("""
            INSERT INTO xlinks_new SELECT x.src_kind, x.src_key, x.src_name, x.state, t.dst_kind, t.dst_key, t.dst_name, 'name and state'
            FROM (SELECT src_kind, core, state, min(src_key) AS src_key, min(src_name) AS src_name FROM x_orgs
                  WHERE state IS NOT NULL GROUP BY 1, 2, 3 HAVING count(*) = 1) x
            JOIN (SELECT dst_kind, core, state, min(dst_key) AS dst_key, min(dst_name) AS dst_name FROM t_orgs
                  WHERE state IS NOT NULL GROUP BY 1, 2, 3 HAVING count(*) = 1) t ON t.core = x.core AND t.state = x.state
            ON CONFLICT DO NOTHING""")
        conn.execute("""
            INSERT INTO xlinks_new SELECT x.src_kind, x.src_key, x.src_name, x.state, t.dst_kind, t.dst_key, t.dst_name,
                   'name (an SEC filer''s name, unique on both sides)'
            FROM (SELECT src_kind, core, min(src_key) AS src_key, min(src_name) AS src_name, min(state) AS state FROM x_orgs
                  GROUP BY 1, 2 HAVING count(*) = 1) x
            JOIN (SELECT core, min(dst_key) AS dst_key, min(dst_name) AS dst_name FROM t_orgs WHERE dst_kind = 'sec'
                  GROUP BY 1 HAVING count(*) = 1) t ON t.core = x.core
            ON CONFLICT DO NOTHING""")
        conn.commit()
        status("xlinks: organizations matched")
        db.swap_table(conn, "xlinks")
        conn.execute("ANALYZE xlinks")
        conn.execute("DELETE FROM xlink_counts")
        conn.execute("""INSERT INTO xlink_counts SELECT src_kind, dst_kind, count(*), count(DISTINCT src_key), now()
                        FROM xlinks GROUP BY 1, 2""")
        conn.commit()
        counts = conn.execute("SELECT src_kind, dst_kind, n, sources FROM xlink_counts ORDER BY 1, 2").fetchall()
    for src, dst, n, s in counts:
        status(f"xlinks: {src} -> {dst}: {n:,} links ({s:,} records)")
    return {(src, dst): n for src, dst, n, _ in counts}


if __name__ == "__main__":
    build()
    sys.exit(0)
