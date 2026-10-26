"""Virginia business registry: the State Corporation Commission's files on data.virginia.gov (free, no login): LLCs
(llc.csv), corporations, stock and nonstock (corp.xlsx; nonstock includes nonprofits), and officers (officer.csv).
Every status is listed, inactive too; filings the SCC rejected (StatusReason "Rejected": never formed) are skipped.

- Getting the files: `fetch` downloads them to /bulk/registry/va/ and stamps each with the date the state published it.
  As of 2026-10-26 the newest files are from November-December 2024, though the portal says "monthly".
- llc.csv has exactly 1,048,576 lines, Excel's row limit: the state's export looks cut off there, so some Virginia
  LLCs are missing until the SCC publishes a complete file.
- Every row records where it came from (provenance: file, publish date, load date). A full run removes Virginia
  entities the new files no longer list.

Usage: .venv/bin/python -m loader.virginia_registry [fetch|load|officers] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

from loader import db
from loader.uspto import STATES

DIR = Path("/bulk/registry/va")
STATE = "VA"
SOURCE = "va"
UA = "furp.org research michael@furp.org"
BASE = "https://data.virginia.gov/dataset/"
FILES = {"llc.csv": "cdb25eb3-b177-42c6-97e9-be2b170fd778/resource/6d55efe1-1784-414a-a38e-ce1f6b4be5fe/download/llc.csv",
         "corp.xlsx": "3c73d9b4-a544-4cd5-a25f-f522d32815f1/resource/9d79f14f-86cd-4ce2-b2da-2df005958e0d/download/corp.xlsx",
         "officer.csv": "178aa97e-3398-4bc2-98c1-0a2ca7f6398f/resource/c72f2bcd-13f7-4b10-b9ba-d2c88802661e/download/officer.csv"}
EXCEL_ROWS = 1048576


def fetch(status=print) -> None:
    """Download the three files; -R keeps the server's Last-Modified as the file date."""
    DIR.mkdir(parents=True, exist_ok=True)
    for name, path in FILES.items():
        subprocess.run(["curl", "-sSfLR", "-A", UA, "-o", str(DIR / name), BASE + path], check=True)
        status(f"virginia: {name} {(DIR / name).stat().st_size:,} bytes, published {published(DIR / name)}")


def published(p: Path) -> str:
    return dt.date.fromtimestamp(p.stat().st_mtime).isoformat()


