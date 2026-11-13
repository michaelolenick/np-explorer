"""NHGIS (IPUMS) census tables into FURP (owner, 2026-11-12).

Asks the IPUMS NHGIS extract API for whole datasets (every data table, at the state, county, place and tract
levels; NHGIS caps an extract's width, so a dataset goes as several extracts of CHUNK tables, halved whenever the
API answers "Excessive file width"), waits for each extract, downloads it to /bulk/nhgis and loads it into
Postgres schema `nhgis`, one table per
census table (nhgis.d_<dataset>_<source code>, e.g. nhgis.d_2020_2024_acs5a_b01001), with the geography in
nhgis.geo and the catalog in nhgis.datasets / nhgis.tables / nhgis.variables (every column described in plain
words, from the extract's codebook). Needs IPUMS_API_KEY in .env (the owner's key; the account must be registered
for NHGIS at https://uma.pop.umn.edu/nhgis/registration/new or the API answers 401).

    python -m loader.nhgis run [--wait-for-registration] [--datasets NAME ...]   submit, wait, download, load
    python -m loader.nhgis status                                               what is queued, downloaded, loaded
    python -m loader.nhgis load FILE.zip                                         load a downloaded extract

The load itself runs in the quiet hours (loader/offpeak.py; NP_NOW=1 runs it now): prod reads the same database.
Everything is new tables in a new schema, so nothing existing is touched. Rerunning is safe: a dataset already in
nhgis.datasets is skipped, a saved extract number is polled again instead of resubmitted.
Cite (owner, 2026-11-12; also on /data): Jonathan Schroeder, David Van Riper, Steven Manson, Grace Cooper, Zachary
Krause, Tracy Kugler, Tsu Zhu, and Steven Ruggles. IPUMS National Historical Geographic Information System: Version
21.0 [dataset]. Minneapolis, MN: IPUMS. 2026. http://doi.org/10.18128/D050.V21.0
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import resource
import sys
import time
import zipfile
from pathlib import Path

import httpx

from loader import db, offpeak

API = "https://api.ipums.org"
VERSION = "2"
BULK = Path(os.environ.get("NHGIS_DIR", "/bulk/nhgis"))
STATE_FILE = BULK / "state.json"
GEOG_LEVELS = ["state", "county", "place", "tract"]
# The default scope (owner said "all that data"; this is the latest of each, every table; older years and block
# groups can be added as more datasets here or with --datasets).
DEFAULT_DATASETS = ["2020_2024_ACS5a", "2020_DHCa"]
POLL_SECONDS = 60
CHUNK = 40              # tables per extract to start with; halved on "Excessive file width"
CITATION = ("Jonathan Schroeder, David Van Riper, Steven Manson, Grace Cooper, Zachary Krause, Tracy Kugler, Tsu Zhu, "
            "and Steven Ruggles. IPUMS National Historical Geographic Information System: Version 21.0 [dataset]. "
            "Minneapolis, MN: IPUMS. 2026. http://doi.org/10.18128/D050.V21.0")
MAX_WAIT_HOURS = 20
CONTEXT_COLUMNS = {"GISJOIN", "YEAR", "STUSAB", "GEOID", "GEOCODE", "NAME_E", "NAME_M", "NAME"}


def _key() -> str:
    key = os.environ.get("IPUMS_API_KEY", "").strip()
    if not key:
        sys.exit("IPUMS_API_KEY is not set (put it in .env)")
    return key


def _client() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": _key(), "User-Agent": "FURP furp.org nhgis loader"},
                        timeout=120, follow_redirects=True)


class NotRegistered(Exception):
    """The API key works but the IPUMS account is not registered for NHGIS (401 on the extracts endpoint)."""


class TooWide(Exception):
    """NHGIS refused the extract: too many columns for one file (400 "Excessive file width")."""


def _detail(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail", "")
        return " ".join(d) if isinstance(d, list) else str(d)
    except Exception:  # noqa: BLE001
        return r.text[:200]


def _check(r: httpx.Response) -> dict:
    if r.status_code == 401:
        raise NotRegistered(_detail(r) or "401 from the IPUMS API")
    if r.status_code == 400 and "file width" in _detail(r).lower():
        raise TooWide(_detail(r))
    if r.status_code != 200:
        raise httpx.HTTPStatusError(f"{r.status_code} from {r.url}: {_detail(r)[:300]}", request=r.request, response=r)
    return r.json()


def _get(client: httpx.Client, url: str, **params) -> dict:
    """GET with a pause on 429 (the metadata endpoints are rate limited)."""
    for attempt in range(6):
        r = client.get(url, params=params)
        if r.status_code != 429:
            return _check(r)
        time.sleep(5 * (attempt + 1))
    return _check(r)


# --- state ------------------------------------------------------------------------------------------------------

def _state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"extracts": {}}


def _save(state: dict) -> None:
    BULK.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True))


# --- the IPUMS API ------------------------------------------------------------------------------------------------

def dataset_meta(client: httpx.Client, name: str) -> dict:
    return _get(client, f"/metadata/nhgis/datasets/{name}", version=VERSION)


def extract_definition(meta: dict, geog_levels: list[str], tables: list[str] | None = None) -> dict:
    """The given data tables (default: every one) of the dataset at the geography levels it has (of those asked)."""
    have = {g["name"] for g in meta.get("geogLevels", [])}
    levels = [g for g in geog_levels if g in have]
    if not levels:
        raise ValueError(f"{meta['name']}: none of {geog_levels} among its geographies")
    tables = tables if tables is not None else [t["name"] for t in meta["dataTables"]]
    return {"datasets": {meta["name"]: {"dataTables": tables, "geogLevels": levels}},
            "dataFormat": "csv_no_header", "breakdownAndDataTypeLayout": "single_file",
            "description": f"FURP (furp.org): {meta['name']} {len(tables)} tables ({tables[0]}..{tables[-1]}) at "
                           f"{', '.join(levels)}"}


def submit(client: httpx.Client, definition: dict) -> dict:
    return _check(client.post("/extracts", params={"collection": "nhgis", "version": VERSION}, json=definition))


def extract_status(client: httpx.Client, number: int) -> dict:
    return _get(client, f"/extracts/{number}", collection="nhgis", version=VERSION)


def _link(links: dict, key: str) -> str | None:
    v = (links or {}).get(key)
    if isinstance(v, dict):
        return v.get("url")
    return v


def download(client: httpx.Client, url: str, dest: Path, status=print) -> Path:
    tmp = dest.with_suffix(".part")
    with client.stream("GET", url) as r, open(tmp, "wb") as f:
        r.raise_for_status()
        n = 0
        for chunk in r.iter_bytes(1 << 20):
            f.write(chunk)
            n += len(chunk)
            if n % (256 << 20) < (1 << 20):
                status(f"  {n / 1e9:.2f} GB")
    tmp.rename(dest)
    status(f"downloaded {dest} ({dest.stat().st_size / 1e9:.2f} GB)")
    return dest


# --- the codebook and the columns -----------------------------------------------------------------------------------

_VAR = re.compile(r"^\s*([A-Z0-9_]+):\s+(.*\S)\s*$")
_FIELD = re.compile(r"^\s*(Table \d+|Universe|Source code|NHGIS code):\s*(.*\S)\s*$")
_SUMMARY_TITLE = re.compile(r"^\s*\d+\.\s+(\S.*\S)\s*$")        # "1. Total Population" in the Data Summary


def parse_codebook(text: str) -> tuple[dict, dict]:
    """(tables, variables) from an NHGIS codebook: tables by NHGIS code -> {source_code, description, universe},
    variables by column name -> {nhgis_code, description}. Context fields (GISJOIN, NAME_E...) get nhgis_code None."""
    tables, variables = {}, {}
    cur = {"table": None, "universe": None, "source": None, "code": None}
    for line in text.splitlines():
        f = _FIELD.match(line)
        t = _SUMMARY_TITLE.match(line)
        if t and not f:
            cur = {"table": t.group(1), "universe": None, "source": None, "code": None}
            continue
        if f:
            label, value = f.group(1), f.group(2)
            if label.startswith("Table"):
                cur = {"table": value, "universe": None, "source": None, "code": None}
            elif label == "Universe":
                cur["universe"] = value
            elif label == "Source code":
                cur["source"] = value
            else:
                cur["code"] = value
                known = tables.setdefault(value, {"source_code": cur["source"] or value, "description": cur["table"],
                                                  "universe": cur["universe"]})
                known["description"] = known["description"] or cur["table"]
                known["universe"] = known["universe"] or cur["universe"]
            continue
        v = _VAR.match(line)
        if v and v.group(1).upper() == v.group(1):
            name = v.group(1)
            in_table = cur["code"] is not None and name.startswith(cur["code"])
            variables.setdefault(name, {"nhgis_code": cur["code"] if in_table else None, "description": v.group(2)})
        elif line.strip() in ("Context Fields", "Context Fields:") or line.strip().startswith("Data Type ("):
            cur = {"table": None, "universe": None, "source": None, "code": None}
    return tables, variables


_SUFFIX = re.compile(r"^[EM]?\d{3}[A-Z]?$")


def group_columns(columns: list[str], codes: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Split a CSV header into context columns and {nhgis code: [its columns]}; the longest matching code wins."""
    by_len = sorted(codes, key=len, reverse=True)
    context, groups = [], {}
    for c in columns:
        hit = next((k for k in by_len if c.startswith(k) and _SUFFIX.match(c[len(k):])), None)
        if hit:
            groups.setdefault(hit, []).append(c)
        else:
            context.append(c)
    return context, groups


