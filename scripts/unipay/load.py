"""Task 2: parse downloaded files and load them into unipay staging tables.

Usage: load.py <key> [<key> ...] | all-pending      (DB writes; respects the 23:30-01:30 blackout)
Each key's files come from ~/unipay-data/<key>/manifest.json (written by fetch.py).
Re-running a key replaces that key's rows (idempotent).
"""
import datetime as dt
import json
import random
import sys
import time

from common import (DATA, connect, load_progress, name_norm, save_progress, wait_for_window)
import parsers

DDL = """
CREATE TABLE IF NOT EXISTS unipay.public_payroll_sources (
  id serial PRIMARY KEY,
  catalog_source_id integer REFERENCES unipay.university_pay_sources(id),
  source_key text NOT NULL,
  state char(2) NOT NULL,
  institution_or_system text,
  url text,
  file_name text,
  file_sha256 text,
  bytes bigint,
  retrieved_at timestamptz,
  notes text
);
CREATE TABLE IF NOT EXISTS unipay.public_payroll_records (
  id bigserial PRIMARY KEY,
  source_id integer NOT NULL REFERENCES unipay.public_payroll_sources(id) ON DELETE CASCADE,
  state char(2) NOT NULL,
  institution text,
  person_name text,
  name_norm text,
  title text,
  department text,
  base_pay numeric,
  other_pay numeric,
  total_pay numeric,
  pay_components jsonb,
  fiscal_year integer,
  source_url text,
  retrieved_at timestamptz,
  raw jsonb
);
CREATE INDEX IF NOT EXISTS public_payroll_records_source ON unipay.public_payroll_records (source_id);
"""

COLS = ("source_id", "state", "institution", "person_name", "name_norm", "title", "department", "base_pay",
        "other_pay", "total_pay", "pay_components", "fiscal_year", "source_url", "retrieved_at", "raw")
BATCH = 5000


def catalog_id(cur, state, url_like):
    cur.execute("SELECT id FROM unipay.university_pay_sources WHERE state=%s AND (url ILIKE %s OR download_url ILIKE %s) ORDER BY id LIMIT 1",
                (state, url_like, url_like))
    r = cur.fetchone()
    return r[0] if r else None


def clean_num(x):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if x != x or abs(x) > 1e12:  # NaN or overflow
        return None
    return round(x, 2)


def jdump(d):
    def default(o):
        if isinstance(o, (dt.date, dt.datetime)):
            return o.isoformat()
        return str(o)
    return json.dumps(d, default=default, ensure_ascii=False).replace("\\u0000", "")


def load_key(conn, key):
    spec = parsers.SPECS[key]
    dkey = spec.get("data_key", key)  # several source keys may share one download folder
    m = json.loads((DATA / dkey / "manifest.json").read_text())
    with conn.cursor() as cur:
        cid = catalog_id(cur, spec.get("catalog_state", spec["state"]), spec["catalog_url_like"])
        if cid is None:
            print(f"!! no catalog row for {key}; loading with NULL catalog id")
        cur.execute("DELETE FROM unipay.public_payroll_records WHERE source_id IN (SELECT id FROM unipay.public_payroll_sources WHERE source_key=%s)", (key,))
        cur.execute("DELETE FROM unipay.public_payroll_sources WHERE source_key=%s", (key,))
    conn.commit()
    total = 0
    for fname, meta in sorted(m["files"].items()):
        if spec.get("file_filter") and not spec["file_filter"](fname):
            continue
        path = DATA / dkey / fname
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO unipay.public_payroll_sources
                (catalog_source_id, source_key, state, institution_or_system, url, file_name, file_sha256, bytes, retrieved_at, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (cid, key, spec["state"], spec["system"], meta["url"], f"~/unipay-data/{dkey}/{fname}", meta["sha256"],
                         meta["bytes"], meta["retrieved_at"], meta.get("notes") or spec.get("notes")))
            sid = cur.fetchone()[0]
        conn.commit()
        n = 0
        batch = []

        def flush():
            wait_for_window()  # never write during the nightly production load window
            with conn.cursor() as cur:
                with cur.copy(f"COPY unipay.public_payroll_records ({','.join(COLS)}) FROM STDIN") as cp:
                    for row in batch:
                        cp.write_row(row)
            conn.commit()
            batch.clear()
            time.sleep(0.3)

        for rec in spec["parse"](path, fname):
            pname = rec.get("person_name")
            pname = " ".join(str(pname).split()) if pname else None
            batch.append((sid, spec["state"], rec.get("institution"), pname, rec.get("name_norm") or name_norm(pname),
                          (rec.get("title") or None) and str(rec["title"]).strip()[:500],
                          (rec.get("department") or None) and str(rec["department"]).strip()[:500],
                          clean_num(rec.get("base_pay")), clean_num(rec.get("other_pay")), clean_num(rec.get("total_pay")),
                          jdump(rec.get("pay_components") or {}), rec.get("fiscal_year"), meta["url"], meta["retrieved_at"],
                          jdump(rec.get("raw") or {})))
            n += 1
            if len(batch) >= BATCH:
                flush()
        if batch:
            flush()
        total += n
        print(f"  {key}/{fname}: {n:,} rows", flush=True)
    with conn.cursor() as cur:
        if cid:
            cur.execute("""UPDATE unipay.university_pay_sources u SET loaded = true,
                 rows_loaded = (SELECT count(*) FROM unipay.public_payroll_records r JOIN unipay.public_payroll_sources s ON s.id=r.source_id
                                WHERE s.catalog_source_id=u.id) WHERE u.id=%s""", (cid,))
    conn.commit()
    return total, cid


def ddl_only():
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def main():
    keys = sys.argv[1:]
    if keys == ["--ddl"]:
        return ddl_only()
    prog = load_progress()
    if keys == ["all-pending"]:
        keys = [k for k in parsers.ORDER if prog["sources"].get(k, {}).get("status") != "loaded"]
    conn = connect()
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    for key in keys:
        if not (DATA / parsers.SPECS.get(key, {}).get("data_key", key) / "manifest.json").exists():
            print(f"-- {key}: not downloaded; skipping")
            prog["sources"][key] = {"status": "skipped", "reason": "no downloaded files", "at": dt.datetime.now().isoformat()}
            save_progress(prog)
            continue
        wait_for_window()
        t0 = time.time()
        print(f"== {key} {dt.datetime.now():%H:%M:%S}", flush=True)
        try:
            n, cid = load_key(conn, key)
            prog["sources"][key] = {"status": "loaded", "rows": n, "catalog_source_id": cid,
                                    "at": dt.datetime.now().isoformat(), "seconds": round(time.time() - t0)}
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            print(f"!! {key} failed: {type(e).__name__}: {e}", flush=True)
            prog["sources"][key] = {"status": "failed", "error": f"{type(e).__name__}: {str(e)[:300]}", "at": dt.datetime.now().isoformat()}
        save_progress(prog)


if __name__ == "__main__":
    random.seed(1)
    main()
