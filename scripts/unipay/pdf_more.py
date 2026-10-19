"""Follow-up sources (PDF and plain-GET re-checks): fetchers, parsers and SPECS in the parsers.SPECS format.

Usage:  pdf_more.py fetch <key> [...]     download files (network only, writes ~/unipay-data/<key>/manifest.json)
        pdf_more.py verify <key> [...]    parse without the DB and print per-page counts + random rows
The loader can merge SPECS into parsers.SPECS (same dict shape).
"""
import collections
import datetime as dt
import os
import random
import re
import statistics
import sys
import urllib.parse

import pdfplumber

from common import DATA, join_name, polite_get, to_num
from fetch import get_file, manifest

UTC = dt.timezone.utc


def comps(d):
    return {k: v for k, v in d.items() if v is not None}


def _pdf_lines(path):
    """Yield (page_no, line_text) for every text line of a PDF (pdfplumber text layer)."""
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            lines = (page.extract_text() or "").splitlines()
            page.flush_cache()  # the dev box is small: release parsed page objects as we go
            page.close()
            for line in lines:
                yield i, line.replace("‐", "-").replace("‑", "-").strip()


# ---------------------------------------------------------------- Maine (UMS public information PDFs, 2019-2021)
ME_CAMPUS = {"MLAW": "University of Maine School of Law", "SWS": "University of Maine System (System Wide Services)",
             "UM": "University of Maine", "UMA": "University of Maine at Augusta", "UMF": "University of Maine at Farmington",
             "UMFK": "University of Maine at Fort Kent", "UMM": "University of Maine at Machias",
             "UMPI": "University of Maine at Presque Isle", "USM": "University of Southern Maine"}
_ME_ROW = re.compile(r"^(MLAW|SWS|UMFK|UMPI|UMA|UMF|UMM|UM|USM)\s+(.+?,.*?)\s+([A-Z0-9&]{2,12})\s+(.*?)\s+(-?[\d,]+\.\d{2})\s+"
                     r"([A-Z]{2})\b\s*(.*?)\s*(\d+\.\d{2})$")
_ME_ASOF = re.compile(r"As of (\w+ \d{1,2}, \d{4})")


def fetch_me_hist():
    """Four 'Salaries of Regular Employees' snapshots (Nov 2019, Apr 2020, Nov 2020, Nov 2021). No index page lists
    them; these are the URLs found in Phase 1. The WordPress media API that could list more needs a login (401)."""
    base = "https://www.maine.edu/human-resources/wp-content/uploads/sites/7/"
    for rel, name in [("2020/02/Public-Information-Document-11.26.19_accessible.pdf", "me_2019-11-26.pdf"),
                      ("2020/04/Public-Information-Document-4.3.20.pdf", "me_2020-04-03.pdf"),
                      ("2020/11/Public-Information-Document-11.3.20.pdf", "me_2020-11-03.pdf"),
                      ("2021/11/UMS_PUBLICINFO_MAIN_11-22-21-dist-1.pdf", "me_2021-11-22.pdf")]:
        get_file("me_hist", base + rel, name)


def parse_me_hist(path, fname):
    asof = None
    for pg, line in _pdf_lines(path):
        m = _ME_ASOF.search(line)
        if m:
            asof = dt.datetime.strptime(m.group(1), "%B %d, %Y").date()
            continue
        m = _ME_ROW.match(line)
        if not m:
            continue
        cmp_, name, dept, title, sal, jobst, rest, fte = m.groups()
        appt = None
        mm = re.search(r"\s*\b(FY|AY|Federal)$", rest)
        if mm:
            appt, rest = mm.group(1), rest[:mm.start()]
        sal = to_num(sal)
        fy = asof.year + (1 if asof.month >= 7 else 0)  # UMS fiscal year runs July-June
        yield dict(institution=ME_CAMPUS[cmp_], person_name=name, title=title or None, department=dept,
                   base_pay=sal, other_pay=None, total_pay=None,
                   pay_components=comps({"salbase": sal, "fte": to_num(fte), "job_status": jobst,
                                         "bargaining_unit": rest.strip() or None, "faculty_appt": appt,
                                         "as_of": asof.isoformat()}),
                   fiscal_year=fy, raw={"page": pg, "line": line, "as_of": asof.isoformat()})


# ---------------------------------------------------------------- DC (DCHR quarterly 'Public Body Employee Information' PDFs, UDC rows)
# File-name date token -> (year, month) of the listing. Names are inconsistent (MMYY, YYMMDD, MMDDYYYY, MMDDYY, 'jun15');
# each was read by hand from the 33 links on the landing page. Only the fiscal year is derived from it.
DC_DATES = {"1213": (2013, 12), "0314": (2014, 3), "0614": (2014, 6), "0914": (2014, 9), "1214": (2014, 12),
            "0415": (2015, 4), "jun15": (2015, 6), "150930": (2015, 9), "151231": (2015, 12), "0316": (2016, 3),
            "jun16": (2016, 6), "sept_16": (2016, 9), "123116": (2016, 12), "03312017": (2017, 3), "06302017": (2017, 6),
            "09302017": (2017, 9), "123117": (2017, 12), "180331": (2018, 3), "063018": (2018, 6), "09302018": (2018, 9),
            "123118": (2018, 12), "03312019": (2019, 3), "06302019": (2019, 6), "09302019": (2019, 9), "191231": (2019, 12),
            "200331": (2020, 3), "200630": (2020, 6), "200930": (2020, 9), "201231": (2020, 12), "210331": (2021, 3),
            "210630": (2021, 6), "210930": (2021, 9), "211231": (2021, 12)}
DC_UDC = "University of the District of Columbia"


def _dc_token(url):
    name = urllib.parse.unquote(url.rsplit("/", 1)[1])
    name = re.sub(r"(_\d)?\.pdf$", "", name, flags=re.I)
    return re.split(r"information_|Information\s+", name)[-1].strip()


def fetch_dc_hist():
    page = "https://dchr.dc.gov/public-employee-salary-information"
    r = polite_get(page)
    links = sorted({urllib.parse.urljoin(page, h) for h in re.findall(r'href="([^"]+\.pdf)"', r.text) if "attachments" in h})
    for u in links:
        tok = _dc_token(u)
        if tok not in DC_DATES:
            print("  !! unknown date token", tok, u)
            continue
        y, mth = DC_DATES[tok]
        get_file("dc_hist", u.replace(" ", "%20"), f"dc_{y}-{mth:02d}.pdf", notes=f"file-name date token '{tok}'")


def _dc_amount(s):
    """'$ 1 22,952.83' -> 122952.83. The text layer inserts a space inside 6-digit amounts (the glyphs touch:
    the '1' ends where '22,952.83' starts), so spaces are dropped before parsing."""
    return to_num(re.sub(r"[\s$]", "", s or ""))


_DC_TEXT = {}  # path -> {page: normalized text}, filled by _dc_udc_pages and reused by the verification


def _dc_norm(t):
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).upper()


def _dc_is_udc(cell):
    return _dc_norm(cell).replace(" ", "").startswith("UNIVERSITYOFTHED")  # 'University of the District of Columbia' / 'of the D.C.'


def _dc_udc_pages(path):
    """Every page whose text names UDC (full pypdf scan; files are sorted by office in some years and by last name in
    others, so UDC rows are not always contiguous)."""
    import pypdf
    rd = pypdf.PdfReader(str(path))
    texts, pages = {}, []
    for i, p in enumerate(rd.pages, 1):
        t = _dc_norm(p.extract_text())
        if "UNIVERSITY OF THE D" in t:
            pages.append(i)
            texts[i] = t
    _DC_TEXT[str(path)] = texts
    return pages