def clean(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        return v.date().isoformat() if isinstance(v, dt.datetime) else v.isoformat()
    s = " ".join(str(v).split())                         # the SCC pads fields: "TRACI G   CORCORAN"
    return s or None


def day(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    s = clean(v)
    if not s:
        return None
    try:
        m, d, y = s.split("/")
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        try:
            return dt.date.fromisoformat(s[:10])
        except ValueError:
            return None


def abbr(v) -> str | None:
    s = clean(v)
    if not s:
        return None
    return s.upper() if len(s) == 2 else STATES.get(s.upper(), s[:30])


def rows_csv(p: Path):
    with p.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        yield from csv.DictReader(f)


def rows_xlsx(p: Path):
    import openpyxl
    ws = openpyxl.load_workbook(p, read_only=True).worksheets[0]
    it = ws.iter_rows(values_only=True)
    head = [str(h).strip() for h in next(it)]
    for r in it:
        yield dict(zip(head, r))


def entity(r: dict, kind: str, prov: str) -> tuple | None:
    from loader.recalls import core
    eid, name = clean(r.get("EntityID")), clean(r.get("Name"))
    if not eid or not name or (clean(r.get("StatusReason")) or "").lower() == "rejected":
        return None
    if kind == "corp":
        etype = {"S": "Stock corporation", "N": "Nonstock corporation"}.get(clean(r.get("StockInd")) or "", "Corporation")
    else:
        etype = "Limited liability company" + (" (series)" if clean(r.get("Is Series LLC")) else "")
    st, reason = clean(r.get("Status")), clean(r.get("StatusReason"))
    status = (st or "").title() + (f" ({reason})" if reason and reason.lower() != (st or "").lower() else "")
    extra = {k: v for k, v in (("status_date", day(r.get("Status Date"))), ("industry_code", clean(r.get("IndustryCode"))),
                                ("agent_status", clean(r.get("RA-Status"))), ("total_shares", clean(r.get("TotalShares"))))
             if v not in (None, "0")}
    extra = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in extra.items()}
    return (STATE, eid, name[:500], core(name)[:500], etype, status or None, day(r.get("IncorpDate")),
            " ".join(x for x in (clean(r.get("Street1")), clean(r.get("Street2"))) if x) or None, clean(r.get("City")),
            abbr(r.get("State")), clean(r.get("Zip")), clean(r.get("RA-Name")),
            " ".join(x for x in (clean(r.get("RA-Street1")), clean(r.get("RA-City")), abbr(r.get("RA-State")),
                                 clean(r.get("RA-Zip"))) if x) or None,
            abbr(r.get("IncorpState")), SOURCE, None, prov, json.dumps(extra))


COLS = ["state", "entity_id", "name", "name_core", "entity_type", "status", "formed", "street", "city", "addr_state",
        "zip", "agent_name", "agent_address", "jurisdiction", "source", "ein", "provenance", "extra"]


def _flush(conn, ents: list) -> None:
    if not ents:
        return
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS ve (LIKE biz_entities INCLUDING DEFAULTS)")
    conn.execute("TRUNCATE ve")
    with conn.cursor() as cur, cur.copy(f"COPY ve ({', '.join(COLS)}) FROM STDIN") as cp:
        for e in ents:
            cp.write_row(e)
    conn.execute(f"""INSERT INTO biz_entities ({', '.join(COLS)}, loaded) SELECT DISTINCT ON (entity_id) {', '.join(COLS)}, now()
                     FROM ve ORDER BY entity_id
                     ON CONFLICT (state, entity_id) DO UPDATE SET
                     {', '.join(f'{c} = excluded.{c}' for c in COLS[2:])}, loaded = now()""")
    conn.commit()
    ents.clear()


def run(limit: int | None = None, status=print, officers_only: bool = False) -> dict:
    from app.names import normalize_name
    t0, start = time.time(), dt.datetime.now(dt.timezone.utc)
    stats = {"llc": 0, "corp": 0, "rejected_or_blank": 0, "officers": 0, "officers_without_entity": 0}
    today = dt.date.today()
    with db.connect() as conn:
        for name, kind, reader in () if officers_only else (("llc.csv", "llc", rows_csv), ("corp.xlsx", "corp", rows_xlsx)):
            p = DIR / name
            prov = f"VA State Corporation Commission, data.virginia.gov {name} (published {published(p)}), loaded {today}"
            ents, n = [], 0
            for r in reader(p):
                e = entity(r, kind, prov)
                if not e:
                    stats["rejected_or_blank"] += 1
                    continue
                ents.append(e)
                n += 1
                if len(ents) >= 20000:
                    _flush(conn, ents)
                if n % 250000 == 0:
                    status(f"virginia {name}: {n:,}")
                if limit and n >= limit:
                    break
            _flush(conn, ents)
            stats[kind] = n
            status(f"virginia {name}: {n:,} entities ({time.time() - t0:.0f}s)")
        if not limit and not officers_only:
            stats["llc_file_lines"] = sum(1 for _ in (DIR / "llc.csv").open("rb"))
            stats["llc_file_cut_at_excel_limit"] = stats["llc_file_lines"] == EXCEL_ROWS
        # Officers: replaced as a whole, only for entities loaded above.
        p = DIR / "officer.csv"
        prov = f"VA State Corporation Commission, data.virginia.gov officer.csv (published {published(p)}), loaded {today}"
        conn.execute("DELETE FROM biz_people WHERE source = %s", (SOURCE,))
        conn.execute("CREATE TEMP TABLE vp (entity_id text, name text, name_norm text, role text)")
        with conn.cursor() as cur, cur.copy("COPY vp FROM STDIN") as cp:
            for i, r in enumerate(rows_csv(p)):
                eid = clean(r.get("EntityID"))
                nm = " ".join(x for x in (clean(r.get("OfficerFirstName")), clean(r.get("OfficerMiddleName")),
                                          clean(r.get("OfficerLastName"))) if x)
                if eid and nm:
                    cp.write_row((eid, nm[:300], (normalize_name(nm[:300]) or '')[:200] or None, (clean(r.get("OfficerTitle")) or "Officer")[:100]))
                if limit and i >= limit * 3:
                    break
        k = conn.execute("""INSERT INTO biz_people (state, entity_id, name, name_norm, role, is_entity, address, source, provenance)
                            SELECT %s, vp.entity_id, vp.name, vp.name_norm, vp.role, false, NULL, %s, %s FROM vp
                            JOIN biz_entities e ON e.state = %s AND e.entity_id = vp.entity_id""",
                         (STATE, SOURCE, prov, STATE)).rowcount
        stats["officers"] = k
        stats["officers_without_entity"] = conn.execute("SELECT count(*) FROM vp").fetchone()[0] - k
        if not limit and not officers_only:
            stats["removed"] = conn.execute("DELETE FROM biz_entities WHERE source = %s AND loaded < %s",
                                            (SOURCE, start)).rowcount
        if not officers_only:
            conn.execute("""INSERT INTO biz_runs (source, rows) VALUES (%s, %s)
                            ON CONFLICT (source) DO UPDATE SET loaded = now(), rows = excluded.rows""",
                         (SOURCE, stats["llc"] + stats["corp"]))
        conn.commit()
    status(f"virginia: {stats} in {time.time() - t0:.0f}s")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", choices=["fetch", "load", "officers"], default="load")
    ap.add_argument("--limit", type=int, help="entities per file (a test run)")
    a = ap.parse_args()
    fetch() if a.cmd == "fetch" else run(a.limit, officers_only=a.cmd == "officers")
