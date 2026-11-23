"""The suppression list: people kept off the site permanently (owner, 2026-11-23).

Tables (created by migration 0080 and again here with IF NOT EXISTS; neither the loaders nor any rebuild touches them):
  suppressed_people  one row per suppressed name: name, name_norm, FURP person_id, known org-row identifiers (eins,
                     row_ids), date added, reason, active.
  suppression_hits   every time a suppressed person is filtered from new data (insert blocked or a sweep removal);
                     the nightly report email lists the night's rows.
  privacy_removed    (existing) the removed rows, as jsonb, so any removal can be reversed.

How a suppressed person stays out, through every rebuild:
  1. A BEFORE INSERT trigger on people (suppression_guard_people) drops a suppressed name at ingest, even when a
     loader reloads whole years, and logs a hit.
  2. `sweep` (scripts/nightly.sh runs it before and after the loads) removes the name from every other table that
     shows people (see OTHER_TABLES), and cascades through the person-cluster tables, archiving each row first.
     It also re-installs the trigger, because a table rebuilt by swap loses its triggers.
  3. At request time the person page and API answer 410 Gone (app/suppress.py), so a page is never served even in
     the hours between a load and the next sweep; the sitemap leaves the ids out.
Matching is by normalized name (app.names.normalize_name) everywhere; eins and row_ids only record which rows were
known when the person was added.

Usage:  .venv/bin/python -m loader.suppression add --name "First Last" --person-id N [--ein E ...] --reason "..."
        .venv/bin/python -m loader.suppression list | sweep [--dry-run] | ensure | deactivate ID
"""
from __future__ import annotations

import argparse
import json
import sys

from app.names import normalize_name
from loader import db

DDL = """
CREATE TABLE IF NOT EXISTS suppressed_people (
    id serial PRIMARY KEY,
    name text NOT NULL,
    name_norm text NOT NULL,
    person_id bigint,
    eins text[],
    row_ids jsonb,
    added_at timestamptz NOT NULL DEFAULT now(),
    reason text,
    active boolean NOT NULL DEFAULT true);
CREATE UNIQUE INDEX IF NOT EXISTS suppressed_people_name_norm ON suppressed_people (name_norm);
CREATE INDEX IF NOT EXISTS suppressed_people_person ON suppressed_people (person_id);
CREATE TABLE IF NOT EXISTS suppression_hits (
    id bigserial PRIMARY KEY,
    hit_at timestamptz NOT NULL DEFAULT now(),
    table_name text,
    name_norm text,
    n integer NOT NULL DEFAULT 1,
    how text);
CREATE INDEX IF NOT EXISTS suppression_hits_at ON suppression_hits (hit_at);
CREATE OR REPLACE FUNCTION suppression_guard_people() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
    IF EXISTS (SELECT 1 FROM suppressed_people s WHERE s.active AND s.name_norm = NEW.name_norm) THEN
        INSERT INTO suppression_hits (table_name, name_norm, how) VALUES ('people', NEW.name_norm, 'insert blocked');
        RETURN NULL;
    END IF;
    RETURN NEW;
END $f$;
"""

TRIGGER_SQL = ("CREATE TRIGGER suppression_guard BEFORE INSERT ON people FOR EACH ROW "
               "EXECUTE FUNCTION suppression_guard_people()")

# Every other table that shows a person's name, with its normalized-name column (schema.table, column).
OTHER_TABLES = [
    ("biz_people", "name_norm"), ("fund_people", "name_norm"), ("adv_people", "name_norm"), ("adv_owners", "name_norm"),
    ("adv_person_links", "name_norm"), ("sec_formd_people", "name_norm"), ("sec_formd_parties", "name_norm"),
    ("sec_insider_owners", "name_norm"), ("iapd_individuals", "name_norm"), ("pat_inventor_people", "name_norm"),
    ("pat_inventors", "name_norm"), ("lda_activity_lobbyists", "name_norm"), ("op_recipients", "name_norm"),
    ("fara_person_links", "name_norm"), ("payroll_person_links", "name_norm"), ("payroll_person_years", "name_norm"),
    ("payroll_rows", "name_norm"), ("fec_donor_totals", "name_norm"), ("fec_person_keys", "name_norm"),
    ("donors", "name_norm"), ("insider_loans", "name_norm"), ("form5500_names", "name_norm"),
    ("uk.trustee", "name_norm"), ("uk_companies.officer", "name_norm"), ("uk_companies.officer_stats", "name_norm"),
    ("uk_companies.psc_person", "name_norm"), ("wiki.person_name", "name_norm"),
    ("unipay.public_payroll_records", "name_norm"), ("school_rows", "name_norm"),
]
SKIP_CASCADE = ("space_", "privacy_", "suppress")     # private spaces and the archive itself are never swept


