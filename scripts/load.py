#!/usr/bin/env python3
"""np-explorer data loader.

Usage:
  load.py bmf              load the IRS Business Master File into organizations
  load.py index            download the IRS yearly index CSVs (and build 2011-2016 indexes)
  load.py fetch YEAR       download YEAR's zip files (IRS) or index (GivingTuesday mirror, pre-2017)
  load.py parse YEAR       parse and load YEAR (resumable)
  load.py cluster          rebuild person clusters
  load.py sitemap          rebuild the sitemap index
  load.py all              everything, newest year first, then backfill to 2011
  load.py nightly          check IRS for new zip files, load them, re-cluster, rebuild sitemap
  load.py reparse YEAR     refresh filing-level fields for YEAR from the stored XML (after a mapping fix)
  load.py merge-institutions  merge institution records (e.g. every "Bank of America") without a re-cluster
  load.py backfill-fundraising [--all]  read fundraising expenses from stored 990s (board scope by default)
  load.py backfill-extras  read grants, DAF figures, foundation payout and Schedule L loans from stored XML
  load.py boards           build or refresh the leaderboard views
  load.py search-table     rebuild person_search (name search's slim copy of person_clusters)
  load.py split-care-of    give people listed "c/o Wells Fargo" etc. their own person records

Prints one status line a minute to stdout and /var/log/np-explorer/loader.log.
Exit codes: 0 ok, 2 stopped for low disk space, 3 another loader holds the lock.
"""

from __future__ import annotations

import argparse
import fcntl
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import RAW_DIR  # noqa: E402
from loader import boards, bmf, cluster, db, finalize, indexes, irs, sitemap  # noqa: E402
from loader.status import Status  # noqa: E402


CLUSTER_EVERY = 2 * 3600


def year_order(years) -> list[int]:
    """Most recent full year first, then the current partial year, then backfill."""
    full = date.today().year - 1
    years = sorted(set(years), reverse=True)
    first = [y for y in years if y == full]
    current = [y for y in years if y > full]
    rest = [y for y in years if y < full]
    return first + current + rest


def cmd_index(status, irs_years) -> None:
    status.phase = "index"
    for year, info in irs_years.items():
        irs.download(info["index"], irs.index_path(year))
    irs.build_gt_indexes()


def cmd_fetch(status, year: int, irs_years) -> None:
    status.phase = f"fetch {year}"
    if year >= irs.FIRST_IRS_YEAR:
        info = irs_years.get(year)
        if not info:
            status.emit(f"fetch {year}: the IRS lists no files for {year}")
            return
        irs.download(info["index"], irs.index_path(year))
        for url in info["zips"]:
            irs.download(url, irs.year_dir(year) / url.rsplit("/", 1)[1])
    else:
        irs.build_gt_indexes()


def _begin_year(status, conn, year: int) -> None:
    total = irs.index_counts(year)
    row = conn.execute("SELECT coalesce(sum(rows), 0) FROM loader_progress WHERE year = %s AND status = 'done' "
                       "AND kind IN ('zip', 'gt')", (year,)).fetchone()
    status.begin_year(year, total, int(row[0]))


