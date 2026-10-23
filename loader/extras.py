"""Grants, donor-advised funds, foundation payout, insider loans and fundraising events.

The parser (loader/parser.py) extracts them from every filing; new loads write them
through loader/ingest.py, and load.py backfill-extras reads the stored XML of
filings loaded before these were mapped. The backfill walks filings in id order
and records the last id done with each batch, in the same transaction, so a
restart picks up exactly where it stopped. Each batch first deletes what it is
about to write, so rerunning it is harmless.
"""

from __future__ import annotations

import gzip
import json
import multiprocessing as mp
import os

from app.config import XML_DIR
from loader import db
from loader.parser import parse

GRANT_COLS = ["source", "recipient_name", "recipient_name_norm", "recipient_ein", "recipient_is_person", "city",
              "state", "cash_amount", "noncash_amount", "purpose", "irc_section", "foundation_status",
              "relationship", "is_summary"]
DAF_COLS = ["form_type", "maintains_dafs", "daf_count", "daf_contributions", "daf_grants", "daf_value_eoy",
            "other_count", "other_contributions", "other_grants", "other_value_eoy"]
PF_COLS = ["noncharitable_assets", "min_investment_return", "distributable_amount", "qualifying_distributions"]
LOAN_COLS = ["name_raw", "name_norm", "relationship", "purpose", "to_org", "from_org", "original_principal",
             "balance_due", "in_default", "board_approved", "written_agreement"]
EXPENSE_COLS = ["form_type", "total_expenses", "pay_total", "grants_total", "event_lines_total", "conferences_total",
                "special_event_expenses", "special_event_gross", "special_event_net", "lines"]
EVENT_COLS = ["slot", "name", "keyword", "other_count", "gross_receipts", "contributions", "gross_revenue",
              "cash_prizes", "noncash_prizes", "rent_facility", "food_beverage", "entertainment", "other_direct",
              "direct_expenses", "net_income"]
DONOR_COLS = ["contributor_num", "name", "name_norm", "is_person", "city", "state", "total_amount", "noncash_amount"]
TABLES = {"grants": GRANT_COLS, "daf_stats": DAF_COLS, "pf_payout": PF_COLS, "insider_loans": LOAN_COLS,
          "expense_breakdown": EXPENSE_COLS, "donors": DONOR_COLS, "fundraising_events": EVENT_COLS}
ONE_ROW_TABLES = ("daf_stats", "pf_payout", "expense_breakdown")   # keyed by filing_id

# Built once the backfill is done (and kept by later loads).
INDEXES = [
    "CREATE INDEX IF NOT EXISTS grants_ein ON grants (ein, tax_year)",
    "CREATE INDEX IF NOT EXISTS grants_recipient_ein ON grants (recipient_ein) WHERE recipient_ein IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS grants_recipient_name ON grants (recipient_name_norm, state) "
    "WHERE source = '990PF-XV'",
    "CREATE INDEX IF NOT EXISTS daf_stats_ein ON daf_stats (ein, tax_year)",
    "CREATE INDEX IF NOT EXISTS pf_payout_ein ON pf_payout (ein, tax_year)",
    "CREATE INDEX IF NOT EXISTS insider_loans_ein ON insider_loans (ein)",
    "CREATE INDEX IF NOT EXISTS expense_breakdown_ein ON expense_breakdown (ein, tax_year)",
    "CREATE INDEX IF NOT EXISTS donors_ein ON donors (ein, tax_year)",
    "CREATE INDEX IF NOT EXISTS fundraising_events_filing ON fundraising_events (filing_id)",
    "CREATE INDEX IF NOT EXISTS fundraising_events_ein ON fundraising_events (ein, tax_year)",
]
TRGM_INDEXES = [
    "CREATE INDEX IF NOT EXISTS grants_recipient_trgm ON grants USING gin (recipient_name_norm gin_trgm_ops)",
]

