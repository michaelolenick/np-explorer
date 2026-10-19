"""PDF-only B sources (follow-up task 2c): University of Missouri System salary reports (MOspace), Missouri State
University FY27 budget salary detail, Illinois State University salary lists.

Fetch:   python pdf_mo_il.py fetch [mo_um|mo_msu|il_isu ...]     (network only; files + manifest under ~/unipay-data/<key>/)
Register: python pdf_mo_il.py register il_isu                 (hand-downloaded PDFs dropped into ~/unipay-data/il_isu[/manual]/)
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
    "2023_2024": "1a5c00a8-52cd-466b-bafc-0eaf0b11910f",
    "2022_2023": "7907c966-09ee-4fec-981e-6b8310172ffc",
    "2021_2022": "756bf5cf-9bb8-42dc-ab16-9617302c1eb4",
    "2020_2021": "be5cc574-9684-4aa2-8f5c-0b4321dc0f3e",
    "2019_2020": "cf80f345-4957-48a1-a734-8cdc9b442653",
    "2018_2019": "37ebbe39-1e09-44d7-91a2-7b5802c98e0a",
    "2017_2018": "97069164-c1cb-40f5-8d8d-2db4c1a78a9b",
    "2016_2017": "f55809ef-a8dd-407d-83fb-d958b7c4dcfc",
    "2015_2016": "5ce773f4-d4c4-421e-8056-7d07478632b3",
    "2014_2015": "4d5f1951-e124-4d21-9258-529bd2a1ede5",
    "2013_2014": "1e9381e2-0452-4deb-b54c-ff632df930c0",
}  # all 13 items in the collection (Oct 2026); each has one ORIGINAL PDF
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


# Older UM System reports (2013-14 .. 2024-25): layouts change almost every year. Per year: whether the file has a W-2
# column, whether the rate is followed by a W-2 amount (2017-18), and whether it is a Qt-rendered file whose header row
# is drawn over the first data row (chars of the header sit 1 pt above that row's chars and are dropped by position).
MO_UM_LAYOUT = {
    "2013_2014": dict(tail=("rate",)),
    "2014_2015": dict(tail=("rate",)),
    "2015_2016": dict(tail=("rate",)),
    "2017_2018": dict(tail=("rate", "w2")),
    "2018_2019": dict(tail=("rate",)),
    "2019_2020": dict(tail=("rate",)),
    "2020_2021": dict(tail=("rate",), qt=True),
    "2021_2022": dict(tail=("rate",), qt=True),
    "2022_2023": dict(tail=("rate",)),
    "2023_2024": dict(tail=("rate",), qt=True),
    "2024_2025": dict(tail=("rate",), qt=True),
}
_MO_UM_QT = ("Qt-rendered PDF: the header row is drawn over each page's first data row (whose salary rate is lost), words of "
             "adjacent columns overlap and amounts sit on a different baseline than the text, so rows split or merge (2020-21 test: "
             "759 duplicate and 24 missing Idx numbers, 876 rows without a rate): not reliably extractable")
MO_UM_SKIP = {"mo_um_2016_2017.pdf": "fonts are embedded as bare glyph ids (/g38/g50...): the PDF has no usable text layer",
              "mo_um_2020_2021.pdf": _MO_UM_QT, "mo_um_2021_2022.pdf": _MO_UM_QT, "mo_um_2023_2024.pdf": _MO_UM_QT,
              "mo_um_2024_2025.pdf": _MO_UM_QT + " (also broken 'ti' ligature glyphs)"}
_BU = r"(?:[A-Z]{5})"  # business unit codes: COLUM, KCITY, ROLLA, STLOU, UMSYS, HOSPT, UOEXT ...
MO_UM_BU_OLD = {**MO_UM_BU, "UOEXT": "University of Missouri Extension"}
_BU_TOK = re.compile(r"^%s(?:/%s)*\*?$|^[‐-]$" % (_BU, _BU))
_W2_FUSED = re.compile(r"^(\$[\d,]+\.\d\d|Null)(%s)?\*?$" % _BU)
_RATE = re.compile(r"^\$[\d,]+(\.\d+)?$")


def _um_words(page, qt):
    """Words of a page; for Qt files the header row's chars (the line holding 'Idx') are removed first."""
    if qt:
        hdr = [c for c in page.chars if c["text"] == "I" and c["top"] < 120]
        tops = {round(c["top"], 2) for c in page.chars if c["top"] < 120 and c["text"] in "Idx"}
        drop = None
        for t in sorted(tops):
            line = "".join(c["text"] for c in sorted((c for c in page.chars if abs(c["top"] - t) < 0.05), key=lambda c: c["x0"]))
            if line.startswith("IdxName"):
                drop = t
                break
        if drop is not None:
            page = page.filter(lambda o: not (o.get("object_type") == "char" and abs(o["top"] - drop) < 0.05))
        del hdr
    ws = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    for w in ws:
        w["text"] = w["text"].replace("(cid:415)", "ti").replace("Ɵ", "ti").replace("‐", "-")
    return ws


