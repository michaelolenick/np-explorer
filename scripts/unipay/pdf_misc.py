"""PDF-only B sources (follow-up task 2c): UVM base pay, NMHU salary reports, WMU employee list, Austin Peay, ETSU,
University of Michigan salary record. Fetch with fetch.get_file (manifest + sha256); parse with pdfplumber.

Usage: pdf_misc.py fetch <key> [...] | pdf_misc.py check <key>     (network / local only; no database access)
SPECS has the same shape as parsers.SPECS so load.py can load these keys.
"""
import re
import sys
import urllib.parse

import pdfplumber

from common import DATA, join_name, polite_get, to_num
from fetch import get_file


def _pdf_links(page_url, pattern, delay=2.0):
    r = polite_get(page_url, delay=delay)
    out = []
    for h in re.findall(r'href="([^"]+\.pdf)"', r.text, re.I):
        u = urllib.parse.urljoin(str(r.url), h.replace("&amp;", "&"))
        if re.search(pattern, u, re.I) and u not in out:
            out.append(u)
    return out


# ---------------------------------------------------------------- fetch
def fetch_vt_uvm():
    for u in _pdf_links("https://www.uvm.edu/oira/faculty-and-staff", r"(Base[_-]Pay|/sr\d\d)\.pdf$"):
        fn = urllib.parse.unquote(u.rsplit("/", 1)[1])
        get_file("vt_uvm", u, fn)


def fetch_nm_nmhu():
    for u in _pdf_links("https://www.nmhu.edu/aur/salary-report/", r"Salary-Report", delay=10):
        get_file("nm_nmhu", u, u.rsplit("/", 1)[1], delay=10)


def fetch_mi_wmu():
    get_file("mi_wmu", "https://files.wmich.edu/s3fs-public/attachments/u335/2023/EMPLOYEE_LIST_AS_OF_10_6_23.pdf",
             "EMPLOYEE_LIST_AS_OF_10_6_23.pdf")


def fetch_tn_apsu():
    get_file("tn_apsu", "https://www.apsu.edu/human-resources/documents/employee-salary-data.pdf", "employee-salary-data.pdf", delay=10)


def fetch_tn_etsu():
    get_file("tn_etsu", "https://www.etsu.edu/human-resources/documents/active_employees_as_of_05.22.2024.pdf",
             "active_employees_as_of_05.22.2024.pdf")


def fetch_mi_um():
    get_file("mi_um", "https://hr.umich.edu/sites/default/files/salary_record_2025.pdf", "salary_record_2025.pdf", delay=10)


# ---------------------------------------------------------------- PDF helpers
_MONEY = re.compile(r"^\$?-?[\d,]+(\.\d+)?$")


def _lines(page, ytol=2.5):
    """Group a page's words into text lines (by vertical position), each a list of words sorted by x0."""
    words = page.extract_words(keep_blank_chars=False, x_tolerance=1.5, y_tolerance=2)
    words.sort(key=lambda w: (w["top"], w["x0"]))
    out, cur, top = [], [], None
    for w in words:
        if top is None or abs(w["top"] - top) <= ytol:
            cur.append(w)
            top = w["top"] if top is None else top
        else:
            out.append(sorted(cur, key=lambda w: w["x0"]))
            cur, top = [w], w["top"]
    if cur:
        out.append(sorted(cur, key=lambda w: w["x0"]))
    return out


def _cols(line, bounds):
    """Split one line's words into named columns. bounds = [(name, x_start), ...] ascending; a word goes to the last
    column whose start is <= its x0. Returns {name: text or None}."""
    d = {n: [] for n, _ in bounds}
    for w in line:
        name = bounds[0][0]
        for n, x in bounds:
            if w["x0"] >= x:
                name = n
        d[name].append(w["text"])
    return {k: (" ".join(v) if v else None) for k, v in d.items()}


def _money(s):
    if s is None:
        return None
    s = s.strip()
    return to_num(s) if _MONEY.match(s) else None


def _pages(path, chunk=100):
    """Yield (page_number, page), reopening the PDF every `chunk` pages and closing each page so memory stays bounded."""
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
    for start in range(0, n, chunk):
        with pdfplumber.open(path) as pdf:
            for i in range(start, min(start + chunk, n)):
                page = pdf.pages[i]
                yield i + 1, page
                page.close()


def _base(inst, name, title, dept, base, fy, comps_, raw):
    return dict(institution=inst, person_name=name, title=title, department=dept, base_pay=base, other_pay=None,
                total_pay=None, pay_components={k: v for k, v in comps_.items() if v is not None}, fiscal_year=fy, raw=raw)


