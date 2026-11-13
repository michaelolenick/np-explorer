"""The continuous cross-referencing engine (owner, 2026-11-13: "the key to FURP is not just the records but they're
all cross referenced ... in the background cross reference everything and continue cross referencing").

Every record kind in the database is a source and a destination: nonprofits, people, contractors, federal award
recipients, lobbying clients and registrants, political committees, SEC filers, Form D issuers, advisers, Form 5500
sponsors, Open Payments companies, FARA registrants, business registrations, recall firms, patent and trademark
owners, colleges, IPO registrants and underwriters, student-loan issuers, SEC insiders, inventors, and interests
(NTEE codes, FURP topics, lobbying issues, Form D industries, SIC codes, patent classes). Links go into the same
`xlinks` table loader/xlinks.py fills (app/xlinks.py reads it on every entity page, /api/v1/xlinks and the MCP tool
get_links return it), as rows tagged with the linker that made them, so the nightly xlinks rebuild keeps them.

How it works
  1. Collectors copy each kind's records into xref_names (kind, key, name, core, state, city, zip5, street, ein,
     cik, crd), one row per record, with the site's usual name core (loader/recalls.core, the one the registries,
     IPOs, patents and trademarks already carry) and a normalized street. Each collector keeps a cursor in
     xref_state (the last key or timestamp it saw), so a sweep copies only new records.
  2. Linkers join the records collected since they last ran against everything, by one rule each, in order of
     confidence: identifiers (EIN, CIK, CRD), name and state, name and city, street address and ZIP, an SEC
     filer's name unique among filers; people by full name (three or more parts) to the one person page with that
     name in that state; interests to category keys. Every link says how it was made in `how`, in the words the
     pages show, with EXACT or FUZZY as the existing rows have it. Symmetric rules write both directions, so every
     page shows the link.
  3. Imports copy the links the dataset loaders already computed (sec_person_links, op_person_links, ...) into
     xlinks, so one table and one API carry them all.
Nothing is ever deleted here; rows are inserted with ON CONFLICT DO NOTHING on the table's primary key.

Usage
  python -m loader.xref sweep                     incremental, any time: new records only, batches under a statement
                                                  timeout, stops after SWEEP_BUDGET seconds and resumes next time
  python -m loader.xref rebuild [--linker NAME]   every record again (cursors reset), off peak (loader/offpeak.py)
  python -m loader.xref sample NAME [--n 50]      print a random sample of a linker's links, to judge precision
  python -m loader.xref status                    the state table
Cron (dev): every two hours, flock; scripts/nightly.sh (prod) runs the weekly rebuild after loader.xlinks.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import time

from loader import db
from loader.recalls import core

SWEEP_BUDGET = int(os.environ.get("XREF_SWEEP_SECONDS", "1500"))      # 25 minutes, then the next sweep continues
BATCH = 5000
EPOCH = "1970-01-01"

DDL = """
CREATE TABLE IF NOT EXISTS xlinks (
    src_kind text NOT NULL, src_key text NOT NULL, src_name text, src_state text,
    dst_kind text NOT NULL, dst_key text NOT NULL, dst_name text, how text NOT NULL,
    PRIMARY KEY (src_kind, src_key, dst_kind, dst_key));
CREATE INDEX IF NOT EXISTS xlinks_dst ON xlinks (dst_kind, dst_key);
ALTER TABLE xlinks ADD COLUMN IF NOT EXISTS linker text;
ALTER TABLE xlinks ADD COLUMN IF NOT EXISTS added timestamptz DEFAULT now();
CREATE INDEX IF NOT EXISTS xlinks_interest ON xlinks (dst_key, src_state) WHERE dst_kind = 'interest';
CREATE TABLE IF NOT EXISTS xref_state (
    linker text PRIMARY KEY, src_kind text, dst_kinds text, rule text, last_run timestamptz, last_full timestamptz,
    cursor text, rows_added bigint DEFAULT 0, total_added bigint DEFAULT 0, seconds real, runs integer DEFAULT 0,
    error text);
CREATE TABLE IF NOT EXISTS xref_names (
    kind text NOT NULL, key text NOT NULL, ref text, name text, core text, state text, city text, zip5 text,
    street text, ein text, cik text, crd text, updated timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, key));
CREATE INDEX IF NOT EXISTS xref_names_core ON xref_names (core, state);
CREATE INDEX IF NOT EXISTS xref_names_ein ON xref_names (ein) WHERE ein IS NOT NULL;
CREATE INDEX IF NOT EXISTS xref_names_cik ON xref_names (cik) WHERE cik IS NOT NULL;
CREATE INDEX IF NOT EXISTS xref_names_crd ON xref_names (crd) WHERE crd IS NOT NULL;
CREATE INDEX IF NOT EXISTS xref_names_addr ON xref_names (zip5, street) WHERE street IS NOT NULL;
CREATE INDEX IF NOT EXISTS xref_names_updated ON xref_names (updated, kind, key);
CREATE TABLE IF NOT EXISTS xref_counts (
    src_kind text NOT NULL, dst_kind text NOT NULL, linker text NOT NULL, rule text, n bigint NOT NULL,
    sources bigint NOT NULL, built timestamptz NOT NULL, PRIMARY KEY (src_kind, dst_kind, linker));
"""

NAME_COLS = ["kind", "key", "ref", "name", "core", "state", "city", "zip5", "street", "ein", "cik", "crd"]
# One record per name and state in these kinds (a second record with the same name is a different, ambiguous match);
# a company has several registrations, PACs, UEIs and lobbying ids, so those kinds allow up to MULTI per name and state.
UNIQUE_KINDS = ("org", "formd", "adv", "college", "f5500_sponsor", "recallfirm", "op_payer", "op_recipient", "ipo_company",
                "pat_assignee", "tm_owner", "sl_issuer", "contractor", "fara_principal", "ipo_underwriter")
MULTI_KINDS = ("biz", "lda_client", "lda_registrant", "fec_committee", "fed", "fara_registrant")
MULTI = 12
STATE_RE = re.compile(r"^[A-Z]{2}$")
_SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "ROAD": "RD", "DRIVE": "DR", "BOULEVARD": "BLVD", "LANE": "LN",
           "COURT": "CT", "PLACE": "PL", "PARKWAY": "PKWY", "HIGHWAY": "HWY", "CIRCLE": "CIR", "TERRACE": "TER",
           "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W", "SUITE": "STE", "UNIT": "STE", "APT": "STE",
           "FLOOR": "FL", "BUILDING": "BLDG", "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW"}
_PO_BOX = re.compile(r"^(P\s*O\s*BOX|PO\s*BOX|POST OFFICE BOX|BOX)\b")


def street_norm(street: str | None) -> str | None:
    """A street line for matching: "431 18th Street, N.W., Suite 200" and "431 18TH ST NW STE 200" are the same;
    PO boxes and lines without a street number are None (shared mailboxes and bare street names are not an address)."""
    s = re.sub(r"[^A-Z0-9 ]+", " ", (street or "").upper().replace(".", "").replace("#", " STE "))
    s = re.sub(r"\s+", " ", s).strip()
    if not s or _PO_BOX.match(s) or not re.match(r"^\d", s):
        return None
    words = [_SUFFIX.get(w, w) for w in s.split()]
    out = " ".join(words)
    return out[:80] if len(out) >= 6 else None


def zip5(z: str | None) -> str | None:
    m = re.match(r"^\s*(\d{5})", z or "")
    return m.group(1) if m else None


def state_of(s: str | None) -> str | None:
    s = (s or "").strip().upper()
    return s if STATE_RE.match(s) else None


def _log(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} xref: {msg}"
    print(line, flush=True)


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (table,)).fetchone()[0]


def ensure_schema(conn) -> None:
    """The tables and the two columns on xlinks, created once (the ALTER and CREATE INDEX take locks; not every sweep)."""
    ok = conn.execute("""SELECT to_regclass('xref_counts') IS NOT NULL AND to_regclass('xref_names') IS NOT NULL
                         AND to_regclass('xref_state') IS NOT NULL AND to_regclass('xlinks_interest') IS NOT NULL
                         AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'xlinks' AND column_name = 'linker')""").fetchone()[0]
    if not ok:
        conn.execute(DDL)
        conn.commit()


def _rebuilding(conn) -> bool:
    """loader/xlinks.py is swapping the table (xlinks_new exists): wait for it, never write into a table being replaced."""
    return _has(conn, "xlinks_new")


# --- state -------------------------------------------------------------------------------------------------------

def get_state(conn, name: str) -> dict:
    cur = conn.execute("SELECT * FROM xref_state WHERE linker = %s", (name,))
    r = cur.fetchone()
    return dict(zip([d.name for d in cur.description], r)) if r else {}


def set_state(conn, name: str, *, src_kind=None, dst_kinds=None, rule=None, cursor=None, added=0, seconds=0.0,
              error=None, full=False) -> None:
    conn.execute("""INSERT INTO xref_state (linker, src_kind, dst_kinds, rule, last_run, last_full, cursor, rows_added,
                                            total_added, seconds, runs, error)
                    VALUES (%(l)s, %(s)s, %(d)s, %(r)s, now(), CASE WHEN %(f)s THEN now() END, %(c)s, %(a)s, %(a)s, %(sec)s, 1, %(e)s)
                    ON CONFLICT (linker) DO UPDATE SET
                        src_kind = coalesce(EXCLUDED.src_kind, xref_state.src_kind),
                        dst_kinds = coalesce(EXCLUDED.dst_kinds, xref_state.dst_kinds),
                        rule = coalesce(EXCLUDED.rule, xref_state.rule), last_run = now(),
                        last_full = coalesce(EXCLUDED.last_full, xref_state.last_full),
                        cursor = coalesce(EXCLUDED.cursor, xref_state.cursor), rows_added = EXCLUDED.rows_added,
                        total_added = xref_state.total_added + EXCLUDED.rows_added, seconds = EXCLUDED.seconds,
                        runs = xref_state.runs + 1, error = EXCLUDED.error""",
                 dict(l=name, s=src_kind, d=dst_kinds, r=rule, c=cursor, a=added, sec=seconds, e=error, f=full))


# --- collectors: every kind's records into xref_names ----------------------------------------------------------

def _upsert_names(conn, rows) -> int:
    """rows: dicts with NAME_COLS keys. Returns the number copied (updated rows get a fresh `updated`)."""
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS xn_batch (LIKE xref_names INCLUDING DEFAULTS) ON COMMIT DROP")
    conn.execute("TRUNCATE xn_batch")
    n = 0
    with conn.cursor() as cur:
        n = db.copy_rows(cur, "xn_batch", NAME_COLS, (tuple(r.get(c) for c in NAME_COLS) for r in rows))
    conn.execute("""INSERT INTO xref_names (kind, key, ref, name, core, state, city, zip5, street, ein, cik, crd, updated)
                    SELECT DISTINCT ON (kind, key) kind, key, ref, name, core, state, census_city_norm(city), zip5, street,
                           ein, cik, crd, now()
                    FROM xn_batch WHERE core IS NOT NULL AND length(core) >= 3
                    ON CONFLICT (kind, key) DO UPDATE SET ref = EXCLUDED.ref, name = EXCLUDED.name, core = EXCLUDED.core,
                        state = EXCLUDED.state, city = EXCLUDED.city, zip5 = EXCLUDED.zip5, street = EXCLUDED.street,
                        ein = EXCLUDED.ein, cik = EXCLUDED.cik, crd = EXCLUDED.crd, updated = now()
                    WHERE (xref_names.name, xref_names.state, xref_names.zip5, xref_names.street, xref_names.ein, xref_names.cik)
                          IS DISTINCT FROM (EXCLUDED.name, EXCLUDED.state, EXCLUDED.zip5, EXCLUDED.street, EXCLUDED.ein, EXCLUDED.cik)""")
    return n


def _ein(e) -> str | None:
    d = re.sub(r"\D", "", str(e or ""))
    return d if len(d) == 9 and d != "000000000" else None


def _rec(kind, key, name, state=None, city=None, zip_=None, street=None, ein=None, cik=None, crd=None, ref=None) -> dict:
    return {"kind": kind, "key": str(key), "ref": ref, "name": name, "core": core(name)[:200] if name else None,
            "state": state_of(state), "city": (city or "")[:80] or None, "zip5": zip5(zip_), "street": street_norm(street),
            "ein": _ein(ein), "cik": str(int(cik)) if cik and str(cik).isdigit() else None,
            "crd": str(crd) if crd else None}


# Each collector: (kind, table it needs, cursor style, SQL returning rows keyed after the cursor, row -> _rec).
# "key" cursors walk the key in order (new keys below the cursor wait for the weekly rebuild); "ts" cursors read
# rows loaded after the cursor. Collectors marked sweep=False run only in a rebuild (no index for their cursor).
def c_org(conn, cur, n):
    rows = conn.execute("""SELECT ein, name, street, city, state, zip FROM organizations WHERE name IS NOT NULL AND ein > %s
                           ORDER BY ein LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("org", r[0], r[1], r[4], r[3], r[5], r[2], ein=r[0]) for r in rows], (rows[-1][0] if rows else None)