def _um_starts(rows, k=3, gap=40):
    cnt = collections.Counter(round(w["x0"]) for tws in rows for w in tws)
    out = []
    for x, n in cnt.most_common():
        if n < 0.4 * len(rows):
            break
        if all(abs(x - y) >= gap for y in out):
            out.append(x)
        if len(out) == k:
            break
    return sorted(out) if len(out) == k else None


def parse_mo_um_old(path, fname):
    label = re.search(r"mo_um_(\d{4}_\d{4})\.pdf$", fname).group(1)
    cfg = MO_UM_LAYOUT[label]
    fy = int(label[-4:])
    tail = cfg["tail"]
    bu_cur, starts_prev = None, None
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
    for first in range(0, n, 25):
        with pdfplumber.open(path) as pdf:
            for i in range(first, min(first + 25, n)):
                page = pdf.pages[i]
                try:
                    words = _um_words(page, cfg.get("qt"))
                finally:
                    page.close()
                pno = i + 1
                parsed = []
                for top, ws in lines_of(words):
                    toks = list(ws)
                    if any(t["text"] in ("Idx", "Name", "Department", "DEPTNAME") for t in toks) or len(toks) < 3:
                        continue
                    ends_money = bool(_RATE.match(toks[-1]["text"]))
                    # Qt files: the first row of each page lost its rate under the header; it still has Idx + W-2/BU
                    qt_first = cfg.get("qt") and toks[0]["text"].isdigit() and any(_W2_FUSED.match(t["text"]) for t in toks[1:5])
                    if not ends_money and not qt_first:
                        continue
                    cells = {"idx": None, "bu": [], "w2": None, "rate": None}
                    trail = []
                    while toks and _RATE.match(toks[-1]["text"]) and len(trail) < len(tail):
                        trail.insert(0, toks.pop())
                    if tail == ("rate", "w2") and len(trail) == 1:
                        # one amount only: its right edge tells the column (W-2 amounts end further right)
                        cells["w2" if trail[0]["x1"] > 510 else "rate"] = trail[0]["text"]
                    else:
                        for k, t in zip(tail, trail):
                            cells[k] = t["text"]
                    if toks and toks[0]["text"].isdigit():
                        cells["idx"] = toks.pop(0)["text"]
                    while toks and _BU_TOK.match(toks[0]["text"]):
                        cells["bu"].append(toks.pop(0)["text"])
                    if toks:
                        m = re.match(r"^(%s)(?=[A-Z][a-z])(.*)$" % _BU, toks[0]["text"])  # 'COLUMAbadir,Danna'
                        if m:
                            cells["bu"].append(m.group(1))
                            toks[0] = {**toks[0], "text": m.group(2)}
                    rest, after_w2 = [], False
                    for t in toks:
                        m = _W2_FUSED.match(t["text"])
                        if m and cells["w2"] is None and rest:
                            cells["w2"] = m.group(1)
                            after_w2 = True
                            if m.group(2):
                                cells["bu"].append(m.group(2))
                                after_w2 = False
                        elif after_w2 and re.fullmatch(_BU + r"\*?", t["text"]):  # 2022-23: 'Null' / '$x' then 'COLUM'
                            cells["bu"].append(t["text"])
                            after_w2 = False
                        else:
                            after_w2 = False
                            rest.append(t)
                    if not rest:
                        continue
                    parsed.append((ws, rest, cells))
                starts = _um_starts([r for _, r, _ in parsed]) if len(parsed) >= 8 else None
                starts = starts or starts_prev
                if starts is None:
                    for ws, rest, cells in parsed:
                        yield {"_nondata": True, "raw": {"page": pno, "line": _join(ws), "why": "no column starts"}}
                    continue
                starts_prev = starts
                for ws, rest, cells in parsed:
                    col = collections.defaultdict(list)
                    for w in rest:
                        j = max((j for j, x in enumerate(starts) if x <= w["x0"] + 2), default=0)
                        col[("name", "dept", "title")[j]].append(w)
                    if cells["bu"]:
                        bu_cur = " ".join(cells["bu"]).replace(" - ", "/").replace("*", "")
                    rate = to_num(cells["rate"]) if cells["rate"] else None
                    w2 = None if cells["w2"] in (None, "Null") else to_num(cells["w2"])
                    bu = bu_cur
                    inst = MO_UM_BU_OLD.get(bu) if bu else None
                    if inst is None:
                        inst = "University of Missouri" if bu and bu.startswith("COLUM") else (f"University of Missouri ({bu})" if bu else "University of Missouri")
                    raw_cells = {"idx": cells["idx"], "business_unit": " ".join(cells["bu"]) or None, "name": _join(col["name"]),
                                 "department": _join(col["dept"]), "job_title": _join(col["title"]), "w2": cells["w2"], "salary_rate": cells["rate"]}
                    yield dict(institution=inst, person_name=_join(col["name"]), title=_join(col["title"]), department=_join(col["dept"]),
                               base_pay=rate if rate is not None and rate >= 1000 else None, other_pay=None, total_pay=w2,
                               pay_components=comps({"salary_rate": rate, "w2_box5_wages": w2,
                                                     "rate_kind": None if rate is None else ("annual" if rate >= 1000 else "hourly/per-unit"),
                                                     "business_unit": bu, "report": label.replace("_", "-"),
                                                     "salary_rate_missing_in_pdf": True if rate is None and cfg.get("qt") else None}),
                               fiscal_year=fy, raw={"page": pno, "line": _join(ws), "cells": raw_cells})