_DC_COLS = [("agency", r"AGENCY|OFFICE"), ("appt", r"TYPE|APPOINTMENT"), ("last", r"LAST"), ("first", r"FIRST"),
            ("title", r"TITLE|POSITION"), ("grade", r"GRADE"), ("rate", r"ANNUAL|RATE|COMPENSATION"), ("start", r"START|HIRE")]


def _dc_colmap(row):
    cells = [_dc_norm(c) for c in row]
    if not any("LAST" in c for c in cells):
        return None
    m = {}
    for j, c in enumerate(cells):
        for key, pat in _DC_COLS:
            if key not in m and re.search(pat, c) and not (key == "title" and "TYPE" in c):
                m[key] = j
                break
    if "title" not in m and "grade" in m and m["grade"] - 1 not in m.values() and m["grade"] - 1 >= 0:
        m["title"] = m["grade"] - 1  # some years print the title header in a merged/blank cell; title always precedes grade
    return m if {"agency", "last", "first", "rate"} <= set(m) else None


def parse_dc_hist(path, fname):
    """UDC rows from pdfplumber tables. Columns are mapped from the table's header row (layouts change across years);
    pages without a ruled table are reported by the verification (and such files are not loaded)."""
    y, mth = map(int, re.search(r"dc_(\d{4})-(\d{2})", fname).groups())
    fy = y + (1 if mth >= 10 else 0)  # DC fiscal year runs October-September
    colmap = None
    with pdfplumber.open(path) as pdf:
        p1 = pdf.pages[0].extract_table() or []
        pdf.pages[0].flush_cache()
        for row in p1[:3]:
            colmap = _dc_colmap(row) or colmap
        for i in _dc_udc_pages(path):
            page = pdf.pages[i - 1]
            table = page.extract_table() or []
            page.flush_cache(); page.close()
            for row in table:
                cm = _dc_colmap(row)
                if cm:
                    colmap = cm
                    continue
                if colmap is None or len(row) <= max(colmap.values()):
                    continue
                cells = [(c or "").replace("\n", " ").replace("\xa0", " ").strip() for c in row]
                if _dc_is_udc(cells[colmap["agency"]]):
                    yield _dc_row(cells, colmap, fy, y, mth, i)


def _dc_row(cells, cm, fy, y, mth, page_no):
    get = lambda k: (re.sub(r"\s+", " ", cells[cm[k]]).strip() or None) if k in cm else None  # noqa: E731
    rate_v = _dc_amount(get("rate"))
    annual = rate_v if rate_v is not None and rate_v >= 1000 else None
    return dict(institution=DC_UDC, person_name=join_name(get("first"), None, get("last")), title=get("title"), department=None,
                base_pay=annual, other_pay=None, total_pay=None,
                pay_components=comps({"annual_rate_as_published": rate_v,
                                      "rate_kind": None if rate_v is None else ("annual" if annual else "hourly/per-unit"),
                                      "grade": get("grade"), "appointment": get("appt"), "start_date": get("start"),
                                      "listing": f"{y}-{mth:02d}"}),
                fiscal_year=fy, raw={"page": page_no, "cells": cells, "columns": cm, "listing": f"{y}-{mth:02d}"})


# One snapshot per DC fiscal year: the September listing where its tables are ruled (pdfplumber can split columns);
# FY2015 uses June 2015 (Sep 2015 is unruled); FY2022 = Dec 2021 (last file published). No listing of FY2016
# (Dec 2015, Mar/Jun/Sep 2016) or FY2019 (Dec 2018, Mar/Jun/Sep 2019) has ruled tables, so those years are not loaded:
# without column rules, multi-word last/first names cannot be split reliably. Dec 2013 has no agency column at all.
DC_ANNUAL = {"dc_2014-09.pdf", "dc_2015-06.pdf", "dc_2017-09.pdf", "dc_2018-09.pdf", "dc_2020-09.pdf", "dc_2021-09.pdf",
             "dc_2021-12.pdf"}


# ---------------------------------------------------------------- Arkansas ADHE Administrator's Compensation Survey
AR_PAGE = "https://adhe.edu/data-publications/administrator%E2%80%99s-compensation-survey"


def fetch_ar_adhe():
    """Every survey year linked from the ADHE landing page (FY10-FY26), one PDF per fiscal year."""
    import html as _h
    r = polite_get(AR_PAGE)
    for h in sorted(set(re.findall(r'href="([^"]+\.pdf)"', r.text, re.I))):
        u = _h.unescape(h)
        m = re.search(r"Compensation[ _]Survey[ _]FY(\d\d)", u, re.I)
        if not m:
            continue
        fy = 2000 + int(m.group(1))
        u = urllib.parse.urljoin(AR_PAGE, u)
        u = urllib.parse.quote(u, safe=":/%()")  # spaces and apostrophes as published
        get_file("ar_adhe", u, f"ar_adhe_fy{fy}.pdf", notes=f"linked from {AR_PAGE}")


_AR_LABEL = re.compile(r"^(\d{1,2})[A-Z(]")
_AR_MONEY_LINES = {8: "salary_within_lim", 9: "state_funds_above_lim", 10: "uams_professional_income", 11: "remaining_salary_other",
                   12: "total_base_salary", 13: "retirement_match", 14: "health_insurance", 15: "life_insurance",
                   16: "social_security_match", 17: "unemployment_insurance", 18: "ltd_insurance", 19: "car",
                   20: "housing", 21: "deferred_comp_paid", 22: "annual_bonus", 23: "special_bonuses",
                   24: "career_service_payment", 25: "additional_life_insurance", 26: "club_dues", 41: "total_compensation"}


def _ar_toc(pdf):
    """Table of contents (page 2): [(start_page_label, entry)] in page order. Entries under 'University of Arkansas
    Fund' etc. are campus names as printed."""
    txt = pdf.pages[1].extract_text() or ""
    pdf.pages[1].flush_cache()
    ents = []
    found = re.findall(r"([A-Z][A-Za-z&'.,\- ]+?)\s*\.{3,}\s*(\d+)", txt)
    if len(found) < 5:  # FY2010-style contents: unicode ellipsis leaders, page numbers split by spaces ('1 95')
        found = re.findall(r"([A-Z][A-Za-z&'.,\- ]+?)\s*(?:\.{3,}|…+)[ .…]*(\d[\d ]*\d|\d)\b", txt)
    if len(found) < 5:  # FY2017-style contents: 'Arkansas Tech University - Page 58'
        found = re.findall(r"([A-Z][A-Za-z&'.,\- ]+?)\s+-\s+Page\s+(\d+)", txt)
    if len(found) < 5:  # FY2019-style contents, two columns: 'Arkansas Tech University ....... Page 65'
        found = re.findall(r"([A-Z][A-Za-z&'.,\- ]+?)\s*\.{3,}\s*Page\s*(\d+)", txt)
    for e, n in found:
        e = re.sub(r"\s+", " ", e).strip()
        n = n.replace(" ", "")
        e = re.sub(r"^(?:[A-Z][A-Z\-]+ )+(?=[A-Z][a-z])", "", e)  # drop section headings glued on ('UNIVERSITIES ...')
        ents.append((int(n), AR_TOC_NAMES.get(e, e)))
    return sorted(ents)