def cmd_parse(status, year: int, loader) -> int:
    """Load a year; returns how many filings were newly loaded."""
    status.phase = f"parse {year}"
    before = status.filings
    with db.connect() as conn:
        _begin_year(status, conn, year)
    if year >= irs.FIRST_IRS_YEAR:
        for path in sorted(irs.year_dir(year).glob("*.zip")):
            irs.check_disk()
            loader.load_zip(path, year)
        # Releases from finished years: pick up indexed returns the zips left out.
        if year < date.today().year:
            loader.fill_gaps(year)
    else:
        loader.load_gt_year(year)
    new = status.filings - before
    if new:
        finalize.run(status)
    return new


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["bmf", "index", "fetch", "parse", "cluster", "sitemap", "all",
                                        "nightly", "finalize", "reparse", "merge-institutions", "split-care-of",
                                        "backfill-fundraising", "backfill-extras", "boards", "search-table"])
    ap.add_argument("--only", help="boards: comma-separated slugs to refresh; backfill-extras: tables to fill")
    ap.add_argument("--all", action="store_true", help="backfill-fundraising: every 990, not just the board scope")
    ap.add_argument("year", nargs="?", type=int)
    args = ap.parse_args()
    if args.command in ("fetch", "parse", "reparse") and not args.year:
        ap.error(f"{args.command} needs a YEAR")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(RAW_DIR / ".loader.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another loader is already running (lock held on /data/raw/.loader.lock)", file=sys.stderr)
        return 3

    status = Status()
    status.start_ticker()
    loader = None
    try:
        needs_irs = args.command in ("index", "fetch", "all", "nightly")
        irs_years = irs.discover() if needs_irs else {}
        if args.command in ("parse", "all", "nightly", "reparse"):
            from loader.ingest import Loader
            loader = Loader(status)

        if args.command == "bmf":
            bmf.load(status)
        elif args.command == "index":
            cmd_index(status, irs_years)
        elif args.command == "fetch":
            cmd_fetch(status, args.year, irs_years)
        elif args.command == "parse":
            cmd_parse(status, args.year, loader)
        elif args.command == "reparse":
            status.phase = f"reparse {args.year}"
            n = loader.reparse_filings(args.year)
            finalize.run(status)
            status.emit(f"reparse {args.year}: refreshed {n:,} filings")
        elif args.command == "backfill-extras":
            from loader import extras
            extras.backfill(status, only=args.only.split(",") if args.only else None)
            extras.ensure_indexes(status)
            finalize.run(status)          # marks DAF sponsors
        elif args.command == "backfill-fundraising":
            from loader import backfill
            backfill.fundraising(status, everything=args.all)
        elif args.command == "search-table":
            from loader import search_table
            search_table.build(status)
        elif args.command == "boards":
            boards.refresh(status, only=args.only.split(",") if args.only else None)
        elif args.command == "split-care-of":
            cluster.split_care_of(status)
        elif args.command == "merge-institutions":
            cluster.merge_institutions(status)
        elif args.command == "finalize":
            finalize.run(status)
        elif args.command == "cluster":
            cluster.run(status)
        elif args.command == "sitemap":
            sitemap.run(status)
        elif args.command == "all":
            with db.connect() as conn:
                bmf_done = db.status_of(conn, "bmf") == "done"
            if not bmf_done:
                bmf.load(status)
            # The site's coverage notice says "still loading" until this row reads done.
            with db.connect() as conn:
                db.progress(conn, "all", "running", kind="all")
                conn.commit()
            years = year_order(list(irs_years) + list(range(irs.FIRST_YEAR, irs.FIRST_IRS_YEAR)))
            # Re-cluster as soon as the first year with new data is in, then at most
            # every CLUSTER_EVERY seconds (it slows as data grows), and after the last year.
            # The last finished cluster run is kept in loader_progress, so a restart
            # doesn't trigger an extra (slow) re-cluster.
            with db.connect() as conn:
                row = conn.execute("SELECT extract(epoch FROM finished) FROM loader_progress "
                                   "WHERE file = 'cluster' AND status = 'done'").fetchone()
            last_cluster, pending = float(row[0]) if row and row[0] else 0.0, False
            for i, year in enumerate(years):
                cmd_fetch(status, year, irs_years)
                pending |= cmd_parse(status, year, loader) > 0
                if pending and (i == len(years) - 1 or time.time() - last_cluster > CLUSTER_EVERY):
                    cluster.run(status)
                    boards.refresh(status)
                    sitemap.run(status)
                    last_cluster, pending = time.time(), False
                    status.emit(f"through {year}: loaded and searchable")
            if pending:
                cluster.run(status)
                boards.refresh(status)
                sitemap.run(status)
            loader.conn.rollback()   # an open read transaction would stall CREATE INDEX CONCURRENTLY
            created = indexes.ensure(status)
            if created:
                status.emit(f"rebuilt people indexes: {', '.join(created)}")
            with db.connect() as conn:
                db.progress(conn, "all", "done", kind="all")
                conn.commit()
        elif args.command == "nightly":
            current = max(irs_years)
            new = 0
            for year in sorted(y for y in irs_years if y >= current - 1):
                cmd_fetch(status, year, irs_years)
                new += cmd_parse(status, year, loader)
            if new:
                cluster.run(status)
                boards.refresh(status)
            loader.conn.rollback()   # an open read transaction would stall CREATE INDEX CONCURRENTLY
            indexes.ensure(status)
            sitemap.run(status)
        status.phase = "done"
        return 0
    except irs.DiskFull as e:
        status.emit(str(e))
        return 2
    finally:
        if loader:
            loader.close()
        status.stop()


if __name__ == "__main__":
    sys.exit(main())