def parse_mo_um_any(path, fname):
    if fname == "mo_um_2025_2026.pdf":
        return parse_mo_um(path, fname)
    return parse_mo_um_old(path, fname)


def mo_um_check(path, fname, rows):
    """Extra checks for the older reports: Idx continuity where an Idx column exists (every missing number is a lost row),
    rows without a parsed rate, and per-page counts vs lines ending in a $ amount in the pypdf text."""
    idx = sorted(int(r["raw"]["cells"]["idx"]) for r in rows if r["raw"]["cells"].get("idx"))
    out = {}
    if idx:
        missing = sorted(set(range(idx[0], idx[-1] + 1)) - set(idx))
        dup = len(idx) - len(set(idx))
        out["idx_range"] = (idx[0], idx[-1])
        out["idx_missing"] = (len(missing), missing[:10])
        out["idx_dup"] = dup
    out["no_rate"] = sum(1 for r in rows if r["pay_components"].get("salary_rate") is None)
    out["no_name"] = sum(1 for r in rows if not r["person_name"] or "," not in r["person_name"])
    out["no_title"] = sum(1 for r in rows if not r["title"])
    out["no_dept"] = sum(1 for r in rows if not r["department"])
    out["institutions"] = dict(collections.Counter(r["institution"] for r in rows))
    return out


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


ISU_LANDING = "https://ir.library.illinoisstate.edu/salaries"
ISU_MANUAL_NOTE = "downloaded by hand by the site owner (Cloudflare-protected page); supplied 2026-10-18"
# Files present on disk but deliberately not loaded (name relative to ~/unipay-data/il_isu/ -> reason). Any other PDF in
# il_isu/ or il_isu/manual/ is registered by `pdf_mo_il.py register il_isu` and loaded by the generic parser below.
ISU_SKIP = {
    **{f"manual/Illinois State University Salaries FY{y}.pdf":
       "scanned paper list with an OCR text layer (garbled headers and names, e.g. 'nou-Qulbain' for 'Abu-Qulbain', column "
       "order changes between sections): not reliably extractable" for y in range(2013, 2020)},
    "manual/Illinois State University Salaries FY2023.pdf": "same list as isu_fy2023.pdf (files.library copy) plus a cover page; not loaded twice",
    "manual/Illinois State University Salaries FY2024.pdf": "same list as isu_fy2024.pdf (files.library copy) plus a cover page; not loaded twice",
    "manual/Illinois State University Salaries FY2025.pdf": "superseded by 'FY2025 Update', a complete re-issue of the same list as of "
    "5/19/25 (both employee groups; 3,583 vs 3,605 lines, about 95% of names in common, salaries updated for about a fifth); not loaded twice",
}
# The second-to-last salary column is not always the previous fiscal year: FY2026 prints FY2026 salary as of 7/1/25 and as of 1/20/26.
ISU_PRIOR_KEY = {2026: "salary_fy2026_as_of_2025-07-01_as_published"}


