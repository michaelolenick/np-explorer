"""FEC bulk data: committees, candidates and individual contributions, by two-year election cycle.

Source: https://www.fec.gov/data/browse-data/?tab=bulk-data (pipe-delimited, no header; data dictionaries at
/files/bulk-downloads/data_dictionaries/). Each cycle's indivYY.zip holds itcont.txt (the whole cycle) plus
by_date/ slices of the same rows, so only itcont.txt is read.

A cycle loads into a fresh table that is indexed and then swapped in as that cycle's partition of
fec_contributions, so pages keep showing the previous load until the new one is complete. The FEC rewrites
the files for open cycles (about weekly), so refresh() reloads the current and previous cycle whenever the FEC
has posted a newer file (nightly check from scripts/offhours.py).

Every contribution links to its source: the FEC's image of the report page (IMAGE_NUM) via SOURCE_URL.
"""

from __future__ import annotations

import io
import re
import time
import urllib.request
import zipfile
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path

import psycopg

from app.names import normalize_name
from loader import db

BASE = "https://www.fec.gov/files/bulk-downloads"
RAW = Path("/data/raw/fec")
FIRST_CYCLE = 1980
SOURCE_URL = "https://docquery.fec.gov/cgi-bin/fecimg/?{image_num}"

CM_COLS = ["cmte_id", "name", "treasurer", "street1", "street2", "city", "state", "zip", "designation",
           "cmte_type", "party", "filing_freq", "org_type", "connected_org", "cand_id"]
CN_COLS = ["cand_id", "name", "party", "election_year", "office_state", "office", "district", "ici", "status",
           "pcc", "street1", "street2", "city", "state", "zip"]
INDIV_COLS = ["cycle", "sub_id", "cmte_id", "amendment", "report_type", "pgi", "image_num", "tran_type",
              "entity_type", "name", "name_norm", "city", "state", "zip5", "employer", "occupation", "tran_date",
              "amount", "other_id", "tran_id", "file_num", "memo_cd", "memo_text"]
# Indexes every cycle partition carries (the parent's partitioned indexes attach to them).
INDEXES = [("sub", "(cycle, sub_id)", True), ("name", "(name_norm)", False), ("cmte", "(cmte_id)", False),
           ("zip_name", "(zip5, name_norm)", False)]


def cycles(today: date | None = None) -> list[int]:
    today = today or date.today()
    last = today.year + (today.year % 2)
    return list(range(FIRST_CYCLE, last + 1, 2))


