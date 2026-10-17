"""Parse filings in parallel and load them through staging tables.

A "source" is one IRS zip file, or (for 2011-2016) one chunk of object ids
fetched one by one from the GivingTuesday mirror. Each source is loaded
atomically: rows are COPYed into unlogged stage_* tables, then moved into the
live tables in one transaction that also records the source as done in
loader_progress and every object id in loaded_objects. A restart skips done
sources and already-loaded object ids, so nothing is processed twice.
"""

from __future__ import annotations

import gzip
import multiprocessing as mp
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import XML_DIR
from loader import db, extras, irs
from loader.parser import parse

WORKERS = max(1, (os.cpu_count() or 8) - 1)
CHUNK = 250          # filings per worker task
FLUSH = 5000         # filings per COPY batch into staging
GT_CHUNK = 10000     # object ids per GivingTuesday source
FETCH_THREADS = 48   # concurrent mirror fetches per worker process

FILING_COLS = ["object_id", "ein", "form_type", "return_version", "tax_year", "tax_period_begin",
               "tax_period_end", "filed_date", "org_name", "dba", "street", "city", "state", "zip",
               "website", "total_revenue", "total_expenses", "total_assets_eoy", "total_liabilities_eoy",
               "net_assets_eoy", "contributions", "program_service_revenue", "fundraising_expenses", "officer_comp_total",
               "num_employees", "num_volunteers", "mission", "amended", "xml_path", "source_file"]
PEOPLE_COLS = ["source", "name_raw", "name_norm", "title", "avg_hours", "avg_hours_related", "is_officer",
               "is_director", "is_trustee", "is_key_employee", "is_highest_comp", "is_former", "comp_org",
               "comp_related", "other_comp", "street", "city", "state", "zip"]
CONTRACTOR_COLS = ["source", "name_raw", "name_norm", "street", "city", "state", "zip",
                   "service_description", "compensation"]
SJ_COLS = ["name_raw", "name_norm", "title", "base_org", "base_related", "bonus_org", "bonus_related",
           "other_org", "other_related", "deferred_org", "deferred_related", "nontaxable_org",
           "nontaxable_related", "total_org", "total_related"]
RELATED_COLS = ["related_ein", "related_name"]

STAGE_DDL = f"""
CREATE UNLOGGED TABLE IF NOT EXISTS stage_filings (LIKE filings INCLUDING DEFAULTS);
ALTER TABLE stage_filings DROP COLUMN IF EXISTS id;
CREATE UNLOGGED TABLE IF NOT EXISTS stage_people (object_id bigint, ord integer,
    {", ".join(c + (" numeric" if c.startswith("avg_hours") else " boolean" if c.startswith("is_")
                    else " bigint" if c in ("comp_org", "comp_related", "other_comp") else " text")
               for c in PEOPLE_COLS)});
CREATE UNLOGGED TABLE IF NOT EXISTS stage_contractors (object_id bigint, ord integer,
    {", ".join(c + (" bigint" if c == "compensation" else " text") for c in CONTRACTOR_COLS)});
CREATE UNLOGGED TABLE IF NOT EXISTS stage_schedule_j (object_id bigint, ord integer,
    {", ".join(c + (" text" if c in ("name_raw", "name_norm", "title") else " bigint") for c in SJ_COLS)});
CREATE UNLOGGED TABLE IF NOT EXISTS stage_related (object_id bigint, related_ein text, related_name text);
CREATE UNLOGGED TABLE IF NOT EXISTS stage_objects (object_id bigint, status text);
"""
STAGE_TABLES = ["stage_filings", "stage_people", "stage_contractors", "stage_schedule_j", "stage_related",
                "stage_objects"] + extras.STAGE_TABLES


def xml_relpath(oid: str) -> str:
    return f"{oid[:4]}/{oid[4:8]}/{oid}.xml.gz"


def _clean(v):
    if isinstance(v, str):
        v = v.replace("\x00", "").strip()
        return v or None
    return v


# --- worker side ---------------------------------------------------------------

_zip_cache: dict[str, object] = {}


def _open_zip(path: str):
    import zipfile_deflate64 as zipfile
    z = _zip_cache.get(path)
    if z is None:
        for old in _zip_cache.values():
            old.close()
        _zip_cache.clear()
        z = _zip_cache[path] = zipfile.ZipFile(path)
    return z