_CODE = re.compile(r"^([A-Z0-9]{3,4}?)[EM]?\d{3}[A-Z]?$")


def infer_codes(columns: list[str]) -> list[str]:
    """Table codes from the column names alone (when the codebook could not be read): ASNQE001 -> ASNQ, U7H001 -> U7H."""
    out = []
    for c in columns:
        if c in CONTEXT_COLUMNS or c.endswith("A"):
            continue
        m = _CODE.match(c)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def pg_table(dataset: str, source_code: str) -> str:
    return "d_" + re.sub(r"[^a-z0-9]+", "_", f"{dataset}_{source_code}".lower())


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


# --- loading ------------------------------------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS nhgis;
CREATE TABLE IF NOT EXISTS nhgis.datasets (
    name text PRIMARY KEY, group_name text, description text, geog_levels text[], extract_number int,
    n_tables int, n_rows bigint, loaded_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS nhgis.tables (
    dataset text NOT NULL, source_code text NOT NULL, nhgis_code text, description text, universe text,
    pg_table text NOT NULL, n_variables int, PRIMARY KEY (dataset, source_code));
CREATE TABLE IF NOT EXISTS nhgis.variables (
    dataset text NOT NULL, column_name text NOT NULL, source_code text, nhgis_code text, data_type text,
    description text, PRIMARY KEY (dataset, column_name));
CREATE TABLE IF NOT EXISTS nhgis.geo (
    dataset text NOT NULL, gisjoin text NOT NULL, geog_level text NOT NULL, year text, name text, stusab text,
    geoid text, context jsonb, PRIMARY KEY (dataset, gisjoin));
CREATE INDEX IF NOT EXISTS geo_level_name ON nhgis.geo (dataset, geog_level, name);
"""

_CSV_RE = re.compile(r"_ds(\d+)_(\d+)_([a-z_0-9]+)\.csv$")


def _raise_open_files(n: int = 8192) -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < n:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(n, hard), hard))


def _data_type(col: str, code: str) -> str | None:
    rest = col[len(code):]
    return rest[0] if rest[:1] in ("E", "M") else None


def load_zip(path: Path, dataset: str, extract_number: int | None, status=print, made: set[str] | None = None) -> dict:
    """Load one extract zip (one dataset, one CSV per geography level) into schema nhgis. `made` carries the data
    tables already created in this run across a dataset's several extracts (each table is in exactly one)."""
    _raise_open_files()
    tmpdir = BULK / "tmp" / dataset
    tmpdir.mkdir(parents=True, exist_ok=True)
    totals = {"rows": 0, "tables": 0, "levels": []}
    with zipfile.ZipFile(path) as z, db.connect() as conn:
        conn.execute(SCHEMA_SQL)
        conn.commit()
        names = z.namelist()
        csvs = sorted(n for n in names if _CSV_RE.search(n))
        if not csvs:
            raise SystemExit(f"{path}: no NHGIS csv files inside ({names[:5]})")
        codebooks = {n for n in names if n.endswith("_codebook.txt")}
        table_meta: dict[str, dict] = {}
        var_meta: dict[str, dict] = {}
        for cb in sorted(codebooks):
            t, v = parse_codebook(z.read(cb).decode("utf-8", "replace"))
            table_meta.update(t)
            var_meta.update(v)
        codes = list(table_meta)
        made = made if made is not None else set()
        for csv_name in csvs:
            level = _CSV_RE.search(csv_name).group(3)
            status(f"{dataset} {level}: {csv_name}")
            with z.open(csv_name) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="latin-1", newline=""))
                header = next(reader)
                context, groups = group_columns(header, codes or infer_codes(header))
                if not groups:
                    raise SystemExit(f"{csv_name}: no data columns recognised in {header[:12]}")
                if "GISJOIN" not in context:
                    raise SystemExit(f"{csv_name}: no GISJOIN column")
                idx = {c: i for i, c in enumerate(header)}
                gi = idx["GISJOIN"]
                # One temp csv per census table, then one COPY each: far fewer round trips than row-by-row.
                files = {code: open(tmpdir / f"{code}_{level}.csv", "w", newline="", encoding="utf-8") for code in groups}
                writers = {code: csv.writer(f) for code, f in files.items()}
                col_idx = {code: [idx[c] for c in cols] for code, cols in groups.items()}
                geo_f = open(tmpdir / f"geo_{level}.csv", "w", newline="", encoding="utf-8")
                geo_w = csv.writer(geo_f)
                n = 0
                for row in reader:
                    if not row:
                        continue
                    gis = row[gi]
                    ctx = {c: row[idx[c]] for c in context if row[idx[c]] != ""}
                    name = ctx.get("NAME_E") or ctx.get("NAME") or ctx.get("NAME_M")
                    geo_w.writerow([dataset, gis, level, ctx.get("YEAR"), name, ctx.get("STUSAB"),
                                    ctx.get("GEOID") or ctx.get("GEOCODE"), json.dumps(ctx, ensure_ascii=False)])
                    for code, ix in col_idx.items():
                        writers[code].writerow([gis, level] + [row[i] if row[i] != "" else None for i in ix])
                    n += 1
                for f in files.values():
                    f.close()
                geo_f.close()
            status(f"  {n:,} rows, {len(groups)} tables; copying into Postgres")
            with conn.cursor() as cur:
                # Several extracts of one dataset carry the same geographies: keep the first copy of each.
                cur.execute("CREATE TEMP TABLE geo_in (LIKE nhgis.geo) ON COMMIT DROP")
                with open(tmpdir / f"geo_{level}.csv", "rb") as f, cur.copy(
                        "COPY geo_in (dataset, gisjoin, geog_level, year, name, stusab, geoid, context) "
                        "FROM STDIN WITH (FORMAT csv)") as cp:
                    while chunk := f.read(1 << 20):
                        cp.write(chunk)
                cur.execute("INSERT INTO nhgis.geo SELECT * FROM geo_in ON CONFLICT (dataset, gisjoin) DO NOTHING")
                for code, cols in groups.items():
                    meta = table_meta.get(code) or {"source_code": code, "description": None, "universe": None}
                    tname = pg_table(dataset, meta["source_code"])
                    full = f"nhgis.{_q(tname)}"
                    if tname not in made:
                        cur.execute(f"DROP TABLE IF EXISTS {full}")
                        cur.execute(f"CREATE TABLE {full} (gisjoin text NOT NULL, geog_level text NOT NULL, "
                                    + ", ".join(f"{_q(c.lower())} numeric" for c in cols) + ", PRIMARY KEY (gisjoin))")
                        cur.execute("INSERT INTO nhgis.tables (dataset, source_code, nhgis_code, description, universe, "
                                    "pg_table, n_variables) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (dataset, "
                                    "source_code) DO UPDATE SET nhgis_code = EXCLUDED.nhgis_code, description = "
                                    "EXCLUDED.description, universe = EXCLUDED.universe, pg_table = EXCLUDED.pg_table, "
                                    "n_variables = EXCLUDED.n_variables",
                                    (dataset, meta["source_code"], code, meta["description"], meta["universe"], tname,
                                     len(cols)))
                        cur.executemany("INSERT INTO nhgis.variables (dataset, column_name, source_code, nhgis_code, "
                                        "data_type, description) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (dataset, "
                                        "column_name) DO UPDATE SET description = EXCLUDED.description",
                                        [(dataset, c.lower(), meta["source_code"], code, _data_type(c, code),
                                          (var_meta.get(c) or {}).get("description")) for c in cols])
                        made.add(tname)
                    with open(tmpdir / f"{code}_{level}.csv", "rb") as f, cur.copy(
                            f"COPY {full} (gisjoin, geog_level, " + ", ".join(_q(c.lower()) for c in cols)
                            + ") FROM STDIN WITH (FORMAT csv)") as cp:
                        while chunk := f.read(1 << 20):
                            cp.write(chunk)
                    (tmpdir / f"{code}_{level}.csv").unlink()
                (tmpdir / f"geo_{level}.csv").unlink()
            conn.commit()
            totals["rows"] += n
            totals["levels"].append(level)
            status(f"  {level} done")
        totals["tables"] = len(made)
        # Context columns are described too (GISJOIN, YEAR, NAME_E...), for the catalog.
        conn.cursor().executemany(
            "INSERT INTO nhgis.variables (dataset, column_name, source_code, nhgis_code, data_type, description) "
            "VALUES (%s, %s, NULL, NULL, NULL, %s) ON CONFLICT DO NOTHING",
            [(dataset, c.lower(), v["description"]) for c, v in var_meta.items() if v["nhgis_code"] is None])
        conn.commit()
    status(f"{dataset} #{extract_number}: {len(groups) if csvs else 0} tables, {totals['rows']:,} geography rows "
           f"({', '.join(totals['levels'])})")
    return totals


