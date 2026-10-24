"""Florida corporate registry: the Division of Corporations' quarterly file (cordata.zip), every entity Florida has on
record, with registered agents and up to six officers each. Layout: docs/florida-sunbiz-layout.md (the state's own
definition, checked against the data).

- Getting the file: the owner downloads it each quarter (January, April, July, October) from the state's public SFTP
  (https://sftp.floridados.gov, user Public; the password is posted at
  https://dos.fl.gov/sunbiz/other-services/data-downloads/), folder doc/Quarterly/Cor, file cordata.zip, and puts it in
  ~/Dropbox/furp-upload/. It's copied to /bulk/registry/fl/ on the dev server. FURP's automation doesn't log in.
- Reading it: members cordata0.txt .. cordata9.txt are Deflate64, which Python's zipfile can't read, so each is
  streamed with `unzip -p` (nothing is extracted to disk).
- Every row records where it came from (provenance: file, member, quarter, load date). Re-running replaces rows from
  the same member; a full run then removes Florida entities the new file no longer lists.

Usage: .venv/bin/python -m loader.florida_registry [--limit N] [--member N] [--zip PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

from loader import db

ZIP = Path("/bulk/registry/fl/cordata.zip")
STATE = "FL"
SOURCE = "fl"
RECORD = 1440
# 1-based start and length (docs/florida-sunbiz-layout.md)
FIELDS = [("cor_number", 1, 12), ("name", 13, 192), ("status", 205, 1), ("filing_type", 206, 15),
          ("addr1", 221, 42), ("addr2", 263, 42), ("city", 305, 28), ("state", 333, 2), ("zip", 335, 10), ("country", 345, 2),
          ("mail_addr1", 347, 42), ("mail_addr2", 389, 42), ("mail_city", 431, 28), ("mail_state", 459, 2),
          ("mail_zip", 461, 10), ("mail_country", 471, 2), ("file_date", 473, 8), ("fei_number", 481, 14),
          ("more_than_six_officers", 495, 1), ("last_txn_date", 496, 8), ("state_country", 504, 2),
          ("report_year_1", 506, 4), ("report_date_1", 511, 8), ("report_year_2", 519, 4), ("report_date_2", 524, 8),
          ("report_year_3", 532, 4), ("report_date_3", 537, 8), ("agent_name", 545, 42), ("agent_type", 587, 1),
          ("agent_address", 588, 42), ("agent_city", 630, 28), ("agent_state", 658, 2), ("agent_zip", 660, 9)]
OFFICER = [("title", 1, 4), ("type", 5, 1), ("name", 6, 42), ("address", 48, 42), ("city", 90, 28), ("state", 118, 2),
           ("zip", 120, 9)]
OFFICER_STARTS = [669 + 128 * k for k in range(6)]
FILING_TYPES = {"DOMP": "Domestic profit corporation", "DOMNP": "Domestic nonprofit corporation",
                "FLAL": "Florida limited liability company", "FORP": "Foreign profit corporation",
                "FORNP": "Foreign nonprofit corporation", "FORL": "Foreign limited liability company",
                "DOMLP": "Domestic limited partnership", "FORLP": "Foreign limited partnership",
                "DOMLLP": "Domestic limited liability partnership", "FORLLP": "Foreign limited liability partnership",
                "NPREG": "Nonprofit, registered", "TRUST": "Declaration of trust", "AGENT": "Registered agent",
                "MISC": "Miscellaneous", "FLAP": "Florida professional limited liability company"}


def fields(s: str) -> dict:
    return {n: s[a - 1:a - 1 + l].strip() for n, a, l in FIELDS}


def officers(s: str) -> list[dict]:
    out = []
    for st in OFFICER_STARTS:
        o = {n: s[st - 1 + a - 1:st - 1 + a - 1 + l].strip() for n, a, l in OFFICER}
        o["raw_name"] = s[st - 1 + 5:st - 1 + 47]          # spacing kept: last 20, first 14, middle 8
        if o["name"]:
            out.append(o)
    return out


def person_name(raw42: str, kind: str) -> tuple[str, str | None, bool]:
    """(name to show, normalized name for matching or None, is a company). A person's 42 characters are last 20,
    first 14, middle 8; a company (type C) uses all 42."""
    from app.names import normalize_name
    raw42 = raw42.ljust(42)
    if kind == "C" or not raw42[20:].strip():
        name = " ".join(raw42.split())
        return name, None, kind == "C"
    last, first, middle = raw42[:20].strip(), raw42[20:34].strip(), raw42[34:42].strip()
    show = " ".join(x for x in (first, middle, last) if x)
    return show, normalize_name(f"{last}, {first} {middle}".strip()) or None, False


def mdy(v: str) -> dt.date | None:
    if re.fullmatch(r"\d{8}", v or ""):
        try:
            return dt.date(int(v[4:]), int(v[:2]), int(v[2:4]))
        except ValueError:
            return None
    return None


def ein(v: str) -> str | None:
    d = re.sub(r"\D", "", v or "")
    return d if len(d) == 9 and d != "000000000" else None


def members(path: Path) -> list[str]:
    out = subprocess.run(["unzip", "-Z1", str(path)], capture_output=True, text=True, check=True).stdout.split()
    return sorted(m for m in out if m.lower().endswith(".txt"))


def stream(path: Path, member: str):
    p = subprocess.Popen(["unzip", "-p", str(path), member], stdout=subprocess.PIPE)
    try:
        for raw in p.stdout:
            yield raw.decode("latin-1").rstrip("\r\n")
    finally:
        p.stdout.close()
        p.wait()


def quarter_of(path: Path) -> str:
    try:
        info = subprocess.run(["unzip", "-l", str(path)], capture_output=True, text=True).stdout
        m = re.search(r"(\d\d)-(\d\d)-(\d{4})", info)
        if m:
            return f"{m.group(3)} Q{(int(m.group(1)) - 1) // 3 + 1}"
    except Exception:  # noqa: BLE001
        pass
    return "unknown quarter"


def load_member(conn, path: Path, member: str, quarter: str, limit: int | None, stats: dict, status=print) -> int:
    from loader.recalls import core
    prov = f"FL Division of Corporations quarterly file {path.name} ({member}), {quarter}, loaded {dt.date.today()}"
    ents, people, n = [], [], 0

    def flush():
        if not ents:
            return
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS fe (LIKE biz_entities INCLUDING DEFAULTS)")
        conn.execute("TRUNCATE fe")
        cols = ["state", "entity_id", "name", "name_core", "entity_type", "status", "formed", "street", "city", "addr_state",
                "zip", "agent_name", "agent_address", "jurisdiction", "source", "ein", "provenance", "extra"]
        with conn.cursor() as cur, cur.copy(f"COPY fe ({', '.join(cols)}) FROM STDIN") as cp:
            for e in ents:
                cp.write_row(e)
        conn.execute(f"""INSERT INTO biz_entities ({', '.join(cols)}, loaded) SELECT {', '.join(cols)}, now() FROM fe
                         ON CONFLICT (state, entity_id) DO UPDATE SET
                         {', '.join(f'{c} = excluded.{c}' for c in cols[2:])}, loaded = now()""")
        conn.execute("DELETE FROM biz_people WHERE state = %s AND entity_id = ANY(%s)", (STATE, [e[1] for e in ents]))
        with conn.cursor() as cur, cur.copy("""COPY biz_people (state, entity_id, name, name_norm, role, is_entity, address,
                                               source, provenance) FROM STDIN""") as cp:
            for p in people:
                cp.write_row(p)
        conn.commit()
        ents.clear()
        people.clear()

    for s in stream(path, member):
        if len(s) < 668:
            stats["short_lines"] += 1
            continue
        if len(s) != RECORD:
            stats["odd_length"] += 1
        f = fields(s)
        if not f["cor_number"] or not f["name"]:
            stats["no_number_or_name"] += 1
            continue
        ftype = f["filing_type"]
        agent, _, _ = person_name(s[544:586], f["agent_type"])
        extra = {k: f[k] for k in ("mail_addr1", "mail_addr2", "mail_city", "mail_state", "mail_zip", "mail_country",
                                    "country", "fei_number", "more_than_six_officers", "state_country") if f[k]}
        for k in ("last_txn_date", "report_date_1", "report_date_2", "report_date_3"):
            d = mdy(f[k])
            if d:
                extra[k] = d.isoformat()
        for k in ("report_year_1", "report_year_2", "report_year_3"):
            if f[k]:
                extra[k] = f[k]
        ents.append((STATE, f["cor_number"], f["name"][:500], core(f["name"])[:500],
                     f"{FILING_TYPES.get(ftype, ftype)} ({ftype})" if ftype else None,
                     {"A": "Active", "I": "Inactive"}.get(f["status"], f["status"] or None), mdy(f["file_date"]),
                     " ".join(x for x in (f["addr1"], f["addr2"]) if x) or None, f["city"] or None, f["state"] or None,
                     f["zip"] or None, agent or None,
                     " ".join(x for x in (f["agent_address"], f["agent_city"], f["agent_state"], f["agent_zip"]) if x) or None,
                     f["state_country"] or None, SOURCE, ein(f["fei_number"]), prov, json.dumps(extra)))
        for o in officers(s):
            show, norm, company = person_name(o["raw_name"], o["type"])
            people.append((STATE, f["cor_number"], show[:300], norm, (o["title"] or "Officer")[:100], company,
                           ", ".join(x for x in (o["city"], o["state"]) if x) or None, SOURCE, prov))
            stats["officers"] += 1
        n += 1
        if len(ents) >= 20000:
            flush()
        if n % 250000 == 0:
            status(f"florida {member}: {n:,} entities")
        if limit and n >= limit:
            break
    flush()
    return n


def run(path: Path = ZIP, limit: int | None = None, only: int | None = None, status=print) -> dict:
    t0 = time.time()
    start = dt.datetime.now(dt.timezone.utc)
    stats = {"entities": 0, "officers": 0, "short_lines": 0, "odd_length": 0, "no_number_or_name": 0}
    mems = members(path)
    if only is not None:
        mems = [m for m in mems if re.search(rf"cordata{only}\.txt$", m)]
    quarter = quarter_of(path)
    with db.connect() as conn:
        for m in mems:
            k = load_member(conn, path, m, quarter, limit, stats, status)
            stats["entities"] += k
            status(f"florida {m}: {k:,} entities ({time.time() - t0:.0f}s)")
        if only is None and not limit:
            gone = conn.execute("DELETE FROM biz_entities WHERE source = %s AND loaded < %s", (SOURCE, start)).rowcount
            conn.execute("DELETE FROM biz_people p WHERE p.source = %s AND NOT EXISTS (SELECT 1 FROM biz_entities e "
                         "WHERE e.state = p.state AND e.entity_id = p.entity_id)", (SOURCE,))
            stats["removed"] = gone
        conn.execute("""INSERT INTO biz_runs (source, rows) VALUES (%s, %s)
                        ON CONFLICT (source) DO UPDATE SET loaded = now(), rows = excluded.rows""", (SOURCE, stats["entities"]))
        conn.commit()
    status(f"florida: {stats} in {time.time() - t0:.0f}s")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="entities per member (a test run)")
    ap.add_argument("--member", type=int, help="only cordataN.txt")
    ap.add_argument("--zip", type=Path, default=ZIP)
    a = ap.parse_args()
    run(a.zip, a.limit, a.member)
