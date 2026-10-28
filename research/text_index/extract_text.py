"""Extract the free text the loader doesn't keep (owner, 2026-10-28): Part III program service descriptions and the
Schedule O narrative, from the stored e-file XML, into research.filing_xml_text (filing_id, field, text).

Runs on the box that holds the XML (prod: /data/xml), at low priority, in id ranges of BATCH filings. Each range is
written and recorded in research.text_extract_done in one transaction, so a restart picks up where it stopped and
rerunning is harmless.

Fields:
  program     990 Part III lines 4a-4d; 990-EZ Part III; 990-PF Part IX-A (summary of direct charitable activities)
  schedule_o  Schedule O (supplemental information), 990 and 990-EZ

Usage (from the np-explorer checkout, .env loaded):  nice -n 19 .venv/bin/python research/text_index/extract_text.py [workers]
"""

from __future__ import annotations

import gzip
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lxml import etree  # noqa: E402

from app.config import XML_DIR  # noqa: E402
from loader import db  # noqa: E402

BATCH = 5000
PART3_IN_RETURN = {"Desc", "Description"}            # 990 line 4a sits directly under IRS990
PART3_GROUPS = {"ProgSrvcAccomActy2Grp", "ProgSrvcAccomActy3Grp", "ProgSrvcAccomActyOtherGrp",   # 990 4b-4d (2013+)
                "Activity2", "Activity3", "ActivityOther",                                       # 990 4b-4d (2009-12)
                "ProgramSrvcAccomplishmentGrp", "ProgramServiceAccomplishment",                  # 990-EZ Part III
                "SummaryOfDirectChrtblActyGrp", "SummaryOfDirectCharitableActivities"}           # 990-PF Part IX-A
SCHED_O_GROUPS = {"SupplementalInformationDetail", "GeneralExplanation"}

SETUP = """
CREATE SCHEMA IF NOT EXISTS research;
CREATE TABLE IF NOT EXISTS research.filing_xml_text (filing_id bigint NOT NULL, field text NOT NULL, text text NOT NULL);
CREATE TABLE IF NOT EXISTS research.text_extract_done (lo bigint PRIMARY KEY, hi bigint NOT NULL, files int,
                                                       failed int, done_at timestamptz DEFAULT now());
"""


def _local(e) -> str:
    t = e.tag
    return t.rsplit("}", 1)[-1] if isinstance(t, str) else ""


def extract(raw: bytes) -> dict[str, str]:
    root = etree.fromstring(raw)
    out: dict[str, list[str]] = {"program": [], "schedule_o": []}
    for e in root.iter():
        if len(e):
            continue
        name = _local(e)
        if not name.startswith(("Desc", "Explanation")):
            continue
        txt = " ".join((e.text or "").split())
        if not txt:
            continue
        parent = _local(e.getparent())
        if (parent in ("IRS990",) and name in PART3_IN_RETURN) or \
                (parent in PART3_GROUPS and name.startswith("Desc")):
            out["program"].append(txt)
        elif parent in SCHED_O_GROUPS and name in ("ExplanationTxt", "Explanation") and \
                any(_local(a) == "IRS990ScheduleO" for a in e.iterancestors()):
            out["schedule_o"].append(txt)
    return {k: "\n".join(dict.fromkeys(v)) for k, v in out.items() if v}     # de-duplicated, in order


def _read(item):
    fid, path = item
    try:
        with gzip.open(XML_DIR / path) as f:
            return fid, extract(f.read())
    except Exception:  # noqa: BLE001 - unreadable file: counted, skipped
        return fid, None


def main(workers: int = 4) -> None:
    with db.connect(autocommit=True) as conn:
        conn.execute(SETUP)
        lo_all, hi_all = conn.execute("SELECT min(id), max(id) FROM filings").fetchone()
        done = {r[0] for r in conn.execute("SELECT lo FROM research.text_extract_done")}
    ranges = [lo for lo in range(lo_all, hi_all + 1, BATCH) if lo not in done]
    print(f"{len(ranges)} ranges of {BATCH} to do ({len(done)} done)", flush=True)
    t0 = time.time()
    with mp.Pool(workers) as pool:
        for i, lo in enumerate(ranges, 1):
            hi = lo + BATCH - 1
            with db.connect() as conn:
                items = conn.execute("SELECT id, xml_path FROM filings WHERE id BETWEEN %s AND %s AND xml_path IS NOT NULL",
                                     (lo, hi)).fetchall()
                failed = 0
                with conn.cursor() as cur, cur.copy("COPY research.filing_xml_text (filing_id, field, text) FROM STDIN") as cp:
                    for fid, got in pool.imap_unordered(_read, items, chunksize=50):
                        if got is None:
                            failed += 1
                            continue
                        for field, txt in got.items():
                            cp.write_row((fid, field, txt.replace("\x00", "")))
                conn.execute("INSERT INTO research.text_extract_done (lo, hi, files, failed) VALUES (%s, %s, %s, %s)",
                             (lo, hi, len(items), failed))
                conn.commit()
            if i % 20 == 0 or i == len(ranges):
                el = time.time() - t0
                print(f"{i}/{len(ranges)} ranges, {el / 60:.0f} min, ~{el / i * (len(ranges) - i) / 60:.0f} min left",
                      flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
