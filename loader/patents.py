"""USPTO patents: granted patents with assignees, inventors and CPC subclasses from PatentsView's disambiguated
tables (product PVGPATDIS), and patent assignments, ownership transfers and security interests from the USPTO
Patent Assignment Dataset (ECORSEXC). Bulk files only (loader/uspto.py downloads and counts them).

- What's loaded: g_patent (number, type, kind, grant date, title, claim count), g_application (filing date),
  g_patent_abstract, g_assignee_disambiguated, g_inventor_disambiguated, g_location_disambiguated (city, state,
  country), g_cpc_current (CPC subclasses, one row per subclass) and g_cpc_title. No claims text or full text.
- How far back (owner, 2026-10-24): patents filed in the last 20 years (uspto.CUTOFF), newest first, in grant-year
  parts (PARTS) so the most recent are on the site first: 2023 on, then 2019-2022, 2015-2018, 2011-2014, the rest.
  Assignments: the recorded documents that name a loaded patent (the same window).
- Each part is a full pass over each file, keeping only that part's patents (an in-memory set of about a million
  numbers), COPYed in batches into staging tables and inserted from there. Re-running replaces the same rows.
- Every row records its source product (PVGPATDIS or ECORSEXC) and that file's release date.
- links(): assignees to nonprofits, colleges, Form D issuers, state business registrations and SEC filers, and
  inventors to people, each with EXACT or FUZZY and a confidence (see links()).

Usage: .venv/bin/python -m loader.patents [patents [PART ...]] | assignments | summaries | links | all
"""

from __future__ import annotations

import datetime as dt
import re
import sys
import time

from loader import db, uspto
from loader.uspto import clean, date_any, log

PV, AS = "PVGPATDIS", "ECORSEXC"
PV_FILES = ["g_patent.tsv.zip", "g_application.tsv.zip", "g_patent_abstract.tsv.zip", "g_assignee_disambiguated.tsv.zip",
            "g_inventor_disambiguated.tsv.zip", "g_location_disambiguated.tsv.zip", "g_cpc_current.tsv.zip",
            "g_cpc_title.tsv.zip"]
ASSIGN_FILES = ["2025_assignment.csv.zip", "2025_assignment_conveyance.csv.zip", "2025_assignee.csv.zip",
                "2025_assignor.csv.zip", "2025_documentid.csv.zip"]
# Grant-date parts, newest first: (name, from, to); the last runs back to the 20-year filing cutoff.
PARTS = [("2023-", dt.date(2023, 1, 1), None), ("2019-2022", dt.date(2019, 1, 1), dt.date(2023, 1, 1)),
         ("2015-2018", dt.date(2015, 1, 1), dt.date(2019, 1, 1)), ("2011-2014", dt.date(2011, 1, 1), dt.date(2015, 1, 1)),
         ("cutoff-2010", uspto.CUTOFF, dt.date(2011, 1, 1))]
BATCH = 20000
# PatentsView assignee_type: 2 US company, 3 foreign company, 4 US person, 5 foreign person, 6 US government,
# 7 foreign government, 8 county government, 9 state government; 1x = part interest (e.g. 12).
TYPE_LABEL = {1: "Unassigned", 2: "US company or organization", 3: "Foreign company or organization",
              4: "US individual", 5: "Foreign individual", 6: "US federal government", 7: "Foreign government",
              8: "US county government", 9: "US state government"}
PERSON_TYPES = {4, 5}


def patent_number(v: str | None) -> str | None:
    """A patent number as PatentsView writes it: 10000000, D1006496, RE49123, PP34567 (leading zeros dropped);
    'US 10,000,000 B2' and 'D0654321' work too."""
    s = re.sub(r"[\s,/-]", "", (v or "").upper())
    s = re.sub(r"^US", "", s)
    s = re.sub(r"(?<=\d)(A[12]|B[123]|C[12]|E1?|S1?|P[23]|H1?)$", "", s)
    m = re.fullmatch(r"(D|RE|PP|T|H|X)?0*(\d{1,8})", s)
    return f"{m.group(1) or ''}{m.group(2)}" if m else None


def google_url(patent_id: str, kind: str | None) -> str:
    return f"https://patents.google.com/patent/US{patent_id}{kind or ''}"