# CREATE ... IF NOT EXISTS keeps a stage table made before a column was added, so every column is also added if
# missing (2026-10-23: special_event_net was missing from stage_expense_breakdown and the nightly 990 load failed).
STAGE_DDL = "\n".join(
    f"CREATE UNLOGGED TABLE IF NOT EXISTS stage_{t} (object_id bigint, "
    + ", ".join(f"{c} {_type}" for c, _type in cols) + ");\n"
    + "\n".join(f"ALTER TABLE stage_{t} ADD COLUMN IF NOT EXISTS {c} {_type};" for c, _type in cols)
    for t, cols in {
        "grants": [(c, "boolean" if c in ("recipient_is_person", "is_summary") else
                    "bigint" if c.endswith("_amount") else "text") for c in GRANT_COLS],
        "daf_stats": [(c, "text" if c == "form_type" else "boolean" if c == "maintains_dafs" else "bigint")
                      for c in DAF_COLS],
        "pf_payout": [(c, "bigint") for c in PF_COLS],
        "insider_loans": [(c, "bigint" if c in ("original_principal", "balance_due") else
                           "text" if c in ("name_raw", "name_norm", "relationship", "purpose") else "boolean")
                          for c in LOAN_COLS],
        "expense_breakdown": [(c, "text" if c == "form_type" else "jsonb" if c == "lines" else "bigint")
                              for c in EXPENSE_COLS],
        "donors": [(c, "boolean" if c == "is_person" else "integer" if c == "contributor_num" else
                    "bigint" if c.endswith("_amount") else "text") for c in DONOR_COLS],
        "fundraising_events": [(c, "text" if c in ("slot", "name", "keyword") else "integer" if c == "other_count"
                                else "bigint") for c in EVENT_COLS],
    }.items())
STAGE_TABLES = [f"stage_{t}" for t in TABLES]


def _clean(v):
    if isinstance(v, str):
        v = v.replace("\x00", "").strip()
        return v or None
    return v


def rows_from(result) -> dict[str, list[tuple]]:
    """Rows for each extras table from one parsed filing (without filing_id/ein/tax_year)."""
    form = result["filing"]["form_type"]
    out = {
        "grants": [tuple(_clean(g.get(c)) for c in GRANT_COLS) for g in result.get("grants") or []],
        "daf_stats": [],
        "pf_payout": [],
        "insider_loans": [tuple(_clean(x.get(c)) for c in LOAN_COLS) for x in result.get("loans") or []],
    }
    if result.get("daf"):
        out["daf_stats"].append(tuple(form if c == "form_type" else result["daf"].get(c) for c in DAF_COLS))
    if result.get("pf_payout"):
        out["pf_payout"].append(tuple(result["pf_payout"].get(c) for c in PF_COLS))
    out["donors"] = [tuple(_clean(d.get(c)) for c in DONOR_COLS) for d in result.get("donors") or []]
    out["fundraising_events"] = [tuple(_clean(e.get(c)) for c in EVENT_COLS)
                                 for e in result.get("fundraising_events") or []]
    e = result.get("expenses")
    out["expense_breakdown"] = [tuple(
        form if c == "form_type" else json.dumps(e["lines"], ensure_ascii=False) if c == "lines" else e.get(c)
        for c in EXPENSE_COLS)] if e else []
    return out


def insert_from_stage(cur) -> None:
    """Move staged rows (keyed by object_id) into the live tables; needs the new_f temp table."""
    for t, cols in TABLES.items():
        cl = ", ".join(cols)
        cur.execute(f"""INSERT INTO {t} (filing_id, ein, tax_year, {cl})
                        SELECT nf.id, nf.ein, nf.tax_year, {", ".join("s." + c for c in cols)}
                        FROM stage_{t} s JOIN new_f nf USING (object_id)
                        {"ON CONFLICT (filing_id) DO NOTHING" if t in ONE_ROW_TABLES else ""}""")


# --- backfill ---------------------------------------------------------------------

BATCH = 2000
PROGRESS_KEY = "extras-backfill"
WORKERS = max(1, (os.cpu_count() or 8) - 2)   # leave room for the web app


def _read(item):
    fid, oid, path, ein, year, only = item
    try:
        with gzip.open(XML_DIR / path) as f:
            r = parse(f.read(), oid)
    except Exception:  # noqa: BLE001 - unreadable file: nothing to add
        return fid, None
    if r is None:
        return fid, None
    rows = rows_from(r)
    return fid, (ein, year, {t: rows[t] for t in only})