def c_fed(conn, cur, n):
    rows = conn.execute("""SELECT uei, name, state, ein FROM fed_recipient_names WHERE uei > %s ORDER BY uei LIMIT %s""",
                        (cur or "", n)).fetchall()
    return [_rec("fed", r[0], r[1], r[2], ein=r[3]) for r in rows], (rows[-1][0] if rows else None)


def c_lda_client(conn, cur, n):
    rows = conn.execute("""SELECT client_id, min(client_name), min(client_state), min(client_ein) FROM lda_filings
                           WHERE client_name IS NOT NULL AND client_id > %s GROUP BY client_id ORDER BY client_id LIMIT %s""",
                        (int(cur or 0), n)).fetchall()
    return [_rec("lda_client", r[0], r[1], r[2], ein=r[3]) for r in rows], (str(rows[-1][0]) if rows else None)


def c_lda_registrant(conn, cur, n):
    rows = conn.execute("""SELECT registrant_id, min(registrant_name), min(registrant_state), min(registrant_ein) FROM lda_filings
                           WHERE registrant_name IS NOT NULL AND registrant_id > %s GROUP BY registrant_id ORDER BY registrant_id LIMIT %s""",
                        (int(cur or 0), n)).fetchall()
    return [_rec("lda_registrant", r[0], r[1], r[2], ein=r[3]) for r in rows], (str(rows[-1][0]) if rows else None)


def c_fec_committee(conn, cur, n):
    rows = conn.execute("""SELECT DISTINCT ON (cmte_id) cmte_id, name, connected_org, street1, city, state, zip FROM fec_committees
                           WHERE connected_org IS NOT NULL AND connected_org <> '' AND cmte_id > %s
                           ORDER BY cmte_id, cycle DESC LIMIT %s""", (cur or "", n)).fetchall()
    return [dict(_rec("fec_committee", r[0], r[2], r[5], r[4], r[6], r[3]), name=f"{r[1]} (connected to {r[2]})") for r in rows], \
        (rows[-1][0] if rows else None)


def c_sec(conn, cur, n):
    rows = conn.execute("""SELECT cik, name FROM (
                               SELECT DISTINCT ON (cik) cik::bigint::text AS cik, name FROM sec_fin_subs WHERE name IS NOT NULL ORDER BY cik, filed DESC) a
                           WHERE cik::bigint > %s ORDER BY cik::bigint LIMIT %s""", (int(cur or 0), n)).fetchall()
    return [_rec("sec", r[0], r[1], cik=r[0]) for r in rows], (rows[-1][0] if rows else None)


def c_sec_issuers(conn, cur, n):
    rows = conn.execute("""SELECT issuer_cik::bigint::text, issuer_name FROM (
                               SELECT DISTINCT ON (issuer_cik) issuer_cik, issuer_name FROM sec_insider_filings
                               WHERE issuer_name IS NOT NULL AND issuer_cik::bigint > %s ORDER BY issuer_cik, filing_date DESC) a
                           ORDER BY issuer_cik::bigint LIMIT %s""", (int(cur or 0), n)).fetchall()
    return [_rec("sec", r[0], r[1], cik=r[0]) for r in rows], (rows[-1][0] if rows else None)


def c_formd(conn, cur, n):
    rows = conn.execute("""SELECT DISTINCT ON (cik) cik, issuer_name, city, state FROM sec_formd_offerings
                           WHERE issuer_name IS NOT NULL AND cik > %s ORDER BY cik, latest_date DESC LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("formd", r[0], r[1], r[3], r[2], cik=r[0]) for r in rows], (rows[-1][0] if rows else None)


def c_adv(conn, cur, n):
    rows = conn.execute("""SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name), street, city, state, postal FROM adv_filings
                           WHERE crd IS NOT NULL AND crd > %s ORDER BY crd, submitted DESC NULLS LAST LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("adv", r[0], r[1], r[4], r[3], r[5], r[2], crd=r[0]) for r in rows if r[1]], (rows[-1][0] if rows else None)


def c_f5500(conn, cur, n):
    """Plan sponsors: one row per EIN, from the filings loaded after the cursor (rebuild only: no index on `loaded`)."""
    since = cur or EPOCH
    rows = conn.execute("""SELECT DISTINCT ON (sponsor_ein) sponsor_ein, sponsor_name, sponsor_state, sponsor_city, loaded
                           FROM form5500_filings WHERE sponsor_ein IS NOT NULL AND sponsor_name IS NOT NULL AND loaded > %s
                           ORDER BY sponsor_ein, plan_year DESC NULLS LAST""", (since,)).fetchall()
    newest = max((r[4] for r in rows), default=None)
    return [_rec("f5500_sponsor", r[0], r[1], r[2], r[3], ein=r[0]) for r in rows], (newest.isoformat() if newest else None)


def c_op_payer(conn, cur, n):
    rows = conn.execute("SELECT id, name, state FROM op_payers WHERE name IS NOT NULL AND id > %s ORDER BY id LIMIT %s", (int(cur or 0), n)).fetchall()
    return [_rec("op_payer", r[0], r[1], r[2]) for r in rows], (str(rows[-1][0]) if rows else None)


def c_op_recipient(conn, cur, n):
    rows = conn.execute("""SELECT key, name, city, state FROM op_recipients WHERE profile_id IS NULL AND name IS NOT NULL AND key > %s
                           ORDER BY key LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("op_recipient", r[0], r[1], r[3], r[2]) for r in rows], (rows[-1][0] if rows else None)


def c_fara_registrant(conn, cur, n):
    rows = conn.execute("""SELECT reg_number, name, address1, city, state, zip FROM fara_registrants WHERE reg_number > %s
                           ORDER BY reg_number LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("fara_registrant", r[0], r[1], r[4], r[3], r[5], r[2]) for r in rows], (rows[-1][0] if rows else None)


def c_fara_principal(conn, cur, n):
    rows = conn.execute("""SELECT id, principal, city, state FROM fara_principals WHERE state ~ '^[A-Z]{2}$' AND id > %s
                           ORDER BY id LIMIT %s""", (int(cur or 0), n)).fetchall()
    return [_rec("fara_principal", r[0], r[1], r[3], r[2]) for r in rows], (str(rows[-1][0]) if rows else None)


