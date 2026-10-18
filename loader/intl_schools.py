"""Load data/international-schools.csv into `intl_school_links` (US nonprofits tied to foreign schools).

Not wired into the site or the nightly load yet: the CSV is a review draft produced by
scripts/intl_schools_discover.py (see docs/international-schools.md). Run by hand once the owner has
reviewed it:

    python -m loader.intl_schools [path/to/international-schools.csv] [--exact-only]

The table is rebuilt in place inside one transaction (TRUNCATE + COPY), so readers never see it empty.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from loader import db

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "international-schools.csv"
COLUMNS = ["ror_id", "school_name", "country", "website", "ein", "org_name", "match", "evidence", "latest_revenue"]

DDL = """
CREATE TABLE IF NOT EXISTS intl_school_links (
    ror_id          text NOT NULL,      -- https://ror.org/xxxxxxxxx
    school_name     text NOT NULL,
    country         text,
    website         text,
    ein             text NOT NULL,      -- US affiliate (organizations.ein)
    org_name        text,
    match           text NOT NULL CHECK (match IN ('EXACT', 'FUZZY')),
    evidence        text,
    latest_revenue  bigint,
    PRIMARY KEY (ror_id, ein)
);
CREATE INDEX IF NOT EXISTS intl_school_links_ein ON intl_school_links (ein);
"""


def read_rows(path: Path, exact_only: bool = False) -> list[tuple]:
    """Validate and de-duplicate CSV rows; returns tuples in COLUMNS order."""
    rows: dict[tuple[str, str], tuple] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for n, r in enumerate(reader, 2):
            ror = (r["ror_id"] or "").strip()
            ein = re.sub(r"\D", "", r["ein"] or "").zfill(9)
            match = (r["match"] or "").strip().upper()
            if not ror.startswith("https://ror.org/") or len(ein) != 9 or match not in ("EXACT", "FUZZY"):
                raise ValueError(f"{path}:{n}: bad row {r!r}")
            if exact_only and match != "EXACT":
                continue
            rev = (r["latest_revenue"] or "").strip()
            row = (ror, r["school_name"].strip(), r["country"].strip() or None, r["website"].strip() or None, ein,
                   r["org_name"].strip() or None, match, r["evidence"].strip() or None,
                   int(float(rev)) if rev else None)
            prev = rows.get((ror, ein))
            if prev is None or (prev[6] == "FUZZY" and match == "EXACT"):
                rows[(ror, ein)] = row
    return list(rows.values())


def build(conn, path: Path = DEFAULT_CSV, exact_only: bool = False) -> int:
    """(Re)build intl_school_links from the CSV on an open psycopg connection. Returns the row count."""
    rows = read_rows(path, exact_only)
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("TRUNCATE intl_school_links")
        db.copy_rows(cur, "intl_school_links", COLUMNS, rows)
        # Refresh revenue from organizations; drop links to EINs we do not have.
        cur.execute("""UPDATE intl_school_links l SET latest_revenue = o.latest_total_revenue,
                              org_name = coalesce(l.org_name, o.name)
                       FROM organizations o WHERE o.ein = l.ein""")
        cur.execute("DELETE FROM intl_school_links l WHERE NOT EXISTS "
                    "(SELECT 1 FROM organizations o WHERE o.ein = l.ein)")
        cur.execute("SELECT count(*) FROM intl_school_links")
        return cur.fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", nargs="?", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--exact-only", action="store_true", help="load only EXACT links")
    ap.add_argument("--dry-run", action="store_true", help="validate the CSV without touching the database")
    a = ap.parse_args()
    if a.dry_run:
        rows = read_rows(a.csv, a.exact_only)
        print(f"{len(rows)} links OK ({sum(r[6] == 'EXACT' for r in rows)} EXACT)")
        return
    with db.connect() as conn:
        print(f"intl_school_links: {build(conn, a.csv, a.exact_only)} rows")


if __name__ == "__main__":
    main()