def describe_dataset(client: httpx.Client, dataset: str, status=print) -> None:
    """Group and description from the metadata API into nhgis.datasets (after a load)."""
    try:
        meta = dataset_meta(client, dataset)
    except Exception as ex:  # noqa: BLE001
        status(f"{dataset}: metadata not updated ({ex})")
        return
    with db.connect() as conn:
        conn.execute("UPDATE nhgis.datasets SET group_name = %s, description = %s WHERE name = %s",
                     (meta.get("group"), meta.get("description"), dataset))
        conn.commit()


# --- the run ------------------------------------------------------------------------------------------------------

def loaded_datasets() -> set[str]:
    with db.connect() as conn:
        if not conn.execute("SELECT to_regclass('nhgis.datasets')").fetchone()[0]:
            return set()
        return {r[0] for r in conn.execute("SELECT name FROM nhgis.datasets")}


def _submit_next(client, ds: str, meta: dict, state: dict, status) -> dict | None:
    """Submit the next extract of up to CHUNK tables (halved while NHGIS calls it too wide); None when every table
    has been submitted. One extract is in flight at a time (owner, 2026-11-12: NHGIS queues them, so no flood)."""
    done_tables = {t for ex in state["extracts"].get(ds, []) for t in ex["tables"]}
    pending = [t["name"] for t in meta["dataTables"] if t["name"] not in done_tables]
    if not pending:
        return None
    size = state.get("chunk", {}).get(ds, CHUNK)
    while True:
        chunk = pending[:size]
        try:
            r = submit(client, extract_definition(meta, GEOG_LEVELS, chunk))
            break
        except TooWide:
            if size == 1:
                raise
            size = max(1, size // 2)
            status(f"{ds}: {len(chunk)} tables too wide for one extract; trying {size}")
    ex = {"number": r["number"], "status": r.get("status"), "tables": chunk, "submitted": time.strftime("%F %T")}
    state["extracts"].setdefault(ds, []).append(ex)
    state.setdefault("chunk", {})[ds] = size
    _save(state)
    status(f"{ds}: extract #{r['number']} {r.get('status')}: {len(chunk)} tables ({chunk[0]}..{chunk[-1]})")
    return ex


def _wait_and_fetch(client, ds: str, ex: dict, state: dict, status) -> Path | None:
    dest = BULK / f"{ds}_extract{ex['number']}.zip"
    if dest.exists():
        return dest
    t0 = time.time()
    while True:
        st = extract_status(client, ex["number"])
        if st.get("status") != ex.get("status"):
            ex["status"] = st.get("status")
            _save(state)
            status(f"{ds}: extract #{ex['number']} {ex['status']}")
        if st.get("status") == "completed":
            break
        if st.get("status") in ("failed", "canceled"):
            status(f"{ds}: extract #{ex['number']} {st.get('status')}; remove it from {STATE_FILE} to resubmit")
            return None
        if time.time() - t0 > MAX_WAIT_HOURS * 3600:
            status(f"{ds}: #{ex['number']} still {st.get('status')} after {MAX_WAIT_HOURS} h; run again later")
            return None
        time.sleep(POLL_SECONDS)
    url = _link(st.get("downloadLinks") or {}, "tableData")
    if not url:
        status(f"{ds}: #{ex['number']} completed but no tableData link: {st.get('downloadLinks')}")
        return None
    status(f"{ds}: extract #{ex['number']} ready; downloading")
    return download(client, url, dest, status)


def _load_ready(ds: str, state: dict, made: set[str], status, force: bool = False) -> tuple[int, list[str]]:
    """Load every downloaded, not yet loaded extract of the dataset: in the quiet hours (or NP_NOW=1), or when
    `force` (the end of the run waits for the quiet hours first). Returns (geography rows, levels)."""
    rows, levels = 0, []
    for ex in state["extracts"].get(ds, []):
        path = BULK / f"{ds}_extract{ex['number']}.zip"
        if ex.get("loaded") or not path.exists():
            continue
        if not (force or offpeak.is_quiet() or os.environ.get("NP_NOW") == "1"):
            continue
        t = load_zip(path, ds, ex["number"], status, made)
        rows, levels = max(rows, t["rows"]), t["levels"] or levels
        ex["loaded"] = time.strftime("%F %T")
        _save(state)
    return rows, levels


def run(datasets: list[str], wait_for_registration: bool, status=print) -> int:
    BULK.mkdir(parents=True, exist_ok=True)
    done = loaded_datasets()
    todo = [d for d in datasets if d not in done]
    if not todo:
        status(f"nothing to do: {', '.join(datasets)} already loaded")
        return 0
    state = _state()
    with _client() as client:
        for ds in todo:
            while True:
                try:
                    meta = dataset_meta(client, ds)
                    break
                except NotRegistered as ex:
                    if not wait_for_registration:
                        status(f"not registered for NHGIS: {ex}")
                        return 2
                    status(f"{time.strftime('%H:%M')} waiting for NHGIS registration ({str(ex)[:90]}); retry in 10 min")
                    time.sleep(600)
            made: set[str] = set()
            rows, levels = 0, []
            while True:
                # The next extract: one already submitted and not yet downloaded, else submit the next chunk.
                ex = next((e for e in state["extracts"].get(ds, [])
                           if not (BULK / f"{ds}_extract{e['number']}.zip").exists()), None)
                if ex is None:
                    ex = _submit_next(client, ds, meta, state, status)
                if ex is None:
                    break
                if _wait_and_fetch(client, ds, ex, state, status) is None:
                    return 3
                r, lv = _load_ready(ds, state, made, status)
                rows, levels = max(rows, r), lv or levels
            offpeak.wait(f"nhgis {ds} load", status)
            r, lv = _load_ready(ds, state, made, status, force=True)
            rows, levels = max(rows, r), lv or levels
            n_tables = sum(len(e["tables"]) for e in state["extracts"][ds])
            with db.connect() as conn:
                conn.execute("INSERT INTO nhgis.datasets (name, geog_levels, extract_number, n_tables, n_rows, loaded_at) "
                             "VALUES (%s, %s, %s, %s, %s, now()) ON CONFLICT (name) DO UPDATE SET geog_levels = "
                             "EXCLUDED.geog_levels, extract_number = EXCLUDED.extract_number, n_tables = "
                             "EXCLUDED.n_tables, n_rows = EXCLUDED.n_rows, loaded_at = now()",
                             (ds, levels, state["extracts"][ds][0]["number"], n_tables, rows))
                conn.commit()
            describe_dataset(client, ds, status)
            status(f"{ds}: loaded, {n_tables} tables over {len(state['extracts'][ds])} extracts")
    return 0


def show_status(status=print) -> None:
    state = _state()
    for ds, exs in state["extracts"].items():
        for ex in (exs if isinstance(exs, list) else [exs]):
            status(f"{ds}: #{ex['number']} {ex.get('status')} {len(ex.get('tables', []))} tables"
                   f"{' loaded ' + ex['loaded'] if ex.get('loaded') else ''}")
    status(f"files: {sorted(p.name for p in BULK.glob('*.zip')) if BULK.exists() else []}")
    with db.connect() as conn:
        if conn.execute("SELECT to_regclass('nhgis.datasets')").fetchone()[0]:
            for r in conn.execute("SELECT name, n_tables, n_rows, geog_levels, loaded_at FROM nhgis.datasets ORDER BY 1"):
                status(f"loaded: {r}")
        else:
            status("loaded: nothing yet")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--datasets", nargs="+", default=DEFAULT_DATASETS)
    r.add_argument("--wait-for-registration", action="store_true")
    sub.add_parser("status")
    ld = sub.add_parser("load")
    ld.add_argument("zip")
    ld.add_argument("--dataset", help="dataset name (default: from the file name before _extract)")
    a = p.parse_args(argv)
    if a.cmd == "run":
        return run(a.datasets, a.wait_for_registration)
    if a.cmd == "status":
        show_status()
        return 0
    path = Path(a.zip)
    ds = a.dataset or path.name.split("_extract")[0]
    offpeak.wait(f"nhgis {ds} load")
    load_zip(path, ds, None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