def c_contractor(conn, cur, n):
    """Nonprofit contractors by vendor key (contractors.vendor_key merges spellings); the page is /contractor/<latest id>."""
    rows = conn.execute("""SELECT DISTINCT ON (vendor_key) vendor_key, id, name_raw, street, city, state, zip
                           FROM contractors WHERE vendor_key IS NOT NULL AND vendor_key > %s
                           ORDER BY vendor_key, tax_year DESC NULLS LAST, id DESC LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("contractor", r[0][:200], r[2], r[5], r[4], r[6], r[3], ref=str(r[1])) for r in rows], (rows[-1][0] if rows else None)


def c_college(conn, cur, n):
    rows = conn.execute("""SELECT unitid, name, street, city, state, zip, ein FROM colleges WHERE NOT coalesce(international, false)
                           AND unitid > %s ORDER BY unitid LIMIT %s""", (int(cur or 0), n)).fetchall()
    return [_rec("college", r[0], r[1], r[4], r[3], r[5], r[2], ein=r[6]) for r in rows], (str(rows[-1][0]) if rows else None)


def c_recallfirm(conn, cur, n):
    rows = conn.execute("SELECT firm_id, name, city, state FROM food_recall_firms WHERE firm_id > %s ORDER BY firm_id LIMIT %s", (cur or "", n)).fetchall()
    return [_rec("recallfirm", r[0], r[1], r[3], r[2]) for r in rows], (rows[-1][0] if rows else None)


def c_ipo(conn, cur, n):
    rows = conn.execute("""SELECT cik, name, street, city, state, zip, ein FROM ipo_companies WHERE cik > %s ORDER BY cik LIMIT %s""",
                        (cur or "", n)).fetchall()
    return [_rec("ipo_company", r[0], r[1], r[4], r[3], r[5], r[2], ein=r[6], cik=r[0]) for r in rows], (rows[-1][0] if rows else None)


def c_ipo_underwriter(conn, cur, n):
    rows = conn.execute("""SELECT name_key, name, bd_cik, ia_crd FROM ipo_underwriters WHERE name_key > %s ORDER BY name_key LIMIT %s""",
                        (cur or "", n)).fetchall()
    return [_rec("ipo_underwriter", r[0], r[1], cik=r[2], crd=r[3]) for r in rows], (rows[-1][0] if rows else None)


def c_pat_assignee(conn, cur, n):
    rows = conn.execute("""SELECT assignee_id, name, city, state FROM pat_assignee_orgs WHERE NOT coalesce(is_person, false)
                           AND coalesce(country, 'US') = 'US' AND assignee_id > %s ORDER BY assignee_id LIMIT %s""", (cur or "", n)).fetchall()
    return [_rec("pat_assignee", r[0], r[1], r[3], r[2]) for r in rows], (rows[-1][0] if rows else None)


def c_tm_owner(conn, cur, n):
    rows = conn.execute("""SELECT owner_key, name, state FROM tm_owner_orgs WHERE coalesce(country, 'US') = 'US' AND state ~ '^[A-Z]{2}$'
                           AND coalesce(entity, '') NOT ILIKE 'individual%%' AND owner_key > %s ORDER BY owner_key LIMIT %s""",
                        (cur or "", n)).fetchall()
    return [_rec("tm_owner", r[0], r[1], r[2]) for r in rows], (rows[-1][0] if rows else None)


def c_sl_issuer(conn, cur, n):
    rows = conn.execute("""SELECT id, party, slug, state, ein, sec_cik FROM student_loan_parties WHERE id > %s ORDER BY id LIMIT %s""",
                        (int(cur or 0), n)).fetchall()
    return [_rec("sl_issuer", r[0], r[1], r[3], ein=r[4], cik=r[5], ref=r[2]) for r in rows], (str(rows[-1][0]) if rows else None)


COLLECTORS = [
    # name, kind, table, function, sweep?
    ("collect:org", "org", "organizations", c_org, True),
    ("collect:fed", "fed", "fed_recipient_names", c_fed, True),
    ("collect:lda_client", "lda_client", "lda_filings", c_lda_client, True),
    ("collect:lda_registrant", "lda_registrant", "lda_filings", c_lda_registrant, True),
    ("collect:fec_committee", "fec_committee", "fec_committees", c_fec_committee, True),
    ("collect:sec", "sec", "sec_fin_subs", c_sec, True),
    ("collect:sec_issuers", "sec", "sec_insider_filings", c_sec_issuers, True),
    ("collect:formd", "formd", "sec_formd_offerings", c_formd, True),
    ("collect:adv", "adv", "adv_filings", c_adv, True),
    ("collect:f5500_sponsor", "f5500_sponsor", "form5500_filings", c_f5500, False),
    ("collect:op_payer", "op_payer", "op_payers", c_op_payer, True),
    ("collect:op_recipient", "op_recipient", "op_recipients", c_op_recipient, True),
    ("collect:fara_registrant", "fara_registrant", "fara_registrants", c_fara_registrant, True),
    ("collect:fara_principal", "fara_principal", "fara_principals", c_fara_principal, True),
    ("collect:contractor", "contractor", "contractors", c_contractor, True),
    ("collect:college", "college", "colleges", c_college, True),
    ("collect:recallfirm", "recallfirm", "food_recall_firms", c_recallfirm, True),
    ("collect:ipo_company", "ipo_company", "ipo_companies", c_ipo, True),
    ("collect:ipo_underwriter", "ipo_underwriter", "ipo_underwriters", c_ipo_underwriter, True),
    ("collect:pat_assignee", "pat_assignee", "pat_assignee_orgs", c_pat_assignee, True),
    ("collect:tm_owner", "tm_owner", "tm_owner_orgs", c_tm_owner, True),
    ("collect:sl_issuer", "sl_issuer", "student_loan_parties", c_sl_issuer, True),
]


def run_collector(conn, name, kind, table, fn, *, reset: bool, deadline: float, timeout: str, max_batches=None) -> int:
    if not _has(conn, table):
        return 0
    st = get_state(conn, name)
    cursor = None if reset else st.get("cursor")
    t0, added, batches = time.time(), 0, 0
    while time.time() < deadline and (max_batches is None or batches < max_batches):
        if _rebuilding(conn):
            _log(f"{name}: xlinks rebuild in progress, pausing")
            break
        conn.execute(f"SET statement_timeout = '{timeout}'")
        rows, new_cursor = fn(conn, cursor, BATCH)
        batches += 1
        if not rows and new_cursor is None:
            break
        added += _upsert_names(conn, rows)
        cursor = new_cursor or cursor
        set_state(conn, name, src_kind=kind, dst_kinds="xref_names", rule="collect the records", cursor=cursor,
                  added=len(rows), seconds=time.time() - t0, full=reset)
        conn.commit()
        if len(rows) < BATCH or new_cursor is None:
            break
    conn.execute("SET statement_timeout = 0")
    conn.commit()
    _log(f"{name}: {added:,} records collected in {time.time() - t0:.0f}s (cursor {cursor!r})")
    return added


# --- linkers -------------------------------------------------------------------------------------------------

INSERT = """INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker) """
_URL_KEY = "coalesce({a}.ref, {a}.key)"


def _both_ways(conn, select: str, params, linker: str) -> int:
    """`select` yields s_kind, s_key, s_name, s_state, t_kind, t_key, t_name, t_state, how; both directions are written."""
    n = conn.execute(INSERT + f"""SELECT s_kind, s_key, s_name, s_state, t_kind, t_key, t_name, how, %(linker)s FROM ({select}) q
                     ON CONFLICT DO NOTHING""", {**params, "linker": linker}).rowcount
    n += conn.execute(INSERT + f"""SELECT t_kind, t_key, t_name, t_state, s_kind, s_key, s_name, how, %(linker)s FROM ({select}) q
                      ON CONFLICT DO NOTHING""", {**params, "linker": linker}).rowcount
    return n


def _batch_names(conn, since, limit) -> tuple[int, str | None]:
    """The records collected after the cursor `since` ("updated|kind|key": thousands of rows share one `updated`, the
    batch's commit time, so the cursor is the whole tuple) into temp table xb; returns (rows, the new cursor)."""
    ts, _, rest = (since or EPOCH).partition("|")
    kind, _, key = rest.partition("|")
    conn.execute("DROP TABLE IF EXISTS xb")
    conn.execute("""CREATE TEMP TABLE xb ON COMMIT DROP AS
                    SELECT * FROM xref_names WHERE (updated, kind, key) > (%s::timestamptz, %s, %s)
                    ORDER BY updated, kind, key LIMIT %s""", (ts, kind, key, limit))
    r = conn.execute("SELECT count(*) FROM xb").fetchone()
    last = conn.execute("SELECT updated, kind, key FROM xb ORDER BY updated DESC, kind DESC, key DESC LIMIT 1").fetchone()
    conn.execute("ANALYZE xb")
    return r[0], (f"{last[0].isoformat()}|{last[1]}|{last[2]}" if last else None)


_COUNT_LIM = f"""(SELECT count(*) FROM (SELECT 1 FROM xref_names u WHERE u.kind = t.kind AND u.core = t.core AND u.state = t.state
                                        LIMIT {MULTI + 1}) z) <= CASE WHEN t.kind = ANY(%(uniq)s) THEN 1 ELSE {MULTI} END"""


def l_ein(conn, since, limit, linker):
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    return ein_links(conn, linker), newest


def ein_links(conn, linker: str) -> int:
    """The EIN rule over the batch in temp table xb (tests build xb themselves)."""
    added = _both_ways(conn, f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, {_URL_KEY.format(a='t')} AS t_key, t.name AS t_name, t.state AS t_state, 'EIN (EXACT)' AS how
        FROM xb s JOIN xref_names t ON t.ein = s.ein AND t.kind <> s.kind WHERE s.ein IS NOT NULL""", {}, linker)
    if _has(conn, "biz_entities"):
        added += _both_ways(conn, """
            SELECT s.kind AS s_kind, coalesce(s.ref, s.key) AS s_key, s.name AS s_name, s.state AS s_state,
                   'biz' AS t_kind, b.state || ':' || b.entity_id AS t_key, b.name AS t_name, b.addr_state AS t_state,
                   'EIN (EXACT, as the state registration reports it)' AS how
            FROM xb s JOIN biz_entities b ON b.ein = s.ein WHERE s.ein IS NOT NULL AND b.source <> 'form5500'""", {}, linker)
    return added


def l_cik(conn, since, limit, linker):
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    return _both_ways(conn, f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, {_URL_KEY.format(a='t')} AS t_key, t.name AS t_name, t.state AS t_state, 'CIK (EXACT)' AS how
        FROM xb s JOIN xref_names t ON t.cik = s.cik AND t.kind <> s.kind WHERE s.cik IS NOT NULL""", {}, linker), newest


def l_crd(conn, since, limit, linker):
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    return _both_ways(conn, f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, {_URL_KEY.format(a='t')} AS t_key, t.name AS t_name, t.state AS t_state, 'CRD (EXACT)' AS how
        FROM xb s JOIN xref_names t ON t.crd = s.crd AND t.kind <> s.kind WHERE s.crd IS NOT NULL""", {}, linker), newest


# A name core worth matching on: at least two words, or one word of eight or more letters ("microsoft"; never "acme").
_SPECIFIC = "(array_length(string_to_array({a}.core, ' '), 1) >= 2 OR length({a}.core) >= 8) AND length({a}.core) >= 5"


def l_name_state(conn, since, limit, linker):
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    return name_state_links(conn, linker), newest


def name_state_links(conn, linker: str) -> int:
    """The name-and-state rule over the batch in temp table xb."""
    params = {"uniq": list(UNIQUE_KINDS)}
    added = _both_ways(conn, f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, {_URL_KEY.format(a='t')} AS t_key, t.name AS t_name, t.state AS t_state, 'name and state' AS how
        FROM xb s JOIN xref_names t ON t.core = s.core AND t.state = s.state AND t.kind <> s.kind
        WHERE s.state IS NOT NULL AND {_SPECIFIC.format(a='s')} AND {_COUNT_LIM}
          AND (s.kind = ANY(%(uniq)s) OR (SELECT count(*) FROM (SELECT 1 FROM xref_names u WHERE u.kind = s.kind AND u.core = s.core
                                                                 AND u.state = s.state LIMIT {MULTI + 1}) z) <= {MULTI})""", params, linker)
    if _has(conn, "biz_entities"):
        added += _both_ways(conn, f"""
            SELECT s.kind AS s_kind, coalesce(s.ref, s.key) AS s_key, s.name AS s_name, s.state AS s_state,
                   'biz' AS t_kind, b.state || ':' || b.entity_id AS t_key, b.name AS t_name, b.addr_state AS t_state, 'name and state' AS how
            FROM xb s JOIN biz_entities b ON b.name_core = s.core AND b.addr_state = s.state
            WHERE s.state IS NOT NULL AND b.source <> 'form5500' AND {_SPECIFIC.format(a='s')}
              AND (SELECT count(*) FROM (SELECT 1 FROM biz_entities b2 WHERE b2.name_core = s.core AND b2.addr_state = s.state LIMIT {MULTI + 1}) z) <= {MULTI}""",
            {}, linker)
    return added


def l_name_city(conn, since, limit, linker):
    """A name shared by several records in a state, but by one in the city (Grace Church, Austin)."""
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    params = {"uniq": list(UNIQUE_KINDS)}
    return _both_ways(conn, f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, {_URL_KEY.format(a='t')} AS t_key, t.name AS t_name, t.state AS t_state, 'name and city' AS how
        FROM xb s JOIN xref_names t ON t.core = s.core AND t.state = s.state AND t.city = s.city AND t.kind <> s.kind
        WHERE s.state IS NOT NULL AND s.city IS NOT NULL AND length(s.city) >= 3 AND {_SPECIFIC.format(a='s')}
          AND t.kind = ANY(%(uniq)s)
          AND NOT ({_COUNT_LIM})
          AND (SELECT count(*) FROM xref_names u WHERE u.kind = t.kind AND u.core = t.core AND u.state = t.state AND u.city = t.city) = 1
          AND (SELECT count(*) FROM xref_names u WHERE u.kind = s.kind AND u.core = s.core AND u.state = s.state AND u.city = s.city) = 1""",
        params, linker), newest


def l_address(conn, since, limit, linker):
    """The same street address and ZIP, different names, at most two names at the address (more is a building or a
    registered agent; the 2026-11-13 sample at three had office-building neighbours). FUZZY: a shared office is not
    proof of a shared organization."""
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    return _both_ways(conn, f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, {_URL_KEY.format(a='t')} AS t_key, t.name AS t_name, t.state AS t_state,
               'same street address and ZIP code, ' || s.street || ' ' || s.zip5 || ' (FUZZY: a shared address, not proof of a shared organization)' AS how
        FROM xb s JOIN xref_names t ON t.zip5 = s.zip5 AND t.street = s.street AND (t.kind, t.key) <> (s.kind, s.key)
        WHERE s.street IS NOT NULL AND s.zip5 IS NOT NULL AND t.core <> s.core
          AND (SELECT count(DISTINCT u.core) FROM xref_names u WHERE u.zip5 = s.zip5 AND u.street = s.street) <= 2""", {}, linker), newest


def l_sec_name(conn, since, limit, linker):
    """SEC filers have no state: a filer whose name core is unique among filers, and specific (two words or a long one)."""
    n, newest = _batch_names(conn, since, limit)
    if not n:
        return 0, None
    sel = f"""
        SELECT s.kind AS s_kind, {_URL_KEY.format(a='s')} AS s_key, s.name AS s_name, s.state AS s_state,
               t.kind AS t_kind, t.key AS t_key, t.name AS t_name, NULL::text AS t_state,
               'name (an SEC filer''s name, unique among filers)' AS how
        FROM xb s JOIN xref_names t ON t.core = s.core AND t.kind = 'sec' AND s.kind <> 'sec'
        WHERE {_SPECIFIC.format(a='s')} AND length(s.core) >= 8
          AND (SELECT count(*) FROM (SELECT 1 FROM xref_names u WHERE u.kind = 'sec' AND u.core = s.core LIMIT 2) z) = 1
          AND (SELECT count(*) FROM (SELECT 1 FROM xref_names u WHERE u.kind = s.kind AND u.core = s.core LIMIT 2) z) = 1"""
    added = _both_ways(conn, sel, {}, linker)
    # the other way round: a newly collected SEC filer against everything with that unique name
    sel2 = f"""
        SELECT t.kind AS s_kind, {_URL_KEY.format(a='t')} AS s_key, t.name AS s_name, t.state AS s_state,
               s.kind AS t_kind, s.key AS t_key, s.name AS t_name, NULL::text AS t_state,
               'name (an SEC filer''s name, unique among filers)' AS how
        FROM xb s JOIN xref_names t ON t.core = s.core AND t.kind <> 'sec'
        WHERE s.kind = 'sec' AND {_SPECIFIC.format(a='s')} AND length(s.core) >= 8
          AND (SELECT count(*) FROM (SELECT 1 FROM xref_names u WHERE u.kind = 'sec' AND u.core = s.core LIMIT 2) z) = 1
          AND (SELECT count(*) FROM (SELECT 1 FROM xref_names u WHERE u.kind = t.kind AND u.core = t.core LIMIT 2) z) = 1"""
    added += _both_ways(conn, sel2, {}, linker)
    return added, newest


# --- people: a dataset's person records to the one person page with that full name in that state -----------------

PERSON_HOW = "same full name with a middle name or initial, one person page, in that person's states"
PERSON_SQL = """
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (s.key, p.id) %(kind)s, s.key, s.name, s.state, 'person', p.id::text, p.display_name, %(how)s, %(linker)s
    FROM xp s JOIN person_clusters p ON p.name_norm = s.name_norm
    WHERE NOT coalesce(p.is_institution, false) AND array_length(string_to_array(s.name_norm, ' '), 1) >= 3
      AND s.state = ANY(p.states)
      AND (SELECT count(*) FROM (SELECT 1 FROM person_clusters p2 WHERE p2.name_norm = s.name_norm LIMIT 2) z) = 1
    ON CONFLICT DO NOTHING"""


def _people_batch(conn, sql: str, params) -> None:
    conn.execute("DROP TABLE IF EXISTS xp")
    conn.execute(f"CREATE TEMP TABLE xp ON COMMIT DROP AS {sql}", params)
    conn.execute("ANALYZE xp")


def _person_linker(kind: str, how: str, batch_sql: str):
    """batch_sql selects key, name, name_norm, state, ck (the cursor column) for rows after %(cur)s, in ck order, LIMIT %(n)s."""
    def run(conn, since, limit, linker):
        cur = since if since not in (None, "", EPOCH) else ""
        _people_batch(conn, batch_sql, {"cur": cur, "n": limit})
        r = conn.execute("SELECT count(*), max(ck) FROM xp").fetchone()
        if not r[0]:
            return 0, None
        n = conn.execute(PERSON_SQL, {"kind": kind, "how": how, "linker": linker}).rowcount
        return n, str(r[1])
    return run


l_sec_insider_person = _person_linker("sec_insider", PERSON_HOW, """
    SELECT ltrim(owner_cik, '0') AS key, owner_name AS name, name_norm, state, owner_cik AS ck FROM (
        SELECT DISTINCT ON (owner_cik) owner_cik, owner_name, name_norm, state FROM sec_insider_owners
        WHERE owner_cik > %(cur)s AND state ~ '^[A-Z]{2}$' AND name_norm IS NOT NULL ORDER BY owner_cik, accession DESC) a
    ORDER BY owner_cik LIMIT %(n)s""")
l_inventor_person = _person_linker("pat_inventor", PERSON_HOW + " (a state the inventor filed from)", """
    SELECT inventor_id AS key, name, name_norm, s AS state, inventor_id AS ck FROM (
        SELECT inventor_id, name, name_norm, states FROM pat_inventor_people
        WHERE inventor_id > %(cur)s AND name_norm IS NOT NULL AND states <> '{}' ORDER BY inventor_id LIMIT %(n)s) p, unnest(p.states) s""")
l_adv_person = _person_linker("adv_person", PERSON_HOW, """
    SELECT id::text AS key, name, name_norm, state, lpad(id::text, 12, '0') AS ck FROM adv_people
    WHERE lpad(id::text, 12, '0') > %(cur)s AND state ~ '^[A-Z]{2}$' AND name_norm IS NOT NULL ORDER BY id LIMIT %(n)s""")
l_formd_person = _person_linker("formd_party", PERSON_HOW, """
    SELECT id::text AS key, name, name_norm, state, lpad(id::text, 12, '0') AS ck FROM sec_formd_parties
    WHERE kind = 'person' AND lpad(id::text, 12, '0') > %(cur)s AND state ~ '^[A-Z]{2}$' AND name_norm IS NOT NULL ORDER BY id LIMIT %(n)s""")
l_fec_donor_person = _person_linker("fec_donor", PERSON_HOW + " (one FEC donor ZIP with that name in the state)", """
    SELECT zip5 || ':' || name_norm AS key, name, name_norm, state, name_norm AS ck FROM (
        SELECT name_norm, state, min(zip5) AS zip5, min(name) AS name FROM fec_donor_totals
        WHERE name_norm > %(cur)s AND state ~ '^[A-Z]{2}$' AND zip5 IS NOT NULL AND array_length(string_to_array(name_norm, ' '), 1) >= 3
        GROUP BY name_norm, state HAVING count(DISTINCT zip5) = 1 ORDER BY name_norm LIMIT %(n)s) d""")


# --- imports: links the dataset loaders already made, into the one table ----------------------------------------

def _import(sql: str, tables: tuple[str, ...]):
    def run(conn, since, limit, linker):
        if not all(_has(conn, t) for t in tables):
            return 0, None
        return conn.execute(sql, {"linker": linker}).rowcount, "done"
    return run


l_import_sec_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.key, l.cluster_id) 'sec_insider', ltrim(l.key, '0'), o.owner_name, o.state, 'person', l.cluster_id::text, p.display_name,
           'matched by the SEC insider loader: full name and state (FUZZY)', %(linker)s
    FROM sec_person_links l JOIN person_clusters p ON p.id = l.cluster_id
    JOIN LATERAL (SELECT owner_name, state FROM sec_insider_owners o WHERE o.owner_cik = l.key LIMIT 1) o ON true
    WHERE l.source = 'insider' ON CONFLICT DO NOTHING""", ("sec_person_links", "sec_insider_owners"))
l_import_formd_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (f.id, f.cluster_id) 'formd_party', f.id::text, f.name, f.state, 'person', f.cluster_id::text, p.display_name,
           'matched by the Form D loader: full name and state (FUZZY)', %(linker)s
    FROM sec_formd_parties f JOIN person_clusters p ON p.id = f.cluster_id WHERE f.cluster_id IS NOT NULL ON CONFLICT DO NOTHING""",
    ("sec_formd_parties",))