# ---------------------------------------------------------------- University of Vermont (List of Base Pay)
def _uvm_fy(fname):
    m = re.match(r"sr(\d\d)\.pdf$", fname)
    if m:
        return 2000 + int(m.group(1)) + 1  # srYY = list as of fall YY (released Nov YY - Jan YY+1) => FY YY+1
    m = re.search(r"FY(\d\d)", fname)
    if m:
        return 2000 + int(m.group(1))
    m = re.search(r"(\d{4})-(\d{4})", fname)
    return int(m.group(2))


_UVM_NAME = re.compile(r"^[^\s,][^,]*, ?[^\s,]")


def parse_vt_uvm(path, fname):
    """Columns: Name | Primary Job Title | Base Pay. Boundaries come from the page's own header words."""
    fy = _uvm_fy(fname)
    for pno, page in _pages(path):
        lines = _lines(page)
        hdr = next((ln for ln in lines if ln[0]["text"].lower() == "name" and any(w["text"].lower() == "primary" for w in ln)), None)
        if not hdr:
            continue  # cover page
        tx = next(w["x0"] for w in hdr if w["text"].lower() == "primary") - 4
        px = next(w["x0"] for w in hdr if w["text"].lower() == "base") - 25
        top = hdr[0]["top"]
        held = None  # first line of a long name that wraps onto the next line (which carries title and pay)
        for ln in lines:
            if ln[0]["top"] <= top + 1:
                continue
            c = _cols(ln, [("name", 0), ("title", tx), ("pay", px)])
            if c["name"] and not c["title"] and not c["pay"] and _UVM_NAME.match(c["name"]) and not re.search(r",\s*$", c["name"]):
                held = c["name"]
                continue
            if held:
                if c["pay"]:
                    c["name"] = (held + " " + (c["name"] or "")).strip()
                    c["wrapped_name"] = True
                held = None
            # a data row has a 'Last,First' name and a pay cell that is a $ amount or a leave marker ('upl', 'unpaid
            # leave'); page footers and the disclaimer paragraph (whose words also fall in these columns) fail this
            if not c["name"] or "," not in c["name"] or not c["pay"]:
                continue
            ptoks = c["pay"].split()
            if len(ptoks) > 1 and _money(ptoks[-1]) is not None:  # a long title spilled into the pay column
                c["title"] = ((c["title"] or "") + " " + " ".join(ptoks[:-1])).strip()
                c["pay"] = ptoks[-1]
            if _money(c["pay"]) is None and c["pay"].lower() not in ("upl", "unpaid leave"):
                continue
            base = _money(c["pay"])
            yield _base("University of Vermont", c["name"], c["title"], None, base, fy,
                        {"base_pay": base, "pay_text": None if base is not None else c["pay"]},
                        {"page": pno, "line": " ".join(w["text"] for w in ln), "cells": c})


# ---------------------------------------------------------------- New Mexico Highlands University
NMHU_LAYOUT = {
    # file -> (fiscal_year, column bounds, name order)
    "NMHU-Salary-Report-3.1.23-1.pdf": (2023, [("last", 0), ("first", 140), ("middle", 195), ("salary", 255), ("fte", 308),
                                                ("title", 342), ("dept", 520)]),
    "NMHU-Salary-Report-FY24.pdf": (2024, [("last", 0), ("first", 105), ("middle", 200), ("salary", 245), ("fte", 320),
                                           ("title", 355), ("dept", 560)]),
    "NMHU-Salary-Report-FY25.pdf": (2025, [("first", 0), ("last", 135), ("dept", 270), ("title", 430), ("fte", 630),
                                           ("salary", 700)]),
    "FY26-NMHU-Salary-Report.pdf": (2026, [("first", 0), ("last", 120), ("fte", 235), ("title", 268), ("salary", 528),
                                           ("dept", 600)]),
}
_HDR_WORDS = {"last", "legal_firstname", "last_name", "full-", "time_e", "mployee", "_factor", "legal_lastname"}


