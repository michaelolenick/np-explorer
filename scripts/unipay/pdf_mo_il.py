"""PDF-only B sources (follow-up task 2c): University of Missouri System salary reports (MOspace), Missouri State
University FY27 budget salary detail, Illinois State University salary lists.

Fetch:   python pdf_mo_il.py fetch [mo_um|mo_msu|il_isu ...]     (network only; files + manifest under ~/unipay-data/<key>/)
Verify:  python pdf_mo_il.py verify <key>                        (no DB; per-page counts, number parsing, reconciliation, spot checks)
Loading goes through load.py once SPECS here is merged into parsers.SPECS.

PDFs are processed one page at a time (page.close() after each) to keep memory low on the dev box.
"""
import collections
import json
import random
import re
import statistics
import sys

import pdfplumber

from common import DATA, join_name, polite_get, to_num  # noqa: F401
from fetch import get_file, manifest

MONEY = re.compile(r"^\$?\(?[\d,]+(\.\d+)?\)?$")


def comps(d):
    return {k: v for k, v in d.items() if v is not None}


def pages(path, first=0, last=None, chunk=25):
    """Yield (page_no, words, text) one page at a time. The PDF is reopened every `chunk` pages because pdfplumber /
    pdfminer keep per-document caches that page.close() alone does not release (keeps RSS low on the dev box)."""
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
    end = n if last is None else min(n, last)
    for start in range(first, end, chunk):
        with pdfplumber.open(path) as pdf:
            for i in range(start, min(start + chunk, end)):
                p = pdf.pages[i]
                try:
                    words = p.extract_words(use_text_flow=False, keep_blank_chars=False)
                    text = p.extract_text() or ""
                finally:
                    p.close()
                yield i + 1, words, text


def lines_of(words, tol=2.5):
    """Group words into visual lines by their top coordinate."""
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    return [(top, sorted(ws, key=lambda w: w["x0"])) for top, ws in rows]


def _join(ws):
    return " ".join(w["text"] for w in ws).strip() or None


# ---------------------------------------------------------------- University of Missouri System (MOspace)
MOSPACE_COLLECTION = "e9ae9f73-aa9b-44e7-aca2-a3bc09223743"  # handle 10355/43681
MO_UM_ITEMS = {  # year label -> MOspace item uuid (from the collection listing)
    "2025_2026": "18938a72-809a-4e64-8ddf-b3f7c096965f",
    "2024_2025": "82a3134e-ad47-404b-8cfc-a5fcb1d7d58b",
}
MO_UM_BU = {"COLUM": "University of Missouri", "KCITY": "University of Missouri-Kansas City",
            "ROLLA": "Missouri University of Science and Technology", "STLOU": "University of Missouri-St. Louis",
            "UMSYS": "University of Missouri System", "HOSPT": "MU Health Care"}  # HOSPT rows: hospital/clinic departments


def fetch_mo_um():
    """MOspace (DSpace 7). robots.txt: Crawl-delay 10, /server/api not disallowed. Bitstream = ORIGINAL bundle PDF."""
    for label, uuid in MO_UM_ITEMS.items():
        name = f"mo_um_{label}.pdf"
        if name in manifest("mo_um")["files"]:
            print("  have", name)
            continue
        r = polite_get(f"https://mospace.umsystem.edu/server/api/core/items/{uuid}/bundles", params={"embed": "bitstreams"}, delay=10)
        url = None
        for b in r.json()["_embedded"]["bundles"]:
            if b["name"] == "ORIGINAL":
                bs = b["_embedded"]["bitstreams"]["_embedded"]["bitstreams"][0]
                url = bs["_links"]["content"]["href"]
        get_file("mo_um", url, name, delay=10,
                 notes=f"MOspace item {uuid} (collection handle 10355/43681); MOspace rights statement: protected by copyright, "
                       "all rights reserved unless otherwise indicated")


def _um_header(lines):
    for top, ws in lines:
        t = [w["text"] for w in ws]
        if "Name" in t and "Department" in t and "Job" in t:
            return top, {w["text"]: w for w in ws}
    return None, None