l_import_adv_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (a.id, a.cluster_id) 'adv_person', a.id::text, a.name, a.state, 'person', a.cluster_id::text, p.display_name,
           'matched by the Form ADV loader: full name and state (FUZZY)', %(linker)s
    FROM adv_people a JOIN person_clusters p ON p.id = a.cluster_id WHERE a.cluster_id IS NOT NULL ON CONFLICT DO NOTHING""", ("adv_people",))
l_import_op_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.recipient_key, l.cluster_id) 'op_recipient', l.recipient_key, r.name, r.state, 'person', l.cluster_id::text, p.display_name,
           'matched by the Open Payments loader: ' || coalesce(l.how, 'name and state') || ' (FUZZY)', %(linker)s
    FROM op_person_links l JOIN op_recipients r ON r.key = l.recipient_key JOIN person_clusters p ON p.id = l.cluster_id ON CONFLICT DO NOTHING""",
    ("op_person_links", "op_recipients"))
l_import_lda_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.lobbyist_id, l.cluster_id) 'lda_lobbyist', l.lobbyist_id::text, a.name, NULL, 'person', l.cluster_id::text, p.display_name,
           'matched by the lobbying loader: full name (FUZZY)', %(linker)s
    FROM lda_person_links l JOIN person_clusters p ON p.id = l.cluster_id
    JOIN LATERAL (SELECT name FROM lda_activity_lobbyists a WHERE a.lobbyist_id = l.lobbyist_id LIMIT 1) a ON true ON CONFLICT DO NOTHING""",
    ("lda_person_links", "lda_activity_lobbyists"))
l_import_payroll_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.state, l.label, l.name_norm, l.cluster_id) 'payroll_person', l.state || ':' || l.label || ':' || l.name_norm,
           coalesce(l.evidence->>'payroll_name', l.name_norm), l.state, 'person', l.cluster_id::text, p.display_name,
           'matched by the payroll loader: ' || coalesce(l.evidence->>'rule', 'same full name') || ' at the linked nonprofit (' || l.match || ')', %(linker)s
    FROM payroll_person_links l JOIN person_clusters p ON p.id = l.cluster_id ON CONFLICT DO NOTHING""", ("payroll_person_links",))