def isu_fy(fname):
    m = re.search(r"FY ?(\d{4})", fname) or re.search(r"fy(\d{4})", fname)
    if m:
        return int(m.group(1))
    return 2000 + int(re.search(r"fy(\d\d)_salaries", fname).group(1))


def register_il_isu():
    """Loader path for PDFs dropped into ~/unipay-data/il_isu/ (or manual/) by hand: add each new PDF to the manifest
    with its sha256 (checked against SHA256SUMS when one is present), the landing page as URL and the file time as
    retrieved_at. Then run `load_keys.sh il_isu`."""
    import datetime as dt
    import hashlib
    d = DATA / "il_isu"
    m = manifest("il_isu")
    for sub in ("", "manual/"):
        sums = {}
        if (d / sub / "SHA256SUMS").exists():
            for ln in (d / sub / "SHA256SUMS").read_text().splitlines():
                if ln.strip():
                    h, n = ln.split(None, 1)
                    sums[n.strip().lstrip("*")] = h
        for f in sorted((d / sub).glob("*.pdf")) if (d / sub).is_dir() else []:
            name = sub + f.name
            if name in m["files"]:
                continue
            h = hashlib.sha256(f.read_bytes()).hexdigest()
            if f.name in sums and sums[f.name] != h:
                raise SystemExit(f"sha256 mismatch for {name}")
            m["files"][name] = {"url": ISU_LANDING,
                                "retrieved_at": dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc).isoformat(),
                                "sha256": h, "bytes": f.stat().st_size,
                                "notes": ISU_MANUAL_NOTE if sub == "manual/" else "PDF dropped into ~/unipay-data/il_isu/ by hand (Cloudflare-protected page)"}
            print("  registered", name, h[:12], "(skipped at load: " + ISU_SKIP[name] + ")" if name in ISU_SKIP else "")
    (d / "manifest.json").write_text(json.dumps(m, indent=1))


_ISU_NUM = re.compile(r"^(\$|[\d,.]+%?|[-‐])$")


def _isu_tail(ws):
    """Split a visual line into (text words, months, fte, money groups). Money groups are split at '$' signs when the
    layout prints them, else at gaps between words (digits of one amount touch: '6' '30.00')."""
    i = len(ws)
    while i > 0 and _ISU_NUM.match(ws[i - 1]["text"]):
        i -= 1
    text, tail = ws[:i], ws[i:]
    if len(tail) < 3 or not re.fullmatch(r"\d{1,2}\.\d\d", tail[0]["text"]) or not re.fullmatch(r"\d?\.\d+|\d\.\d+|\d+%", tail[1]["text"]):
        return text, None, None, None
    rest = tail[2:]
    groups = []
    if any(w["text"] == "$" for w in rest):
        for w in rest:
            if w["text"] == "$" or not groups:
                groups.append([w])
            else:
                groups[-1].append(w)
    else:
        for w in rest:
            if groups and w["x0"] - groups[-1][-1]["x1"] < 1.5:
                groups[-1].append(w)
            else:
                groups.append([w])
    return text, tail[0], tail[1], groups


def _isu_val(g):
    toks = [w["text"] for w in g if w["text"] != "$"]
    if any(t.startswith(".") for t in toks[1:]):
        return None, False  # '$ 9 .25': a gap before the decimals may hide a missing digit (same rule as the FY2024 parser): text only
    t = "".join(toks).replace(",", "")
    if t in ("", "-", "‐"):
        return None, True
    v = to_num(t)
    return v, v is not None