# sub-entries printed under 'University of Arkansas Fund' in the table of contents
AR_TOC_NAMES = {"Fayetteville Campus": "University of Arkansas, Fayetteville",
                "System Administration": "University of Arkansas System Administration",
                "System Office": "University of Arkansas System Administration",
                "Division of Agriculture": "University of Arkansas System Division of Agriculture"}


def _ar_amount(ws):
    toks = [w["text"] for w in ws if w["text"] != "$"]
    if any(re.search(r"\d", t) for t in toks):
        # a neighbouring column's empty-cell dash ('$ -') can sit inside this column's x-range: ignore lone dashes
        toks = [t for t in toks if t != "-"]
    s = "".join(toks).replace(",", "").replace(" ", "")
    if s in ("", "-"):
        return None
    return to_num(s)


def parse_ar_adhe(path, fname):
    with pdfplumber.open(path) as pdf:
        toc = _ar_toc(pdf)
        limit = int(os.environ.get("UNIPAY_MAXPAGES", "0"))  # dev testing only
        for i, page in enumerate(pdf.pages, 1):
            if limit and i > limit:
                break
            words = page.dedupe_chars().extract_words()  # some forms simulate bold by printing each glyph twice
            page.flush_cache(); page.close()
            # 'Name:' can be fused with an overlapping value ('NameD:r.' = 'Name:' + 'Dr.'); the value words after it still read
            if any(re.fullmatch(r"(\d{1,2})?Institution:", w["text"]) for w in words) and any(w["text"].startswith("Name") for w in words):
                r = _ar_form_a(words, i, fname, toc)  # FY2010-FY2019 form
                if r:
                    yield r
                continue
            if not any(w["text"] == "6Employee" for w in words):
                if any(w["text"] == "Reporting:" for w in words) and any(w["text"] == "Last" for w in words):
                    r = _ar_form_b2(words, i, fname, toc)  # same form, other page geometry (e.g. FY2021: separate label numbers)
                    if r:
                        yield r
                continue
            hdr = {}
            for w in sorted(words, key=lambda w: w["x0"]):  # first occurrence: 'Private' also appears in 'Source of Private Funds'
                if w["text"] in ("Public", "Private", "Total", "Source") and 170 < w["top"] < 200:
                    hdr.setdefault(w["text"], w["x0"])
            rows = collections.defaultdict(list)
            labels = {}
            for w in words:
                m = _AR_LABEL.match(w["text"])
                if m and w["x0"] < 90:
                    labels[int(m.group(1))] = w["top"]
            for w in words:
                rows[round(w["top"])].append(w)

            def on_line(n, xmin):
                t = labels.get(n)
                if t is None:
                    return []
                return sorted((w for w in words if abs(w["top"] - t) < 3 and w["x0"] >= xmin), key=lambda w: w["x0"])

            def field(n):
                return " ".join(w["text"] for w in on_line(n, 285)) or None

            def money(n):
                ws = on_line(n, 285)
                pub = [w for w in ws if hdr["Public"] - 12 <= w["x0"] < hdr["Private"] - 12]
                pri = [w for w in ws if hdr["Private"] - 12 <= w["x0"] < hdr["Total"] - 15]
                tot = [w for w in ws if hdr["Total"] - 15 <= w["x0"] < hdr["Source"] - 12]
                src = " ".join(w["text"] for w in ws if w["x0"] >= hdr["Source"] - 12) or None
                return _ar_amount(pub), _ar_amount(pri), _ar_amount(tot), src

            pnum = next((int(w["text"]) for w in sorted(words, key=lambda w: -w["top"]) if w["text"].isdigit()), None)
            inst = next((e for start, e in reversed(toc) if pnum is not None and start <= pnum), None)
            fy_txt, abbr, first, last, title = field(1), field(3), field(5), field(6), field(7)
            m12, m41 = money(12), money(41)
            comp = {}
            for n, k in _AR_MONEY_LINES.items():
                pub, pri, tot, src = money(n)
                for part, v in (("public", pub), ("private", pri), ("total", tot)):
                    if v is not None:
                        comp[f"{k}_{part}"] = v
                if src and n not in (12, 41):
                    comp[f"{k}_private_source"] = src
            # the survey year comes from the publication (file); the per-form 'Fiscal Year Reporting' field is typed by each
            # institution and is sometimes blank or a different year, so it is kept as reported in pay_components only
            fy = int(re.search(r"fy(\d{4})", fname).group(1))
            comp["fiscal_year_reported_on_form"] = fy_txt
            if not last:  # identity block not at the FY2026 positions: read the page's own geometry (e.g. FY2020) or skip
                r = _ar_form_b2(words, i, fname, toc) if any(w["text"] == "Reporting:" for w in words) else None
                if r:
                    yield r
                else:
                    print(f"   !! ar_adhe page {i}: no last name read; form skipped", flush=True)
                continue
            base_tot = m12[2] if m12[2] is not None else nsum_(m12[0], m12[1])
            yield dict(institution=inst, person_name=join_name(first, None, last), title=title, department=None,
                       base_pay=base_tot, other_pay=None, total_pay=m41[2],
                       pay_components=comps({**comp, "institution_abbreviation": abbr, "fice": field(2),
                                             "employee_college_id": field(4)}),
                       fiscal_year=fy,
                       raw={"page": i, "printed_page": pnum, "line": f"{abbr} | {first} {last} | {title} | L12 {m12[:3]} | L41 {m41[:3]}",
                            "fields": {str(n): field(n) for n in range(1, 8)}, "line12": m12, "line41": m41})