def _write(cur, done: list, only: list[str]) -> dict[str, int]:
    ids = [fid for fid, _ in done]
    counts = {t: 0 for t in only}
    for t in only:
        cur.execute(f"DELETE FROM {t} WHERE filing_id = ANY(%s)", (ids,))
    for t in only:
        cols = TABLES[t]
        rows = [(fid, ein, year) + row for fid, data in done if data
                for ein, year, by_table in [data] for row in by_table[t]]
        if rows:
            db.copy_rows(cur, t, ["filing_id", "ein", "tax_year"] + cols, rows)
            counts[t] = len(rows)
    return counts


def backfill(status, only: list[str] | None = None, forms: list[str] | None = None) -> int:
    """Read the extras tables (all, or just `only`) from stored XML, for every filing or only
    some form types; resumable per table set and form set."""
    only = list(only or TABLES)
    key = PROGRESS_KEY + ":" + ",".join(only) + (":" + ",".join(forms) if forms else "")
    form_filter = "AND form_type = ANY(%(forms)s)" if forms else ""
    if only and set(only) <= {"fundraising_events", "expense_breakdown"}:
        form_filter += (" AND id IN (SELECT filing_id FROM expense_breakdown WHERE coalesce(special_event_gross, 0) <> 0"
                        " OR coalesce(special_event_expenses, 0) <> 0)")
    status.phase = "backfill " + ", ".join(only)
    with db.connect() as conn:
        row = conn.execute("SELECT rows FROM loader_progress WHERE file = %s", (key,)).fetchone()
        last = int(row[0]) if row and row[0] else 0
        total = conn.execute(f"SELECT count(*) FROM filings WHERE xml_path IS NOT NULL {form_filter}",
                             {"forms": forms}).fetchone()[0]
        before = conn.execute(f"SELECT count(*) FROM filings WHERE xml_path IS NOT NULL AND id <= %(last)s {form_filter}",
                              {"last": last, "forms": forms}).fetchone()[0]
        status.begin_year("all", total, before)
        status.emit(f"backfill extras: {total - before:,} of {total:,} filings to read (resuming after id {last:,})")
        totals = {t: 0 for t in only}
        with mp.get_context("fork").Pool(WORKERS, maxtasksperchild=5000) as pool:
            while True:
                items = [tuple(r) + (only,) for r in conn.execute(
                    f"""SELECT id, object_id, xml_path, ein, tax_year FROM filings
                        WHERE xml_path IS NOT NULL AND id > %(last)s {form_filter} ORDER BY id LIMIT %(lim)s""",
                    {"last": last, "forms": forms, "lim": BATCH * WORKERS * 4}).fetchall()]
                if not items:
                    break
                done = []
                for res in pool.imap(_read, items, chunksize=32):
                    done.append(res)
                    if len(done) >= BATCH:
                        last = _commit(conn, done, totals, status, only, key)
                        done = []
                if done:
                    last = _commit(conn, done, totals, status, only, key)
        db.progress(conn, key, "done", kind="backfill", rows=last)
        conn.commit()
    status.emit("backfill extras: done; " + ", ".join(f"{t} {n:,} rows" for t, n in totals.items()))
    return sum(totals.values())


def _commit(conn, done, totals, status, only, key) -> int:
    with conn.cursor() as cur:
        counts = _write(cur, done, only)
    last = max(fid for fid, _ in done)
    db.progress(conn, key, "running", kind="backfill", rows=last)
    conn.commit()
    for t, n in counts.items():
        totals[t] += n
    status.add(filings=len(done))
    return last


def ensure_indexes(status=None) -> None:
    with db.connect(autocommit=True) as conn:
        conn.execute("SET maintenance_work_mem = '1GB'")
        for ddl in INDEXES + (TRGM_INDEXES if db.has_extension(conn, "pg_trgm") else []):
            if status:
                status.phase = "extras indexes: " + ddl.split(" ON ")[0].split()[-1]
            conn.execute(ddl)
        for t in TABLES:
            conn.execute(f"ANALYZE {t}")
    if status:
        status.emit("extras indexes ready")
