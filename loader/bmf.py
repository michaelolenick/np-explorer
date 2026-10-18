"""Load the IRS Exempt Organizations Business Master File into organizations."""

from __future__ import annotations

import csv
import os

from app.names import normalize_org
from loader import db, irs

COLUMNS = ["ein", "name", "name_norm", "dba", "street", "city", "state", "zip", "ntee", "subsection",
           "ruling_year"]


def _rows(paths):
    seen = set()
    for p in paths:
        with open(p, newline="", encoding="latin-1") as f:
            for r in csv.DictReader(f):
                ein = (r.get("EIN") or "").strip().zfill(9)
                if not ein.strip("0") or ein in seen:
                    continue
                seen.add(ein)
                ruling = (r.get("RULING") or "").strip()
                name = (r.get("NAME") or "").strip() or None
                yield (
                    ein, name, normalize_org(name), None,  # SORT_NAME is not a reliable DBA; filings supply it
                    (r.get("STREET") or "").strip() or None, (r.get("CITY") or "").strip() or None,
                    (r.get("STATE") or "").strip() or None, (r.get("ZIP") or "").strip() or None,
                    (r.get("NTEE_CD") or "").strip() or None, (r.get("SUBSECTION") or "").strip() or None,
                    int(ruling[:4]) if ruling[:4].isdigit() and ruling[:4] != "0000" else None,
                )


def changed() -> list[str]:
    """BMF files the IRS has republished since our copy (or that aren't on disk yet).

    The IRS republishes the BMF monthly under the same names and sends no Content-Length,
    so Last-Modified is the signal. load() stamps each file with it."""
    stale = []
    for name in irs.BMF_FILES:
        dest = irs.RAW_DIR / "bmf" / f"{name}.csv"
        remote = irs.remote_mtime(irs.BMF_URL.format(name=name))
        if not dest.exists() or (remote is not None and remote > dest.stat().st_mtime):
            stale.append(name)
    return stale


def load(status, refresh: list[str] | None = None) -> int:
    """Download the BMF (re-fetching the files named in refresh) and upsert it into organizations."""
    status.phase = "bmf"
    paths = []
    for name in irs.BMF_FILES:
        url = irs.BMF_URL.format(name=name)
        dest = irs.RAW_DIR / "bmf" / f"{name}.csv"
        if refresh and name in refresh:
            dest.unlink(missing_ok=True)   # download() keeps an existing copy when the size is unknown
        irs.download(url, dest)
        remote = irs.remote_mtime(url)
        if remote is not None:
            os.utime(dest, (remote, remote))
        paths.append(dest)
    with db.connect() as conn:
        db.progress(conn, "bmf", "running", kind="bmf")
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS stage_bmf")
            cur.execute("CREATE UNLOGGED TABLE stage_bmf (ein text, name text, name_norm text, dba text, "
                        "street text, city text, state text, zip text, ntee text, subsection text, "
                        "ruling_year integer)")
            n = db.copy_rows(cur, "stage_bmf", COLUMNS, _rows(paths))
            # Upsert in one transaction: the site keeps reading the old rows until commit.
            cur.execute("""
                INSERT INTO organizations (ein, name, name_norm, dba, street, city, state, zip, ntee,
                                           subsection, ruling_year, in_bmf)
                SELECT ein, name, name_norm, dba, street, city, state, zip, ntee, subsection, ruling_year, true
                FROM stage_bmf
                ON CONFLICT (ein) DO UPDATE SET
                    name = EXCLUDED.name, name_norm = EXCLUDED.name_norm,
                    street = EXCLUDED.street, city = EXCLUDED.city, state = EXCLUDED.state,
                    zip = EXCLUDED.zip, ntee = EXCLUDED.ntee, subsection = EXCLUDED.subsection,
                    ruling_year = EXCLUDED.ruling_year, in_bmf = true
            """)
            cur.execute("DROP TABLE stage_bmf")
        db.progress(conn, "bmf", "done", rows=n)
        conn.commit()
    status.emit(f"bmf: loaded {n:,} organizations")
    return n