def _type(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def assignee_name(r: dict) -> tuple[str | None, bool]:
    org = clean(r.get("disambig_assignee_organization"))
    if org:
        return org, False
    person = " ".join(x for x in (clean(r.get("disambig_assignee_individual_name_first")),
                                  clean(r.get("disambig_assignee_individual_name_last"))) if x)
    return (person or None), True


# --- patents -----------------------------------------------------------------------------------------------------

def _locations() -> dict:
    out = {}
    for r in uspto.rows(uspto.DATA / PV / "g_location_disambiguated.tsv.zip", "\t"):
        out[r["location_id"]] = (clean(r["disambig_city"], 100), clean(r["disambig_state"], 10),
                                 clean(r["disambig_country"], 10))
    return out


def load_cpc_titles(conn) -> int:
    d = uspto.file_date(PV, "g_cpc_title.tsv.zip")
    seen = {}
    for r in uspto.rows(uspto.DATA / PV / "g_cpc_title.tsv.zip", "\t"):
        if r["cpc_subclass"] and r["cpc_subclass"] not in seen:
            seen[r["cpc_subclass"]] = (r["cpc_subclass"], clean(r["cpc_subclass_title"], 1000),
                                       clean(r["cpc_class_title"], 1000), PV, d)
    batch = list(seen.values())
    uspto.bulk(conn, "pat_cpc_titles", ["subclass", "title", "class_title", "src_product", "src_date"], batch,
               uspto.upsert("pat_cpc_titles", ["subclass"], ["title", "class_title", "src_product", "src_date"]))
    return len(seen)


def load_part(name: str, start: dt.date, end: dt.date | None, status=log) -> int:
    """One grant-date part: patents, abstracts, assignees, inventors and CPC subclasses."""
    t0 = time.time()
    path = lambda f: uspto.DATA / PV / f  # noqa: E731
    dates = {f: uspto.file_date(PV, f) for f in PV_FILES}
    # 1. The part's patents straight into a staging table (only the numbers stay in memory), their filing dates
    # (dropping those filed before the 20-year cutoff), then in with their abstracts in one insert.
    pcols = ["patent_id", "patent_type", "kind", "granted", "title", "num_claims", "withdrawn", "src_product", "src_file",
             "src_date"]
    ids: set[str] = set()
    with db.connect() as conn:
        done = lambda step, f: uspto.step_done(PV, f, name, step)  # noqa: E731

        def mark_step(step, f, n):
            uspto.mark_step(conn, PV, f, name, step, n)
            uspto.checkpoint("patents", part=name, step=step, rows_=n, newest=end or dt.date.today(), oldest=start)
            uspto.status_line(f"{step} done for grants {name}; continuing {uspto.current()}")

        conn.execute("SET work_mem = '256MB'")
        load_cpc_titles(conn)
        batch: list = []
        if not done("patents", "g_patent.tsv.zip"):
            conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_pat_part (LIKE pat_patents INCLUDING DEFAULTS)")
            conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_pat_app (patent_id text, application_id text, filed date)")
            conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_pat_abstract (patent_id text, abstract text)")
            conn.execute("TRUNCATE stage_pat_part, stage_pat_app, stage_pat_abstract")
            conn.commit()
            granted = 0
            with conn.cursor() as cur, cur.copy(f"COPY stage_pat_part ({', '.join(pcols)}) FROM STDIN") as cp:
                for r in uspto.rows(path("g_patent.tsv.zip"), "\t"):
                    g = date_any(r["patent_date"])
                    if not g or g < start or (end is not None and g >= end):
                        continue
                    ids.add(r["patent_id"])
                    cp.write_row((r["patent_id"], clean(r["patent_type"], 20), clean(r["wipo_kind"], 4), g,
                                  clean(r["patent_title"], 2000), _type(r["num_claims"]), r.get("withdrawn") == "1", PV,
                                  clean(r.get("filename"), 40), dates["g_patent.tsv.zip"]))
            granted = len(ids)
            with conn.cursor() as cur, cur.copy("COPY stage_pat_app FROM STDIN") as cp:
                for r in uspto.rows(path("g_application.tsv.zip"), "\t"):
                    if r["patent_id"] in ids:
                        fd = date_any(r["filing_date"])
                        cp.write_row((r["patent_id"], clean(r["application_id"], 20), fd))
                        if fd and fd < uspto.CUTOFF:
                            ids.discard(r["patent_id"])     # filed too long ago: the insert below leaves it out
            status(f"patents {name}: {len(ids):,} patents filed since {uspto.CUTOFF} ({granted:,} granted in the part)")
            with conn.cursor() as cur, cur.copy("COPY stage_pat_abstract (patent_id, abstract) FROM STDIN") as cp:
                for r in uspto.rows(path("g_patent_abstract.tsv.zip"), "\t"):
                    if r["patent_id"] in ids and r.get("patent_abstract"):
                        cp.write_row((r["patent_id"], r["patent_abstract"].strip()[:20000]))
            allc = pcols + ["filed", "application_id", "abstract"]
            conn.execute(f"""INSERT INTO pat_patents ({', '.join(allc)})
                             SELECT {', '.join('p.' + c for c in pcols)}, a.filed, a.application_id, b.abstract
                             FROM stage_pat_part p
                             LEFT JOIN (SELECT DISTINCT ON (patent_id) * FROM stage_pat_app) a USING (patent_id)
                             LEFT JOIN (SELECT DISTINCT ON (patent_id) * FROM stage_pat_abstract) b USING (patent_id)
                             WHERE coalesce(a.filed, p.granted) >= %s
                             ON CONFLICT {uspto.upsert('pat_patents', ['patent_id'], allc)}, loaded = now()""",
                         (uspto.CUTOFF,))
            conn.execute("TRUNCATE stage_pat_part, stage_pat_app, stage_pat_abstract")
            conn.commit()
            status(f"patents {name}: patents and abstracts in ({time.time() - t0:.0f}s)")
            mark_step("patents", "g_patent.tsv.zip", len(ids))
        else:
            ids = {r[0] for r in conn.execute("SELECT patent_id FROM pat_patents WHERE granted >= %s AND granted < %s",
                                              (start, end or dt.date(2100, 1, 1))).fetchall()}
            status(f"patents {name}: patents already in ({len(ids):,}), carrying on from the checkpoint")
        locs = _locations()

        # 2. Assignees.
        if not done("assignees", "g_assignee_disambiguated.tsv.zip"):
            acols = ["patent_id", "seq", "assignee_id", "name", "name_core", "is_person", "assignee_type", "city", "state",
                     "country", "src_product", "src_date"]
            from loader.recalls import core
            na = 0
            for r in uspto.rows(path("g_assignee_disambiguated.tsv.zip"), "\t"):
                if r["patent_id"] not in ids:
                    continue
                nm, person = assignee_name(r)
                t = _type(r["assignee_type"])
                person = person or (t is not None and t % 10 in PERSON_TYPES)
                city, st, country = locs.get(r["location_id"], (None, None, None))
                batch.append((r["patent_id"], _type(r["assignee_sequence"]) or 0, clean(r["assignee_id"], 64),
                              (nm or "")[:500] or None, None if person else (core(nm)[:500] or None), person, t, city,
                              st if country == "US" else None, country, PV, dates["g_assignee_disambiguated.tsv.zip"]))
                na += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "pat_assignees", acols, batch, uspto.upsert("pat_assignees", ["patent_id", "seq"], acols))
            uspto.bulk(conn, "pat_assignees", acols, batch, uspto.upsert("pat_assignees", ["patent_id", "seq"], acols))
            status(f"patents {name}: {na:,} assignee rows ({time.time() - t0:.0f}s)")
            mark_step("assignees", "g_assignee_disambiguated.tsv.zip", na)

        # 3. Inventors.
        if not done("inventors", "g_inventor_disambiguated.tsv.zip"):
            from app.names import normalize_name
            icols = ["patent_id", "seq", "inventor_id", "first_name", "last_name", "name_norm", "city", "state", "country",
                     "src_product", "src_date"]
            ni = 0
            for r in uspto.rows(path("g_inventor_disambiguated.tsv.zip"), "\t"):
                if r["patent_id"] not in ids:
                    continue
                first, last = clean(r["disambig_inventor_name_first"], 200), clean(r["disambig_inventor_name_last"], 200)
                city, st, country = locs.get(r["location_id"], (None, None, None))
                batch.append((r["patent_id"], _type(r["inventor_sequence"]) or 0, clean(r["inventor_id"], 64), first, last,
                              normalize_name(" ".join(x for x in (first, last) if x)) or None, city,
                              st if country == "US" else None, country, PV, dates["g_inventor_disambiguated.tsv.zip"]))
                ni += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "pat_inventors", icols, batch, uspto.upsert("pat_inventors", ["patent_id", "seq"], icols))
            uspto.bulk(conn, "pat_inventors", icols, batch, uspto.upsert("pat_inventors", ["patent_id", "seq"], icols))
            status(f"patents {name}: {ni:,} inventor rows ({time.time() - t0:.0f}s)")
            mark_step("inventors", "g_inventor_disambiguated.tsv.zip", ni)

        # 4. CPC subclasses (current classification), the first group listed under each.
        if not done("cpc", "g_cpc_current.tsv.zip"):
            ccols = ["patent_id", "subclass", "cpc_group", "seq", "src_product", "src_date"]
            nc, seen = 0, set()
            for r in uspto.rows(path("g_cpc_current.tsv.zip"), "\t"):
                if r["patent_id"] not in ids or not r["cpc_subclass"]:
                    continue
                k = (r["patent_id"], r["cpc_subclass"])
                if k in seen:
                    continue
                seen.add(k)
                batch.append((r["patent_id"], r["cpc_subclass"][:10], clean(r["cpc_group"], 40), _type(r["cpc_sequence"]),
                              PV, dates["g_cpc_current.tsv.zip"]))
                nc += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "pat_cpc", ccols, batch)
                    seen.clear()
            uspto.bulk(conn, "pat_cpc", ccols, batch)
            mark_step("cpc", "g_cpc_current.tsv.zip", nc)

        # 5. Firms for the business directory from this part's assignees (loader/ip_firms.py); a failure here is
        # logged and retried on the next run, and doesn't stop the load.
        if not done("firms", "g_assignee_disambiguated.tsv.zip"):
            from loader import ip_firms
            try:
                f = ip_firms.derive(f"part grants-{name}", patents_where=f"p.granted >= '{start}' AND p.granted < "
                                    f"'{end or dt.date(2100, 1, 1)}'", status=status)
                mark_step("firms", "g_assignee_disambiguated.tsv.zip", f["total"])
            except Exception as e:  # noqa: BLE001
                uspto.status_line(f"firms for grants {name} again on the next run; continuing {uspto.current()}",
                                  event=f"ERROR firms: {type(e).__name__}: {str(e)[:150]}")
        uspto.drop_stages(conn)
    status(f"patents {name}: done in {time.time() - t0:.0f}s")
    return len(ids)