def parse_nm_nmhu(path, fname):
    """One row per published line (people with overloads/second jobs have several lines). FY25 cells are bottom-aligned:
    wrapped title/department text sits on lines above the row's name line and is prepended to that row."""
    fy, bounds = NMHU_LAYOUT[fname]
    pending = []
    for pno, page in _pages(path):
        for ln in _lines(page):
            c = _cols(ln, bounds)
            if ln[0]["text"].lower() in _HDR_WORDS or (c.get("salary") or "").lower().startswith(("annual", "salary")):
                continue
            name_part = c.get("first") if "first" in c and bounds[0][0] == "first" else c.get("last")
            if not name_part:
                pending.append(c)  # wrapped fragment (only title/department columns)
                continue
            for frag in pending:
                for k in ("title", "dept"):
                    if frag.get(k):
                        c[k] = frag[k] + " " + (c[k] or "")
            frags, pending = pending, []
            if not c.get("salary") and c.get("title"):
                # a very long title can run into the salary with no space ('...Collections60,643.52'); split it back
                mm = re.match(r"^(.*?)(\d{1,3}(?:,\d{3})*\.\d{2})$", c["title"])
                if mm:
                    c["title"], c["salary"] = mm.group(1), mm.group(2)
            sal, fte = _money(c.get("salary")), _money(c.get("fte"))
            name = join_name(c.get("first"), c.get("middle"), c.get("last"))
            yield _base("New Mexico Highlands University", name, (c.get("title") or "").strip() or None,
                        (c.get("dept") or "").strip() or None, sal, fy,
                        {"annual_salary": sal, "fte": fte, "salary_text": None if sal is not None else c.get("salary"),
                         # FY25 report prints $0.00 for 122 lines: kept as published, flagged so the site can show "not reported"
                         "source_published_zero": True if fy == 2025 and sal == 0 else None},
                        {"page": pno, "line": " ".join(w["text"] for w in ln), "cells": c, "wrapped_fragments": frags or None})
    if pending:
        raise ValueError(f"{fname}: {len(pending)} trailing fragments without a row")


# ---------------------------------------------------------------- Austin Peay State University (ruled table)
def parse_tn_apsu(path, fname):
    """Columns: Name | Business Title | Department Name | Salary. Salary is annual, or an hourly rate for hourly staff
    (values under $1,000); hourly rates stay in pay_components only."""
    for pno, page in _pages(path):
        for t in page.extract_tables():
            for row in t:
                if not row or not row[0] or row[0].strip().lower() == "name":
                    continue
                cells = [(x or "").replace("\n", " ").strip() or None for x in row]
                name, title, dept, sal = (cells + [None] * 4)[:4]
                v = _money(sal)
                annual = v if v is not None and v >= 1000 else None
                yield _base("Austin Peay State University", name, title, dept, annual, 2027,
                            {"salary": v, "rate_kind": None if v is None else ("annual" if annual else "hourly"),
                             "salary_text": None if v is not None else sal,
                             "year_derived": "pdf_creation_date"},  # no date printed; FY2027 from the PDF creation date (2026-09-21)
                            {"page": pno, "cells": cells})


# ---------------------------------------------------------------- East Tennessee State University
def parse_tn_etsu(path, fname):
    """Columns: Name | Department | Title | Salary; active employees as of 2024-05-22 (FY2024)."""
    for pno, page in _pages(path):
        lines = _lines(page)
        hdr = next((ln for ln in lines if ln[0]["text"] == "Name" and any(w["text"] == "Salary" for w in ln)), None)
        if hdr:
            pos = {w["text"]: w["x0"] for w in hdr}
            bounds = [("name", 0), ("dept", pos["Department"] - 4), ("title", pos["Title"] - 4), ("salary", pos["Salary"] - 30)]
        for ln in lines:
            if hdr and ln[0]["top"] <= hdr[0]["top"] + 1:
                continue
            c = _cols(ln, bounds)
            if not c["name"] or "," not in c["name"]:
                continue
            v = _money(c["salary"])
            yield _base("East Tennessee State University", c["name"], c["title"], c["dept"], v, 2024,
                        {"salary": v, "salary_text": None if v is not None else c["salary"]},
                        {"page": pno, "line": " ".join(w["text"] for w in ln), "cells": c})


# ---------------------------------------------------------------- University of Michigan (Salary Record)
UM_CAMPUS = {"UM_ANN-ARBOR": "University of Michigan-Ann Arbor", "UM_DEARBORN": "University of Michigan-Dearborn",
             "UM_FLINT": "University of Michigan-Flint"}