l_import_fara_people = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.short_form_id, l.cluster_id) 'fara_person', l.short_form_id::text, f.name, f.state, 'person', l.cluster_id::text, p.display_name,
           'matched by the FARA loader: ' || coalesce(l.how, 'name and state') || ' (FUZZY)', %(linker)s
    FROM fara_person_links l JOIN fara_short_forms f ON f.id = l.short_form_id JOIN person_clusters p ON p.id = l.cluster_id ON CONFLICT DO NOTHING""",
    ("fara_person_links", "fara_short_forms"))
l_import_recall_links = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.firm_id, k.dst_kind, l.key) 'recallfirm', l.firm_id, f.name, f.state, k.dst_kind, l.key, l.name,
           'matched by the recalls loader: normalized name, and state where both have one (FUZZY)', %(linker)s
    FROM food_recall_links l JOIN food_recall_firms f ON f.firm_id = l.firm_id
    JOIN (VALUES ('sec', 'sec'), ('fed', 'fed'), ('lobbying', 'lda_client'), ('org', 'org'), ('pac', 'fec_committee')) k(kind, dst_kind) ON k.kind = l.kind
    ON CONFLICT DO NOTHING""", ("food_recall_links", "food_recall_firms"))
l_import_sec_company_links = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (l.cik, k.dst_kind, l.key) 'sec', ltrim(l.cik, '0'), n.name, NULL, k.dst_kind, l.key, l.name,
           'matched by the SEC loader: company name (FUZZY)', %(linker)s
    FROM sec_company_links l JOIN (VALUES ('lobbying', 'lda_client'), ('pac', 'fec_committee')) k(kind, dst_kind) ON k.kind = l.kind
    LEFT JOIN LATERAL (SELECT name FROM sec_fin_subs s WHERE s.cik = l.cik ORDER BY filed DESC LIMIT 1) n ON true
    ON CONFLICT DO NOTHING""", ("sec_company_links",))
l_import_college_orgs = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (c.unitid, c.ein) 'college', c.unitid::text, k.name, k.state, 'org', c.ein, o.name,
           'matched by the colleges loader: ' || coalesce(c.relation, 'related') || ' (' || coalesce(c.match, 'name') || ')', %(linker)s
    FROM college_orgs c JOIN colleges k ON k.unitid = c.unitid JOIN organizations o ON o.ein = c.ein ON CONFLICT DO NOTHING""",
    ("college_orgs", "colleges"))
l_import_pension_funds = _import("""
    INSERT INTO xlinks (src_kind, src_key, src_name, src_state, dst_kind, dst_key, dst_name, how, linker)
    SELECT DISTINCT ON (m.pension, m.fund_name, m.kind, m.key) 'pension_fund', m.pension || ':' || m.fund_name, m.fund_name, NULL,
           CASE m.kind WHEN 'adv_fund' THEN 'adv_fund' WHEN 'formd' THEN 'formd_offering' ELSE m.kind END, m.key, m.fund_name,
           'matched by the pensions loader: fund name (' || coalesce(m.confidence, 'FUZZY') || ')', %(linker)s
    FROM pension_fund_matches m WHERE m.key IS NOT NULL ON CONFLICT DO NOTHING""", ("pension_fund_matches",))


# --- interests: records to category keys (dst_kind 'interest'), peers share a key ---------------------------------

# A common topic vocabulary across the taxonomies, so an NTEE health charity, a client lobbying on health issues,
# a biotechnology Form D issuer and a pharmaceutical IPO registrant share the interest key topic:health.
NTEE_TOPIC = {"A": "arts", "B": "education", "C": "environment", "D": "animals", "E": "health", "F": "mental_health",
              "G": "health", "H": "medical_research", "I": "crime_legal", "J": "employment", "K": "food_agriculture",
              "L": "housing", "M": "public_safety", "N": "recreation_sports", "O": "youth", "P": "human_services",
              "Q": "international", "R": "civil_rights", "S": "community", "T": "philanthropy", "U": "science",
              "V": "social_science", "W": "public_policy", "X": "religion", "Y": "mutual_benefit"}