def _process_one(oid: str, xml: bytes, source_file: str):
    """Parse one filing and store its XML. Returns a compact result tuple."""
    try:
        r = parse(xml, oid)
    except Exception as e:
        return (oid, "error", f"{type(e).__name__}: {e}", None)
    if r is None:
        return (oid, "skipped", None, None)
    rel = xml_relpath(oid)
    dest = XML_DIR / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with gzip.open(tmp, "wb", compresslevel=6) as f:
            f.write(xml)
        tmp.rename(dest)
    f = r["filing"]
    f["ein"] = (f["ein"] or "").zfill(9)
    f["xml_path"] = rel
    f["source_file"] = source_file
    filing = tuple(_clean(f.get(c)) for c in FILING_COLS)
    people = [tuple(_clean(p.get(c)) for c in PEOPLE_COLS) for p in r["people"]]
    contractors = [tuple(_clean(c.get(k)) for k in CONTRACTOR_COLS) for c in r["contractors"]]
    sj = [tuple(_clean(s.get(k)) for k in SJ_COLS) for s in r["schedule_j"]]
    related = [(x["related_ein"].zfill(9), _clean(x["related_name"])) for x in r["related"]]
    return (oid, "loaded", r["warnings"], (filing, people, contractors, sj, related, extras.rows_from(r)))


def work_zip(args):
    path, names, source_file = args
    z = _open_zip(path)
    out = []
    for name in names:
        oid = Path(name).name.split("_")[0]
        try:
            xml = z.read(name)
        except Exception as e:
            out.append((oid, "error", f"read: {type(e).__name__}: {e}", None))
            continue
        out.append(_process_one(oid, xml, source_file))
    return out


def _fetch_and_process(item):
    oid, url, source_file = item
    cached = XML_DIR / xml_relpath(oid)
    try:
        xml = gzip.open(cached).read() if cached.exists() else irs.fetch_bytes(url)
    except Exception as e:
        if getattr(e, "code", None) in (403, 404):
            return (oid, "missing", None, None)   # not in the mirror; recorded, not retried
        return (oid, "error", f"fetch: {type(e).__name__}: {e}", None)
    return _process_one(oid, xml, source_file)


def work_gt(args):
    items, source_file = args
    # Mirror fetches are latency-bound (~0.3 s each), so each worker runs many at once.
    with ThreadPoolExecutor(max_workers=FETCH_THREADS) as ex:
        return list(ex.map(_fetch_and_process, [(oid, url, source_file) for oid, url in items]))


def work_reparse(items):
    """Re-parse stored XML for filing-level fields only."""
    out = []
    for oid, rel, source_file in items:
        try:
            xml = gzip.open(XML_DIR / rel).read()
            r = parse(xml, oid)
        except Exception as e:
            out.append((oid, "error", f"{type(e).__name__}: {e}"))
            continue
        if r is None:
            continue
        f = r["filing"]
        f["ein"] = (f["ein"] or "").zfill(9)
        f["xml_path"] = rel
        f["source_file"] = source_file
        out.append((oid, "ok", tuple(_clean(f.get(c)) for c in FILING_COLS)))
    return out


# --- main side -----------------------------------------------------------------