def parse_mi_um(path, fname):
    """One row per appointment as published (people with several appointments have several rows). base_pay = appointment
    annual full-time rate (FTR) x appointment fraction is NOT computed; base_pay holds the published annual FTR and the
    fraction / general-fund amount are kept in pay_components. As of 2025-11-01 => UM FY2026."""
    bounds = [("campus", 0), ("name", 82), ("title", 280), ("dept", 430), ("ftr", 580), ("basis", 633), ("fraction", 690),
              ("genfund", 712)]
    for pno, page in _pages(path):
        for ln in _lines(page):
            if not ln[0]["text"].startswith("UM_"):
                continue
            c = _cols(ln, bounds)
            ftr, frac, gf = _money(c["ftr"]), _money(c["fraction"]), _money(c["genfund"])
            yield _base(UM_CAMPUS.get(c["campus"], c["campus"]), c["name"], c["title"], c["dept"], ftr, 2026,
                        {"appt_annual_ftr": ftr, "appt_ftr_basis": c["basis"], "appt_fraction": frac, "salary_paid_from_general_fund": gf},
                        {"page": pno, "line": " ".join(w["text"] for w in ln), "cells": c})


SPECS = {
    "vt_uvm": dict(state="VT", system="University of Vermont List of Base Pay (PDF)", catalog_url_like="%uvm.edu%", parse=parse_vt_uvm,
                   file_filter=lambda f: f.endswith(".pdf"),
                   notes="base pay (primary job) as published each fall; fiscal_year = FY in which the list was released "
                         "(srYY = fall YY => FY YY+1; FYnn files as named); non-numeric entries (e.g. 'unpaid leave') kept as pay_text; "
                         "older files fetched from www.uvm.edu (the Drupal origin host linked on the page is not robots-allowed)"),
    "nm_nmhu": dict(state="NM", system="New Mexico Highlands University salary reports (PDF)", catalog_url_like="%nmhu.edu%", parse=parse_nm_nmhu,
                    file_filter=lambda f: f.endswith(".pdf"),
                    notes="annual salary + FTE per published line (multiple lines per person for overloads/second jobs); "
                          "fiscal_year from the report (3.1.23 report = FY2023); department text is truncated by the publisher; "
                          "the FY25 report publishes $0.00 for 122 lines: kept as 0 and flagged pay_components.source_published_zero = true"),
    "tn_apsu": dict(state="TN", system="Austin Peay State University employee salary data (PDF)", catalog_url_like="%apsu.edu%", parse=parse_tn_apsu,
                    file_filter=lambda f: f.endswith(".pdf"),
                    notes="current salary list (no date printed; PDF created 2026-09-21 => FY2027, Tennessee FY Jul-Jun); salary under $1,000 is an hourly rate kept in pay_components only; every row carries pay_components.year_derived = 'pdf_creation_date'"),
    "tn_etsu": dict(state="TN", system="East Tennessee State University active employees (PDF)", catalog_url_like="%etsu.edu%", parse=parse_tn_etsu,
                    file_filter=lambda f: f.endswith(".pdf"),
                    notes="salary of active employees as of 2024-05-22 => FY2024"),
    "mi_um": dict(state="MI", system="University of Michigan Salary Record (PDF)", catalog_url_like="%umich.edu%", parse=parse_mi_um,
                  file_filter=lambda f: f.endswith(".pdf"),
                  notes="one row per appointment; base_pay = appointment annual full-time rate (FTR); fraction, FTR basis and amount "
                        "paid from general fund in pay_components; as of 2025-11-01 => FY2026; Ann Arbor (incl. Michigan Medicine), Dearborn, Flint"),
}


FETCHERS = {k[6:]: v for k, v in dict(globals()).items() if k.startswith("fetch_")}


# Independent count of data rows in the raw page text (extract_text), to reconcile with parsed rows.
RECON = {"vt_uvm": (r"\$[\d,]+\b|\bupl\s*$|unpaid leave\s*$", "money/upl tokens"),
         "tn_etsu": (r"\$[\d,]+\.\d\d", "$ amounts"), "tn_apsu": (r"\$[\d,]+\.\d\d", "$ amounts"),
         "mi_um": (r"^UM_[A-Z-]+ ", "lines starting UM_")}