LDA_TOPIC = {"ANI": "animals", "ART": "arts", "EDU": "education", "ENV": "environment", "HCR": "health", "MMM": "health",
             "MED": "health", "PHA": "health", "FOO": "food_agriculture", "AGR": "food_agriculture", "HOU": "housing",
             "HOM": "public_safety", "LAW": "crime_legal", "CIV": "civil_rights", "REL": "religion", "SCI": "science",
             "SPO": "recreation_sports", "VET": "veterans", "WEL": "human_services", "FAM": "human_services",
             "DIS": "public_safety", "ENG": "energy", "FUE": "energy", "FIN": "finance", "BAN": "finance", "INS": "insurance",
             "TAX": "taxes", "TRD": "trade", "TRA": "transportation", "AVI": "transportation", "RRR": "transportation",
             "MAR": "transportation", "TEC": "technology", "CPI": "technology", "CPT": "intellectual_property",
             "DEF": "defense", "BUD": "budget", "LBR": "labor", "IMM": "immigration", "FOR": "international",
             "RES": "real_estate", "CON": "construction", "MAN": "manufacturing", "RET": "retail", "TOU": "tourism",
             "URB": "community", "ECN": "economy", "SMB": "small_business", "CSP": "consumer_safety", "ALC": "alcohol_tobacco",
             "TOB": "alcohol_tobacco", "GAM": "gaming", "MIA": "media", "UNM": "unemployment", "WAS": "waste", "NAT": "natural_resources",
             "CHM": "chemicals", "UTI": "utilities", "TEL": "telecommunications", "POS": "postal", "RET": "retirement",
             "GOV": "government", "AER": "aerospace", "ACC": "accounting", "ADV": "advertising", "AUT": "automotive",
             "BEV": "beverages", "CAW": "clean_air_water", "CDT": "commodities", "COM": "communications", "FIR": "firearms",
             "INT": "intelligence", "HCR": "health", "IND": "indian_affairs", "MON": "minting", "ROD": "roads", "SCI": "science",
             "TRU": "trucking", "WEL": "human_services", "APP": "apparel", "ART": "arts", "BNK": "finance", "DOC": "district_of_columbia",
             "EDU": "education", "ENV": "environment", "FAM": "human_services", "HOU": "housing", "LAW": "crime_legal",
             "MMM": "health", "NAT": "natural_resources", "RRR": "transportation", "SPO": "recreation_sports"}
FORMD_TOPIC = {"Biotechnology": "medical_research", "Health Insurance": "health", "Hospitals & Physicians": "health",
               "Pharmaceuticals": "health", "Other Health Care": "health", "Energy Conservation": "energy", "Coal Mining": "energy",
               "Electric Utilities": "energy", "Oil & Gas": "energy", "Other Energy": "energy", "Commercial": "real_estate",
               "Residential": "real_estate", "REITS & Finance": "real_estate", "Construction": "construction",
               "Other Real Estate": "real_estate", "Commercial Banking": "finance", "Insurance": "insurance", "Investing": "finance",
               "Investment Banking": "finance", "Other Banking & Financial Services": "finance", "Agriculture": "food_agriculture",
               "Restaurants": "food_agriculture", "Business Services": "technology", "Computers": "technology",
               "Telecommunications": "telecommunications", "Other Technology": "technology", "Airlines & Airports": "transportation",
               "Travel & Tourism": "tourism", "Lodging & Conventions": "tourism", "Tourism & Travel Services": "tourism",
               "Manufacturing": "manufacturing", "Retailing": "retail", "Environmental Services": "environment"}
SIC_TOPIC = [("01", "food_agriculture"), ("02", "food_agriculture"), ("07", "food_agriculture"), ("10", "natural_resources"),
             ("12", "energy"), ("13", "energy"), ("15", "construction"), ("16", "construction"), ("17", "construction"),
             ("20", "food_agriculture"), ("28", "health"), ("283", "health"), ("35", "manufacturing"), ("36", "technology"),
             ("37", "transportation"), ("38", "technology"), ("40", "transportation"), ("42", "transportation"), ("44", "transportation"),
             ("45", "transportation"), ("48", "telecommunications"), ("49", "energy"), ("50", "retail"), ("52", "retail"), ("53", "retail"),
             ("54", "retail"), ("56", "retail"), ("57", "retail"), ("58", "food_agriculture"), ("59", "retail"), ("60", "finance"),
             ("61", "finance"), ("62", "finance"), ("63", "insurance"), ("64", "insurance"), ("65", "real_estate"), ("67", "finance"),
             ("70", "tourism"), ("73", "technology"), ("737", "technology"), ("79", "recreation_sports"), ("80", "health"), ("82", "education"),
             ("83", "human_services"), ("87", "science"), ("8731", "medical_research")]
TOPIC_LABEL = {"mental_health": "Mental health", "medical_research": "Medical research", "crime_legal": "Crime and legal",
               "food_agriculture": "Food and agriculture", "public_safety": "Public safety", "recreation_sports": "Recreation and sports",
               "human_services": "Human services", "civil_rights": "Civil rights", "social_science": "Social science",
               "public_policy": "Public policy", "mutual_benefit": "Mutual benefit", "real_estate": "Real estate",
               "intellectual_property": "Intellectual property", "small_business": "Small business", "consumer_safety": "Consumer safety",
               "alcohol_tobacco": "Alcohol and tobacco", "natural_resources": "Natural resources", "clean_air_water": "Clean air and water",
               "indian_affairs": "Indian affairs", "district_of_columbia": "District of Columbia"}


def topic_label(t: str) -> str:
    return TOPIC_LABEL.get(t, t.replace("_", " ").capitalize())


def _topic_rows(conn, pairs, linker: str) -> int:
    """pairs: (src_kind, src_key, src_name, src_state, topic, how). Writes interest rows topic:<t>."""
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS xi (src_kind text, src_key text, src_name text, src_state text, topic text, how text) ON COMMIT DROP")
    conn.execute("TRUNCATE xi")
    with conn.cursor() as cur:
        db.copy_rows(cur, "xi", ["src_kind", "src_key", "src_name", "src_state", "topic", "how"], pairs)
    labels = [(t, topic_label(t)) for t in set(NTEE_TOPIC.values()) | set(LDA_TOPIC.values()) | set(FORMD_TOPIC.values()) | {t for _, t in SIC_TOPIC}]
    return conn.execute(INSERT + """SELECT DISTINCT xi.src_kind, xi.src_key, xi.src_name, xi.src_state, 'interest', 'topic:' || xi.topic, l.label, xi.how, %(linker)s
                                    FROM xi LEFT JOIN unnest(%(t)s::text[], %(l)s::text[]) l(topic, label) ON l.topic = xi.topic
                                    ON CONFLICT DO NOTHING""", {"linker": linker, "t": [a for a, _ in labels], "l": [b for _, b in labels]}).rowcount


def l_ntee(conn, since, limit, linker):
    """A nonprofit to its NTEE code (one code everywhere: coalesce(nn.ntee_code, o.ntee)) and to the code's topic."""
    if not _has(conn, "nonprofit_ntee"):
        return 0, None
    cur = since if since not in (None, EPOCH) else ""
    rows = conn.execute("""SELECT o.ein, o.name, o.state, upper(left(coalesce(nn.ntee_code, o.ntee), 3)) AS code, t.name
                           FROM organizations o LEFT JOIN nonprofit_ntee nn ON nn.ein = o.ein
                           LEFT JOIN ntee_taxonomy t ON t.code = upper(left(coalesce(nn.ntee_code, o.ntee), 3))
                           WHERE o.ein > %s AND upper(coalesce(nn.ntee_code, o.ntee)) ~ '^[A-Z][0-9]{2}' ORDER BY o.ein LIMIT %s""", (cur, limit)).fetchall()
    if not rows:
        return 0, None
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS xi2 (ein text, name text, state text, code text, cname text) ON COMMIT DROP")
    conn.execute("TRUNCATE xi2")
    with conn.cursor() as c:
        db.copy_rows(c, "xi2", ["ein", "name", "state", "code", "cname"], rows)
    n = conn.execute(INSERT + """SELECT 'org', ein, name, state, 'interest', 'ntee:' || code, coalesce(cname, code),
                                        'same NTEE code ' || code || coalesce(' (' || cname || ')', ''), %s FROM xi2 ON CONFLICT DO NOTHING""",
                     (linker,)).rowcount
    n += _topic_rows(conn, ((("org", r[0], r[1], r[2], NTEE_TOPIC[r[3][0]], f"NTEE major group {r[3][0]}: {topic_label(NTEE_TOPIC[r[3][0]])}"))
                            for r in rows if r[3][0] in NTEE_TOPIC), linker)
    return n, rows[-1][0]


def l_furp_fields(conn, since, limit, linker):
    """A nonprofit to its FURP topics (research.org_fields, from its 990 text)."""
    if not _has(conn, "research.org_fields"):
        return 0, None
    cur = since if since not in (None, EPOCH) else ""
    n = conn.execute(INSERT + """SELECT 'org', f.ein, o.name, o.state, 'interest', 'field:' || f.field, f.field,
                                        'same FURP topic (' || replace(f.field, ':', ': ') || ', from its 990 text)', %s
                                 FROM (SELECT ein, field FROM research.org_fields WHERE ein > %s ORDER BY ein LIMIT %s) f
                                 JOIN organizations o ON o.ein = f.ein ON CONFLICT DO NOTHING""", (linker, cur, limit)).rowcount
    last = conn.execute("SELECT max(ein) FROM (SELECT ein FROM research.org_fields WHERE ein > %s ORDER BY ein LIMIT %s) f", (cur, limit)).fetchone()[0]
    return n, last