def _ar_form_b2(words, i, fname, toc):
    """FY2020+ form with a different page geometry than FY2026 (label numbers as separate words, values and money
    columns elsewhere on the page): positions are read from the page itself; lines and fields as in parse_ar_adhe."""
    rep = next(w for w in words if w["text"] == "Reporting:")
    first = min((w for w in words if abs(w["top"] - rep["top"]) < 3), key=lambda w: w["x0"])  # '1' or glued '1Fiscal'
    labels = {}
    for w in words:
        if w["top"] <= rep["top"] - 3:
            continue
        if re.fullmatch(r"\d{1,2}", w["text"]) and w["x0"] < rep["x0"] - 40:
            labels.setdefault(int(w["text"]), w["top"])
        elif re.match(r"^(\d{1,2})[A-Za-z(]", w["text"]) and w["x0"] <= first["x0"] + 8:
            labels.setdefault(int(re.match(r"^\d{1,2}", w["text"]).group(0)), w["top"])
    hdr = {}
    hline = sorted({round(w["top"]) for w in words if w["text"] == "Public" and w["top"] > rep["top"]})
    for w in sorted(words, key=lambda w: w["x0"]):
        if hline and abs(w["top"] - hline[0]) < 3 and w["text"] in ("Public", "Private", "Total", "Source"):
            hdr.setdefault(w["text"], w["x0"])
    if len(hdr) < 4 or 7 not in labels:
        print(f"   !! ar_adhe page {i}: form layout not recognized; form skipped", flush=True)
        return None
    ends = [w for w in words if w["text"].endswith(":") and w["top"] <= labels[7] + 3]
    starts = []
    for e in ends:
        nxt = [w for w in words if abs(w["top"] - e["top"]) < 3 and w["x0"] > e["x1"] + 2]
        if nxt:
            starts.append(min(w["x0"] for w in nxt))
    vx = (statistics.median(starts) if starts else rep["x1"] + 40) - 3

    def on_line(n, xmin, xmax=9999):
        t = labels.get(n)
        if t is None:
            return []
        return sorted((w for w in words if abs(w["top"] - t) < 3 and xmin <= w["x0"] < xmax), key=lambda w: w["x0"])

    def field(n):
        return " ".join(w["text"] for w in on_line(n, vx)) or None

    def money(n):
        ws = on_line(n, hdr["Public"] - 15)
        t = labels.get(n)
        # the private-fund source text can start just left of its header ('ASU Foundation' at Source-13): stop totals at Source-16
        cols = [(hdr["Public"] - 12, hdr["Private"] - 12), (hdr["Private"] - 12, hdr["Total"] - 15), (hdr["Total"] - 15, hdr["Source"] - 16)]
        out = []
        for lo, hi in cols:
            cw = [w for w in ws if lo <= w["x0"] < hi]
            if cw and cw[-1]["text"].endswith(",") and t is not None:
                # an amount wrapped inside its cell ('372,' / '000$' on the next text line)
                cw += sorted((w for w in words if t + 3 < w["top"] < t + 14 and lo <= w["x0"] < hi), key=lambda w: w["x0"])
            out.append(_ar_amount(cw))
        src = " ".join(w["text"] for w in ws if w["x0"] >= hdr["Source"] - 16) or None
        return out[0], out[1], out[2], src

    lowest = max((w["top"] for w in words), default=0)
    pnum = next((int(w["text"]) for w in sorted(words, key=lambda w: -w["top"]) if w["text"].isdigit() and w["top"] > lowest - 30), None)
    inst = next((e for start, e in reversed(toc) if pnum is not None and start <= pnum), None)
    fy_txt, abbr, first, last, title = field(1), field(3), field(5), field(6), field(7)
    if not last:
        print(f"   !! ar_adhe page {i}: no last name read; form skipped", flush=True)
        return None
    m12, m41 = money(12), money(41)
    comp = {}
    for n, k in _AR_MONEY_LINES.items():
        pub, pri, tot, src = money(n)
        for part, v in (("public", pub), ("private", pri), ("total", tot)):
            if v is not None:
                comp[f"{k}_{part}"] = v
        if src and n not in (12, 41):
            comp[f"{k}_private_source"] = src
    comp["fiscal_year_reported_on_form"] = fy_txt
    fy = int(re.search(r"fy(\d{4})", fname).group(1))
    base_tot = m12[2] if m12[2] is not None else nsum_(m12[0], m12[1])
    return dict(institution=inst, person_name=join_name(first, None, last), title=title, department=None,
                base_pay=base_tot, other_pay=None, total_pay=m41[2],
                pay_components=comps({**comp, "institution_abbreviation": abbr, "fice": field(2), "employee_college_id": field(4)}),
                fiscal_year=fy,
                raw={"page": i, "printed_page": pnum, "line": f"{abbr} | {first} {last} | {title} | L12 {m12[:3]} | L41 {m41[:3]}",
                     "fields": {str(n): field(n) for n in range(1, 8)}, "line12": m12, "line41": m41})


# FY2010-FY2019 form ('Salaries of $100,000 or More'): 24 numbered lines; identity in lines 1-3 (institution, full name,
# title), base salary parts 4-7, total base 8, benefits 9-22, total compensation 23, deferred compensation not paid 24.
_AR_A_MONEY = {4: "salary_within_lim", 5: "state_funds_above_lim", 6: "uams_professional_income", 7: "remaining_salary_other",
               8: "total_base_salary", 9: "retirement_match", 10: "health_insurance", 11: "life_insurance",
               12: "social_security_match", 13: "unemployment_insurance", 14: "ltd_insurance", 15: "car", 16: "housing",
               17: "deferred_comp_paid", 18: "annual_bonus", 19: "special_bonuses", 20: "additional_life_insurance",
               21: "club_dues", 22: "other_compensation", 23: "total_compensation", 24: "deferred_comp_accumulated_not_paid"}


def _ar_norm(printed):
    """Typos, abbreviations and punctuation of a printed institution name -> the FY2020+ label (renamed institutions keep
    the name of that year)."""
    t = re.sub(r"\s+", " ", (printed or "").replace("\u2013", "-")).strip().rstrip(".")
    t = re.sub(r"^\d{3,5}\s+", "", t)  # '0192 Rich Mountain ...' (FICE code typed in front)
    for a, b in (("Univeristy", "University"), ("Uinversity", "University"), ("Unversity", "University"), ("Universitiy", "University"),
                 ("Univrsity", "University"), ("Arkansaas", "Arkansas"), ("Arkanasas", "Arkansas"), ("Akansas", "Arkansas"),
                 ("Arkanss", "Arkansas"), ("Northestern", "Northeastern"), ("Philliips", "Phillips"), ("Colllege", "College"),
                 ("Collge", "College"), ("Collee", "College"), ("Siouth", "South"), ("Archeologicsl", "Archeological"),
                 (" lPine", " Pine"), ("University of AR ", "University of Arkansas ")):
        t = t.replace(a, b)
    t = re.sub(r"^ASU\b", "Arkansas State University", t)
    t = re.sub(r"\s+-\s*|\s*-\s+", " - ", t).strip(" -")  # 'ASU - Mountain Home' style; 'Mid-South' keeps its hyphen
    t = re.sub(r" at (Monticello|Pine Bluff|Fort Smith|Little Rock)$", r" \1", t)
    if t.isupper() and len(t) > 6:
        t = " ".join(w.capitalize() for w in t.split())
    t = re.sub(r"\b(Of|The)\b", lambda m: m.group(1).lower(), t) if t.startswith("College") else t
    return AR_A_NAMES.get(t, AR_A_NAMES.get(t.replace(" - ", " "), t.replace(" - ", " ")))  # unmapped: as printed


def ar_institution(printed, toc_name=None):
    """Printed institution (FY2010-2019 forms) -> label. 'University of Arkansas' is printed by the Fayetteville campus,
    the System office and several UA units alike: the table-of-contents section the page falls in decides where the
    contents list those sections; otherwise it is kept as printed ('University of Arkansas'), not guessed."""
    t = _ar_norm(printed)
    toc = _ar_norm(AR_TOC_NAMES.get(toc_name, toc_name)) if toc_name else None
    if not t:
        return toc
    if t in ("University of Arkansas", "University of Arkansas Fund"):
        return toc if toc and toc not in ("University of Arkansas Fund", "University of Arkansas") else "University of Arkansas"
    return t