def parse_mo_um(path, fname):
    fy = int(re.search(r"_(\d{4})\.pdf$", fname).group(1))  # report 2025-26 -> 2026
    for pno, words, text in pages(path):
        yield from _um_page(pno, words, fy)


def _um_page(pno, words, fy):
    lines = lines_of(words)
    htop, h = _um_header(lines)
    if h is None:
        return
    x_bu, x_dep, x_job = h["Business"]["x0"], h["Department"]["x0"], h["Job"]["x0"]
    x_w2_end = h.get("Box51", h.get("W2"))["x1"]
    x_sal = h["Salary"]["x0"]
    for top, ws in lines:
        if top <= htop + 1:
            continue
        name, w2, bu, dep, job, rate = [], [], [], [], [], []
        for w in ws:
            x0, x1, t = w["x0"], w["x1"], w["text"]
            if x0 < x_bu - 2:
                (w2 if MONEY.match(t) and x1 > x_w2_end - 45 else name).append(w)
            elif x0 < x_dep - 2:
                bu.append(w)
            elif x0 < x_job - 2:
                dep.append(w)
            elif MONEY.match(t) and x1 > x_sal:
                rate.append(w)
            else:
                job.append(w)
        raw = {"page": pno, "line": _join(ws)}
        if not bu:  # not a data row (footnote, wrapped text): surfaced by verify()
            yield {"_nondata": True, "raw": raw}
            continue
        w2v = to_num(_join(w2)) if w2 else None
        ratev = to_num(_join(rate)) if rate else None
        b = _join(bu)
        yield dict(institution=MO_UM_BU.get(b, f"University of Missouri ({b})"), person_name=_join(name), title=_join(job),
                   department=_join(dep), base_pay=ratev if ratev is not None and ratev >= 1000 else None, other_pay=None,
                   total_pay=w2v,
                   pay_components=comps({"w2_box5_wages": w2v, "salary_rate": ratev,
                                         "rate_kind": None if ratev is None else ("annual" if ratev >= 1000 else "hourly/per-unit"),
                                         "business_unit": b}),
                   fiscal_year=fy, raw={**raw, "cells": {"name": _join(name), "w2_box5": _join(w2), "business_unit": b,
                                                        "department": _join(dep), "job_title": _join(job), "salary_rate": _join(rate)}})


# ---------------------------------------------------------------- Missouri State University (FY27 budget book)
MSU_URL = "https://www.missouristate.edu/FinancialServices/_Files/FY27OpeartingBudgetDetail.pdf"
MSU_ROW = re.compile(r"^(?P<org>.*?)\s*(?P<fund>[A-Z]\d{5})\s+(?P<orgn>\d{6})\s+(?P<acct>\d{5})\s+(?P<prog>\d{3})\s+"
                     r"(?P<name>.+?)\s+(?P<pos>[A-Z]\d{5})\s+\$(?P<amt>[\d,]+(?:\.\d*)?)\s+(?P<fte>\d+\.\d+)$")
MSU_TOT = re.compile(r"^(?P<key>\S+) Total \$(?P<amt>[\d,]+(?:\.\d*)?) (?P<fte>[\d.]+)$")


def fetch_mo_msu():
    get_file("mo_msu", MSU_URL, "msu_fy2027_operating_budget_detail.pdf")


def _msu_lines(path):
    """(page, line) for the 'Detail Full-Time Salary Budget' section only."""
    for pno, words, text in pages(path):
        if "Detail Full" not in text[:120] or "Salary Budget" not in text[:120]:
            continue
        for ln in text.splitlines():
            yield pno, ln.strip()


def parse_mo_msu(path, fname):
    org = None
    for pno, ln in _msu_lines(path):
        m = MSU_ROW.match(ln)
        if not m:
            continue
        if m.group("org"):
            org = m.group("org").strip()
        name = m.group("name").strip()
        if name.lower().startswith("vacant"):
            continue
        amt = to_num(m.group("amt"))
        inst = "Missouri State University-West Plains" if (m.group("fund")[:3] in ("A92", "H92", "D92") or (org or "").startswith("WP ")) \
            else "Missouri State University"
        yield dict(institution=inst, person_name=name, title=None, department=org, base_pay=amt, other_pay=None, total_pay=None,
                   pay_components=comps({"budget_amount": amt, "fte": to_num(m.group("fte")), "fund": m.group("fund"),
                                         "orgn": m.group("orgn"), "account": m.group("acct"), "program": m.group("prog"),
                                         "position": m.group("pos"),
                                         # the PDF text layer clips some amounts after one decimal digit (e.g. '$124,080.3');
                                         # kept as extracted (error < $0.10) and flagged
                                         "amount_text_clipped": True if re.search(r"\.\d$", m.group("amt")) else None,
                                         "note": "one row per budget line; split-funded people have several lines"}),
                   fiscal_year=2027, raw={"page": pno, "line": ln, "org_description": org})