def l_lda_issues(conn, since, limit, linker):
    """A lobbying client to the issues it lobbied on (the House/Senate issue codes) and their topics."""
    if not _has(conn, "lda_activities"):
        return 0, None
    cur = int(since) if since not in (None, EPOCH, "") else 0
    rows = conn.execute("""SELECT f.client_id, min(f.client_name), min(f.client_state), a.issue_code, min(a.issue)
                           FROM (SELECT DISTINCT client_id FROM lda_filings WHERE client_id > %s ORDER BY client_id LIMIT %s) c
                           JOIN lda_filings f ON f.client_id = c.client_id JOIN lda_activities a ON a.filing_uuid = f.filing_uuid
                           WHERE a.issue_code IS NOT NULL GROUP BY f.client_id, a.issue_code""", (cur, limit)).fetchall()
    last = conn.execute("SELECT max(client_id) FROM (SELECT DISTINCT client_id FROM lda_filings WHERE client_id > %s ORDER BY client_id LIMIT %s) c",
                        (cur, limit)).fetchone()[0]
    if not rows:
        return 0, (str(last) if last else None)
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS xi3 (key text, name text, state text, code text, issue text) ON COMMIT DROP")
    conn.execute("TRUNCATE xi3")
    with conn.cursor() as c:
        db.copy_rows(c, "xi3", ["key", "name", "state", "code", "issue"], ((str(r[0]), r[1], r[2], r[3], r[4]) for r in rows))
    n = conn.execute(INSERT + """SELECT 'lda_client', key, name, state, 'interest', 'lda:' || code, coalesce(issue, code),
                                        'lobbied on the same issue (' || coalesce(issue, code) || ')', %s FROM xi3 ON CONFLICT DO NOTHING""",
                     (linker,)).rowcount
    n += _topic_rows(conn, (("lda_client", str(r[0]), r[1], r[2], LDA_TOPIC[r[3]], f"lobbying issue {r[3]}: {topic_label(LDA_TOPIC[r[3]])}")
                            for r in rows if r[3] in LDA_TOPIC), linker)
    return n, str(last)


def l_formd_industry(conn, since, limit, linker):
    """A Form D issuer to its industry group's topic (pooled investment funds and 'Other' carry no interest)."""
    if not _has(conn, "sec_formd_offerings"):
        return 0, None
    cur = since if since not in (None, EPOCH) else ""
    rows = conn.execute("""SELECT DISTINCT ON (cik) cik, issuer_name, state, industry FROM sec_formd_offerings
                           WHERE cik > %s AND industry IS NOT NULL ORDER BY cik, latest_date DESC LIMIT %s""", (cur, limit)).fetchall()
    if not rows:
        return 0, None
    n = _topic_rows(conn, (("formd", r[0], r[1], r[2], FORMD_TOPIC[r[3]], f"Form D industry group: {r[3]}") for r in rows if r[3] in FORMD_TOPIC), linker)
    n += conn.execute(INSERT + """SELECT 'formd', cik, issuer_name, state, 'interest', 'formd_industry:' || industry, industry,
                                         'same Form D industry group (' || industry || ')', %s
                                  FROM (SELECT DISTINCT ON (cik) cik, issuer_name, state, industry FROM sec_formd_offerings
                                        WHERE cik > %s AND industry IS NOT NULL AND industry NOT IN ('Other', 'Pooled Investment Fund')
                                        ORDER BY cik, latest_date DESC LIMIT %s) f ON CONFLICT DO NOTHING""", (linker, cur, limit)).rowcount
    return n, rows[-1][0]


def l_ipo_sic(conn, since, limit, linker):
    """An IPO registrant to its SIC industry and the SIC's topic."""
    if not _has(conn, "ipo_companies"):
        return 0, None
    cur = since if since not in (None, EPOCH) else ""
    rows = conn.execute("""SELECT cik, name, state, sic, sic_desc FROM ipo_companies WHERE cik > %s AND sic IS NOT NULL AND sic <> '6770'
                           ORDER BY cik LIMIT %s""", (cur, limit)).fetchall()
    if not rows:
        return 0, None
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS xi4 (key text, name text, state text, sic text, sdesc text) ON COMMIT DROP")
    conn.execute("TRUNCATE xi4")
    with conn.cursor() as c:
        db.copy_rows(c, "xi4", ["key", "name", "state", "sic", "sdesc"], rows)
    n = conn.execute(INSERT + """SELECT 'ipo_company', key, name, state, 'interest', 'sic:' || sic, coalesce(sdesc, sic),
                                        'same SIC industry code ' || sic || coalesce(' (' || sdesc || ')', ''), %s FROM xi4 ON CONFLICT DO NOTHING""",
                     (linker,)).rowcount

    def topic(sic):
        best = None
        for prefix, t in SIC_TOPIC:
            if sic.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
                best = (prefix, t)
        return best[1] if best else None
    n += _topic_rows(conn, (("ipo_company", r[0], r[1], r[2], topic(r[3]), f"SIC code {r[3]}: {topic_label(topic(r[3]))}") for r in rows if topic(r[3])), linker)
    return n, rows[-1][0]


def l_patent_class(conn, since, limit, linker):
    """A patent assignee to the CPC subclasses of its patents (rebuild only: a join over 10 million CPC rows)."""
    if not _has(conn, "pat_cpc") or not _has(conn, "pat_assignee_orgs"):
        return 0, None
    cur = since if since not in (None, EPOCH) else ""
    ids = conn.execute("SELECT assignee_id FROM pat_assignee_orgs WHERE assignee_id > %s AND NOT coalesce(is_person, false) ORDER BY assignee_id LIMIT %s",
                       (cur, limit)).fetchall()
    if not ids:
        return 0, None
    n = conn.execute(INSERT + """SELECT 'pat_assignee', a.assignee_id, min(o.name), min(o.state), 'interest', 'cpc:' || c.subclass, min(coalesce(t.title, c.subclass)),
                                        'patents in the same CPC subclass ' || c.subclass || min(coalesce(' (' || t.title || ')', '')), %s
                                 FROM unnest(%s::text[]) i(id) JOIN pat_assignee_orgs o ON o.assignee_id = i.id
                                 JOIN pat_assignees a ON a.assignee_id = i.id JOIN pat_cpc c ON c.patent_id = a.patent_id
                                 LEFT JOIN pat_cpc_titles t ON t.subclass = c.subclass
                                 GROUP BY a.assignee_id, c.subclass ON CONFLICT DO NOTHING""", (linker, [r[0] for r in ids])).rowcount
    return n, ids[-1][0]


def l_fed_program(conn, since, limit, linker):
    """A federal award recipient to the assistance programs (CFDA) it was funded under (rebuild only: usa_awards is 138M rows;
    a keyed pass over recipients, each recipient's awards by the recipient_uei index)."""
    if not _has(conn, "usa_awards"):
        return 0, None
    cur = since if since not in (None, EPOCH) else ""
    ueis = conn.execute("SELECT uei FROM fed_recipient_names WHERE uei > %s ORDER BY uei LIMIT %s", (cur, limit)).fetchall()
    if not ueis:
        return 0, None
    n = conn.execute(INSERT + """SELECT 'fed', a.recipient_uei, min(a.recipient_name), min(a.state), 'interest', 'cfda:' || a.program_code,
                                        min(a.program_title), 'funded under the same federal program ' || a.program_code || min(coalesce(' (' || a.program_title || ')', '')), %s
                                 FROM usa_awards a WHERE a.recipient_uei = ANY(%s) AND a.program_code IS NOT NULL AND a.program_code <> ''
                                 GROUP BY a.recipient_uei, a.program_code ON CONFLICT DO NOTHING""", (linker, [r[0] for r in ueis])).rowcount
    return n, ueis[-1][0]


class Linker:
    def __init__(self, name, fn, src, dst, rule, *, sweep=True, by="names", batch=BATCH):
        self.name, self.fn, self.src, self.dst, self.rule, self.sweep, self.by, self.batch = name, fn, src, dst, rule, sweep, by, batch