def _download(name: str, cycle: int) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    yy = str(cycle)[2:]
    dest = RAW / f"{name}{yy}.zip"
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(f"{BASE}/{cycle}/{name}{yy}.zip", headers={"User-Agent": "furp.org"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 22):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def _lines(path: Path, member: str | None = None):
    with zipfile.ZipFile(path) as z:
        info = next(i for i in z.infolist() if (member is None and "/" not in i.filename) or i.filename == member)
        with z.open(info) as raw:
            for line in io.TextIOWrapper(raw, encoding="latin-1", newline="\n"):
                yield line.rstrip("\r\n").replace("\x00", "").split("|")   # a few files carry NUL bytes


def _blank(v: str) -> str | None:
    v = v.strip()
    return v or None


def _date(v: str) -> date | None:
    """MMDDYYYY; anything else (blank, impossible dates) is NULL."""
    if len(v) != 8 or not v.isdigit():
        return None
    try:
        return date(int(v[4:]), int(v[:2]), int(v[2:4]))
    except ValueError:
        return None


@lru_cache(maxsize=2_000_000)
def _norm(name: str) -> str:
    return normalize_name(name)


def indiv_row(cycle: int, f: list[str]) -> tuple | None:
    if len(f) < 21 or not f[20].strip().isdigit():
        return None
    name = _blank(f[7])
    z = re.sub(r"\D", "", f[10])
    try:
        amount = float(f[14]) if f[14].strip() else None
    except ValueError:
        amount = None
    return (cycle, int(f[20]), f[0].strip(), _blank(f[1]), _blank(f[2]), _blank(f[3]), _blank(f[4]), _blank(f[5]),
            _blank(f[6]), name, _norm(name) if name else None, _blank(f[8]), _blank(f[9]),
            z[:5] if len(z) >= 5 else None, _blank(f[11]), _blank(f[12]), _date(f[13].strip()), amount,
            _blank(f[15]), _blank(f[16]), int(f[17]) if f[17].strip().isdigit() else None, _blank(f[18]),
            _blank(f[19]))


def _master(conn, table: str, cols: list[str], cycle: int, path: Path) -> int:
    conn.execute(f"DELETE FROM {table} WHERE cycle = %s", (cycle,))
    n = 0
    seen = set()
    with conn.cursor().copy(f"COPY {table} (cycle, {', '.join(cols)}) FROM STDIN") as cp:
        for f in _lines(path):
            f = (f + [""] * len(cols))[:len(cols)]
            if not f[0].strip() or f[0] in seen:
                continue
            seen.add(f[0])
            row = [_blank(x) for x in f]
            if table == "fec_candidates":
                row[3] = int(row[3]) if row[3] and row[3].isdigit() else None
            cp.write_row([cycle] + row)
            n += 1
    return n


def load_cycle(cycle: int, status=print, keep_zip: bool = False) -> int:
    """Committees, candidates and individual contributions for one cycle, swapped in when complete."""
    t0 = time.time()
    with db.connect() as conn:
        run = conn.execute("INSERT INTO fec_runs (cycle) VALUES (%s) RETURNING id", (cycle,)).fetchone()[0]
        conn.commit()
        try:
            for name, table, cols in (("cm", "fec_committees", CM_COLS), ("cn", "fec_candidates", CN_COLS)):
                p = _download(name, cycle)
                status(f"fec {cycle}: {table} {_master(conn, table, cols, cycle, p):,}")
                conn.commit()
                p.unlink()
            p = _download("indiv", cycle)
            status(f"fec {cycle}: downloaded {p.stat().st_size / 1e9:.1f} GB in {time.time() - t0:.0f}s")
            new = f"fec_contributions_{cycle}_new"
            conn.execute(f"DROP TABLE IF EXISTS {new}")
            conn.execute(f"CREATE TABLE {new} (LIKE fec_contributions INCLUDING DEFAULTS)")
            conn.execute(f"ALTER TABLE {new} SET (autovacuum_enabled = false)")
            conn.commit()
            n, bad = 0, 0
            with conn.cursor().copy(f"COPY {new} ({', '.join(INDIV_COLS)}) FROM STDIN") as cp:
                for f in _lines(p):
                    row = indiv_row(cycle, f)
                    if row is None:
                        bad += 1
                        continue
                    cp.write_row(row)
                    n += 1
                    if n % 5_000_000 == 0:
                        status(f"fec {cycle}: {n:,} contributions ({time.time() - t0:.0f}s)")
            conn.commit()
            # Re-filed rows can repeat a SUB_ID; keep one.
            conn.execute(f"""DELETE FROM {new} a USING {new} b
                             WHERE a.sub_id = b.sub_id AND a.ctid > b.ctid""")
            for suffix, cols, unique in INDEXES:
                conn.execute(f"CREATE {'UNIQUE ' if unique else ''}INDEX {new}_{suffix} ON {new} {cols}")
            conn.execute(f"ALTER TABLE {new} ADD CONSTRAINT {new}_cycle CHECK (cycle = {cycle})")
            conn.execute(f"ALTER TABLE {new} SET (autovacuum_enabled = true)")
            conn.commit()
            conn.execute(f"ANALYZE {new}")
            conn.commit()
            _swap(conn, cycle, new)
            conn.execute("UPDATE fec_runs SET finished = now(), status = 'done', rows = %s, note = %s WHERE id = %s",
                         (n, f"{bad} unreadable lines", run))
            conn.commit()
            if not keep_zip:
                p.unlink()
            status(f"fec {cycle}: {n:,} contributions loaded ({bad} unreadable lines) in {time.time() - t0:.0f}s")
            return n
        except Exception as e:
            conn.rollback()
            conn.execute("UPDATE fec_runs SET finished = now(), status = 'failed', note = %s WHERE id = %s",
                         (str(e)[:500], run))
            conn.commit()
            raise


def _swap(conn, cycle: int, new: str) -> None:
    """Detach the old partition and attach the new one in one transaction. Pages queue behind the detach's lock,
    and prod gives each statement 5 s, so a lock not granted within 3 s is given up and tried again."""
    part = f"fec_contributions_{cycle}"
    for attempt in range(40):
        try:
            conn.execute("SET lock_timeout = '3s'")
            old = conn.execute("SELECT to_regclass(%s)", (part,)).fetchone()[0]
            if old:
                conn.execute(f"ALTER TABLE fec_contributions DETACH PARTITION {part}")
                conn.execute(f"DROP TABLE {part}")
            conn.execute(f"ALTER TABLE {new} RENAME TO {part}")
            for suffix, _, _ in INDEXES:
                conn.execute(f"ALTER INDEX {new}_{suffix} RENAME TO {part}_{suffix}")
            conn.execute(f"ALTER TABLE fec_contributions ATTACH PARTITION {part} FOR VALUES IN ({cycle})")
            conn.execute("SET lock_timeout = 0")
            conn.commit()
            return
        except psycopg.errors.LockNotAvailable:
            conn.rollback()
            time.sleep(15)
    raise RuntimeError(f"fec {cycle}: could not get the locks to swap in {new}")


def ensure_parent_indexes() -> None:
    """Indexes on the partitioned parent, made before any partition exists; an attached partition's matching
    index then attaches to them (and ATTACH builds any that are missing)."""
    with db.connect() as conn:
        for suffix, cols, unique in INDEXES:
            conn.execute(f"CREATE {'UNIQUE ' if unique else ''}INDEX IF NOT EXISTS fec_contributions_{suffix} "
                         f"ON fec_contributions {cols}")
        conn.commit()


def load_all(status=print, only: list[int] | None = None) -> None:
    ensure_parent_indexes()
    for c in only or cycles():
        load_cycle(c, status)


def posted(cycle: int) -> datetime:
    """When the FEC last rewrote the cycle's indivYY.zip (Last-Modified)."""
    req = urllib.request.Request(f"{BASE}/{cycle}/indiv{str(cycle)[2:]}.zip", method="HEAD",
                                 headers={"User-Agent": "furp.org"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return parsedate_to_datetime(r.headers["Last-Modified"])


def stale(status=print) -> list[int]:
    """The open cycle and the one before it (late amendments), where the FEC has posted a newer indivYY.zip
    than the one in the last finished load."""
    out = []
    with db.connect() as conn:
        for c in cycles()[-2:]:
            last = conn.execute("SELECT max(started) FROM fec_runs WHERE cycle = %s AND status = 'done'",
                                (c,)).fetchone()[0]
            p = posted(c)
            if last is None or p > last:
                status(f"fec {c}: indiv file posted {p:%Y-%m-%d %H:%M}, newer than the load of "
                       f"{last:%Y-%m-%d %H:%M}" if last else f"fec {c}: not loaded yet")
                out.append(c)
    return out


def refresh(status=print) -> list[int]:
    """The open cycle and the one before it, each only when the FEC has posted a newer file (about weekly).
    Returns the cycles reloaded; links and boards are rebuilt after (scripts/offhours.py)."""
    cs = stale(status)
    for c in cs:
        load_cycle(c, status)
    return cs