# ---------------------------------------------------------------- Illinois State University
ISU_FILES = {"2023": "https://files.library.illinoisstate.edu/ISUSalaries/fy23_salaries.pdf",
             "2024": "https://files.library.illinoisstate.edu/ISUSalaries/fy24_salaries.pdf"}


def fetch_il_isu():
    """FY2023-24 from files.library (plain GET). FY2025-26 live only on ir.library.illinoisstate.edu, whose
    viewcontent.cgi downloads return a Cloudflare challenge (403) to scripted requests: not fetched."""
    for y, u in ISU_FILES.items():
        get_file("il_isu", u, f"isu_fy{y}.pdf")


ISU_COLS = ["last", "first", "title", "dept", "months", "fte", "sal_prev", "sal"]


def _isu_cols(lines):
    """Column start x positions found from the data itself: every data row has a word starting exactly at each column's
    left edge (cells are left-aligned; '$' signs of both salary columns too), so the 8 most frequent word x0 values on
    the page, kept only if shared by at least half of the rows, are the column starts. Returns (starts, header_bottom)."""
    hdr_bottom = None
    for top, ws in lines[:10]:
        if any(w["text"] == "Months" for w in ws) or any(w["text"] == "Last" for w in ws):
            hdr_bottom = max(hdr_bottom or 0, max(w["bottom"] for w in ws))
    if hdr_bottom is None:
        return None, None
    body = [ws for top, ws in lines if top > hdr_bottom + 1]
    cnt = collections.Counter(round(w["x0"]) for ws in body for w in ws)
    starts = sorted(x for x, n in cnt.most_common(8) if n >= 0.5 * len(body))
    if len(starts) != 8:
        return None, hdr_bottom
    return starts, hdr_bottom


def parse_il_isu(path, fname):
    fy = int(re.search(r"fy(\d{4})", fname).group(1))
    for pno, words, text in pages(path):
        lines = lines_of(words)
        starts, hb = _isu_cols(lines)
        group = (text.splitlines()[1:2] or [""])[0].strip()
        if not starts:
            if hb is not None:
                yield {"_nondata": True, "raw": {"page": pno, "line": "PAGE SKIPPED: column starts not found", "group": group}}
            continue
        for top, ws in lines:
            if top <= hb + 1:
                continue
            cell = collections.defaultdict(list)
            for w in ws:
                i = max((j for j, x in enumerate(starts) if x <= w["x0"] + 1), default=0)
                cell[ISU_COLS[i]].append(w)
            raw = {"page": pno, "line": _join(ws), "group": group}
            if not cell.get("last") or not cell.get("sal"):
                yield {"_nondata": True, "raw": raw}
                continue
            sal_txt = (_join(cell["sal"]) or "").replace("$", "").strip()
            prev_txt = (_join(cell.get("sal_prev", [])) or "").replace("$", "").strip()
            sal = None if sal_txt in ("", "-") else to_num(sal_txt)
            prev = None if prev_txt in ("", "-") else to_num(prev_txt)
            yield dict(institution="Illinois State University", person_name=join_name(_join(cell["first"]), None, _join(cell["last"])),
                       title=_join(cell["title"]), department=_join(cell["dept"]), base_pay=None, other_pay=None, total_pay=None,
                       pay_components=comps({f"salary_fy{fy}_as_published": sal, f"salary_fy{fy - 1}_as_published": prev,
                                             # e.g. '$ 9 .25': a gap inside the number may hide a missing digit; kept as text only
                                             f"salary_fy{fy - 1}_text_unparsed": prev_txt if prev_txt not in ("", "-") and prev is None else None,
                                             f"salary_fy{fy}_text_unparsed": sal_txt if sal_txt not in ("", "-") and sal is None else None,
                                             "contract_months": to_num(_join(cell.get("months", []))), "fte": to_num(_join(cell.get("fte", []))),
                                             "employee_group": group,
                                             "unit_note": "amount as published; the PDF does not state the unit (values look like monthly salary amounts and hourly rates), so it is not annualized"}),
                       fiscal_year=fy, raw={**raw, "cells": {k: _join(v) for k, v in cell.items()}})