AR_A_NAMES = {  # normalized printed name -> FY2020+ label (same institution, same name, different spelling)
    "Arkansas State University - Jonesboro": "Arkansas State University", "Arkansas State University Jonesboro": "Arkansas State University",
    "Arkansas State University - Mountain Home": "Arkansas State University Mountain Home",
    "Arkansas State University - Beebe": "Arkansas State University Beebe", "Arkansas State University - Newport": "Arkansas State University Newport",
    "Arkansas School for Mathematics, Sciences and the Arts": "Arkansas School for Math, Sciences and the Arts",
    "NorthWest Arkansas Community College": "Northwest Arkansas Community College",
    "SAU Tech": "Southern Arkansas University Tech", "Southern Arkansas University Tech ( SAU Tech)": "Southern Arkansas University Tech",
    "Southern Arkansas University Tech (SAU Tech)": "Southern Arkansas University Tech",
    "Southern Arkansas University": "Southern Arkansas University Magnolia", "Southern Arkansas University - Magnolia": "Southern Arkansas University Magnolia",
    "UALR": "University of Arkansas Little Rock", "University of Arkansas - Fort Smith": "University of Arkansas Fort Smith",
    "University of Arkansas Division of Agriculture": "University of Arkansas System Division of Agriculture",
    "University of Arkansas System Office": "University of Arkansas System Administration",
    "University of Arkansas - Monticello": "University of Arkansas Monticello", "University of Arkansas - Pine Bluff": "University of Arkansas Pine Bluff",
    "University of Arkansas - Little Rock": "University of Arkansas Little Rock",
    "Cossatot Community College of the University": "Cossatot Community College of the University of Arkansas",
    "Arkansas State University-Beebe": "Arkansas State University Beebe", "Arkansas State University-Newport": "Arkansas State University Newport",
    "Arkansas State University-Mountain Home": "Arkansas State University Mountain Home",
    "Arkansas State University-Jonesboro": "Arkansas State University", "Southern Arkansas University-Magnolia": "Southern Arkansas University Magnolia",
    "University of Arkansas-Fort Smith": "University of Arkansas Fort Smith", "University of Arkansas-Monticello": "University of Arkansas Monticello",
    "University of Arkansas-Pine Bluff": "University of Arkansas Pine Bluff", "University of Arkansas-Little Rock": "University of Arkansas Little Rock",
    "Phillips Community College": "Phillips Community College of the University of Arkansas",
    "Arkansas State University Mid-South": "Arkansas State University Mid-South",
    "Arkansas Archeologicsl Survey": "Arkansas Archeological Survey", "University of Arkansas Archaeological Survey": "Arkansas Archeological Survey",
    "University of Arkansas: Archaeological Survey": "Arkansas Archeological Survey", "Arkansas Archaeological Survey": "Arkansas Archeological Survey",
    "UA Cossatot": "Cossatot Community College of the University of Arkansas",
    "Criminal Justice Institute--UA System": "Criminal Justice Institute", "University of Arkansas CJI": "Criminal Justice Institute",
    "University of Arkansas Criminal Justice Institute": "Criminal Justice Institute", "University of Arkansas: Criminal Justice Institute": "Criminal Justice Institute",
    "Southern Arkansas Univ Tech (SAU Tech)": "Southern Arkansas University Tech",
    "UA-Pulaski Technical College": "University of Arkansas Pulaski Technical College",
    "UA System Division of Agriculture": "University of Arkansas System Division of Agriculture",
    "University of Arkansas AREON": "AREON", "University of Arkansas: AREON": "AREON", "University of Arkansas Fayetteville AREON": "AREON",
    "University of Arkansas Clinton School of Public Service": "Clinton School of Public Service",
    "University of Arkansas: Clinton School of Public Service": "Clinton School of Public Service", "University of Arkansas CSPS": "Clinton School of Public Service",
    "University of Arkansas Community College at Morrilton (UACCM)": "University of Arkansas Community College at Morrilton",
    "University of Arkansas Community College Hope Texarkana": "University of Arkansas Community College at Hope-Texarkana",
    "University of Arkansas Community College Hope-Texarkana": "University of Arkansas Community College at Hope-Texarkana",
    "University of Arkansas Hope Texarkana": "University of Arkansas Community College at Hope-Texarkana",
    "University of Arkansas Fayetteville": "University of Arkansas, Fayetteville", "University of Arkansas - Fayetteville": "University of Arkansas, Fayetteville",
    "University of Arkansas System": "University of Arkansas System Administration",
    "University of Arkansas at Fort Smith": "University of Arkansas Fort Smith",
    "Arkansas School for Mathematics, Sciences, and the Arts": "Arkansas School for Math, Sciences and the Arts",
}


def _ar_form_a(words, i, fname, toc=()):
    # column headers: 'Public', 'Private', 'Total' on one line; 'Source (of Private Funds)' on that line or the line above
    hdr = {}
    pub = next((w for w in sorted(words, key=lambda w: (w["top"], w["x0"])) if w["text"] == "Public" and w["top"] < 220), None)
    if pub:
        hdr["Public"] = pub["x0"]
        # header words may sit on two baselines (up to ~15 pt apart): search a band around the 'Public' word
        band = sorted((w for w in words if pub["top"] - 20 < w["top"] < pub["top"] + 5 and w["x0"] > pub["x0"]), key=lambda w: w["x0"])
        tot = next((w for w in band if w["text"] == "Total"), None)
        if tot:
            hdr["Total"] = tot["x0"]
            prv = next((w for w in band if w["text"] == "Private" and w["x0"] < tot["x0"]), None)  # not 'Source of Private'
            if prv:
                hdr["Private"] = prv["x0"]
        if "Total" in hdr:
            src = [w for w in words if w["text"] == "Source" and w["x0"] > hdr["Total"] and pub["top"] - 20 < w["top"] < pub["top"] + 5]
            if src:
                hdr["Source"] = min(w["x0"] for w in src)
    if len(hdr) < 4:
        print(f"   !! ar_adhe page {i}: column header not found; form skipped", flush=True)
        return None
    # page geometry varies (some institutions' pages are offset): label numbers sit left of the 'Institution:' label,
    # values start where line 1's value starts
    lab = next(w for w in words if re.fullmatch(r"(\d{1,2})?Institution:", w["text"]))
    labels = {}
    for w in words:
        if w["top"] <= lab["top"] - 3:
            continue
        if re.fullmatch(r"\d{1,2}", w["text"]) and w["x0"] <= lab["x0"] + 2:
            labels.setdefault(int(w["text"]), w["top"])
        elif re.match(r"^(\d{1,2})[A-Za-z(]", w["text"]) and w["x0"] <= lab["x0"] + 2:  # glued '1Institution:', '8Total'
            labels.setdefault(int(re.match(r"^\d{1,2}", w["text"]).group(0)), w["top"])
    vals1 = [w for w in words if abs(w["top"] - lab["top"]) < 3 and w["x0"] > lab["x1"] + 2]
    vx = min((w["x0"] for w in vals1), default=lab["x1"] + 40) - 3

    def on_line(n, xmin, xmax=9999):
        t = labels.get(n)
        if t is None:
            return []
        return sorted((w for w in words if abs(w["top"] - t) < 3 and xmin <= w["x0"] < xmax), key=lambda w: w["x0"])

    def field(n):
        return " ".join(w["text"] for w in on_line(n, vx, hdr["Public"] - 12)) or None

    def money(n):
        ws = on_line(n, hdr["Public"] - 15)
        pub = [w for w in ws if hdr["Public"] - 12 <= w["x0"] < hdr["Private"] - 12]
        pri = [w for w in ws if hdr["Private"] - 12 <= w["x0"] < hdr["Total"] - 15]
        tot = [w for w in ws if hdr["Total"] - 15 <= w["x0"] < hdr["Source"] - 18]
        src = " ".join(w["text"] for w in ws if w["x0"] >= hdr["Source"] - 18) or None
        return _ar_amount(pub), _ar_amount(pri), _ar_amount(tot), src

    inst_p, name, title = field(1), field(2), field(3)
    if not name:
        print(f"   !! ar_adhe page {i}: no name read; form skipped", flush=True)
        return None
    m8, m23 = money(8), money(23)
    comp = {}
    for n, k in _AR_A_MONEY.items():
        pub, pri, tot, src = money(n)
        for part, v in (("public", pub), ("private", pri), ("total", tot)):
            if v is not None:
                comp[f"{k}_{part}"] = v
        if src and n not in (8, 23):
            comp[f"{k}_private_source"] = src
    lowest = max((w["top"] for w in words), default=0)
    pnum = next((int(w["text"]) for w in sorted(words, key=lambda w: -w["top"]) if w["text"].isdigit() and w["top"] > lowest - 30), None)
    toc_name = next((e for start, e in reversed(toc) if pnum is not None and start <= pnum), None)
    fy = int(re.search(r"fy(\d{4})", fname).group(1))
    base_tot = m8[2] if m8[2] is not None else nsum_(m8[0], m8[1])
    return dict(institution=ar_institution(inst_p, toc_name), person_name=name, title=title, department=None,
                base_pay=base_tot, other_pay=None, total_pay=m23[2],
                pay_components=comps({**comp, "institution_as_printed": inst_p, "form_layout": "FY2010-2019 (24 lines)"}),
                fiscal_year=fy,
                raw={"page": i, "printed_page": pnum, "layout": "A",
                     "line": f"{inst_p} | {name} | {title} | L8 {m8[:3]} | L23 {m23[:3]}",
                     "fields": {str(n): field(n) for n in range(1, 4)}, "line12": m8, "line41": m23})