LINKERS = [
    Linker("ein", l_ein, "every kind with an EIN", "org, fed, biz, lda_client, lda_registrant, f5500_sponsor, college, ipo_company, sl_issuer",
           "the same EIN (EXACT)"),
    Linker("cik", l_cik, "sec, formd, ipo_company, ipo_underwriter, sl_issuer", "the same kinds", "the same SEC CIK (EXACT)"),
    Linker("crd", l_crd, "adv, ipo_underwriter", "adv, ipo_underwriter", "the same CRD number (EXACT)"),
    Linker("name_state", l_name_state, "every collected kind", "every collected kind and biz",
           "the same name core and state; one record per name and state in nonprofits, Form D, advisers, colleges, sponsors, recall firms, "
           "Open Payments, IPOs, patents, trademarks, contractors; up to 12 registrations, UEIs, lobbying ids, PACs or FARA registrations"),
    Linker("name_city", l_name_city, "every collected kind", "the one-per-name kinds",
           "a name shared in the state but held by one record in the city"),
    Linker("address", l_address, "every collected kind with a street", "the same",
           "the same street address and ZIP code with a different name, at most two names at the address (FUZZY)"),
    Linker("sec_name", l_sec_name, "every collected kind", "sec", "an SEC filer's name core, unique among filers and in the other kind (no state on filers)"),
    Linker("person_sec_insider", l_sec_insider_person, "sec_insider", "person", "full name with a middle part, one person page, in that person's states", by="key"),
    Linker("person_inventor", l_inventor_person, "pat_inventor", "person", "full name with a middle part, one person page, a state the inventor filed from", by="key"),
    Linker("person_adv", l_adv_person, "adv_person", "person", "full name with a middle part, one person page, in that person's states", by="key"),
    Linker("person_formd", l_formd_person, "formd_party", "person", "full name with a middle part, one person page, in that person's states", by="key"),
    Linker("person_fec_donor", l_fec_donor_person, "fec_donor", "person", "full name with a middle part, one donor ZIP in the state, one person page there", by="key"),
    Linker("import_sec_people", l_import_sec_people, "sec_insider", "person", "the SEC loader's person matches (sec_person_links)", by="import"),
    Linker("import_formd_people", l_import_formd_people, "formd_party", "person", "the Form D loader's person matches", by="import"),
    Linker("import_adv_people", l_import_adv_people, "adv_person", "person", "the Form ADV loader's person matches", by="import"),
    Linker("import_op_people", l_import_op_people, "op_recipient", "person", "the Open Payments loader's person matches", by="import"),
    Linker("import_lda_people", l_import_lda_people, "lda_lobbyist", "person", "the lobbying loader's person matches", by="import"),
    Linker("import_payroll_people", l_import_payroll_people, "payroll_person", "person", "the payroll loader's person matches", by="import"),
    Linker("import_fara_people", l_import_fara_people, "fara_person", "person", "the FARA loader's person matches", by="import"),
    Linker("import_recall_links", l_import_recall_links, "recallfirm", "sec, fed, lda_client, org, fec_committee", "the recalls loader's firm matches", by="import"),
    Linker("import_sec_company_links", l_import_sec_company_links, "sec", "lda_client, fec_committee", "the SEC loader's company matches", by="import"),
    Linker("import_college_orgs", l_import_college_orgs, "college", "org", "the colleges loader's nonprofit matches (college_orgs)", by="import"),
    Linker("import_pension_funds", l_import_pension_funds, "pension_fund", "adv_fund, formd_offering", "the pensions loader's fund matches", by="import"),
    Linker("interest_ntee", l_ntee, "org", "interest", "the organization's NTEE code and its major group's topic", by="key", batch=50000),
    Linker("interest_furp", l_furp_fields, "org", "interest", "the organization's FURP topics (from its 990 text)", by="key", batch=50000),
    Linker("interest_lda", l_lda_issues, "lda_client", "interest", "the issues a client lobbied on, and their topics", by="key", batch=2000),
    Linker("interest_formd", l_formd_industry, "formd", "interest", "a Form D issuer's industry group and its topic", by="key", batch=20000),
    Linker("interest_sic", l_ipo_sic, "ipo_company", "interest", "an IPO registrant's SIC code and its topic", by="key", batch=20000),
    Linker("interest_patent_class", l_patent_class, "pat_assignee", "interest", "the CPC subclasses of an assignee's patents", by="key", batch=2000, sweep=False),
    Linker("interest_fed_program", l_fed_program, "fed", "interest", "the federal assistance programs (CFDA) a recipient was funded under", by="key", batch=1000, sweep=False),
]
BY_NAME = {k.name: k for k in LINKERS}


def run_linker(conn, k: Linker, *, reset: bool, deadline: float, timeout: str, max_batches=None) -> int:
    st = get_state(conn, k.name)
    cursor = None if reset else st.get("cursor")
    if k.by == "import":
        if not reset and cursor == "done" and st.get("last_run") and (dt.datetime.now(dt.timezone.utc) - st["last_run"]).days < 7:
            return 0            # imports re-read their source tables weekly (and on every rebuild)
        cursor = None
    since = cursor or EPOCH
    t0, added, batches = time.time(), 0, 0
    while time.time() < deadline and (max_batches is None or batches < max_batches):
        if _rebuilding(conn):
            _log(f"{k.name}: xlinks rebuild in progress, pausing")
            break
        try:
            conn.execute(f"SET statement_timeout = '{timeout}'")
            n, newest = k.fn(conn, since, k.batch, k.name)
        except Exception as ex:  # noqa: BLE001 - one batch; the state keeps the error and the next sweep retries
            conn.rollback()
            set_state(conn, k.name, src_kind=k.src, dst_kinds=k.dst, rule=k.rule, cursor=since, added=added,
                      seconds=time.time() - t0, error=f"{type(ex).__name__}: {str(ex)[:300]}")
            conn.commit()
            _log(f"{k.name}: batch failed at cursor {since!r}: {type(ex).__name__}: {str(ex)[:200]}")
            return added
        added += n
        batches += 1
        if newest is None or newest == since:
            since = newest or since
            break
        since = newest
        set_state(conn, k.name, src_kind=k.src, dst_kinds=k.dst, rule=k.rule, cursor=since, added=n, seconds=time.time() - t0, full=reset)
        conn.commit()
        if k.by == "import":
            break
    conn.execute("SET statement_timeout = 0")
    set_state(conn, k.name, src_kind=k.src, dst_kinds=k.dst, rule=k.rule, cursor=since, added=0, seconds=time.time() - t0, full=reset)
    conn.commit()
    _log(f"{k.name}: {added:,} links added in {batches} batches, {time.time() - t0:.0f}s (cursor {since!r})")
    return added


def refresh_counts(conn) -> None:
    conn.execute("SET statement_timeout = '600s'")
    conn.execute("DELETE FROM xref_counts")
    conn.execute("""INSERT INTO xref_counts SELECT src_kind, dst_kind, coalesce(linker, 'xlinks'), min(how), count(*), count(DISTINCT src_key), now()
                    FROM xlinks GROUP BY 1, 2, 3""")
    conn.execute("SET statement_timeout = 0")
    conn.commit()


def sweep(*, full: bool = False, only: list[str] | None = None, budget: int = SWEEP_BUDGET, max_batches=None) -> dict:
    """The incremental pass (or, with full=True, the rebuild: every cursor reset, no budget)."""
    t0 = time.time()
    deadline = t0 + (10 ** 9 if full else budget)
    timeout = "900s" if full else "180s"
    totals = {}
    with db.connect() as conn:
        conn.execute("SET lock_timeout = '10s'")
        ensure_schema(conn)
        if _rebuilding(conn):
            _log("xlinks rebuild (xlinks_new) in progress: nothing to do now")
            return totals
        for name, kind, table, fn, in_sweep in COLLECTORS:
            if only and name not in only and kind not in only:
                continue
            if not full and not in_sweep:
                continue
            if time.time() > deadline:
                break
            totals[name] = run_collector(conn, name, kind, table, fn, reset=full, deadline=deadline, timeout=timeout, max_batches=max_batches)
        for k in LINKERS:
            if only and k.name not in only:
                continue
            if not full and not k.sweep:
                continue
            if time.time() > deadline:
                _log(f"budget of {budget}s spent; the next sweep continues")
                break
            totals[k.name] = run_linker(conn, k, reset=full, deadline=deadline, timeout=timeout, max_batches=max_batches)
        if time.time() < deadline + 600:
            refresh_counts(conn)
    _log(f"{'rebuild' if full else 'sweep'} done in {time.time() - t0:.0f}s: " +
         ", ".join(f"{k}={v:,}" for k, v in totals.items() if v))
    return totals


def sample(name: str, n: int = 50) -> list[tuple]:
    with db.connect() as conn:
        rows = conn.execute("""SELECT src_kind, src_name, src_state, dst_kind, dst_name, how FROM xlinks TABLESAMPLE BERNOULLI (3)
                               WHERE linker = %s ORDER BY random() LIMIT %s""", (name, n)).fetchall()
        if len(rows) < n:
            rows = conn.execute("""SELECT src_kind, src_name, src_state, dst_kind, dst_name, how FROM xlinks WHERE linker = %s
                                   ORDER BY random() LIMIT %s""", (name, n)).fetchall()
    for r in rows:
        print(f"{r[0]:>16} | {(r[1] or '')[:45]:<45} | {r[2] or '  '} | {r[3]:>14} | {(r[4] or '')[:45]:<45} | {r[5][:60]}")
    return rows


def status() -> None:
    with db.connect() as conn:
        for r in conn.execute("""SELECT linker, last_run, cursor, rows_added, total_added, seconds, runs, error FROM xref_state
                                 ORDER BY linker""").fetchall():
            print(f"{r[0]:<28} last {r[1].strftime('%m-%d %H:%M') if r[1] else '-':<12} cursor {str(r[2])[:24]:<24} "
                  f"+{r[3] or 0:>8,} total {r[4] or 0:>11,} {r[5] or 0:>7.0f}s runs {r[6]:>4} {('ERR ' + r[7][:60]) if r[7] else ''}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FURP cross-referencing engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sweep", help="incremental pass over new records (any time)")
    s.add_argument("--only", nargs="*", help="linker or collector names")
    s.add_argument("--budget", type=int, default=SWEEP_BUDGET)
    s.add_argument("--max-batches", type=int, help="batches per collector and linker (a smoke test)")
    r = sub.add_parser("rebuild", help="every record again, off peak")
    r.add_argument("--linker", nargs="*", help="linker names (default: everything)")
    p = sub.add_parser("sample")
    p.add_argument("linker")
    p.add_argument("--n", type=int, default=50)
    sub.add_parser("status")
    a = ap.parse_args(argv)
    if a.cmd == "sweep":
        sweep(only=a.only, budget=a.budget, max_batches=a.max_batches)
    elif a.cmd == "rebuild":
        from loader import offpeak
        offpeak.wait("xref rebuild", _log)
        sweep(full=True, only=a.linker)
    elif a.cmd == "sample":
        sample(a.linker, a.n)
    elif a.cmd == "status":
        status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