# ---------------------------------------------------------------- specs (merge into parsers.SPECS)
def _data_only(gen):
    def f(path, fname):
        for r in gen(path, fname):
            if not r.get("_nondata"):
                yield r
    return f


SPECS = {
    "mo_um": dict(state="MO", system="University of Missouri System annual salary report (MOspace PDFs)", catalog_url_like="%mospace.umsystem.edu%",
                  parse=_data_only(parse_mo_um), file_filter=lambda f: f == "mo_um_2025_2026.pdf",
                  notes="PDF table parsed by column position; fiscal_year = ending year of the report label (2025-26 -> 2026); "
                        "base_pay = 'Salary Rate' when >= $1,000 (annual), smaller rates (hourly/per-unit) only in pay_components; "
                        "total_pay = 'W2 Box 5' (Medicare wages) as published (the PDF does not state the W-2 calendar year). MOspace rights statement: protected by copyright, all "
                        "rights reserved unless otherwise indicated (owner question). Only the 2025-26 report is loaded: the 2024-25 PDF (downloaded, "
                        "not loaded) has a different layout with broken 'ti' ligature glyphs, W2 amounts fused to the business unit and the "
                        "first data row of every page overprinted on the header, so it cannot be extracted reliably."),
    "mo_msu": dict(state="MO", system="Missouri State University FY27 internal operating budget, Detail Full-Time Salary Budget", catalog_url_like="%missouristate.edu%",
                   parse=parse_mo_msu,
                   notes="budgeted (not paid) full-time salary per budget line for FY2027 (year ending 2027-06-30); one row per budget "
                         "line, so split-funded people have several rows; vacant positions skipped; no job titles (position numbers only); "
                         "department = organization description"),
    "il_isu": dict(state="IL", system="Illinois State University salary lists (FY2023, FY2024 PDFs)", catalog_url_like="%illinoisstate.edu%",
                   parse=_data_only(parse_il_isu), file_filter=lambda f: f == "isu_fy2024.pdf",
                   notes="PDF table parsed by column position; salary as of Jan 2 of the fiscal year, as published (monthly amount or "
                         "hourly rate; units not stated so base_pay left NULL and the value kept in pay_components); FY2024 file only: the FY2023 PDF uses a different layout that the column detector does not handle (downloaded, not loaded); FY2025+ only behind a Cloudflare challenge"),
}
FETCHERS = {"mo_um": fetch_mo_um, "mo_msu": fetch_mo_msu, "il_isu": fetch_il_isu}
RAW_PARSERS = {"mo_um": parse_mo_um, "mo_msu": parse_mo_msu, "il_isu": parse_il_isu}