def nsum_(*xs):
    v = [x for x in xs if x is not None]
    return sum(v) if v else None


def _ar_pypdf_lines(path, pages):
    """Independent extraction (pypdf) of lines 12 and 41 for the given pages: {page: {12: (pub, priv, tot), 41: (...)}}.
    For FY2010-2019 forms (layout A) it returns {page: text} instead (see _ar_check)."""
    import pypdf
    rd = pypdf.PdfReader(str(path))
    out = {}
    for pg in pages:
        try:
            t = rd.pages[pg - 1].extract_text() or ""
        except Exception as e:  # noqa: BLE001  pypdf token limit on a few dense pages: counted as a disagreement
            print(f"   pypdf could not read page {pg}: {type(e).__name__}", flush=True)
            out[pg] = {}
            continue
        if re.search(r"^1 Institution:", t, re.M):
            out[pg] = {"A": re.sub(r",\s+", ",", t.replace("$", " "))}
            continue
        # FY2020-style text: amounts wrap inside cells ('372,\n000$') and labels break after one letter ('41 T\notal')
        t = re.sub(r",[ \t]*\n[ \t]*", ",", t)
        t = re.sub(r"(?m)^(\d{1,2} ?[A-Z])\n", r"\1", t)
        d = {}
        for n, label in ((12, "Total Base Salary"), (41, "Total Compensation")):
            m = next((m for m in (re.match(rf"{n} ?{label}", l) for l in t.splitlines()) if m), None)
            if m is None:
                continue
            parts = [p.strip().replace(" ", "").replace(",", "") for p in m.string[m.end():].split("$")][:3]
            d[n] = tuple(None if p in ("", "-") else to_num(p) for p in parts)
        out[pg] = d
    return out


_AR_LAST = {}  # counts from the last _ar_check, used by verify_load to accept or reject a year


def _ar_check(path, rows):
    ind = _ar_pypdf_lines(path, [r["raw"]["page"] for r in rows])
    xdiff, unconf = [], []
    for r in rows:
        d = ind.get(r["raw"]["page"], {})
        if r["raw"].get("layout") == "A":
            # layout A: private amounts carry no '$', so pypdf text cannot be split into columns; instead every amount that
            # pdfplumber read on lines 8 and 23 must appear (as printed, thousands separators) in the pypdf text of the page
            txt = " " + re.sub(r"\s+", " ", d.get("A", "")) + " "
            for n, key in ((8, "line12"), (23, "line41")):
                for v in r["raw"][key][:3]:
                    if v is None:
                        continue
                    forms = {f"{v:,.0f}", f"{v:,.2f}", f"{v:.0f}", f"{v:.2f}", f"{v:,.1f}", f"{v:.1f}"}
                    if not any(re.search(r"(?<![\d,.])" + re.escape(f) + r"(?![\d,])", txt) for f in forms):
                        xdiff.append((r["raw"]["page"], n, v))
            continue
        for n, key in ((12, "line12"), (41, "line41")):
            a = tuple(r["raw"][key][:3])
            b = d.get(n)
            # a conflict is a value pypdf reads differently, or one only pypdf finds; amounts pypdf cannot read at all
            # (its text layer drops some wrapped cells) are counted separately as unconfirmed
            if b is None or any(y is not None and (x is None or abs(x - y) > 0.005) for x, y in zip(a, b)):
                xdiff.append((r["raw"]["page"], n, a, b))
            elif any(x is not None and y is None for x, y in zip(a, b)):
                unconf.append((r["raw"]["page"], n))
    xmsg = (f"pdfplumber-vs-pypdf disagreements on lines 12/41 (all forms): {len(xdiff)} {xdiff[:6]}; "
            f"amounts pypdf cannot read (unconfirmed): {len(unconf)}; ")
    bad12 = [r["raw"]["page"] for r in rows if None not in r["raw"]["line12"][:3] and abs((r["raw"]["line12"][0] or 0) + (r["raw"]["line12"][1] or 0) - r["raw"]["line12"][2]) > 1]
    bad41 = [r["raw"]["page"] for r in rows if r["raw"]["line41"][2] is not None and abs((r["raw"]["line41"][0] or 0) + (r["raw"]["line41"][1] or 0) - r["raw"]["line41"][2]) > 1]
    under = [r["raw"]["page"] for r in rows if r["base_pay"] is not None and r["base_pay"] < 100000]
    # FY2020+ forms have separate first/last fields (joined 'Last, First'); FY2010-2019 forms print the name as one field
    noname = [r["raw"]["page"] for r in rows if not r["person_name"] or (r["raw"].get("layout") != "A" and "," not in r["person_name"])]
    nobase = [r["raw"]["page"] for r in rows if r["base_pay"] is None]
    nototal = [r["raw"]["page"] for r in rows if r["total_pay"] is None]
    noinst = [r["raw"]["page"] for r in rows if not r["institution"]]
    fys = collections.Counter(r["fiscal_year"] for r in rows)
    _AR_LAST.clear()
    _AR_LAST.update(rows=len(rows), xdiff=len(xdiff), noname=len(noname), nobase=len(nobase), noinst=len(noinst), bad12=len(bad12))
    return xmsg + (f"L12 pub+priv!=total: {len(bad12)} {bad12[:10]}; L41 pub+priv!=total: {len(bad41)} {bad41[:10]}; base<100k: {len(under)} {under[:10]}; "
            f"no name: {len(noname)} {noname[:10]}; no base: {len(nobase)} {nobase[:10]}; no total comp: {len(nototal)} {nototal[:10]}; "
            f"no institution: {len(noinst)}; fiscal years {dict(fys)}")


# ---------------------------------------------------------------- Pennsylvania state-related universities: top-200 lists
# Act 1505 (Right-to-Know) requires the 200 highest-paid non-officer employees; PARTIAL coverage by design.
def fetch_pa_pitt():
    base = "https://www.financeoperations.pitt.edu/sites/default/files/"
    get_file("pa_pitt", base + "assets/cfo%20documents/FY24%20PITT%20FORM%20990%20PUBLIC%20DISCLOSURE%20FILED%20COPY%205-28-25.pdf", "pitt_fy2024.pdf")
    get_file("pa_pitt", base + "2026-05/FY25%20PITT%20FORM%20990%20Public%20Disclosure%20Filed%20Copy.pdf", "pitt_fy2025.pdf")


