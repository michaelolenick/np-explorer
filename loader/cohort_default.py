"""Federal cohort default rates by school (Department of Education, Federal Student Aid).

  python -m loader.cohort_default [path-or-url]

Reads FSA's "Official CDRs for the past three fiscal years" Excel file (one row per school,
keyed by its 6-digit OPE school code, with the three most recent official 3-year cohort
default rates: number in default, number entering repayment, rate) into
cohort_default_rates, one row per school per cohort fiscal year. These are the federal
government's official rates for federal student loans by school (Prog Length and School Type
are FSA's codes, stored as published); the rates for cohorts that entered repayment during the
2020-2023 federal payment pause are near zero because no payments were due; they are not about the
securitized loans on the student loan ABS pages, which issuers report only as pool totals.

The .xlsx is read with the standard library (zipfile + streaming XML), one row at a time.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from datetime import datetime, timezone
from xml.etree.ElementTree import iterparse

from loader import db, sec

URL = "https://fsapartners.ed.gov/sites/default/files/2026-09/EligibleSchoolFileFY2023OfficialFinal.xlsx"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def rows(data: bytes):
    """Yield each worksheet row as a list of strings (first sheet)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        with z.open("xl/sharedStrings.xml") as f:
            for _, el in iterparse(f):
                if el.tag == NS + "si":
                    shared.append("".join(t.text or "" for t in el.iter(NS + "t")))
                    el.clear()
    sheet = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
    with z.open(sheet) as f:
        for _, el in iterparse(f):
            if el.tag != NS + "row":
                continue
            out: dict[int, str] = {}
            for c in el.iter(NS + "c"):
                v = c.find(NS + "v")
                if c.get("t") == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(NS + "t"))
                elif v is None:
                    continue
                else:
                    val = shared[int(v.text)] if c.get("t") == "s" else v.text
                out[_col(c.get("r"))] = (val or "").strip()
            el.clear()
            if out:
                yield [out.get(i, "") for i in range(max(out) + 1)]


def _num(v: str):
    try:
        return float(v.replace(",", "").replace("%", ""))
    except (AttributeError, ValueError):
        return None


def load(source: str = URL, status=print) -> int:
    data = open(source, "rb").read() if not source.startswith("http") else _download(source)
    it = rows(data)
    header = None
    for r in it:                       # the header row names OPEID
        if any(re.fullmatch(r"OPE ?ID|School Code", x, re.I) for x in r):
            header = [x.strip().lower() for x in r]
            break
    if header is None:
        raise ValueError("no header row with OPEID / School Code")
    find = lambda *pats: next((i for i, h in enumerate(header) if any(re.search(p, h) for p in pats)), None)  # noqa: E731
    i_ope, i_name = find(r"^ope ?id$", r"^school code$"), find(r"^name$", r"school name", r"institution")
    i_city, i_state = find(r"^city$"), find(r"^state", r"^st$")
    i_len, i_type = find(r"prog.*length", r"program length"), find(r"school type", r"^type$")
    # Three cohort years: "Year 1".."Year 3" with fiscal year, number in default, number in repay, rate.
    years = [(find(rf"^year {k}$"), find(rf"^num {k}$"), find(rf"^denom {k}$"), find(rf"^default rate {k}$"))
             for k in (1, 2, 3)]
    now = datetime.now(timezone.utc)
    n = 0
    with db.connect() as conn, conn.cursor() as cur:
        for r in it:
            get = lambda i: r[i] if i is not None and i < len(r) else ""  # noqa: E731
            ope = re.sub(r"\D", "", get(i_ope))
            if not ope:
                continue
            ope = ope.zfill(6) if len(ope) <= 6 else ope.zfill(8)
            for y, d, b, rt in years:
                fy = _num(get(y))
                rate = _num(get(rt))
                if not fy or rate is None:
                    continue
                cur.execute("""
                    INSERT INTO cohort_default_rates (opeid, fiscal_year, school_name, city, state, program_length,
                                                      school_type, borrowers, defaulters, rate, source_url, retrieved_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (opeid, fiscal_year) DO UPDATE SET school_name = excluded.school_name,
                        city = excluded.city, state = excluded.state, program_length = excluded.program_length,
                        school_type = excluded.school_type, borrowers = excluded.borrowers,
                        defaulters = excluded.defaulters, rate = excluded.rate, source_url = excluded.source_url,
                        retrieved_at = excluded.retrieved_at""",
                    (ope, int(fy) if fy > 1900 else int(fy) + 2000, get(i_name) or None, get(i_city) or None,
                     get(i_state) or None, get(i_len) or None, get(i_type) or None,
                     int(_num(get(b))) if _num(get(b)) is not None else None,
                     int(_num(get(d))) if _num(get(d)) is not None else None, rate,
                     source if source.startswith("http") else URL, now))
                n += 1
        conn.commit()
    status(f"cohort default rates: {n} school-years")
    return n


def _download(url: str) -> bytes:
    import httpx
    r = httpx.get(url, headers={"User-Agent": sec.USER_AGENT}, timeout=120, follow_redirects=True)
    r.raise_for_status()
    return r.content


if __name__ == "__main__":
    load(*(sys.argv[1:2] or [URL]))