# ---------------------------------------------------------------- verification (no DB)
def verify(key, sample=20, seed=7):
    m = json.loads((DATA / key / "manifest.json").read_text())
    rnd = random.Random(seed)
    for fname in sorted(m["files"]):
        if SPECS[key].get("file_filter") and not SPECS[key]["file_filter"](fname):
            print(f"== {key}/{fname}: excluded by file_filter")
            continue
        path = DATA / key / fname
        per_page, nondata, bad_num, nrows, empty, samp, nnon = collections.Counter(), [], 0, 0, 0, [], 0
        inst = collections.Counter()
        for r in RAW_PARSERS[key](path, fname):
            if r.get("_nondata"):
                nnon += 1
                if len(nondata) < 200:
                    nondata.append(r["raw"])
                continue
            per_page[r["raw"]["page"]] += 1
            inst[r["institution"]] += 1
            pc = r["pay_components"]
            vals = [v for k, v in pc.items() if k in ("salary_rate", "w2_box5_wages", "budget_amount") or k.startswith("salary_fy")]
            vals = [v for v in vals if not isinstance(v, str)]
            raw_money = [x for x in (r["raw"].get("cells") or {}).values() if x and "$" in x and x.strip() not in ("$", "$ -")]
            if len(vals) < len(raw_money):
                bad_num += 1
                if bad_num <= 10:
                    print("   money parse failure:", r["raw"]["page"], r["raw"]["line"], r["raw"].get("cells"))
            nrows += 1
            empty += not r["person_name"]
            if len(samp) < sample:  # reservoir sample keeps memory flat
                samp.append(r)
            else:
                j = rnd.randrange(nrows)
                if j < sample:
                    samp[j] = r
        counts = sorted(per_page.values())
        print(f"== {key}/{fname}: rows {nrows}; pages with rows {len(per_page)}; per-page min/median/max "
              f"{counts[0] if counts else 0}/{statistics.median(counts) if counts else 0}/{counts[-1] if counts else 0}")
        med = statistics.median(counts) if counts else 0
        odd = sorted((p, n) for p, n in per_page.items() if n < 0.7 * med)
        print("   pages with few rows:", odd[:30])
        print("   institutions:", dict(inst))
        print("   money cells that failed to parse:", bad_num)
        print("   non-data lines:", nnon, [d["line"] for d in nondata[:12]])
        print("   empty names:", empty, flush=True)
        yield fname, samp


def spot_check(key, picks):
    """Compare sampled rows with the raw page text: every parsed cell value must appear on that page's text line."""
    by_file = collections.defaultdict(list)
    for fname, r in picks:
        by_file[fname].append(r)
    ok = bad = 0
    for fname, rs in by_file.items():
        want = {r["raw"]["page"] for r in rs}
        texts = {}
        for pno, words, text in pages(DATA / key / fname):
            if pno in want:
                texts[pno] = text
        for r in rs:
            t = texts.get(r["raw"]["page"], "")
            line = next((ln for ln in t.splitlines() if r["raw"]["line"] and ln.strip() == r["raw"]["line"].strip()), None)
            cells = [v for v in (r["raw"].get("cells") or {}).values() if v] if r["raw"].get("cells") else [r["raw"]["line"]]
            hit = line is not None and all(c in line for c in cells)
            ok += hit
            bad += not hit
            print(f"   {'OK ' if hit else 'BAD'} p{r['raw']['page']}: {r['person_name']} | {r['title']} | {r['department']} | "
                  f"base={r['base_pay']} total={r['total_pay']} | {json.dumps({k: v for k, v in r['pay_components'].items() if k not in ('unit_note', 'note')})[:160]}")
    print(f"   spot check: {ok} match, {bad} mismatch")


def msu_reconcile(path):
    """Sum budget lines (incl. vacant) per account within each org and compare with the printed 'acct Total' lines."""
    cur, mism, checked = collections.defaultdict(float), [], 0
    fte = collections.defaultdict(float)
    for pno, ln in _msu_lines(path):
        m = MSU_ROW.match(ln)
        if m:
            cur[m.group("acct")] += to_num(m.group("amt"))
            fte[m.group("acct")] += float(m.group("fte"))
            continue
        t = MSU_TOT.match(ln)
        if t and len(t.group("key")) == 5 and t.group("key") in cur:
            checked += 1
            if abs(cur[t.group("key")] - to_num(t.group("amt"))) > 0.05:
                mism.append((pno, ln, round(cur[t.group("key")], 2)))
            del cur[t.group("key")]
        elif t and len(t.group("key")) == 6:
            cur.clear()
    print(f"   account subtotals checked: {checked}; mismatches: {len(mism)}", mism[:10])


if __name__ == "__main__":
    cmd, keys = sys.argv[1], sys.argv[2:]
    if cmd == "fetch":
        for k in keys or FETCHERS:
            FETCHERS[k]()
    elif cmd == "verify":
        for k in keys:
            picks = []
            for fname, samp in verify(k):
                picks += [(fname, r) for r in samp]
                if k == "mo_msu":
                    msu_reconcile(DATA / k / fname)
            spot_check(k, picks)