def ensure(conn=None, status=print) -> None:
    """Create the tables and function, and the trigger on people if it is missing (lock_timeout: never queue behind a
    long transaction and block the site)."""
    own = conn is None
    conn = conn or db.connect(autocommit=True)
    try:
        conn.execute(DDL)
        have = conn.execute("""SELECT 1 FROM pg_trigger WHERE tgrelid = 'people'::regclass
                               AND tgname = 'suppression_guard' AND NOT tgisinternal""").fetchone()
        if not have:
            conn.execute("SET lock_timeout = '10s'")
            try:
                conn.execute(TRIGGER_SQL)
                status("suppression: insert guard installed on people")
            except Exception as e:  # noqa: BLE001 - tried again at the next sweep
                status(f"suppression: could not install the people trigger now ({type(e).__name__}); will retry")
            finally:
                conn.execute("RESET lock_timeout")
    finally:
        if own:
            conn.close()


def add(conn, name: str, person_id: int | None, eins=None, row_ids=None, reason: str = "") -> int:
    norm = normalize_name(name)
    if not norm:
        raise ValueError("name has no usable letters")
    r = conn.execute("""INSERT INTO suppressed_people (name, name_norm, person_id, eins, row_ids, reason)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (name_norm) DO UPDATE SET active = true, person_id = coalesce(excluded.person_id,
                            suppressed_people.person_id), eins = coalesce(excluded.eins, suppressed_people.eins),
                            row_ids = coalesce(excluded.row_ids, suppressed_people.row_ids),
                            reason = coalesce(nullif(excluded.reason, ''), suppressed_people.reason)
                        RETURNING id""",
                     (name, norm, person_id, eins or None, json.dumps(row_ids) if row_ids else None, reason)).fetchone()
    # The existing filing-text redaction (app/suppress.py) reads privacy_suppressions: keep a name there too.
    for v in {name.upper(), norm.upper()}:
        conn.execute("""INSERT INTO privacy_suppressions (kind, value, note)
                        SELECT 'name', %s, %s WHERE NOT EXISTS (SELECT 1 FROM privacy_suppressions WHERE value = %s)""",
                     (v, f"suppression list #{r[0]}: {name}", v))
    return r[0]


def _archive(conn, request: str, table: str, where_sql: str, params) -> int:
    n = conn.execute(f"""INSERT INTO privacy_removed (request, table_name, "row")
                         SELECT %s, %s, to_jsonb(t) FROM {table} t WHERE {where_sql}""", (request, table, *params)).rowcount
    if n:
        conn.execute(f"DELETE FROM {table} WHERE {where_sql}", params)
    return n


def _cluster_tables(conn) -> list[tuple[str, str]]:
    rows = conn.execute("""SELECT c.table_schema, c.table_name FROM information_schema.columns c
                           JOIN information_schema.tables t USING (table_schema, table_name)
                           WHERE t.table_type = 'BASE TABLE' AND c.column_name = 'cluster_id'
                             AND c.table_schema = 'public' ORDER BY 2""").fetchall()
    return [(s, n) for s, n in rows if not n.startswith(SKIP_CASCADE) and n not in ("person_cluster_members",)]