def load_patents(parts: list[str] | None = None, status=log) -> int:
    n = 0
    todo = [x for x in PARTS if not parts or x[0] in parts]
    for k, (name, start, end) in enumerate(todo):
        uspto.next_up(f"patent grants {name} (part {k + 1} of {len(todo)}), ETA about "
                      f"{10 * (len(todo) - k)} min for the parts left")
        n += load_part(name, start, end, status)
    for f in PV_FILES:
        with db.connect() as conn:
            uspto.record_run(conn, PV, f, n)
    return n


# --- assignments -------------------------------------------------------------------------------------------------

def load_assignments(status=log) -> int:
    """Recorded assignments, security interests, releases and other conveyances on loaded patents. rf_id is the
    reel and frame (reel * 10000 + frame); a bitmap of the relevant rf_ids filters the other files. Checkpointed
    per file; the checkpoint is keyed to how many patents are loaded, so a backfill reruns it for the older ones."""
    t0 = time.time()
    path = lambda f: uspto.DATA / AS / f  # noqa: E731
    dates = {f: uspto.file_date(AS, f) for f in ASSIGN_FILES}
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        part = f"{conn.execute('SELECT count(*) FROM pat_patents').fetchone()[0]}-patents"
        done = lambda step, f: uspto.step_done(AS, f, part, step)  # noqa: E731

        def mark_step(step, f, n):
            uspto.mark_step(conn, AS, f, part, step, n)
            uspto.checkpoint("pat_assignments", part=part, step=step, rows_=n)
            uspto.status_line(f"patent assignment {step} done; continuing {uspto.current()}")
        batch: list = []
        n = 0
        # 1. Documents (patents) on each recorded assignment: only granted patents in pat_patents.
        if not done("docs", "2025_documentid.csv.zip"):
            dcols = ["rf_id", "patent_id", "appno", "appno_date", "title", "src_product", "src_date"]
            nd = 0
            for r in uspto.rows(path("2025_documentid.csv.zip")):
                pid = patent_number(r.get("grant_doc_num"))
                if not pid:
                    continue
                ad, gd = date_any(r.get("appno_date")), date_any(r.get("grant_date"))
                if (ad or gd or dt.date.min) < uspto.CUTOFF:
                    continue
                batch.append((int(r["rf_id"]), pid, clean(r.get("appno_doc_num"), 20), ad, clean(r.get("title"), 1000),
                              AS, dates["2025_documentid.csv.zip"]))
                nd += 1
                if len(batch) >= BATCH:
                    _docs(conn, dcols, batch)
            _docs(conn, dcols, batch)
            status(f"assignments: {nd:,} documents read ({time.time() - t0:.0f}s)")
            mark_step("docs", "2025_documentid.csv.zip", nd)
        rfs = [r[0] for r in conn.execute("SELECT DISTINCT rf_id FROM pat_assignment_docs").fetchall()]
        bits = bytearray((max(rfs) >> 3) + 1 if rfs else 1)
        for rf in rfs:
            bits[rf >> 3] |= 1 << (rf & 7)
        has = lambda rf: rf < (len(bits) << 3) and bits[rf >> 3] >> (rf & 7) & 1  # noqa: E731
        status(f"assignments: {len(rfs):,} recorded documents name loaded patents")
        del rfs

        # 2. Assignments, with their conveyance types (assignment, security, release, merger, name change, ...).
        if not done("assignments", "2025_assignment.csv.zip"):
            conv = {}
            for r in uspto.rows(path("2025_assignment_conveyance.csv.zip")):
                rf = int(r["rf_id"])
                if has(rf):
                    conv[rf] = (clean(r["convey_ty"], 40), r.get("employer_assign") == "1")
            cols = ["rf_id", "reel_no", "frame_no", "record_date", "convey_text", "convey_type", "is_security",
                    "employer_assign", "src_product", "src_date"]
            for r in uspto.rows(path("2025_assignment.csv.zip")):
                rf = int(r["rf_id"])
                if not has(rf):
                    continue
                ty, emp = conv.get(rf, (None, False))
                batch.append((rf, _type(r["reel_no"]), _type(r["frame_no"]), date_any(r["record_dt"]),
                              clean(r["convey_text"], 1000), ty, ty == "security", emp, AS,
                              dates["2025_assignment.csv.zip"]))
                n += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "pat_assignments", cols, batch, uspto.upsert("pat_assignments", ["rf_id"], cols))
            uspto.bulk(conn, "pat_assignments", cols, batch, uspto.upsert("pat_assignments", ["rf_id"], cols))
            del conv
            status(f"assignments: {n:,} assignments ({time.time() - t0:.0f}s)")
            mark_step("assignments", "2025_assignment.csv.zip", n)
            mark_step("assignments", "2025_assignment_conveyance.csv.zip", n)

        # 3. Parties: assignors (with execution dates) and assignees (with addresses).
        from loader.recalls import core
        pcols = ["rf_id", "role", "seq", "name", "name_core", "exec_date", "city", "state", "country", "src_product",
                 "src_date"]
        for f, role in (("2025_assignor.csv.zip", "assignor"), ("2025_assignee.csv.zip", "assignee")):
            if done(role, f):
                continue
            seqs, k = {}, 0
            for r in uspto.rows(path(f)):
                rf = int(r["rf_id"])
                if not has(rf):
                    continue
                nm = clean(r.get("or_name") or r.get("ee_name"), 500)
                seq = seqs[rf] = seqs.get(rf, -1) + 1
                if len(seqs) > 200000:              # the files are in rf_id order: older entries aren't needed
                    seqs = {rf: seq}
                batch.append((rf, role, seq, nm, core(nm)[:500] or None, date_any(r.get("exec_dt")),
                              clean(r.get("ee_city"), 100), uspto.state_code(r.get("ee_state")),
                              clean(r.get("ee_country"), 60), AS, dates[f]))
                k += 1
                if len(batch) >= BATCH:
                    uspto.bulk(conn, "pat_assignment_parties", pcols, batch,
                               uspto.upsert("pat_assignment_parties", ["rf_id", "role", "seq"], pcols))
            uspto.bulk(conn, "pat_assignment_parties", pcols, batch,
                       uspto.upsert("pat_assignment_parties", ["rf_id", "role", "seq"], pcols))
            status(f"assignments: {k:,} {role}s ({time.time() - t0:.0f}s)")
            mark_step(role, f, k)
        n = conn.execute("SELECT count(*) FROM pat_assignments").fetchone()[0]
        for f in ASSIGN_FILES:
            uspto.record_run(conn, AS, f, n)
        uspto.drop_stages(conn)
    return n