_PITT_ROW = re.compile(r"^(\d{1,3})\s+(.+?)\s+\$\s*([\d ,]+\.\d{2})$")


def parse_pa_pitt(path, fname):
    """Numbered list (1-200) appended to the 990 public disclosure copy: rank, name, total compensation. Rows are
    taken only from pages at/after the first page that mentions 'Non-Officer'."""
    fy = int(re.search(r"fy(\d{4})", fname).group(1))  # 990 tax year (Pitt fiscal year Jul-Jun) the list is filed with
    started = False
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            page.flush_cache(); page.close()
            if not started and re.search(r"Non-?Officer", txt, re.I):
                started = True
            if not started:
                continue
            for line in txt.splitlines():
                m = _PITT_ROW.match(line.strip())
                if not m:
                    continue
                rank, name, amt = m.groups()
                tot = to_num(amt.replace(" ", ""))  # '$ 3 20,362.50' -> 320362.50 (text layer splits 6-digit amounts)
                yield dict(institution="University of Pittsburgh", person_name=name, title=None, department=None,
                           base_pay=None, other_pay=None, total_pay=tot,
                           pay_components=comps({"total_compensation": tot, "rank_top200": int(rank),
                                                 "calendar_year": fy - 1, "list": "200 highest-paid non-officers (990 tax year)"}),
                           fiscal_year=fy, raw={"page": i, "line": line})


def fetch_pa_temple():
    base = "https://finance.temple.edu/sites/finance/files/documents/"
    get_file("pa_temple", base + "Top%20200%20Non-Officer%20Salaries%2005%2027%202026.pdf", "temple_top200_2026-05-27.pdf")
    get_file("pa_temple", base + "Fiscal%202023%20(calendar%202022)%20Top%20200%20Highest%20paid%20employees%20other%20than%20officers.pdf",
             "temple_top200_fy2023.pdf")


def parse_pa_temple(path, fname):
    """'Employee Name | Position Title | Total Compensation' list. Columns are split by word x-position against the
    header words, because names and titles both contain spaces."""
    with pdfplumber.open(path) as pdf:
        cal = None
        for i, page in enumerate(pdf.pages, 1):
            txt = page.extract_text() or ""
            m = re.search(r"Calendar Year (\d{4})", txt)
            cal = int(m.group(1)) if m else cal
            words = page.extract_words()
            page.flush_cache(); page.close()
            hdr = {w["text"]: w["x0"] for w in words if w["text"] in ("Employee", "Position", "Total")}
            if not {"Employee", "Position", "Total"} <= set(hdr):
                continue
            htop = min(w["top"] for w in words if w["text"] == "Employee")
            body = [w for w in words if w["top"] > htop + 5]
            # the title column is left-aligned well left of its centred 'Position Title' header: take the most common
            # left edge of words between the name area and the header word
            xs = collections.Counter(round(w["x0"]) for w in body if hdr["Employee"] + 100 < w["x0"] < hdr["Position"])
            title_x = min((x for x, n in xs.items() if n >= max(xs.values()) * 0.5), default=hdr["Position"]) if xs else hdr["Position"]
            lines = collections.defaultdict(list)
            for w in body:
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w["x0"])
                name = " ".join(w["text"] for w in ws if w["x0"] < title_x - 3)
                title = " ".join(w["text"] for w in ws if title_x - 3 <= w["x0"] < hdr["Total"] - 40)
                amt = " ".join(w["text"] for w in ws if w["x0"] >= hdr["Total"] - 40)
                tot = to_num(amt.replace(" ", ""))
                if not name or "," not in name or tot is None:
                    continue
                yield dict(institution="Temple University", person_name=name, title=title or None, department=None,
                           base_pay=None, other_pay=None, total_pay=tot,
                           pay_components=comps({"total_compensation": tot, "calendar_year": cal,
                                                 "list": "200 highest-paid employees other than officers and directors"}),
                           fiscal_year=cal + 1 if cal else None,
                           raw={"page": i, "line": " | ".join((name, title, amt)), "calendar_year": cal})


# ---------------------------------------------------------------- registry
SPECS = {
    "me_hist": dict(state="ME", system="University of Maine System salaries of regular employees (historical PDFs)",
                    catalog_url_like="%UMS_PUBLICINFO_MAIN%", parse=parse_me_hist,
                    notes="annual base salary snapshots (Nov 2019, Apr 2020, Nov 2020, Nov 2021) parsed from the PDF text layer; "
                          "fiscal_year = UMS fiscal year (Jul-Jun) containing the 'As of' date, so FY2020 has two snapshots "
                          "(pay_components.as_of tells them apart); primary title only; overtime/overload excluded by the publisher"),
    "dc_hist": dict(state="DC", system="DC DCHR quarterly public body employee listings (UDC rows), Dec 2013 - Dec 2021",
                    catalog_url_like="%dchr.dc.gov%", parse=parse_dc_hist, file_filter=lambda f: f in DC_ANNUAL,
                    notes="UDC rows of the DC government employee listing PDFs, one listing per DC fiscal year for FY2014, 2015, "
                          "2017, 2018, 2020, 2021, 2022 (September listings; Jun 2015 for FY2015, Dec 2021 for FY2022; FY2016 and "
                          "FY2019 listings have no table rules and are not loaded); pdfplumber tables with header-mapped columns on pages found by a pypdf "
                          "text scan; point-in-time annual rate; rates under $1,000 are hourly/per-unit and kept only in "
                          "pay_components; fiscal_year = DC fiscal year (Oct-Sep) of the listing month (pay_components.listing); "
                          "other quarterly files are downloaded but not loaded"),
    "ar_adhe": dict(state="AR", system="Arkansas Division of Higher Education Administrator's Compensation Survey (>= $100k)",
                    catalog_url_like="%administrator%compensation-survey%", parse=parse_ar_adhe,
                    notes="PARTIAL coverage: only administrators with salary >= $100,000 at public institutions; one form page per person "
                          "parsed by position (pdfplumber words); base_pay = line 12 total base salary (public + private funds), "
                          "total_pay = line 41 total compensation as published; every line's public/private/total and private-fund "
                          "source in pay_components ('$ -' accounting dashes are stored as NULL, not 0); fiscal_year = the survey's fiscal year (AR FY Jul-Jun, from the publication; "
                          "the per-form typed year is kept as fiscal_year_reported_on_form); institution from the table-of-contents "
                          "section the page falls in. FY2010-FY2019 use the older 24-line form: base_pay = line 8, total_pay = line 23, "
                          "name as printed (one field), institution as printed (typos/abbreviations normalized, institution_as_printed kept; "
                          "'University of Arkansas' split by contents section where the contents list the sub-units, else kept as printed). "
                          "Every year is verified and loaded on its own (ar_years.sh / pdf_more.verify_load): form count vs pypdf, pay parsed, "
                          "pdfplumber-vs-pypdf cross-check of the base and total lines, random sample"),
    "pa_pitt": dict(state="PA", system="University of Pittsburgh 200 highest-paid non-officers (Right-to-Know / 990 disclosure)",
                    catalog_url_like="%financeoperations.pitt.edu%", parse=parse_pa_pitt,
                    notes="PARTIAL coverage: only the 200 highest-paid non-officer employees; name + total compensation (no title); "
                          "compensation is for the calendar year inside the 990 tax year; fiscal_year = 990 tax year end (Jun 30)"),
    "pa_temple": dict(state="PA", system="Temple University 200 highest-paid employees other than officers (Right-to-Know)",
                      catalog_url_like="%temple.edu/about/public-information%", parse=parse_pa_temple,
                      file_filter=lambda f: f.startswith("temple_top200_"),  # RTK-AllData is a contracts report, not pay
                      notes="PARTIAL coverage: only the 200 highest-paid non-officer employees; name, position title, total compensation "
                            "for the calendar year stated in the file; fiscal_year = the 990 fiscal year that calendar year is reported "
                            "in (calendar year + 1, e.g. calendar 2024 -> FY2024-25)"),
}
FETCHERS = {"me_hist": fetch_me_hist, "dc_hist": fetch_dc_hist, "pa_pitt": fetch_pa_pitt, "pa_temple": fetch_pa_temple,
            "ar_adhe": fetch_ar_adhe}


