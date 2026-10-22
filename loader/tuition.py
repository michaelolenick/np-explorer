"""Average undergraduate tuition by academic year: NCES Digest of Education Statistics Table 330.10.

The Digest publishes one edition a year (d24 = 2024, covering 1963-64 through 2023-24). refresh() looks for the
newest edition by plain GET (newest first; robots.txt honored), and replaces tuition_averages in one transaction
only when the edition or the file changed. Run weekly by the student loan cron (loader/student_loans.py refresh):

    python -m loader.tuition refresh
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import re
import sys
import time
import urllib.robotparser

import httpx

from loader import db

URL = "https://nces.ed.gov/programs/digest/d{yy:02d}/tables/xls/tabn330.10.xlsx"
USER_AGENT = "furp.org public data loader (+https://furp.org; info@furp.org)"
FIRST_EDITION = 22          # oldest edition checked (d22)

SECTIONS = {"all institutions": "all", "public institutions": "public", "private institutions": "private",
            "nonprofit": "private_nonprofit", "for-profit": "private_for_profit"}
LEVELS = ("all", "4-year", "2-year")
# Column positions in Table 330.10 (0 = the year label): current dollars 1-12, constant dollars 13-24.
COLS = {"total_current": (1, 2, 3), "tuition_fees_current": (4, 5, 6),
        "total_constant": (13, 14, 15), "tuition_fees_constant": (16, 17, 18)}
_YEAR = re.compile(r"^(\d{4})-(\d{4}|\d{2})")   # 1999-2000 before 1976-77


def _num(v):
    """'$1,248' or '1,248' -> 1248.0; blanks, dashes and NCES symbols (---, †, ‡, #) -> None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_rows(rows) -> tuple[list[dict], str]:
    """Rows of the table (lists of cell values) -> ([{control, level, year_start, academic_year, ...}], constant_base)."""
    base = None
    for r in rows[:6]:
        for c in r:
            m = re.search(r"Constant (\d{4}-\d{2}) dollars", str(c or ""))
            if m:
                base = m.group(1)
    if not base:
        raise ValueError("Table 330.10: no 'Constant YYYY-YY dollars' header")
    out, section, seen = [], None, set()
    for r in rows:
        label = re.sub(r"\\\d+(,\d+)*\\", "", str(r[0] or "")).strip()   # footnote markers like \5\
        key = label.lower()
        if key in SECTIONS and not any(_num(c) is not None for c in r[1:]):
            section = SECTIONS[key]
            continue
        m = _YEAR.match(label)
        if not m or not section:
            continue
        year = int(m.group(1))
        for i, level in enumerate(LEVELS):
            rec = {"control": section, "level": level, "year_start": year, "academic_year": m.group(0)}
            for field, idx in COLS.items():
                rec[field] = _num(r[idx[i]]) if idx[i] < len(r) else None
            if all(rec[f] is None for f in COLS):
                continue
            if (section, level, year) in seen:
                raise ValueError(f"Table 330.10: {section} {level} {year} appears twice")
            seen.add((section, level, year))
            out.append(rec)
    return out, base


def _robots_ok(client: httpx.Client) -> bool:
    rp = urllib.robotparser.RobotFileParser()
    r = client.get("https://nces.ed.gov/robots.txt")
    rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    return rp.can_fetch(USER_AGENT, URL.format(yy=FIRST_EDITION))


def latest(client: httpx.Client) -> tuple[int, str, bytes] | None:
    """(edition year, url, file bytes) of the newest edition found, newest first."""
    for yy in range(dt.date.today().year % 100 + 1, FIRST_EDITION - 1, -1):
        url = URL.format(yy=yy)
        r = client.get(url)
        time.sleep(1)                       # one request a second to nces.ed.gov
        if r.status_code == 200 and "spreadsheet" in r.headers.get("content-type", ""):
            return 2000 + yy, url, r.content
    return None


def refresh(status=print) -> bool:
    """True when the table is current (loaded or unchanged); False when nothing could be fetched or parsed."""
    import openpyxl
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        if not _robots_ok(client):
            status("tuition: robots.txt disallows the Digest tables; not fetched")
            return False
        found = latest(client)
    if not found:
        status("tuition: no Table 330.10 edition found")
        return False
    edition, url, data = found
    sha = hashlib.sha256(data).hexdigest()
    with db.connect() as conn:
        have = conn.execute("SELECT max(edition_year), max(file_sha256) FROM tuition_averages").fetchone()
        if have and have[0] == edition and have[1] == sha:
            status(f"tuition: Digest {edition} already loaded")
            return True
        ws = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
        rows, base = parse_rows([list(r) for r in ws.iter_rows(values_only=True)])
        if len(rows) < 100:
            status(f"tuition: only {len(rows)} rows parsed from {url}; keeping the previous data")
            return False
        with conn.transaction():
            conn.execute("DELETE FROM tuition_averages")
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO tuition_averages (control, level, year_start, academic_year, tuition_fees_current,
                           tuition_fees_constant, total_current, total_constant, constant_base, edition_year,
                           source_url, file_sha256)
                       VALUES (%(control)s, %(level)s, %(year_start)s, %(academic_year)s, %(tuition_fees_current)s,
                           %(tuition_fees_constant)s, %(total_current)s, %(total_constant)s, %(base)s, %(edition)s,
                           %(url)s, %(sha)s)""",
                    [{**r, "base": base, "edition": edition, "url": url, "sha": sha} for r in rows])
    status(f"tuition: loaded Digest {edition} ({len(rows)} rows, constant {base} dollars)")
    return True


if __name__ == "__main__":
    if sys.argv[1:] == ["refresh"]:
        sys.exit(0 if refresh() else 1)
    print(__doc__)