def parse_il_isu2(path, fname):
    """Generic Illinois State parser for the born-digital lists (FY2020 on): columns Last | First | Title | [Department] |
    Months | FTE | prior salary | salary. Text column starts are the most common word x0 values of the page's data rows
    (cells are left-aligned; header words are often centred, so they are not used); a page with few rows reuses the
    previous page's starts. Numbers are read from the right end of the line; with a single salary value, its column is
    the one whose right edge (median over the page's two-value rows) is nearest."""
    fy = isu_fy(fname)
    prev_starts, prev_edges, prev_group = None, None, None
    for pno, words, text in pages(path):
        lines = lines_of(words)
        tl = text.splitlines()
        # employee group title ('Non-Tenure Track, ... - FY2021'); some pages print no title: carry the previous page's
        group = next((ln.strip() for ln in tl[:4] if re.search(r"FY ?20\d\d\s*$", ln.strip()) and "Salary" not in ln
                      and not ln.startswith("Last Name")), prev_group)
        prev_group = group
        hdr_txt = " ".join(ln for ln in tl[:8])
        has_dept = "Department" in hdr_txt if "Last Name" in hdr_txt else (prev_starts is not None and len(prev_starts) == 4)
        asof = re.findall(r"[Aa]s [Oo]f (\d{1,2}/\d{1,2}/\d{2,4})", hdr_txt)
        parsed = []
        for top, ws in lines:
            text_ws, mo, fte, groups = _isu_tail(ws)
            if mo is None or not text_ws:
                if any(w["text"] in ("Last", "Name", "Salary", "Illinois") for w in ws) or not ws:
                    continue
                yield {"_nondata": True, "raw": {"page": pno, "line": _join(ws), "group": group}}
                continue
            parsed.append((ws, text_ws, mo, fte, groups))
        ncol = 4 if has_dept else 3
        cnt = collections.Counter(round(w["x0"]) for _, tws, *_ in parsed for w in tws)
        starts = sorted(x for x, n in cnt.most_common(ncol) if n >= 0.5 * len(parsed)) if len(parsed) >= 5 else None
        if not starts or len(starts) != ncol or min(starts) > min((round(t[1][0]["x0"]) for t in parsed), default=0) + 1:
            starts = prev_starts
        two = [g for *_, g in parsed if len(g) == 2]
        edges = (statistics.median(g[0][-1]["x1"] for g in two), statistics.median(g[1][-1]["x1"] for g in two)) if len(two) >= 3 else prev_edges
        if starts is None or edges is None:
            if parsed:
                yield {"_nondata": True, "raw": {"page": pno, "line": f"PAGE SKIPPED: column starts not found ({len(parsed)} rows)", "group": group}}
            continue
        prev_starts, prev_edges = starts, edges
        names = ["last", "first", "title", "dept"][:len(starts)]
        for ws, text_ws, mo, fte, groups in parsed:
            cell = collections.defaultdict(list)
            for w in text_ws:
                i = max((j for j, x in enumerate(starts) if x <= w["x0"] + 1.5), default=0)
                cell[names[i]].append({**w, "text": w["text"].replace("‐", "-").replace("‑", "-")})  # U+2010/2011 hyphens
            if len(groups) == 2:
                gp, gc = groups
            elif len(groups) == 1:
                x1 = groups[0][-1]["x1"]
                gp, gc = (None, groups[0]) if abs(x1 - edges[1]) <= abs(x1 - edges[0]) else (groups[0], None)
            else:
                yield {"_nondata": True, "raw": {"page": pno, "line": _join(ws), "group": group, "why": f"{len(groups)} money groups"}}
                continue
            sal, ok_c = _isu_val(gc) if gc else (None, True)
            prev, ok_p = _isu_val(gp) if gp else (None, True)
            sal_txt = _join(gc) if gc else None
            prev_txt = _join(gp) if gp else None
            raw = {"page": pno, "line": _join(ws), "group": group,
                   "cells": {**{k: _join(v) for k, v in cell.items()}, "months": mo["text"], "fte": fte["text"],
                             "sal_prev": prev_txt, "sal": sal_txt}}
            if not cell.get("last"):
                yield {"_nondata": True, "raw": raw}
                continue
            fte_v = to_num(fte["text"].rstrip("%"))
            if fte["text"].endswith("%") and fte_v is not None:
                fte_v = round(fte_v / 100, 4)
            prior_key = ISU_PRIOR_KEY.get(fy, f"salary_fy{fy - 1}_as_published")
            yield dict(institution="Illinois State University", person_name=join_name(_join(cell.get("first", [])), None, _join(cell["last"])),
                       title=_join(cell.get("title", [])), department=_join(cell.get("dept", [])), base_pay=None, other_pay=None, total_pay=None,
                       pay_components=comps({f"salary_fy{fy}_as_published": sal, prior_key: prev,
                                             f"salary_fy{fy}_text_unparsed": sal_txt if not ok_c else None,
                                             "prior_salary_text_unparsed": prev_txt if not ok_p else None,
                                             "salary_as_of": asof[-1] if asof else None,
                                             "contract_months": to_num(mo["text"]), "fte": fte_v, "employee_group": group,
                                             "unit_note": "amount as published; the PDF does not state the unit (values look like monthly salary amounts and hourly rates), so it is not annualized"}),
                       fiscal_year=fy, raw=raw)