class Loader:
    def __init__(self, status):
        self.status = status
        self.pool = mp.get_context("fork").Pool(WORKERS, maxtasksperchild=200)
        self.conn = db.connect()
        with self.conn.cursor() as cur:
            cur.execute(STAGE_DDL)
            cur.execute(extras.STAGE_DDL)
        self.conn.commit()

    def close(self):
        self.pool.terminate()
        self.conn.close()

    def _loaded_ids(self, oids: list[str]) -> set[str]:
        out = set()
        with self.conn.cursor() as cur:
            for i in range(0, len(oids), 50000):
                cur.execute("SELECT object_id::text FROM loaded_objects WHERE object_id = ANY(%s)",
                            ([int(o) for o in oids[i:i + 50000]],))
                out.update(r[0] for r in cur)
        return out

    def _flush(self, buf):
        if not any(buf.values()):
            return
        with self.conn.cursor() as cur:
            db.copy_rows(cur, "stage_filings", FILING_COLS, buf["filings"])
            db.copy_rows(cur, "stage_people", ["object_id", "ord"] + PEOPLE_COLS, buf["people"])
            db.copy_rows(cur, "stage_contractors", ["object_id", "ord"] + CONTRACTOR_COLS, buf["contractors"])
            db.copy_rows(cur, "stage_schedule_j", ["object_id", "ord"] + SJ_COLS, buf["sj"])
            db.copy_rows(cur, "stage_related", ["object_id"] + RELATED_COLS, buf["related"])
            db.copy_rows(cur, "stage_objects", ["object_id", "status"], buf["objects"])
            for t, cols in extras.TABLES.items():
                db.copy_rows(cur, f"stage_{t}", ["object_id"] + cols, buf["x_" + t])
        self.conn.commit()
        for v in buf.values():
            v.clear()

    def _consume(self, results_iter, file: str) -> tuple[int, int]:
        buf = {k: [] for k in ("filings", "people", "contractors", "sj", "related", "objects")
               + tuple("x_" + t for t in extras.TABLES)}
        n_loaded = n_err = 0
        seen_warnings = set()
        for batch in results_iter:
            nf = npl = nc = ne = 0
            for oid, st, info, data in batch:
                oid_i = int(oid)
                buf["objects"].append((oid_i, st))
                if st == "error":
                    ne += 1
                    self.status.error(f"{file} {oid}: {info}")
                    continue
                if st != "loaded":
                    continue
                for w in info or ():
                    if w not in seen_warnings:
                        seen_warnings.add(w)
                        self.status.warn(f"{file} {oid} (first of its kind in this file): {w}")
                filing, people, contractors, sj, related, extra = data
                buf["filings"].append(filing)
                buf["people"].extend((oid_i, i) + p for i, p in enumerate(people))
                buf["contractors"].extend((oid_i, i) + c for i, c in enumerate(contractors))
                buf["sj"].extend((oid_i, i) + s for i, s in enumerate(sj))
                buf["related"].extend((oid_i,) + r for r in related)
                for t, rows in extra.items():
                    buf["x_" + t].extend((oid_i,) + x for x in rows)
                nf += 1
                npl += len(people)
                nc += len(contractors)
            n_loaded += nf
            n_err += ne
            self.status.add(filings=nf, people=npl, contractors=nc, errors=0)
            if len(buf["filings"]) >= FLUSH:
                self._flush(buf)
        self._flush(buf)
        return n_loaded, n_err

    def _truncate_stage(self):
        with self.conn.cursor() as cur:
            cur.execute("TRUNCATE " + ", ".join(STAGE_TABLES))
        self.conn.commit()

    def _move(self, file: str, kind: str, year: int, n_loaded: int, n_err: int):
        """Move staged rows into the live tables in one transaction."""
        with self.conn.cursor() as cur:
            cols = ", ".join(FILING_COLS)
            cur.execute(f"INSERT INTO filings ({cols}) SELECT {cols} FROM stage_filings "
                        f"ON CONFLICT (object_id) DO NOTHING")
            cur.execute("""CREATE TEMP TABLE new_f ON COMMIT DROP AS
                           SELECT f.id, f.object_id, f.ein, f.tax_year FROM filings f
                           JOIN stage_filings s USING (object_id) WHERE f.source_file = %s""", (file,))
            cur.execute("CREATE INDEX ON new_f (object_id)")
            pc = ", ".join(PEOPLE_COLS)
            cur.execute(f"""INSERT INTO people (filing_id, ein, tax_year, {pc})
                            SELECT nf.id, nf.ein, nf.tax_year, {", ".join("s." + c for c in PEOPLE_COLS)}
                            FROM stage_people s JOIN new_f nf USING (object_id) ORDER BY nf.id, s.ord""")
            cc = ", ".join(CONTRACTOR_COLS)
            cur.execute(f"""INSERT INTO contractors (filing_id, ein, tax_year, {cc})
                            SELECT nf.id, nf.ein, nf.tax_year, {", ".join("s." + c for c in CONTRACTOR_COLS)}
                            FROM stage_contractors s JOIN new_f nf USING (object_id) ORDER BY nf.id, s.ord""")
            sc = ", ".join(SJ_COLS)
            cur.execute(f"""INSERT INTO schedule_j (filing_id, person_id, ein, tax_year, {sc})
                            SELECT nf.id,
                                   (SELECT min(p.id) FROM people p
                                     WHERE p.filing_id = nf.id AND p.name_norm = s.name_norm),
                                   nf.ein, nf.tax_year, {", ".join("s." + c for c in SJ_COLS)}
                            FROM stage_schedule_j s JOIN new_f nf USING (object_id) ORDER BY nf.id, s.ord""")
            cur.execute("""INSERT INTO related_orgs (filing_id, ein, related_ein, related_name)
                           SELECT nf.id, nf.ein, s.related_ein, s.related_name
                           FROM stage_related s JOIN new_f nf USING (object_id)""")
            extras.insert_from_stage(cur)
            cur.execute("""INSERT INTO loaded_objects (object_id, file, status)
                           SELECT DISTINCT ON (object_id) object_id, %s, status FROM stage_objects
                           ON CONFLICT (object_id) DO NOTHING""", (file,))
            db.progress(self.conn, file, "done", kind=kind, year=year, rows=n_loaded,
                        error=f"{n_err} filings failed to parse; see loader-errors.log" if n_err else None)
        self.conn.commit()

    def load_zip(self, path: Path, year: int) -> None:
        import zipfile_deflate64 as zipfile
        file = path.name
        if db.status_of(self.conn, file) == "done":
            return
        db.progress(self.conn, file, "running", kind="zip", year=year)
        self.conn.commit()
        try:
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".xml")]
            by_oid = {Path(n).name.split("_")[0]: n for n in names}
            done = self._loaded_ids(list(by_oid))
            todo = [n for oid, n in by_oid.items() if oid not in done]
            self._truncate_stage()
            tasks = [(str(path), todo[i:i + CHUNK], file) for i in range(0, len(todo), CHUNK)]
            n_loaded, n_err = self._consume(self.pool.imap_unordered(work_zip, tasks), file)
            self._move(file, "zip", year, n_loaded, n_err)
        except Exception as e:
            self.conn.rollback()
            db.progress(self.conn, file, "error", kind="zip", year=year,
                        error=f"{type(e).__name__}: {e}")
            self.conn.commit()
            self.status.error(f"{file}: {traceback.format_exc()}")
            raise

    def reparse_filings(self, year: int) -> int:
        """Refresh filing-level columns (finances, mission, website...) from stored XML.

        For mapping fixes that don't touch people or contractors. `year` is the
        release year the filings were loaded from.
        """
        rows = self.conn.execute("SELECT object_id::text, xml_path, source_file FROM filings WHERE source_file IN "
                                 "(SELECT file FROM loader_progress WHERE year = %s)", (year,)).fetchall()
        n = 0
        for start in range(0, len(rows), 50000):
            part = rows[start:start + 50000]
            self._truncate_stage()
            tasks = [part[i:i + CHUNK] for i in range(0, len(part), CHUNK)]
            batch = []
            for res in self.pool.imap_unordered(work_reparse, tasks):
                for oid, st, data in res:
                    if st == "error":
                        self.status.error(f"reparse {oid}: {data}")
                    else:
                        batch.append(data)
            with self.conn.cursor() as cur:
                db.copy_rows(cur, "stage_filings", FILING_COLS, batch)
                keep = [c for c in FILING_COLS if c not in ("object_id", "xml_path", "source_file")]
                cur.execute(f"UPDATE filings f SET {', '.join(f'{c} = s.{c}' for c in keep)} "
                            f"FROM stage_filings s WHERE f.object_id = s.object_id")
            self.conn.commit()
            n += len(batch)
        return n

    def _load_items(self, file: str, kind: str, year: int, items: list[tuple[str, str]]) -> None:
        """Fetch (object_id, url) items one by one and load them as one source."""
        if db.status_of(self.conn, file) == "done":
            return
        irs.check_disk()
        db.progress(self.conn, file, "running", kind=kind, year=year)
        self.conn.commit()
        try:
            done = self._loaded_ids([oid for oid, _ in items])
            todo = [(oid, url) for oid, url in items if oid not in done]
            self._truncate_stage()
            tasks = [(todo[i:i + CHUNK], file) for i in range(0, len(todo), CHUNK)]
            n_loaded, n_err = self._consume(self.pool.imap_unordered(work_gt, tasks), file)
            self._move(file, kind, year, n_loaded, n_err)
        except Exception as e:
            self.conn.rollback()
            db.progress(self.conn, file, "error", kind=kind, year=year, error=f"{type(e).__name__}: {e}")
            self.conn.commit()
            self.status.error(f"{file}: {traceback.format_exc()}")
            raise

    def load_gt_year(self, year: int) -> None:
        rows = sorted(irs.gt_index_rows(year), key=lambda r: r["OBJECT_ID"])
        for start in range(0, len(rows), GT_CHUNK):
            chunk = rows[start:start + GT_CHUNK]
            self._load_items(f"gt:{year}:{start // GT_CHUNK:04d}", "gt", year,
                             [(r["OBJECT_ID"], r["URL"]) for r in chunk])

    def fill_gaps(self, year: int) -> int:
        """Filings in the IRS index but in none of the IRS zips, fetched from the mirror.

        The IRS has consolidated some years into fewer zips and dropped batches
        along the way (2022's single zip lacks the 11A-11C batches); the
        GivingTuesday mirror still has those returns. Returns how many were missing.
        """
        oids = sorted(irs.index_object_ids(year))
        missing = sorted(set(oids) - self._loaded_ids(oids))
        for start in range(0, len(missing), GT_CHUNK):
            chunk = missing[start:start + GT_CHUNK]
            self._load_items(f"gap:{year}:{chunk[0]}", "gap", year,
                             [(oid, f"{irs.GT_BUCKET}/EfileData/XmlFiles/{oid}_public.xml") for oid in chunk])
        return len(missing)