def _docs(conn, cols, batch) -> None:
    """Documents naming a loaded patent only (the join keeps the 20-year window and drops unknown numbers)."""
    if not batch:
        return
    conn.execute("CREATE UNLOGGED TABLE IF NOT EXISTS stage_pat_assignment_docs (LIKE pat_assignment_docs)")
    conn.execute("TRUNCATE stage_pat_assignment_docs")
    with conn.cursor() as cur, cur.copy(f"COPY stage_pat_assignment_docs ({', '.join(cols)}) FROM STDIN") as cp:
        for r in batch:
            cp.write_row(r)
    conn.execute(f"""INSERT INTO pat_assignment_docs ({', '.join(cols)})
                     SELECT DISTINCT ON (s.rf_id, s.patent_id) {', '.join('s.' + c for c in cols)}
                     FROM stage_pat_assignment_docs s JOIN pat_patents p USING (patent_id)
                     ON CONFLICT {uspto.upsert('pat_assignment_docs', ['rf_id', 'patent_id'], cols)}""")
    conn.commit()
    batch.clear()


# --- summaries: one row per assignee and per inventor ------------------------------------------------------------

def summaries(status=log) -> None:
    """pat_assignee_orgs and pat_inventor_people, rebuilt beside the live tables and swapped in."""
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("DROP TABLE IF EXISTS pat_assignee_orgs_new")
        conn.execute("CREATE TABLE pat_assignee_orgs_new (LIKE pat_assignee_orgs INCLUDING ALL)")
        conn.execute("""
            INSERT INTO pat_assignee_orgs_new
            SELECT a.assignee_id, mode() WITHIN GROUP (ORDER BY a.name), mode() WITHIN GROUP (ORDER BY a.name_core),
                   bool_and(a.is_person), mode() WITHIN GROUP (ORDER BY a.assignee_type),
                   mode() WITHIN GROUP (ORDER BY a.city), mode() WITHIN GROUP (ORDER BY a.state),
                   mode() WITHIN GROUP (ORDER BY a.country), count(DISTINCT a.patent_id), min(p.granted), max(p.granted),
                   0, 'PVGPATDIS', max(a.src_date)
            FROM pat_assignees a JOIN pat_patents p USING (patent_id)
            WHERE a.assignee_id IS NOT NULL GROUP BY a.assignee_id""")
        # Security interests recorded against each assignee's patents (distinct recorded documents).
        conn.execute("""
            UPDATE pat_assignee_orgs_new o SET n_security = s.n
            FROM (SELECT a.assignee_id, count(DISTINCT x.rf_id) AS n
                  FROM pat_assignments x JOIN pat_assignment_docs d USING (rf_id)
                  JOIN pat_assignees a ON a.patent_id = d.patent_id
                  WHERE x.is_security AND a.assignee_id IS NOT NULL GROUP BY 1) s
            WHERE s.assignee_id = o.assignee_id""")
        db.swap_table(conn, "pat_assignee_orgs")
        conn.commit()
        status(f"patents: assignee summaries ({time.time() - t0:.0f}s)")
        conn.execute("DROP TABLE IF EXISTS pat_inventor_people_new")
        conn.execute("CREATE TABLE pat_inventor_people_new (LIKE pat_inventor_people INCLUDING ALL)")
        conn.execute("""
            INSERT INTO pat_inventor_people_new
            SELECT i.inventor_id,
                   mode() WITHIN GROUP (ORDER BY concat_ws(' ', i.first_name, i.last_name)),
                   mode() WITHIN GROUP (ORDER BY i.name_norm), count(DISTINCT i.patent_id),
                   array_remove(array_agg(DISTINCT i.state), NULL),
                   left(string_agg(DISTINCT concat_ws(', ', i.city, coalesce(i.state, i.country)), '; '), 500),
                   min(p.granted), max(p.granted), NULL, NULL, 'PVGPATDIS', max(i.src_date)
            FROM pat_inventors i JOIN pat_patents p USING (patent_id)
            WHERE i.inventor_id IS NOT NULL GROUP BY i.inventor_id""")
        conn.execute("""
            UPDATE pat_inventor_people_new n SET top_assignee = t.name, top_assignee_id = t.assignee_id
            FROM (SELECT DISTINCT ON (i.inventor_id) i.inventor_id, a.assignee_id, a.name
                  FROM pat_inventors i JOIN pat_assignees a USING (patent_id)
                  WHERE a.assignee_id IS NOT NULL AND i.inventor_id IS NOT NULL
                  GROUP BY 1, 2, 3 ORDER BY i.inventor_id, count(*) DESC, a.name) t
            WHERE t.inventor_id = n.inventor_id""")
        db.swap_table(conn, "pat_inventor_people")
        conn.commit()
    status(f"patents: inventor summaries ({time.time() - t0:.0f}s)")


