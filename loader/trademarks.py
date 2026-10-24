"""USPTO trademarks: case files (the mark, serial and registration numbers, dates, status, classes, goods and
services) with their owners, from the Trademark Case Files Dataset (product TRCFECO2), and recorded assignments
from the Trademark Assignment Dataset (TRASECO). Bulk files only (loader/uspto.py downloads and counts them).

- What's loaded: case_file.csv, owner.csv, classification.csv, statement.csv (goods and services statements only,
  type GS...); the assignment files tm_assignment, tm_convey, tm_assignor, tm_assignee and tm_docid.
- How far back (owner, 2026-10-24): marks filed in the last 20 years (uspto.CUTOFF), plus older marks that are still
  live (registered, not cancelled, abandoned or expired), since a renewed mark doesn't expire. Newest first, in
  filing-date parts (PARTS). Assignments: those naming a loaded mark.
- The case file dataset is published yearly; the latest release (March 2024) runs through 2023, so applications
  filed since then are not here yet. Assignments run through 2025.
- Status: TRCFECO2 has the status code but no descriptions, so the page's status is read from the dates (abandoned,
  cancelled, registered, renewed) and the code ranges for abandonment, cancellation and expiry, with the code itself
  and a link to the USPTO's TSDR record for the exact current status.
- Every row records its source product (TRCFECO2 or TRASECO) and that file's release date.

Usage: .venv/bin/python -m loader.trademarks [marks [PART ...]] | assignments | summaries | links | all
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
import time

from loader import db, uspto
from loader.uspto import clean, date_any, log

CF, TA = "TRCFECO2", "TRASECO"
CASE_FILES = ["case_file.csv.zip", "owner.csv.zip", "classification.csv.zip", "statement.csv.zip"]
ASSIGN_FILES = ["2025_tm_assignment.csv.zip", "2025_tm_convey.csv.zip", "2025_tm_assignor.csv.zip",
                "2025_tm_assignee.csv.zip", "2025_tm_docid.csv.zip"]
# Filing-date parts, newest first; "live-older" is marks filed before the cutoff that are still live.
PARTS = [("2020-", dt.date(2020, 1, 1), None), ("2014-2019", dt.date(2014, 1, 1), dt.date(2020, 1, 1)),
         ("cutoff-2013", uspto.CUTOFF, dt.date(2014, 1, 1)), ("live-older", None, uspto.CUTOFF)]
BATCH = 20000
GOODS_MAX = 3000
OWNER_TYPES = {"10": "Original applicant", "20": "Owner at publication", "30": "Original registrant"}


def owner_type_label(code: str | None) -> str:
    c = (code or "").strip()
    if c in OWNER_TYPES:
        return OWNER_TYPES[c]
    if re.fullmatch(r"1[1-9]", c):
        return "New applicant before publication"
    if re.fullmatch(r"2[1-9]", c):
        return "New applicant after publication"
    if re.fullmatch(r"3[1-9]", c):
        return "New owner after registration"
    return f"Owner (party code {c})" if c else "Owner"


def is_dead(status: str | None, abandon: dt.date | None, cancel: dt.date | None) -> bool:
    """Abandoned, cancelled or expired: by date, or by the code ranges USPTO uses for those (600-618 abandoned,
    626 and 709-714 cancelled, 900 expired, 401-404 cancelled or abandoned in a proceeding)."""
    if abandon or cancel:
        return True
    try:
        s = int(status or 0)
    except ValueError:
        return False
    return 600 <= s <= 618 or s == 626 or 709 <= s <= 714 or s == 900 or 401 <= s <= 404


def status_label(m: dict) -> str:
    """What the page says for status (the code and TSDR give the exact one)."""
    s = int(m["status_code"]) if (m.get("status_code") or "").isdigit() else 0
    if m.get("abandon_date"):
        return "Abandoned"
    if m.get("cancel_date") or s == 626 or 709 <= s <= 714 or 401 <= s <= 404:
        return "Registration cancelled"
    if s == 900:
        return "Expired"
    if 600 <= s <= 618:
        return "Abandoned"
    if m.get("registration_date"):
        return "Registered and renewed" if m.get("renewal_date") else "Registered"
    return "Pending application"


def owner_key(core: str, state: str | None) -> str:
    return hashlib.sha1(f"{core}|{(state or '').upper()}".encode()).hexdigest()[:12]


def mark_norm(v: str | None) -> str | None:
    s = " ".join(re.sub(r"[^a-z0-9]+", " ", (v or "").lower()).split())
    return s or None


def tsdr_url(serial: str) -> str:
    return f"https://tsdr.uspto.gov/#caseNumber={serial}&caseType=SERIAL_NO&searchType=statusSearch"


def _serial(v) -> int | None:
    v = (v or "").strip()
    return int(v) if v.isdigit() else None


# --- marks -------------------------------------------------------------------------------------------------------

def load_part(name: str, start: dt.date | None, end: dt.date | None, status=log) -> int:
    t0 = time.time()
    path = lambda f: uspto.DATA / CF / f  # noqa: E731
    dates = {f: uspto.file_date(CF, f) for f in CASE_FILES}
    mcols = ["serial_no", "registration_no", "mark", "mark_norm", "filing_date", "registration_date", "status_code",
             "status_date", "abandon_date", "cancel_date", "renewal_date", "mark_draw_code", "live", "src_product",
             "src_date"]
    ids: set[int] = set()
    with db.connect() as conn:
        done = lambda step, f: uspto.step_done(CF, f, name, step)  # noqa: E731

        def mark_step(step, f, n):
            uspto.mark_step(conn, CF, f, name, step, n)
            uspto.checkpoint("trademarks", part=name, step=step, rows_=n, newest=end or dt.date.today(),
                             oldest=start)
            uspto.status_line(f"{step} done for marks filed {name}; continuing {uspto.current()}")

        conn.execute("SET work_mem = '256MB'")
        if not done("marks", "case_file.csv.zip"):
            conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_tm_part (LIKE tm_marks INCLUDING DEFAULTS)")
            conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_tm_goods (serial_no text, k text, txt text)")
            conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_tm_class (serial_no text, cls text)")
            conn.execute("TRUNCATE stage_tm_part, stage_tm_goods, stage_tm_class")
            conn.commit()
            # 1. Case files in the part's window.
            with conn.cursor() as cur, cur.copy(f"COPY stage_tm_part ({', '.join(mcols)}) FROM STDIN") as cp:
                for r in uspto.rows(path("case_file.csv.zip")):
                    sn = _serial(r["serial_no"])
                    if sn is None:
                        continue
                    fd = date_any(r["filing_dt"])
                    ab, ca = date_any(r["abandon_dt"]), date_any(r["reg_cancel_dt"])
                    dead = is_dead(r["cfh_status_cd"], ab, ca)
                    if start is None:            # older marks: only those still live and registered
                        if (fd and fd >= end) or dead or not r["registration_dt"]:
                            continue
                    elif not fd or fd < start or (end and fd >= end):
                        continue
                    ids.add(sn)
                    cp.write_row((str(sn), clean(r["registration_no"].lstrip("0") if r["registration_no"] else None, 20),
                                  clean(r["mark_id_char"], 1000), (mark_norm(r["mark_id_char"]) or "")[:1000] or None, fd,
                                  date_any(r["registration_dt"]), clean(r["cfh_status_cd"], 10), date_any(r["cfh_status_dt"]),
                                  ab, ca, date_any(r["renewal_dt"]), clean(r["mark_draw_cd"], 10), not dead, CF,
                                  dates["case_file.csv.zip"]))
            status(f"trademarks {name}: {len(ids):,} marks ({time.time() - t0:.0f}s)")
            # 2. Classes and goods and services, staged and joined in on insert.
            with conn.cursor() as cur, cur.copy("COPY stage_tm_class FROM STDIN") as cp:
                for r in uspto.rows(path("classification.csv.zip")):
                    sn = _serial(r["serial_no"])
                    if sn in ids and r.get("class_primary_cd"):
                        cp.write_row((str(sn), r["class_primary_cd"].strip()[:10]))
            with conn.cursor() as cur, cur.copy("COPY stage_tm_goods FROM STDIN") as cp:
                for r in uspto.rows(path("statement.csv.zip")):
                    if not (r.get("statement_type_cd") or "").startswith("GS"):
                        continue
                    sn = _serial(r["serial_no"])
                    if sn in ids and r.get("statement_text"):
                        cp.write_row((str(sn), r["statement_type_cd"], r["statement_text"].strip()[:GOODS_MAX]))
            conn.execute(f"""
                INSERT INTO tm_marks ({', '.join(mcols)}, classes, goods)
                SELECT {', '.join('p.' + c for c in mcols)}, c.cl, g.gs
                FROM stage_tm_part p
                LEFT JOIN (SELECT serial_no, string_agg(DISTINCT cls, ', ' ORDER BY cls) AS cl FROM stage_tm_class
                           GROUP BY 1) c USING (serial_no)
                LEFT JOIN (SELECT serial_no, left(string_agg(txt, ' | ' ORDER BY k), {GOODS_MAX}) AS gs FROM stage_tm_goods
                           GROUP BY 1) g USING (serial_no)
                ON CONFLICT {uspto.upsert('tm_marks', ['serial_no'], mcols + ['classes', 'goods'])}, loaded = now()""")
            conn.execute("TRUNCATE stage_tm_part, stage_tm_goods, stage_tm_class")
            conn.commit()
            status(f"trademarks {name}: marks with classes and goods in ({time.time() - t0:.0f}s)")
            mark_step("marks", "case_file.csv.zip", len(ids))
        else:
            ids = {int(r[0]) for r in conn.execute(
                "SELECT serial_no FROM tm_marks WHERE " + ("filing_date >= %s AND filing_date < %s" if start else
                "(filing_date < %s OR filing_date IS NULL) AND live"),
                ((start, end or dt.date(2100, 1, 1)) if start else (end,))).fetchall()}
            status(f"trademarks {name}: marks already in ({len(ids):,}), carrying on from the checkpoint")

        # 3. Owners (every party listed: original applicant, owner at publication, registrant, later owners).
        if not done("owners", "owner.csv.zip"):
            from loader.recalls import core
            ocols = ["serial_no", "seq", "owner_type", "name", "name_core", "owner_key", "entity", "city", "state", "country",
                     "src_product", "src_date"]
            batch, no = [], 0
            for r in uspto.rows(path("owner.csv.zip")):
                sn = _serial(r["serial_no"])
                if sn not in ids:
                    continue
                nm = clean(r["own_name"], 500)
                c = core(nm)[:500] or None
                st = uspto.state_code(r.get("own_addr_state_cd")) or None
                batch.append((str(sn), int(r["own_seq"]) if (r.get("own_seq") or "").isdigit() else 0,
                              clean(r["own_type_cd"], 10) or "", nm, c, owner_key(c, st) if c else None,
                              clean(r.get("own_entity_desc"), 100) or clean(r.get("own_entity_cd"), 10),
                              clean(r.get("own_addr_city"), 100), st, clean(r.get("own_addr_country_cd"), 10), CF,
                              dates["owner.csv.zip"]))
                no += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "tm_owners", ocols, batch,
                               uspto.upsert("tm_owners", ["serial_no", "seq", "owner_type"], ocols))
            uspto.bulk(conn, "tm_owners", ocols, batch, uspto.upsert("tm_owners", ["serial_no", "seq", "owner_type"], ocols))
            mark_step("owners", "owner.csv.zip", no)
        uspto.drop_stages(conn)
    status(f"trademarks {name}: done in {time.time() - t0:.0f}s")
    return len(ids)


def load_marks(parts: list[str] | None = None, status=log) -> int:
    n = 0
    todo = [x for x in PARTS if not parts or x[0] in parts]
    for k, (name, start, end) in enumerate(todo):
        uspto.next_up(f"trademarks filed {name} (part {k + 1} of {len(todo)}), ETA about "
                      f"{20 * (len(todo) - k)} min for the parts left")
        n += load_part(name, start, end, status)
    with db.connect() as conn:
        for f in CASE_FILES:
            uspto.record_run(conn, CF, f, n)
    return n


# --- assignments -------------------------------------------------------------------------------------------------

def load_assignments(status=log) -> int:
    """Recorded assignments, security interests, name changes and other conveyances on loaded marks; a bitmap of
    the relevant rf_ids (reel and frame) filters the other files."""
    t0 = time.time()
    path = lambda f: uspto.DATA / TA / f  # noqa: E731
    dates = {f: uspto.file_date(TA, f) for f in ASSIGN_FILES}
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        part = f"{conn.execute('SELECT count(*) FROM tm_marks').fetchone()[0]}-marks"
        done = lambda step, f: uspto.step_done(TA, f, part, step)  # noqa: E731

        def mark_step(step, f, n):
            uspto.mark_step(conn, TA, f, part, step, n)
            uspto.checkpoint("tm_assignments", part=part, step=step, rows_=n)
            uspto.status_line(f"trademark assignment {step} done; continuing {uspto.current()}")
        dcols = ["rf_id", "serial_no", "registration_no", "src_product", "src_date"]
        batch = []
        conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_tm_assignment_docs (LIKE tm_assignment_docs)")

        def docs():
            if not batch:
                return
            conn.execute("TRUNCATE stage_tm_assignment_docs")
            with conn.cursor() as cur, cur.copy(f"COPY stage_tm_assignment_docs ({', '.join(dcols)}) FROM STDIN") as cp:
                for r in batch:
                    cp.write_row(r)
            conn.execute(f"""INSERT INTO tm_assignment_docs ({', '.join(dcols)})
                             SELECT DISTINCT ON (s.rf_id, s.serial_no) {', '.join('s.' + c for c in dcols)}
                             FROM stage_tm_assignment_docs s JOIN tm_marks m USING (serial_no)
                             ON CONFLICT {uspto.upsert('tm_assignment_docs', ['rf_id', 'serial_no'], dcols)}""")
            conn.commit()
            batch.clear()
        if not done("docs", "2025_tm_docid.csv.zip"):
            nd = 0
            for r in uspto.rows(path("2025_tm_docid.csv.zip")):
                sn = _serial(r.get("serial"))
                if sn is None or not (r.get("rf_id") or "").isdigit():
                    continue
                batch.append((str(int(r["rf_id"])), str(sn), clean((r.get("reg_no") or "").lstrip("0"), 20), TA,
                              dates["2025_tm_docid.csv.zip"]))
                nd += 1
                if len(batch) >= BATCH:
                    docs()
            docs()
            mark_step("docs", "2025_tm_docid.csv.zip", nd)
        rfs = [int(r[0]) for r in conn.execute("SELECT DISTINCT rf_id FROM tm_assignment_docs").fetchall()]
        bits = bytearray((max(rfs) >> 3) + 1 if rfs else 1)
        for rf in rfs:
            bits[rf >> 3] |= 1 << (rf & 7)

        def has(v):
            if not (v or "").isdigit():
                return None
            rf = int(v)
            return rf if rf < (len(bits) << 3) and bits[rf >> 3] >> (rf & 7) & 1 else None
        status(f"trademark assignments: {len(rfs):,} recorded documents name loaded marks ({time.time() - t0:.0f}s)")
        del rfs
        n = 0
        if not done("assignments", "2025_tm_assignment.csv.zip"):
            conv = {}
            for r in uspto.rows(path("2025_tm_convey.csv.zip")):
                rf = has(r["rf_id"])
                if rf is not None:
                    conv[rf] = clean(r.get("conv_group"), 40)
            cols = ["rf_id", "reel_no", "frame_no", "record_date", "convey_text", "convey_type", "src_product",
                    "src_date"]
            for r in uspto.rows(path("2025_tm_assignment.csv.zip")):
                rf = has(r["rf_id"])
                if rf is None:
                    continue
                batch.append((str(rf), int(r["reel_no"]) if (r.get("reel_no") or "").isdigit() else None,
                              int(r["frame_no"]) if (r.get("frame_no") or "").isdigit() else None,
                              date_any(r["record_dt"]), clean(r["convey_text"], 1000), conv.get(rf), TA,
                              dates["2025_tm_assignment.csv.zip"]))
                n += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "tm_assignments", cols, batch, uspto.upsert("tm_assignments", ["rf_id"], cols))
            uspto.bulk(conn, "tm_assignments", cols, batch, uspto.upsert("tm_assignments", ["rf_id"], cols))
            del conv
            mark_step("assignments", "2025_tm_assignment.csv.zip", n)
            mark_step("assignments", "2025_tm_convey.csv.zip", n)
        from loader.recalls import core
        pcols = ["rf_id", "role", "seq", "name", "name_core", "exec_date", "city", "state", "country", "entity",
                 "src_product", "src_date"]
        for f, role, p in (("2025_tm_assignor.csv.zip", "assignor", "or"), ("2025_tm_assignee.csv.zip", "assignee", "ee")):
            if done(role, f):
                continue
            seqs, k = {}, 0
            for r in uspto.rows(path(f)):
                rf = has(r["rf_id"])
                if rf is None:
                    continue
                nm = clean(r.get(f"{p}_name"), 500)
                seq = seqs[rf] = seqs.get(rf, -1) + 1
                if len(seqs) > 200000:
                    seqs = {rf: seq}
                batch.append((str(rf), role, seq, nm, core(nm)[:500] or None, date_any(r.get("exec_dt")),
                              clean(r.get(f"{p}_city"), 100), uspto.state_code(r.get(f"{p}_state")),
                              clean(r.get(f"{p}_country"), 60), clean(r.get(f"{p}_legal_entity_text"), 100), TA, dates[f]))
                k += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "tm_assignment_parties", pcols, batch,
                               uspto.upsert("tm_assignment_parties", ["rf_id", "role", "seq"], pcols))
            uspto.bulk(conn, "tm_assignment_parties", pcols, batch,
                       uspto.upsert("tm_assignment_parties", ["rf_id", "role", "seq"], pcols))
            status(f"trademark assignments: {k:,} {role}s ({time.time() - t0:.0f}s)")
            mark_step(role, f, k)
        n = conn.execute("SELECT count(*) FROM tm_assignments").fetchone()[0]
        for f in ASSIGN_FILES:
            uspto.record_run(conn, TA, f, n)
        uspto.drop_stages(conn)
    status(f"trademark assignments: {n:,} assignments in {time.time() - t0:.0f}s")
    return n


# --- summaries and links -----------------------------------------------------------------------------------------

def summaries(status=log) -> None:
    """tm_owner_orgs: one row per owner (core name and state), rebuilt beside the live table and swapped in."""
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("DROP TABLE IF EXISTS tm_owner_orgs_new")
        conn.execute("CREATE TABLE tm_owner_orgs_new (LIKE tm_owner_orgs INCLUDING ALL)")
        conn.execute("""
            INSERT INTO tm_owner_orgs_new
            SELECT o.owner_key, mode() WITHIN GROUP (ORDER BY o.name), min(o.name_core), min(o.state),
                   mode() WITHIN GROUP (ORDER BY o.country), mode() WITHIN GROUP (ORDER BY o.entity),
                   count(DISTINCT o.serial_no), count(DISTINCT o.serial_no) FILTER (WHERE m.live),
                   min(m.filing_date), max(m.filing_date), 'TRCFECO2', max(o.src_date)
            FROM tm_owners o JOIN tm_marks m USING (serial_no)
            WHERE o.owner_key IS NOT NULL GROUP BY o.owner_key""")
        db.swap_table(conn, "tm_owner_orgs")
        conn.commit()
    status(f"trademarks: owner summaries ({time.time() - t0:.0f}s)")


def links(status=log) -> dict:
    """Owners to nonprofits, colleges, Form D issuers, state registrations and SEC filers, with the same EXACT and
    FUZZY rules as patent assignees (loader/patents.org_links). Owners that are people (entity "INDIVIDUAL") are
    left out."""
    from loader import patents
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("DELETE FROM ip_links WHERE src_kind = 'tm_owner'")
        conn.commit()
        n = patents.org_links(conn, "tm_owner", """SELECT owner_key, name, state FROM tm_owner_orgs
                                                   WHERE coalesce(entity, '') NOT ILIKE 'individual%'""", status)
    return n


def run(status=log) -> None:
    load_marks(status=status)
    load_assignments(status=status)
    summaries(status=status)
    uspto.indexes(status=status, only="tm")
    links(status=status)


if __name__ == "__main__":
    args = sys.argv[1:] or ["run"]
    uspto.start_ticker(f"trademarks {' '.join(args)}")
    if args[0] == "marks":
        load_marks(args[1:] or None)
    elif args[0] == "assignments":
        load_assignments()
    else:
        {"summaries": summaries, "links": links, "all": run, "run": run}[args[0]]()