def check(key, nsample=20, seed=7):
    """Verification without the DB, streaming (one page in memory at a time): rows per page (min/median/max, zero-row
    pages), rows without a pay value or name, and a random sample of rows compared with the raw page text."""
    import collections
    import json
    import random
    import statistics
    spec = SPECS[key]
    m = json.loads((DATA / key / "manifest.json").read_text())
    rnd = random.Random(seed)
    want_sample = len(sys.argv) > 3 and sys.argv[3] == "sample"
    for fname in sorted(m["files"]):
        if spec.get("file_filter") and not spec["file_filter"](fname):
            continue
        if len(sys.argv) > 4 and not re.search(sys.argv[4], fname):
            continue
        path = DATA / key / fname
        with pdfplumber.open(path) as pdf:
            npages = len(pdf.pages)
        per = collections.Counter()
        fys, insts, nopay_vals = collections.Counter(), collections.Counter(), collections.Counter()
        n = nopay = noname = bad_fields = 0
        samp = []
        for r in spec["parse"](path, fname):
            n += 1
            per[r["raw"]["page"]] += 1
            fys[r["fiscal_year"]] += 1
            insts[r["institution"]] += 1
            if r["base_pay"] is None:
                nopay += 1
                pc = r["pay_components"]
                nopay_vals[str(pc.get("pay_text") or pc.get("salary_text") or pc.get("rate_kind"))] += 1
            if not r["person_name"]:
                noname += 1
            if key == "mi_um":
                pc = r["pay_components"]
                if not re.fullmatch(r"\d+-Month", pc.get("appt_ftr_basis") or "") or pc.get("appt_fraction") is None \
                        or pc.get("salary_paid_from_general_fund") is None or "," not in (r["person_name"] or ""):
                    bad_fields += 1
                    if bad_fields <= 5:
                        print("   field problem:", r["raw"]["line"][:160], flush=True)
            if want_sample:  # reservoir sample
                if len(samp) < nsample:
                    samp.append(r)
                elif rnd.random() < nsample / n:
                    samp[rnd.randrange(nsample)] = r
        if key in RECON:
            pat, what = RECON[key]
            expect, diffs = 0, []
            for i, pg in _pages(path):
                hits = re.findall(pat, pg.extract_text() or "", re.M)
                expect += len(hits)
                if len(hits) != per.get(i, 0):
                    diffs.append((i, len(hits), per.get(i, 0)))
            print(f"   reconcile: {expect} {what} in raw text vs {n} parsed rows (diff {n - expect}); pages differing (page, raw, parsed): {diffs[:10]}", flush=True)
        counts = [per.get(p, 0) for p in range(1, npages + 1)]
        zero = [p for p in range(1, npages + 1) if per.get(p, 0) == 0]
        print(f"## {key}/{fname}: rows={n} pages={npages} per-page min/median/max={min(counts)}/{statistics.median(counts)}/{max(counts)} "
              f"zero-row pages={zero[:20]}{'...' if len(zero) > 20 else ''} fy={dict(fys)} no-pay={nopay} no-name={noname} field-problems={bad_fields}", flush=True)
        low = sorted((c, p) for p, c in enumerate(counts, 1) if 0 < c < statistics.median(counts) * 0.6)
        print("   low-count pages (count, page):", low[:12])
        print("   no-pay values:", nopay_vals.most_common(8))
        print("   institutions:", insts.most_common(5), flush=True)
        if want_sample:
            ok = 0
            with pdfplumber.open(path) as pdf:
                for r in sorted(samp, key=lambda r: r["raw"]["page"]):
                    pg = pdf.pages[r["raw"]["page"] - 1]
                    flat = re.sub(r"\s+", " ", pg.extract_text() or "")
                    pg.flush_cache()
                    toks = re.findall(r"[A-Za-z']+", r["person_name"] or "")
                    v = r["base_pay"]
                    pay_forms = [] if v is None else [f"{v:,.2f}", f"{v:,.0f}", f"{v:.2f}", ("%.2f" % v).rstrip("0").rstrip("."), str(int(v)) if v == int(v) else ""]
                    f_name = all(t in flat or t.upper() in flat for t in toks)
                    f_pay = v is None or any(p and p in flat for p in pay_forms)
                    f_title = not r["title"] or all(t in flat for t in r["title"].split()[:3])
                    good = f_name and f_pay and f_title
                    ok += good
                    print(f"   p{r['raw']['page']} {'OK ' if good else 'BAD'} | {r['person_name']} | {r['title']} | {r['department']} | {v} | "
                          f"{json.dumps(r['pay_components'])[:110]}")
            print(f"   sample matches: {ok}/{len(samp)}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        for k in sys.argv[2:]:
            print("==", k, flush=True)
            try:
                FETCHERS[k]()
            except Exception as e:  # noqa: BLE001
                print(f"!! {k}: {type(e).__name__}: {e}", flush=True)
    elif sys.argv[1] == "check":
        check(sys.argv[2])