# --- links -------------------------------------------------------------------------------------------------------

# University assignees are usually named for their governing board ("The Regents of the University of California",
# "Board of Trustees of the Leland Stanford Junior University"): those words come off before matching colleges.
BOARD_PREFIX = re.compile(r"^(the )?(regents of the|board of regents of the|board of regents|regents of|"
                          r"board of trustees of the|board of trustees of|trustees of the|trustees of|"
                          r"president and fellows of|the board of trustees of the|board of supervisors of)\s+")


def full_norm(name: str | None) -> str:
    """Every word of the name, legal ending included ("Acme Widgets, Inc." -> "acme widgets inc")."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (name or "").lower().replace("&", " and ")).split())


def college_core(name: str | None) -> str:
    from loader.recalls import core
    return BOARD_PREFIX.sub("", core(name))


NORM_SQL = "trim(regexp_replace(lower(replace({x}, '&', ' and ')), '[^a-z0-9]+', ' ', 'g'))"


def _stage_names(conn, table: str, sql: str, colleges: bool = False) -> int:
    """(key, name, state) rows from `sql` into an unlogged table with the three normalized forms, streamed from a
    second connection (organizations has 3 million names) and COPYed in."""
    from loader.recalls import core
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"CREATE UNLOGGED TABLE {table} (key text, full_n text, core_n text, college_n text, state text)")
    conn.commit()
    n = 0
    with db.connect() as rd, rd.cursor(name="ip_names") as cur:
        cur.itersize = 20000
        cur.execute(sql)
        with conn.cursor() as w, w.copy(f"COPY {table} FROM STDIN") as cp:
            for key, name, st in cur:
                c = core(name)
                if c:
                    cp.write_row((str(key), full_norm(name), c, college_core(name) if colleges else None, st))
                    n += 1
    conn.execute(f"CREATE INDEX ON {table} (core_n)")
    conn.execute(f"ANALYZE {table}")
    conn.commit()
    return n


def org_links(conn, src_kind: str, src_sql: str, status=log) -> dict:
    """Links from named organizations (src_sql: key, name, state) to records elsewhere on the site:

      EXACT, high:   the identical full name, legal ending included (case and punctuation aside), and the same
                     state, one record on each side.
      EXACT, medium: the identical full name, one record nationally on each side, where either side has no state
                     (SEC filers, foreign assignees).
      FUZZY, medium: the same name with legal endings dropped (loader/recalls.core) and the same state, one record
                     on each side; nonprofits and colleges: also with "Regents of", "Trustees of" and the like
                     dropped. A college is also linked through the nonprofit matched this way when that nonprofit's
                     EIN belongs to exactly one college (the match and confidence of the nonprofit link).
      FUZZY, low:    the same core name (two words or more), one record nationally on each side, where either side
                     has no state (SEC filers, foreign assignees).
    Targets: org (nonprofit EIN), college (IPEDS unitid), formd (Form D issuer CIK), biz (state registry
    "STATE:ID"), sec (SEC filer CIK), adv (Form ADV adviser CRD), lda (federal lobbying client ID). Unique means within the target's own records, so a name two nonprofits
    share in one state links to neither."""
    n = {}
    _stage_names(conn, "stage_ip_src", src_sql, colleges=True)
    targets = (
        ("org", "SELECT ein, name, state FROM organizations WHERE name IS NOT NULL"),
        ("college", "SELECT unitid, name, state FROM colleges WHERE NOT coalesce(closed, false)"),
        ("formd", "SELECT DISTINCT ON (cik) cik, issuer_name, state FROM sec_formd_offerings WHERE cik IS NOT NULL "
                  "ORDER BY cik, latest_date DESC"),
        ("biz", None),
        ("sec", "SELECT DISTINCT ON (cik) cik, name, NULL FROM sec_fin_subs ORDER BY cik, filed DESC"),
        ("adv", "SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name), state FROM adv_filings "
                "WHERE crd IS NOT NULL ORDER BY crd, submitted DESC NULLS LAST"),
        ("lda", "SELECT DISTINCT ON (client_id) client_id, client_name, client_state FROM lda_filings "
                "WHERE client_id IS NOT NULL AND client_name IS NOT NULL ORDER BY client_id, dt_posted DESC NULLS LAST"),
    )
    for kind, sql in targets:
        boards_too = kind in ("org", "college")         # "Regents of", "Trustees of" set aside on both sides
        if sql:
            _stage_names(conn, "stage_ip_tgt", sql, colleges=boards_too)
        else:
            # 28 million registry entities: their stored core name, only for names the source side has.
            conn.execute("DROP TABLE IF EXISTS stage_ip_tgt")
            conn.execute(f"""CREATE UNLOGGED TABLE stage_ip_tgt AS
                             SELECT state || ':' || entity_id AS key, {NORM_SQL.format(x='name')} AS full_n,
                                    name_core AS core_n, NULL::text AS college_n, coalesce(addr_state, state) AS state
                             FROM biz_entities WHERE name_core IN (SELECT core_n FROM stage_ip_src)""")
            conn.execute("CREATE INDEX ON stage_ip_tgt (core_n)")
            conn.execute("ANALYZE stage_ip_tgt")
            conn.commit()
        src_core = "college_n" if boards_too else "core_n"
        k = conn.execute(f"""
            INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
            SELECT '{src_kind}', s.key, '{kind}', t.key, 'EXACT', 'high', 'identical full name and state'
            FROM (SELECT full_n, state, min(key) AS key FROM stage_ip_src WHERE state IS NOT NULL
                  GROUP BY 1, 2 HAVING count(*) = 1) s
            JOIN (SELECT full_n, state, min(key) AS key FROM stage_ip_tgt WHERE state IS NOT NULL
                  GROUP BY 1, 2 HAVING count(*) = 1) t USING (full_n, state)
            ON CONFLICT DO NOTHING""").rowcount
        how = ("same name (governing-board words and legal endings aside) and state" if boards_too
               else "same name (legal endings aside) and state")
        k += conn.execute(f"""
            INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
            SELECT '{src_kind}', s.key, '{kind}', t.key, 'EXACT', 'medium', 'identical full name, one of each nationally'
            FROM (SELECT full_n, min(key) AS key, bool_or(state IS NULL) AS nostate FROM stage_ip_src
                  GROUP BY 1 HAVING count(*) = 1) s
            JOIN (SELECT full_n, min(key) AS key, bool_or(state IS NULL) AS nostate FROM stage_ip_tgt
                  GROUP BY 1 HAVING count(*) = 1) t USING (full_n)
            WHERE (s.nostate OR t.nostate) AND full_n ~ ' '
              AND NOT EXISTS (SELECT 1 FROM ip_links l WHERE l.src_kind = '{src_kind}' AND l.src_key = s.key
                              AND l.target_kind = '{kind}')
            ON CONFLICT DO NOTHING""").rowcount
        k += conn.execute(f"""
            INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
            SELECT '{src_kind}', s.key, '{kind}', t.key, 'FUZZY', 'medium', '{how}'
            FROM (SELECT {src_core} AS c, state, min(key) AS key FROM stage_ip_src
                  WHERE state IS NOT NULL AND {src_core} <> '' GROUP BY 1, 2 HAVING count(*) = 1) s
            JOIN (SELECT {src_core} AS c, state, min(key) AS key FROM stage_ip_tgt WHERE state IS NOT NULL
                  GROUP BY 1, 2 HAVING count(*) = 1) t USING (c, state)
            WHERE NOT EXISTS (SELECT 1 FROM ip_links l WHERE l.src_kind = '{src_kind}' AND l.src_key = s.key
                              AND l.target_kind = '{kind}')
            ON CONFLICT DO NOTHING""").rowcount
        k += conn.execute(f"""
            INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
            SELECT '{src_kind}', s.key, '{kind}', t.key, 'FUZZY', 'low',
                   'same name (legal endings aside), one of each nationally'
            FROM (SELECT {src_core} AS c, min(key) AS key, bool_or(state IS NULL) AS nostate FROM stage_ip_src
                  WHERE {src_core} <> '' GROUP BY 1 HAVING count(*) = 1) s
            JOIN (SELECT {src_core} AS c, min(key) AS key, bool_or(state IS NULL) AS nostate FROM stage_ip_tgt
                  GROUP BY 1 HAVING count(*) = 1) t USING (c)
            WHERE (s.nostate OR t.nostate) AND length(c) >= 6 AND c ~ ' '
              AND NOT EXISTS (SELECT 1 FROM ip_links l WHERE l.src_kind = '{src_kind}' AND l.src_key = s.key
                              AND l.target_kind = '{kind}')
            ON CONFLICT DO NOTHING""").rowcount
        conn.commit()
        n[kind] = k
    # Colleges through the nonprofit holding the college's EIN (one college per EIN: not a whole system).
    n["college_via_ein"] = conn.execute(f"""
        INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
        SELECT l.src_kind, l.src_key, 'college', c.unitid::text, l.match, l.confidence,
               'through the nonprofit with the college''s EIN (' || l.how || ')'
        FROM ip_links l JOIN colleges c ON c.ein = l.target_key
        WHERE l.src_kind = '{src_kind}' AND l.target_kind = 'org'
          AND c.ein IN (SELECT ein FROM colleges WHERE ein IS NOT NULL GROUP BY 1 HAVING count(*) = 1)
          AND NOT EXISTS (SELECT 1 FROM ip_links x WHERE x.src_kind = l.src_kind AND x.src_key = l.src_key
                          AND x.target_kind = 'college')
        ON CONFLICT DO NOTHING""").rowcount
    conn.commit()
    conn.execute("DROP TABLE IF EXISTS stage_ip_src, stage_ip_tgt")
    conn.commit()
    status(f"{src_kind} links: " + ", ".join(f"{k} {v:,}" for k, v in n.items()))
    return n


def links(status=log) -> dict:
    """Assignees (companies, universities, other organizations) to records elsewhere; inventors to people:

      FUZZY, high:   the inventor's full name matches a person page's (one page with that name) and one of the
                     inventor's patent assignees has the same name as an organization on that person's page
                     (same employer).
      FUZZY, medium: the inventor's full name, with a middle name or initial, matches exactly one person page,
                     and the inventor lived in one of that person's states."""
    t0 = time.time()
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("DELETE FROM ip_links WHERE src_kind IN ('assignee', 'inventor')")
        conn.commit()
        n = org_links(conn, "assignee", """SELECT assignee_id, name, state FROM pat_assignee_orgs
                                           WHERE NOT is_person AND name_core IS NOT NULL""", status)
        # Inventors to people.
        conn.execute("DROP TABLE IF EXISTS pc1")
        conn.execute("""CREATE TEMP TABLE pc1 AS
                        SELECT name_norm, min(id) AS id, min(states) AS states, min(orgs) AS orgs
                        FROM person_clusters WHERE NOT is_institution AND name_norm ~ '^\\S+ \\S+'
                          AND name_norm IN (SELECT name_norm FROM pat_inventor_people)
                        GROUP BY 1 HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON pc1 (name_norm)")
        # Same employer: an assignee of the inventor's patents has the core name of an organization on the person page.
        from loader.recalls import core
        rows = conn.execute("""SELECT DISTINCT ip.inventor_id, pc1.id, pc1.orgs
                               FROM pat_inventor_people ip JOIN pc1 USING (name_norm)""").fetchall()
        emp = {}
        for inv, pid, orgs in rows:
            emp[inv] = (pid, {core(o) for o in (orgs or []) if o})
        conn.execute("DROP TABLE IF EXISTS ie")
        conn.execute("CREATE TEMP TABLE ie (inventor_id text, cluster_id bigint, org_core text)")
        with conn.cursor() as cur, cur.copy("COPY ie FROM STDIN") as cp:
            for inv, (pid, cores) in emp.items():
                for c in cores:
                    if c:
                        cp.write_row((inv, pid, c))
        n["inventor_employer"] = conn.execute("""
            INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
            SELECT DISTINCT 'inventor', ie.inventor_id, 'person', ie.cluster_id::text, 'FUZZY', 'high',
                   'same name, and a patent assignee has the name of an organization on the person''s page'
            FROM ie JOIN pat_inventors i ON i.inventor_id = ie.inventor_id
            JOIN pat_assignees a ON a.patent_id = i.patent_id AND a.name_core = ie.org_core
            ON CONFLICT DO NOTHING""").rowcount
        n["inventor_state"] = conn.execute("""
            INSERT INTO ip_links (src_kind, src_key, target_kind, target_key, match, confidence, how)
            SELECT 'inventor', ip.inventor_id, 'person', pc1.id::text, 'FUZZY', 'medium',
                   'same full name (with a middle name or initial) and state'
            FROM pat_inventor_people ip JOIN pc1 USING (name_norm)
            WHERE ip.name_norm ~ '^\\S+ \\S+ \\S+' AND ip.states && pc1.states
              AND NOT EXISTS (SELECT 1 FROM ip_links l WHERE l.src_kind = 'inventor' AND l.src_key = ip.inventor_id)
              AND (SELECT count(*) FROM pat_inventor_people x WHERE x.name_norm = ip.name_norm) = 1
            ON CONFLICT DO NOTHING""").rowcount
        conn.commit()
        conn.execute("ANALYZE ip_links")
        conn.commit()
    status(f"patent links: {n} ({time.time() - t0:.0f}s)")
    uni_stats(status)
    return n


# --- universities: patents against federal research grants -------------------------------------------------------

UNI_YEARS = (2021, 2025)


def uni_stats(status=log) -> int:
    """pat_uni_stats: per college linked to patent assignees, patents granted in UNI_YEARS and federal research
    grants in the same fiscal years: USAspending assistance awards to the college's EIN from the National Science
    Foundation or the National Institutes of Health, or under a program whose title names research. FURP has no
    research-spending field from 990s (the form doesn't ask for it), so this is the closest measure on file."""
    y0, y1 = UNI_YEARS
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("SET statement_timeout = 0")
        conn.execute("DROP TABLE IF EXISTS pat_uni_stats_new")
        conn.execute("CREATE TABLE pat_uni_stats_new (LIKE pat_uni_stats INCLUDING ALL)")
        conn.execute(f"""
            INSERT INTO pat_uni_stats_new (unitid, name, ein, state, patents, years)
            SELECT c.unitid, c.name, c.ein, c.state, count(DISTINCT a.patent_id), '{y0}-{y1}'
            FROM ip_links l JOIN colleges c ON c.unitid::text = l.target_key
            JOIN pat_assignees a ON a.assignee_id = l.src_key
            JOIN pat_patents p ON p.patent_id = a.patent_id
            WHERE l.src_kind = 'assignee' AND l.target_kind = 'college'
              AND p.granted >= '{y0}-01-01' AND p.granted < '{y1 + 1}-01-01'
            GROUP BY 1, 2, 3, 4""")
        conn.execute(f"""
            UPDATE pat_uni_stats_new u SET research_grants = g.total
            FROM (SELECT recipient_ein, sum(obligation) AS total FROM usa_awards
                  WHERE kind = 'assistance' AND fiscal_year BETWEEN {y0} AND {y1}
                    AND recipient_ein IN (SELECT ein FROM pat_uni_stats_new WHERE ein IS NOT NULL)
                    AND (agency = 'National Science Foundation' OR sub_agency = 'National Institutes of Health'
                         OR program_title ILIKE '%%research%%')
                  GROUP BY 1) g
            WHERE g.recipient_ein = u.ein""")
        db.swap_table(conn, "pat_uni_stats")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM pat_uni_stats").fetchone()[0]
    status(f"patents: {n:,} colleges with patents")
    return n


def run(status=log) -> None:
    load_patents(status=status)
    load_assignments(status=status)
    summaries(status=status)
    uspto.indexes(status=status, only="pat")
    links(status=status)


if __name__ == "__main__":
    args = sys.argv[1:] or ["run"]
    uspto.start_ticker(f"patents {' '.join(args)}")
    if args[0] == "patents":
        load_patents(args[1:] or None)
    elif args[0] == "assignments":
        load_assignments()
    else:
        {"summaries": summaries, "links": links, "all": run, "run": run, "uni_stats": uni_stats}[args[0]]()