def sweep(conn=None, status=print, dry_run: bool = False, how: str = "sweep") -> dict[str, int]:
    """Remove every suppressed name that has (re)appeared; log each removal as a hit. Returns {table: rows}."""
    own = conn is None
    conn = conn or db.connect()
    found: dict[str, int] = {}
    try:
        if not dry_run:
            ensure(db.connect(autocommit=True), status)
        entries = conn.execute("SELECT id, name, name_norm, person_id FROM suppressed_people WHERE active").fetchall()
        conn.commit()
        for eid, name, norm, person_id in entries:
            req = f"suppression list #{eid}: {name}"
            hits: dict[str, int] = {}
            # people rows, then the person-cluster tables
            ids = [r[0] for r in conn.execute("SELECT id FROM people WHERE name_norm = %s", (norm,))]
            clusters = {int(person_id)} if person_id else set()
            if ids:
                clusters |= {r[0] for r in conn.execute(
                    "SELECT DISTINCT cluster_id FROM person_cluster_members WHERE person_id = ANY(%s) AND cluster_id IS NOT NULL", (ids,))}
            if ids and not dry_run:
                hits["people"] = _archive(conn, req, "people", "id = ANY(%s)", (ids,))
                for t in ("schedule_j",):
                    n = _archive(conn, req, t, "person_id = ANY(%s)", (ids,))
                    if n:
                        hits[t] = n
                n = _archive(conn, req, "person_cluster_members", "person_id = ANY(%s)", (ids,))
                if n:
                    hits["person_cluster_members"] = n
            elif ids:
                hits["people"] = len(ids)
            # A cluster with no member left (or the suppressed person's own id) goes from every cluster table.
            for cid in sorted(clusters):
                left = conn.execute("SELECT count(*) FROM person_cluster_members WHERE cluster_id = %s", (cid,)).fetchone()[0]
                if left and cid != person_id:
                    continue
                exists = conn.execute("SELECT 1 FROM person_clusters WHERE id = %s", (cid,)).fetchone()
                if dry_run:
                    if exists:
                        hits["person_clusters"] = hits.get("person_clusters", 0) + 1
                    continue
                for s, t in _cluster_tables(conn):
                    n = _archive(conn, req, t, "cluster_id = %s", (cid,))
                    if n:
                        hits[t] = hits.get(t, 0) + n
                for t in ("person_clusters", "person_search"):
                    n = _archive(conn, req, t, "id = %s", (cid,))
                    if n:
                        hits[t] = hits.get(t, 0) + n
            # every other table that shows people
            for tbl, col in OTHER_TABLES:
                try:
                    if dry_run:
                        n = conn.execute(f"SELECT count(*) FROM {tbl} WHERE {col} = %s", (norm,)).fetchone()[0]
                    else:
                        n = _archive(conn, req, tbl, f"{col} = %s", (norm,))
                except Exception as e:  # noqa: BLE001 - one missing or locked table must not stop the rest
                    conn.rollback()
                    status(f"suppression: {tbl} skipped ({type(e).__name__}: {str(e)[:120]})")
                    continue
                if n:
                    hits[tbl] = n
            if hits and not dry_run:
                for t, n in hits.items():
                    conn.execute("INSERT INTO suppression_hits (table_name, name_norm, n, how) VALUES (%s, %s, %s, %s)",
                                 (t, norm, n, how))
            conn.commit()
            for t, n in hits.items():
                found[t] = found.get(t, 0) + n
                status(f"suppression: {'would remove' if dry_run else 'removed'} {n} row(s) of {name} from {t}")
        if not found:
            status(f"suppression: {len(entries)} suppressed name(s); none found in the data")
        return found
    finally:
        if own:
            conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--name", required=True)
    a.add_argument("--person-id", type=int)
    a.add_argument("--ein", action="append")
    a.add_argument("--row", action="append", help="an org-row identifier or description; repeatable")
    a.add_argument("--reason", default="")
    s = sub.add_parser("sweep")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("list")
    sub.add_parser("ensure")
    d = sub.add_parser("deactivate")
    d.add_argument("id", type=int)
    args = ap.parse_args()
    if args.cmd == "ensure":
        ensure()
        return 0
    with db.connect() as conn:
        conn.execute(DDL)
        conn.commit()
        if args.cmd == "add":
            i = add(conn, args.name, args.person_id, args.ein, {"rows": args.row} if args.row else None, args.reason)
            conn.commit()
            print(f"suppressed #{i}: {args.name}")
            sweep(conn)
        elif args.cmd == "list":
            for r in conn.execute("""SELECT id, name, person_id, eins, added_at::date, active, reason
                                     FROM suppressed_people ORDER BY id"""):
                print(r)
        elif args.cmd == "deactivate":
            conn.execute("UPDATE suppressed_people SET active = false WHERE id = %s", (args.id,))
            conn.commit()
        elif args.cmd == "sweep":
            sweep(conn, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