def parse_il_isu_any(path, fname):
    """isu_fy2024.pdf keeps the original FY2024 parser (verified and loaded in round 2); every other file uses parse_il_isu2."""
    if fname == "isu_fy2024.pdf":
        return parse_il_isu(path, fname)
    return parse_il_isu2(path, fname)


# ---------------------------------------------------------------- specs (merge into parsers.SPECS)
def _data_only(gen):
    def f(path, fname):
        for r in gen(path, fname):
            if not r.get("_nondata"):
                yield r
    return f


SPECS = {
    "mo_um": dict(state="MO", system="University of Missouri System annual salary reports (MOspace PDFs)", catalog_url_like="%mospace.umsystem.edu%",
                  parse=_data_only(parse_mo_um_any), file_filter=lambda f: f.endswith(".pdf") and f not in MO_UM_SKIP,
                  notes="PDF tables parsed by column position; fiscal_year = ending year of the report label (2025-26 -> 2026); "
                        "base_pay = salary rate when >= $1,000 (annual), smaller rates (hourly/per-unit) only in pay_components; "
                        "total_pay = W-2 amount where the report has one (2017-18 'W2AMT', 2022-23 and 2025-26 'W2 Box 5'), as published. "
                        "Loaded: 2013-14, 2014-15, 2015-16, 2017-18, 2018-19, 2019-20, 2022-23, 2025-26. Not loaded: 2016-17 (no text "
                        "layer), 2020-21, 2021-22, 2023-24, 2024-25 (Qt-rendered: header drawn over each page's first row, overlapping "
                        "words). Reports that print one business unit for Columbia, the System office and MU Health Care together "
                        "(2017-18 to 2019-20) are labelled University of Missouri (business_unit kept). MOspace rights statement: "
                        "protected by copyright, all rights reserved unless otherwise indicated; owner decided to keep and load."),
    "mo_msu": dict(state="MO", system="Missouri State University FY27 internal operating budget, Detail Full-Time Salary Budget", catalog_url_like="%missouristate.edu%",
                   parse=parse_mo_msu,
                   notes="budgeted (not paid) full-time salary per budget line for FY2027 (year ending 2027-06-30); one row per budget "
                         "line, so split-funded people have several rows; vacant positions skipped; no job titles (position numbers only); "
                         "department = organization description"),
    "il_isu": dict(state="IL", system="Illinois State University salary lists (PDFs, FY2020-FY2026)", catalog_url_like="%illinoisstate.edu%",
                   parse=_data_only(parse_il_isu_any), file_filter=lambda f: f.endswith(".pdf") and f not in ISU_SKIP,
                   notes="PDF tables parsed by column position; salary as published on the list's 'as of' date (Jan of the fiscal year; the "
                         "FY2025 Update file is as of 5/19/25), monthly amount or hourly rate - units not stated, so base_pay is NULL and the "
                         "value is kept in pay_components; FY2023/FY2024 from files.library.illinoisstate.edu; FY2020-2022, FY2025, FY2026 "
                         "downloaded by hand by the site owner from ir.library.illinoisstate.edu (Cloudflare-protected); FY2013-2019 are "
                         "OCR scans and are not loaded"),
}
FETCHERS = {"mo_um": fetch_mo_um, "mo_msu": fetch_mo_msu, "il_isu": fetch_il_isu}
RAW_PARSERS = {"mo_um": parse_mo_um_any, "mo_msu": parse_mo_msu, "il_isu": parse_il_isu_any}


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
            raw_money = [x for x in (r["raw"].get("cells") or {}).values() if x and "$" in x and x.replace("‐", "-").strip() not in ("$", "$ -")]
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
            hy = lambda x: x.replace("‐", "-").replace("(cid:415)", "ti")  # noqa: E731  parsers normalize these glyphs
            line = next((hy(ln) for ln in t.splitlines() if r["raw"]["line"] and hy(ln.strip()) == hy(r["raw"]["line"].strip())), None)
            cells = [str(v) for v in (r["raw"].get("cells") or {}).values() if v] if r["raw"].get("cells") else [r["raw"]["line"]]
            hit = line is not None and all(hy(c) in line for c in cells)
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
    elif cmd == "register" and keys == ["il_isu"]:
        register_il_isu()
    elif cmd == "verify":
        for k in keys:
            picks = []
            for fname, samp in verify(k):
                picks += [(fname, r) for r in samp]
                if k == "mo_msu":
                    msu_reconcile(DATA / k / fname)
            spot_check(k, picks)