def _top200_check(path, rows):
    ranks = sorted(r["pay_components"].get("rank_top200") for r in rows if r["pay_components"].get("rank_top200"))
    amts = [r["total_pay"] for r in sorted(rows, key=lambda r: (r["raw"]["page"],))]
    desc_breaks = sum(1 for a, b in zip(amts, amts[1:]) if b > a)
    out = f"rows {len(rows)}; amounts not non-increasing in file order: {desc_breaks}; min/max {min(amts) if amts else None}/{max(amts) if amts else None}"
    if ranks:
        out += f"; ranks 1..200 complete: {ranks == list(range(1, 201))} (missing {sorted(set(range(1, 201)) - set(ranks))[:10]})"
    return out


def _me_unmatched(path):
    """Lines after the page-1 legend that start with a campus code but did not parse as a row (should be 0)."""
    bad = [(p, l) for p, l in _pdf_lines(path)
           if p > 1 and re.match(r"^(MLAW|SWS|UMFK|UMPI|UMA|UMF|UMM|UM|USM)\s", l) and not _ME_ROW.match(l)]
    return f"unmatched campus-code lines: {len(bad)} {bad[:5]}"


def _dc_reconcile(path, rows):
    """Per UDC page: count of 'UNIVERSITY OF THE D' mentions in the pypdf text vs table rows parsed (pdfplumber)."""
    texts = _DC_TEXT.get(str(path), {})
    parsed = collections.Counter(r["raw"]["page"] for r in rows)
    diff = {pg: (t.count("UNIVERSITY OF THE D"), parsed.get(pg, 0)) for pg, t in texts.items()
            if t.count("UNIVERSITY OF THE D") != parsed.get(pg, 0)}
    rates = collections.Counter(r["pay_components"].get("rate_kind") for r in rows)
    notitle = sum(1 for r in rows if not r["title"])
    return (f"UDC pages {len(texts)}; text-vs-table mismatches {len(diff)} (page: text, parsed) {dict(list(diff.items())[:12])}; "
            f"text mentions {sum(t.count('UNIVERSITY OF THE D') for t in texts.values())} vs rows {len(rows)}; rate kinds {dict(rates)}; "
            f"no title {notitle}; columns {rows[0]['raw']['columns'] if rows else None}")


EXTRA_CHECKS = {"me_hist": lambda path, rows: _me_unmatched(path), "dc_hist": _dc_reconcile,
                "pa_pitt": _top200_check, "pa_temple": _top200_check, "ar_adhe": _ar_check}


def _verify_rows(key, fname, rows, nsample=20):
    per_page = collections.Counter(r["raw"].get("page") for r in rows)
    pays = [r for r in rows if r["base_pay"] is not None or r["total_pay"] is not None]
    fy = collections.Counter(r["fiscal_year"] for r in rows)
    inst = collections.Counter(r["institution"] for r in rows)
    vals = sorted(per_page.values()) or [0]
    print(f"== {fname}: rows={len(rows)} pages_with_rows={len(per_page)} per-page min/median/max="
          f"{vals[0]}/{statistics.median(vals)}/{vals[-1]} pay_parsed={len(pays)} fy={dict(fy)}")
    print("   institutions:", dict(inst.most_common()))
    low = [p for p, n in per_page.items() if n < statistics.median(vals) * 0.6]
    print("   low-count pages:", sorted(low)[:30])
    if key in EXTRA_CHECKS:
        print("   ", EXTRA_CHECKS[key](DATA / key / fname, rows))
    random.seed(7)
    for r in random.sample(rows, min(nsample, len(rows))):
        print("   ", r["raw"].get("page"), "|", r["person_name"], "|", r["title"], "|", r["base_pay"], r["total_pay"], r["fiscal_year"], "||",
              str(r["raw"].get("line") or r["raw"].get("cells"))[:160], flush=True)
    return len(pays)


def verify(key, nsample=20):
    spec = SPECS[key]
    m = manifest(key)
    only = os.environ.get("UNIPAY_FILE")  # verify a single file (lets a long source release the shared lock between files)
    for fname in sorted(m["files"]):
        if only:
            if fname != only:
                continue
        elif spec.get("file_filter") and not spec["file_filter"](fname):
            continue
        try:
            rows = list(spec["parse"](DATA / key / fname, fname))
        except Exception as e:  # noqa: BLE001
            print(f"== {fname}: PARSE ERROR {type(e).__name__}: {str(e)[:300]}", flush=True)
            continue
        _verify_rows(key, fname, rows, nsample)


def verify_load(key, fname):
    """ar_adhe: parse one year's PDF once, run the verification (rows per page, pay parsed, pdfplumber-vs-pypdf
    cross-check of lines 12/41, random sample) and load that file only if it passes:
    no form without institution, <= 1% forms without a readable name, base salary or any pay, <= 2% line 12/41 disagreements."""
    spec = SPECS[key]
    rows = list(spec["parse"](DATA / key / fname, fname))
    pays = _verify_rows(key, fname, rows)
    c = dict(_AR_LAST)
    n = max(1, len(rows))
    # completeness: form pages counted independently from the pypdf text layer ('1 Institution:' / '1 Fiscal Year Reporting:')
    import pypdf
    forms, unreadable = 0, 0
    for pg in pypdf.PdfReader(str(DATA / key / fname)).pages:
        try:
            t = pg.extract_text() or ""
        except Exception:  # noqa: BLE001
            unreadable += 1
            continue
        forms += bool(re.search(r"(?m)^\s*1\s*(Institution:|Fiscal Year Reporting)", t))
    c.update(forms_in_pdf=forms, pypdf_unreadable_pages=unreadable)
    ok = len(rows) > 0 and len(rows) >= 0.99 * forms and pays >= 0.99 * n and c.get("noinst", 1) == 0 and c.get("noname", n) <= 0.01 * n \
        and c.get("nobase", n) <= 0.01 * n and c.get("xdiff", n) <= 0.02 * n
    print(f"   VERDICT {fname}: {'PASS' if ok else 'FAIL'} {c} pay_parsed={pays}", flush=True)
    if ok:
        import load
        conn = load.connect()
        load.load_file(conn, key, fname, rows)
        conn.close()


if __name__ == "__main__":
    cmd, keys = sys.argv[1], sys.argv[2:]
    for k in keys:
        if cmd == "fetch":
            FETCHERS[k]()
        elif cmd == "verify":
            verify(k)
        elif cmd == "verify_load":
            verify_load(k, os.environ["UNIPAY_FILE"])
