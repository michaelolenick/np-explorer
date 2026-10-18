"""Per-source parsers. Each parse(path, fname) yields dicts with keys:
institution, person_name, title, department, base_pay, other_pay, total_pay, pay_components, fiscal_year, raw.
"""
import csv
import datetime as dt
import io
import json
import re
import zipfile

import openpyxl

from common import join_name, to_num

csv.field_size_limit(10_000_000)


def _k(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def pick(row, *cands):
    """Value for the first candidate header present (header match ignores case/punctuation)."""
    nk = {_k(k): v for k, v in row.items()}
    for c in cands:
        v = nk.get(_k(c))
        if v not in (None, ""):
            return v
    return None


def nsum(*xs):
    vals = [x for x in xs if x is not None]
    return sum(vals) if vals else None


def jsonl(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


def xlsx_rows(path, header_match, sheet=None, max_scan=60):
    """Yield dict rows from the first sheet (or named one) whose header row contains header_match (case-insens.)."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheets = [wb[sheet]] if sheet else wb.worksheets
    for ws in sheets:
        hdr = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if hdr is None:
                cells = [str(c).strip() if c is not None else "" for c in row]
                if any(_k(header_match) == _k(c) for c in cells):
                    hdr = cells
                elif i > max_scan:
                    break
                continue
            if all(v is None or str(v).strip() == "" for v in row):
                continue
            d = {}
            for h, v in zip(hdr, row):
                if h:
                    if isinstance(v, str):
                        v = v.strip()
                    d[h] = v
            yield ws.title, d
        if hdr is not None and not sheet:
            return


_SMALL = {"of", "and", "the", "at", "for", "in", "on", "de"}


def tcase(s):
    """Title-case an all-caps institution name, keeping small words lower and & intact."""
    if not s:
        return s
    words = str(s).strip().lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in _SMALL:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out).replace("Dupage", "DuPage").replace("Mchenry", "McHenry")


def comps(d):
    return {k: v for k, v in d.items() if v is not None}


# ---------------------------------------------------------------- Connecticut
CT_NAMES = {
    "University of Connecticut": "University of Connecticut",
    "UConn Health Center": "UConn Health",
    "CSU - Central": "Central Connecticut State University",
    "CSU - Eastern": "Eastern Connecticut State University",
    "CSU - Southern": "Southern Connecticut State University",
    "CSU - Western": "Western Connecticut State University",
    "Connecticut State Universities": "Connecticut State University System",
    "CT Community Colleges": "Connecticut Community Colleges",
    "Comm. College System Office": "Connecticut Community College System Office",
    "Charter Oak State College": "Charter Oak State College",
    "Connecticut Board of Regents": "Connecticut State Colleges & Universities (Board of Regents)",
}


CT_BOR_DEPT = {"Central CSU": "Central Connecticut State University", "Eastern CSU": "Eastern Connecticut State University",
               "Southern CSU": "Southern Connecticut State University", "Western CSU": "Western Connecticut State University",
               "Bd State Acdmc Awds": "Charter Oak State College", "CSCU System Office": "CSCU System Office",
               "System Office CSU": "CSCU System Office", "Board of Regents": "CSCU System Office",
               "CSCC Admin Office": "Connecticut State Community College"}


def parse_ct(path, fname):
    for r in jsonl(path):
        ag = r.get("agency")
        inst = CT_NAMES.get(ag) or (ag.replace("CCC - ", "") + " Community College" if ag.startswith("CCC - ") else ag)
        dep = r.get("department") or ""
        if ag == "Connecticut Board of Regents" and dep:
            inst = CT_BOR_DEPT.get(dep) or ("Connecticut State Community College" if dep.startswith("CSCC ") else inst)
        base, ot, oth, tot = (to_num(r.get(k)) for k in ("salaries_wages", "overtime", "other", "tot_gross"))
        yield dict(
            institution=inst,
            person_name=join_name(r.get("first_name"), r.get("middle_initial"), r.get("last_name"), r.get("name_suffix")),
            title=r.get("job_cd_descr"), department=r.get("department"),
            base_pay=base, other_pay=nsum(ot, oth), total_pay=tot,
            pay_components=comps({"salaries_wages": base, "overtime": ot, "other": oth, "tot_gross": tot,
                                  "annual_rate": to_num(r.get("annual_rate")), "paychecks": to_num(r.get("checks"))}),
            fiscal_year=int(r["pyrl_fiscal_yr"]), raw=r)


# ---------------------------------------------------------------- Massachusetts
UMASS_ZIP = {"01003": "University of Massachusetts Amherst", "02125": "University of Massachusetts Boston",
             "02747": "University of Massachusetts Dartmouth", "01854": "University of Massachusetts Lowell",
             "01655": "UMass Chan Medical School", "01605": "UMass Chan Medical School",
             # the 'zip' field actually holds campus text in CTHRU
             "u mass amherst": "University of Massachusetts Amherst", "u mass boston": "University of Massachusetts Boston",
             "u mass dartmouth": "University of Massachusetts Dartmouth", "u mass lowell": "University of Massachusetts Lowell",
             "u mass worcester": "UMass Chan Medical School", "u mass central office": "University of Massachusetts System Office"}


def parse_ma(path, fname):
    for r in jsonl(path):
        div = re.sub(r"\s*\([A-Z]{2,4}\)\s*$", "", r.get("department_division") or "").strip()
        inst = tcase(div)
        if r.get("department_code") == "UMS":
            z = (r.get("department_location_zip_code") or "").strip()
            inst = UMASS_ZIP.get(z.lower()) or UMASS_ZIP.get(z[:5]) or "University of Massachusetts System"
        tot = to_num(r.get("pay_total_actual"))
        base = to_num(r.get("pay_base_actual"))
        pc = {k: to_num(v) for k, v in r.items() if (k.startswith("pay_") or re.fullmatch(r"a[a0-9]\w", k) or k == "annual_rate")}
        yield dict(
            institution=inst, person_name=join_name(r.get("name_first"), None, r.get("name_last")),
            title=r.get("position_title"), department=r.get("department_division"),
            base_pay=base, other_pay=(tot - base) if tot is not None and base is not None else None, total_pay=tot,
            pay_components=comps(pc), fiscal_year=int(r["year"]), raw=r)


# ---------------------------------------------------------------- NYC (CUNY community colleges)
def parse_nyc(path, fname):
    for r in jsonl(path):
        ag = r.get("agency_name", "")
        m = re.match(r"COMMUNITY COLLEGE \((.+)\)", ag)
        inst = (tcase(m.group(1)) + " Community College") if m else tcase(ag)
        inst = inst.replace("Laguardia", "LaGuardia").replace("Manhattan Community College", "Borough of Manhattan Community College")
        reg, ot, oth = (to_num(r.get(k)) for k in ("regular_gross_paid", "total_ot_paid", "total_other_pay"))
        yield dict(
            institution=inst, person_name=join_name(r.get("first_name"), r.get("mid_init"), r.get("last_name")),
            title=r.get("title_description"), department=r.get("work_location_borough"),
            base_pay=reg, other_pay=nsum(ot, oth), total_pay=nsum(reg, ot, oth),
            pay_components=comps({"base_salary_rate": to_num(r.get("base_salary")), "pay_basis": r.get("pay_basis"),
                                  "regular_gross_paid": reg, "total_ot_paid": ot, "total_other_pay": oth,
                                  "regular_hours": to_num(r.get("regular_hours")), "ot_hours": to_num(r.get("ot_hours"))}),
            fiscal_year=int(r["fiscal_year"]), raw=r)


# ---------------------------------------------------------------- Georgia
GA_RE = re.compile(r"UNIVERSITY|COLLEGE|INSTITUTE OF TECHNOLOGY|REGENTS OF THE UNIVERSITY", re.I)


def parse_ga(path, fname):
    z = zipfile.ZipFile(path)
    with z.open(z.namelist()[0]) as f:
        rd = csv.reader(io.TextIOWrapper(f, encoding="latin-1"))
        hdr = next(rd)
        for row in rd:
            if len(row) != len(hdr):
                continue
            r = dict(zip(hdr, [c.strip().strip("'") for c in row]))
            if not GA_RE.search(r["ORGANIZATION"]):
                continue
            sal = to_num(r["SALARY"])
            yield dict(institution=tcase(r["ORGANIZATION"]),
                       person_name=r["NAME"], title=r["TITLE"], department=None,
                       base_pay=None, other_pay=None, total_pay=sal,
                       pay_components=comps({"salary": sal, "travel": to_num(r["TRAVEL"])}),
                       fiscal_year=int(r["FISCAL_YEAR"]), raw=r)


# ---------------------------------------------------------------- Texas College Salaries
def parse_tx(path, fname):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            fy = None
            try:
                d = dt.datetime.strptime(r["data_date"], "%m/%d/%Y")
                fy = d.year + (1 if d.month >= 9 else 0)  # Texas state FY runs Sep-Aug
            except (ValueError, KeyError):
                pass
            sal = to_num(r.get("salary"))
            yield dict(institution=r["institution"], person_name=r["full_name"], title=r.get("job_title"),
                       department=r.get("department"), base_pay=sal, other_pay=None, total_pay=None,
                       pay_components=comps({"salary": sal, "employment_time": r.get("employment_time"), "data_date": r.get("data_date")}),
                       fiscal_year=fy, raw=r)


# ---------------------------------------------------------------- Illinois community colleges (ICCB)
def parse_il_iccb(path, fname):
    for _, r in xlsx_rows(path, "Last Name"):
        base = to_num(pick(r, "Base Pay"))
        extra = to_num(pick(r, "Extra Duty Pay"))
        enh = to_num(pick(r, "Enhancements"))
        pc = {k: (to_num(v) if to_num(v) is not None else v) for k, v in r.items()
              if _k(k) in ("basepay", "benefits", "annuities", "enhancements", "extradutypay", "vacationdays", "sickdays", "personaldays")}
        fy = pick(r, "Fiscal Year")
        yield dict(institution=tcase(pick(r, "College Name") or ""),
                   person_name=join_name(pick(r, "First Name"), pick(r, "Middle Initial"), pick(r, "Last Name")),
                   title=pick(r, "Title"), department=pick(r, "Employment Classification"),
                   base_pay=base, other_pay=nsum(extra, enh), total_pay=nsum(base, extra, enh),
                   pay_components=comps(pc), fiscal_year=int(str(fy)[:4]) if fy else int(re.search(r"fy(\d{4})", fname).group(1)),
                   raw=r)


# ---------------------------------------------------------------- Ohio State (calendar-year earnings files)
def parse_oh_osu(path, fname):
    year = int(re.search(r"osu_(\d{4})_", fname).group(1))
    for _, r in xlsx_rows(path, "Gross Pay"):
        last = pick(r, "Last Name - Legal", "Last Name", "Legal Last Name", "Preferred Last Name")
        first = pick(r, "First Name - Preferred", "First Name", "Preferred First Name")
        reg = to_num(pick(r, "Regular Pay (Base Pay + Paid Time Off + Premium)", "Regular Pay", "Regular"))
        bonus, ot = to_num(pick(r, "Bonus")), to_num(pick(r, "Overtime"))
        oth = to_num(pick(r, "Other (Allowance + Supplemental + Uncategorized)", "Other"))
        gross = to_num(pick(r, "Gross Pay"))
        yield dict(institution="The Ohio State University", person_name=join_name(first, None, last),
                   title=pick(r, "Job Profile Name", "Job Profile", "Job Title"),
                   department=pick(r, "Cost Center", "Department"),
                   base_pay=reg, other_pay=nsum(bonus, ot, oth), total_pay=gross,
                   pay_components=comps({"regular": reg, "bonus": bonus, "overtime": ot, "other": oth, "gross": gross,
                                         "position_group": pick(r, "Position Group")}),
                   fiscal_year=year, raw=r)


def parse_oh_ou(path, fname):
    for _, r in xlsx_rows(path, "LAST_NAME"):
        base = to_num(pick(r, "BASE_SALARY"))
        addl = to_num(pick(r, "ADDL_COMP"))
        w2 = to_num(pick(r, "MEDICARE WAGES"))
        yield dict(institution="Ohio University", person_name=join_name(pick(r, "FIRST_NAME"), pick(r, "MIDDLE_NAME"), pick(r, "LAST_NAME")),
                   title=pick(r, "TITLE", "ACADEMIC_TITLE"), department=pick(r, "DEPARTMENT_NAME"),
                   base_pay=base, other_pay=addl, total_pay=w2,
                   pay_components=comps({"base_salary": base, "addl_comp": addl, "medicare_wages_2025": w2,
                                         "pay_basis": pick(r, "PAY_BASIS"), "campus": pick(r, "LOCATION_NAME")}),
                   fiscal_year=2025, raw=r)


# ---------------------------------------------------------------- Minnesota State (MMB salary files)
def parse_mn(path, fname):
    fy = int(re.search(r"fy(\d{4})", fname).group(1))
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    hr_ws = [w for w in wb.worksheets if "HR" in w.title.upper()][0]
    er_ws = [w for w in wb.worksheets if "EARN" in w.title.upper()][0]
    it = er_ws.iter_rows(values_only=True)
    eh = [str(h) for h in next(it)]
    earn = {}
    for row in it:
        d = dict(zip(eh, row))
        earn[str(d[eh[0]])] = d
    it = hr_ws.iter_rows(values_only=True)
    hh = [str(h) for h in next(it)]
    people = {}
    for row in it:
        d = dict(zip(hh, row))
        ag = pick(d, "AGENCY_NAME", "EMPLT_AGENCY_NM") or ""
        if "Colleges & Universities" not in ag and "MnSCU" not in ag:
            continue
        tid = str(pick(d, "TEMPORARY_ID", "TEMPORARY_EMPLOYEE_ID"))
        rec = to_num(pick(d, "RECORD_NBR", "EMPL_REC_NBR")) or 0
        # one row per person: keep the lowest employment record (primary appointment); others go in pay_components
        if tid in people:
            people[tid]["other_positions"].append(pick(d, "JOB_TITLE", "JOB_DESC"))
            if rec >= people[tid]["rec"]:
                continue
            people[tid].update(rec=rec, hr=d)
        else:
            people[tid] = {"rec": rec, "hr": d, "other_positions": []}
    for tid, p in people.items():
        d = p["hr"]
        e = earn.get(tid, {})
        reg = to_num(pick(e, "REGULAR_WAGES", "REGWAGES", "SALARY"))
        ot = to_num(pick(e, "OVERTIME_WAGES", "OTWAGES", "OVERTIME"))
        oth = to_num(pick(e, "OTHER_WAGES")) if pick(e, "OTHER_WAGES") is not None else nsum(to_num(pick(e, "DIFFERENTIALS_ETC")), to_num(pick(e, "OTHER_PAY")))
        tot = to_num(pick(e, "TOTAL_WAGES", "TOTALWAGES", "TOTAL_PAY")) if pick(e, "TOTAL_WAGES", "TOTALWAGES", "TOTAL_PAY") is not None else nsum(reg, ot, oth)
        dept = pick(d, "DEPARTMENT_NAME", "DEPT_NM")
        yield dict(institution="Minnesota State Colleges and Universities", person_name=pick(d, "EMPLOYEE_NAME", "EMPL_NM"),
                   title=pick(d, "JOB_TITLE", "JOB_DESC"), department=dept,
                   base_pay=reg, other_pay=nsum(ot, oth), total_pay=tot,
                   pay_components=comps({**{k: v for k, v in e.items() if k != eh[0]},
                                         "compensation_rate": to_num(pick(d, "COMPENSATION_RATE", "CMPTN_RT")),
                                         "comp_frequency": pick(d, "COMP_FREQUENCY_DESC", "CMPTN_FREQ_DESC"),
                                         "position_fte": to_num(pick(d, "POSITION_FTE", "POSN_FTE_PRCT_RT")),
                                         "location": pick(d, "LOCATION_NAME", "LOCN_NM"),
                                         "other_positions": p["other_positions"] or None,
                                         "note": "earnings are FY totals across all state positions"}),
                   fiscal_year=fy, raw={"hr": d, "earnings": e})


# ---------------------------------------------------------------- Washington (data.wa.gov 2010-2013, wide)
def _wa_higher(code):
    c = int(code)
    return c == 352 or 360 <= c <= 380 or 600 <= c <= 699


def parse_wa(path, fname):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            if not _wa_higher(r["Agency"]):
                continue
            for y in (2010, 2011, 2012, 2013):
                v = to_num(r.get(f"Salary{y}"))
                if not v:
                    continue
                yield dict(institution=r["AgencyTitle"], person_name=r["EmployeeName"], title=r["JobTitle"], department=None,
                           base_pay=None, other_pay=None, total_pay=v, pay_components={"salary": v, "calendar_year": y},
                           fiscal_year=y, raw=r)


# ---------------------------------------------------------------- Kansas (Kansas Policy Institute compiled payroll)
KS_RE = re.compile(r"University|Medical Center", re.I)


def parse_ks(path, fname):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            ag = r["Agency"]
            if not KS_RE.search(ag) or "Emergency" in ag:
                continue
            inst = {"KUMC University of Kansas Medical Center": "University of Kansas Medical Center",
                    "Univ of Ks Medical Center": "University of Kansas Medical Center",
                    "Pittsburgh State University": "Pittsburg State University"}.get(ag, ag)
            tot = to_num(r["TotalPay"])
            yield dict(institution=inst, person_name=join_name(r["FirstName"], None, r["LastName"]), title=r["Position"],
                       department=None, base_pay=None, other_pay=None, total_pay=tot, pay_components={"total_pay": tot},
                       fiscal_year=int(r["Year"]), raw=r)


# ---------------------------------------------------------------- Nebraska (budgeted salaries)
NE_CAMPUS = {"UNL": "University of Nebraska-Lincoln", "UNO": "University of Nebraska Omaha", "UNMC": "University of Nebraska Medical Center",
             "UNK": "University of Nebraska at Kearney", "NCTA": "Nebraska College of Technical Agriculture",
             "CS": "University of Nebraska System (Central Administration)", "UNCA": "University of Nebraska System (Central Administration)"}


def parse_ne(path, fname):
    y = re.search(r"ne_(\d{4})_(\d{4})", fname)
    fy = int(y.group(2))
    for _, r in xlsx_rows(path, "Employee"):
        name = pick(r, "Employee")
        if not name or str(name).lower().startswith("total"):
            continue
        sal = to_num(pick(r, "Budgeted Annual Salary", "Budgeted \nAnnual\nSalary"))
        if sal is None:
            sal = to_num(next((v for k, v in r.items() if "budgeted" in k.lower()), None))
        st = to_num(next((v for k, v in r.items() if "state" in k.lower()), None))
        ot = to_num(next((v for k, v in r.items() if "other" in k.lower()), None))
        campus = pick(r, "Campus")
        yield dict(institution=NE_CAMPUS.get(str(campus).strip(), f"University of Nebraska ({campus})"), person_name=name,
                   title=pick(r, "Position"), department=pick(r, "Department"), base_pay=sal, other_pay=None, total_pay=None,
                   pay_components=comps({"budgeted_annual_salary": sal, "salary_state_aided_funds": st, "salary_other_funds": ot, "campus": campus}),
                   fiscal_year=fy, raw={k.replace("\n", " "): v for k, v in r.items()})


# ---------------------------------------------------------------- Maine
ME_CAMPUS = {"MLAW": "University of Maine School of Law", "SWS": "University of Maine System (System Wide Services)",
             "UM": "University of Maine", "UMA": "University of Maine at Augusta", "UMF": "University of Maine at Farmington",
             "UMFK": "University of Maine at Fort Kent", "UMM": "University of Maine at Machias",
             "UMPI": "University of Maine at Presque Isle", "USM": "University of Southern Maine"}


def parse_me(path, fname):
    for _, r in xlsx_rows(path, "Formatted Name"):
        sal = to_num(pick(r, "Salbase"))
        c = pick(r, "Campus")
        yield dict(institution=ME_CAMPUS.get(c, c), person_name=pick(r, "Formatted Name"), title=pick(r, "Title"),
                   department=pick(r, "Dept ID"), base_pay=sal, other_pay=None, total_pay=None,
                   pay_components=comps({"salbase": sal, "fte": to_num(pick(r, "FTE")), "job_status": pick(r, "JobSt"),
                                         "faculty_appt": pick(r, "Faculty Appt")}),
                   fiscal_year=2026, raw=r)


# ---------------------------------------------------------------- New Mexico (UNM sunshine salary book)
def parse_nm(path, fname):
    data = json.load(open(path))["data"]
    cols = ["name", "department", "col3", "title", "position", "fte_pct", "salary"]
    for row in data:
        r = dict(zip(cols, row))
        sal = to_num(r.get("salary"))
        yield dict(institution="University of New Mexico", person_name=r["name"], title=r.get("title"), department=r.get("department"),
                   base_pay=sal, other_pay=None, total_pay=None,
                   pay_components=comps({"salary": sal, "fte_pct": to_num(r.get("fte_pct")), "position": r.get("position")}),
                   fiscal_year=2027, raw={"row": row})


# ---------------------------------------------------------------- DC (UDC rows of DC employee layer)
def parse_dc(path, fname):
    for r in jsonl(path):
        rate = to_num(r.get("COMPRATE"))
        annual = rate if rate is not None and rate >= 1000 else None
        yield dict(institution="University of the District of Columbia", person_name=join_name(r.get("FIRST_NAME"), None, r.get("LAST_NAME")),
                   title=r.get("JOBTITLE"), department=None, base_pay=annual, other_pay=None, total_pay=None,
                   pay_components=comps({"comprate": rate, "rate_kind": "annual" if annual else "hourly/per-unit", "grade": r.get("GRADE"),
                                         "appointment": r.get("GVT_TYPE_OF_APPT")}),
                   fiscal_year=2027, raw=r)


# ---------------------------------------------------------------- Arizona
def parse_az_asu(path, fname):
    fy_file = int(re.search(r"(\d{4})", fname).group(1))
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        for r in csv.DictReader(f):
            name = pick(r, "Full Name", "Name")
            if not name:
                continue
            sal = to_num(pick(r, "Salary", "Total Salary"))
            fte = to_num(pick(r, "FTE", "Fte", "Total FTE", "Total Fte"))
            yield dict(institution="Arizona State University", person_name=name.rstrip(" -"),
                       title=pick(r, "Job Description", "Jobcode Descr", "Jobcode Description", "Title"),
                       department=pick(r, "Department Description", "Department Descr", "Department"),
                       base_pay=sal, other_pay=None, total_pay=None,
                       pay_components=comps({"salary": sal, "fte": fte, "college_unit": pick(r, "College/Unit")}),
                       fiscal_year=fy_file, raw=r)


def parse_az_ua(path, fname):
    html = open(path, encoding="utf-8", errors="replace").read()
    cols = json.loads(re.search(r"_Flourish_data_column_names\s*=\s*(\{.*?\}\}),", html).group(1))["rows"]["columns"]
    i = html.index("_Flourish_data = ") + len("_Flourish_data = ")
    data, _ = json.JSONDecoder().raw_decode(html[i:])
    for item in data["rows"]:
        r = dict(zip(cols, item["columns"]))
        sal = to_num(r.get("Annual Salary >> at Employment FTE"))
        yield dict(institution="University of Arizona", person_name=r.get("Name"), title=r.get("Primary Title"), department=r.get("Department"),
                   base_pay=sal, other_pay=None, total_pay=None,
                   pay_components=comps({"annual_salary_at_fte": sal, "full_fte_salary": to_num(r.get("Full FTE Salary")),
                                         "fte": to_num(r.get("FTE >> Full Time Equivalent")), "hourly_rate": to_num(r.get("Hourly Pay Rate >> Primary Job")),
                                         "ft_pt": r.get("FT/PT >> Full Time or Part Time")}),
                   fiscal_year=int(r["Fiscal Year"]), raw=r)


# ---------------------------------------------------------------- Oklahoma (OMES payroll, FY2026 monthly payment lines)
OK_RE = re.compile(r"UNIV|COLLEGE|COLEGE", re.I)


def parse_ok(path, fname):
    """One file per month; rows are payment lines. Aggregated per agency + last name + initials within the file (month)."""
    agg = {}
    with open(path, encoding="latin-1", newline="") as f:
        for r in csv.DictReader(f):
            if not OK_RE.search(r["AGENCY_NAME"]):
                continue
            k = (r["AGENCY_NUMBER"], r["AGENCY_NAME"], r["LAST_NAME"].strip(), r["FIRST_INITIAL"].strip(), r["MIDDLE_INITIAL"].strip())
            a = agg.setdefault(k, {"amount": 0.0, "hours": 0.0, "accounts": {}, "lines": 0, "report_date": r["REPORT_DATE"]})
            amt = to_num(r["AMOUNT"]) or 0.0
            a["amount"] += amt
            a["hours"] += to_num(r["HOURS"]) or 0.0
            a["accounts"][r["ACCOUNT_DESCRIPTION"]] = round(a["accounts"].get(r["ACCOUNT_DESCRIPTION"], 0.0) + amt, 2)
            a["lines"] += 1
    ym = re.search(r"(\d{4})(\d{2})", fname)
    fy = int(ym.group(1)) + (1 if int(ym.group(2)) >= 7 else 0)
    for (num, ag, last, fi, mi), a in agg.items():
        reg = sum(v for k2, v in a["accounts"].items() if "regular" in k2.lower())
        yield dict(institution=tcase(ag), person_name=join_name(fi, mi, last), title=None, department=None,
                   base_pay=round(reg, 2), other_pay=round(a["amount"] - reg, 2), total_pay=round(a["amount"], 2),
                   pay_components={"month": ym.group(0), "by_account": a["accounts"], "hours": round(a["hours"], 2), "payment_lines": a["lines"],
                                   "note": "monthly total; name is last name + initials only"},
                   fiscal_year=fy, raw={"agency_number": num, "agency_name": ag, "last_name": last, "first_initial": fi,
                                        "middle_initial": mi, "report_date": a["report_date"]})


# ---------------------------------------------------------------- New Jersey (pension membership, higher-ed employers)
NJ_EXCLUDE = re.compile(r"C/S|CHRTR|CHARTER|PREP|BORO|HOSPITAL|ACHIEVE", re.I)


def parse_nj(path, fname):
    for r in jsonl(path):
        emp = r.get("employer_name", "")
        if NJ_EXCLUDE.search(emp):
            continue
        sal = to_num(r.get("current_employer_salary_amt"))
        yield dict(institution=tcase(emp), person_name=join_name(r.get("member_first_name"), r.get("member_mi"), r.get("member_last_name")),
                   title=None, department=r.get("location_name"), base_pay=sal, other_pay=None, total_pay=None,
                   pay_components=comps({"current_employer_salary_amt": sal, "all_employers_salary_amt": to_num(r.get("all_employers_salary_amt")),
                                         "pension_fund": r.get("pension_fund_name")}),
                   fiscal_year=2026, raw=r)


# ---------------------------------------------------------------- University of Illinois Gray Book (HTML)
import html as _html

GB_CAMPUS = {"Urbana-Champaign": "University of Illinois Urbana-Champaign", "Chicago": "University of Illinois Chicago",
             "Springfield": "University of Illinois Springfield", "System": "University of Illinois System Offices"}
_TR = re.compile(r'<tr id="(c\d+-d\d+-e(\d+)-j(\d+))">(.*?)</tr>', re.S)
_TD = re.compile(r'<td headers="c\d+-d\d+-([a-z-]+)-header"[^>]*>(.*?)</td>', re.S)
_HDR = re.compile(r'<h([23]) id="(c\d+(?:-d\d+)?)">(.*?)</h[23]>', re.S)


def _txt(x):
    return _html.unescape(re.sub(r"<[^>]+>", " ", x)).replace("\xa0", " ").strip()


def parse_il_graybook(path, fname):
    s = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r'<span class="center">\(([^)]*)\)</span>', s)
    camp_txt = m.group(1) if m else ""
    inst = next((v for k, v in GB_CAMPUS.items() if k.lower() in camp_txt.lower()), "University of Illinois System")
    heads = {mm.group(2): _txt(mm.group(3)) for mm in _HDR.finditer(s)}
    last_name_by_emp = {}
    for mm in _TR.finditer(s):
        rid, emp, job, body = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
        cells = {k: _txt(v) for k, v in _TD.findall(body)}
        c, d = rid.split("-")[0], "-".join(rid.split("-")[:2])
        ekey = (d, emp)
        name = cells.get("empl") or last_name_by_emp.get(ekey)
        if cells.get("empl"):
            last_name_by_emp[ekey] = cells["empl"]
        prop, pres = to_num(cells.get("propsal")), to_num(cells.get("pressal"))
        yield dict(institution=inst, person_name=name, title=cells.get("job"), department=heads.get(d),
                   base_pay=prop, other_pay=None, total_pay=None,
                   pay_components=comps({"proposed_salary_fy2027": prop, "present_salary_fy2026": pres,
                                         "proposed_fte": to_num(cells.get("propfte")), "present_fte": to_num(cells.get("presfte")),
                                         "tenure": cells.get("tenure") or None, "empl_class": cells.get("empclass"),
                                         "job_row": int(job), "college": heads.get(c)}),
                   fiscal_year=2027, raw={"row_id": rid, "page": fname, "campus": camp_txt, "college": heads.get(c),
                                          "department": heads.get(d), **cells})


# ---------------------------------------------------------------- South Carolina state salaries (HTML)
_SC_TR = re.compile(r"<tr>(.*?)</tr>", re.S)
_SC_TD = re.compile(r'<td headers="view-([a-z0-9-]+)-table-column"[^>]*>(.*?)</td>', re.S)


def parse_sc(path, fname):
    s = open(path, encoding="utf-8", errors="replace").read()
    for page in s.split("<!-- UNIPAY PAGE ")[1:]:
        body = page.split("<tbody", 1)[-1].split("</tbody>", 1)[0]
        for tr in _SC_TR.findall(body):
            c = {k: _txt(v) for k, v in _SC_TD.findall(tr)}
            if not c:
                continue
            tot = to_num(c.get("field-total-compensation"))
            bon = to_num(c.get("field-bonuses"))
            yield dict(institution=tcase(c.get("field-agency")).replace("Of Sc", "of SC").replace("of Sc", "of SC"),
                       person_name=join_name(c.get("field-first-name"), None, c.get("label")), title=c.get("field-job-title-sq"),
                       department=None, base_pay=None, other_pay=bon, total_pay=tot,
                       pay_components=comps({"total_compensation": tot, "bonuses": bon}),
                       fiscal_year=2027, raw=c)


SPECS = {
    "ct": dict(state="CT", system="State of Connecticut payroll (higher-ed agencies)", catalog_url_like="%9m78-yc88%", parse=parse_ct,
               notes="fiscal_year = CT payroll fiscal year (Jul-Jun); one row per employee record per agency per FY, aggregated server-side"),
    "ma": dict(state="MA", system="Massachusetts CTHRU statewide payroll (higher-ed departments)", catalog_url_like="%9ttk-7vz6%", parse=parse_ma,
               notes="fiscal_year = calendar year (CTHRU 'year'); UMass campus inferred from department_location_zip_code"),
    "nyc": dict(state="NY", system="NYC Citywide Payroll (CUNY community colleges)", catalog_url_like="%k397-673e%", parse=parse_nyc,
                notes="fiscal_year = NYC FY (Jul-Jun)"),
    "ga": dict(state="GA", system="Open Georgia salaries (USG, TCSG, GMC)", catalog_url_like="%open.ga.gov%", parse=parse_ga,
               notes="filtered ORGANIZATION to universities/colleges; salary only (travel kept in pay_components)"),
    "tx": dict(state="TX", system="Texas College Salaries (volunteer project, TPIA requests)", catalog_url_like="%drive.google.com%", parse=parse_tx,
               notes="bulk export publishes first name + last initial only; base salary snapshot; fiscal_year derived from data_date (Sep-Aug FY)"),
    "il_iccb": dict(state="IL", system="Illinois Community College Board salary & benefits", catalog_url_like="%iccb%", parse=parse_il_iccb,
                    notes="total_pay = base + extra duty + enhancements; benefits/annuities kept in pay_components only"),
    "oh_osu": dict(state="OH", system="The Ohio State University", catalog_url_like="%osu.edu%", parse=parse_oh_osu,
                   file_filter=lambda f: "earnings" in f,
                   notes="calendar-year paid earnings files; salary-snapshot files downloaded but not loaded (same people, rate not pay)"),
    "oh_ou": dict(state="OH", system="Ohio University", catalog_url_like="%ohio.edu%", parse=parse_oh_ou,
                  notes="base salary as of 12/31/2025 plus 2025 Medicare (W-2) wages as total_pay"),
    "mn": dict(state="MN", system="Minnesota MMB state employee salary data (Minnesota State only)", catalog_url_like="%mn.gov/mmb%", parse=parse_mn,
               notes="agency 'MN St Colleges & Universities'; one row per person per FY (primary record); earnings are all state positions"),
    "wa": dict(state="WA", system="Washington state salaries 2010-2013 (data.wa.gov y3ds-rkew)", catalog_url_like="%y3ds-rkew%", parse=parse_wa,
               notes="wide file unpivoted to one row per person/agency/calendar year with non-zero salary; higher-ed agency codes 352, 360-380, 600-699"),
    "ks": dict(state="KS", system="Kansas state payroll 2021-2025 (Kansas Policy Institute / KansasOpenGov)", catalog_url_like="%kansasopengov%", parse=parse_ks,
               notes="third-party compiled from KORA requests; total pay only"),
    "ne": dict(state="NE", system="University of Nebraska budgeted employees", catalog_url_like="%nebraska.edu%", parse=parse_ne,
               notes="budgeted annual salary as of July 1; fiscal_year = ending year of the FY"),
    "me": dict(state="ME", system="University of Maine System regular employee compensation", catalog_url_like="%sharepoint%", parse=parse_me,
               notes="annual base salary snapshot June 2026 (FY2026)"),
    "nm": dict(state="NM", system="University of New Mexico Sunshine salary book", catalog_url_like="%unm.edu%", parse=parse_nm,
               notes="current snapshot (retrieved Oct 2026 = FY2027); primary position salary only"),
    "dc": dict(state="DC", system="DC Government employee salary layer (UDC rows)", catalog_url_like="%dcgis%", parse=parse_dc,
               notes="point-in-time compensation rate; hourly/per-course rates kept in pay_components only; fiscal_year = DC FY2027 (snapshot Oct 2026)"),
    "az_asu": dict(state="AZ", system="Arizona State University (State Press SalaryList)", catalog_url_like="%statepress%", parse=parse_az_asu,
                   notes="base salary by calendar year; revised files used where available"),
    "az_ua": dict(state="AZ", system="University of Arizona (Flourish embed)", catalog_url_like="%flo.uri.sh%", parse=parse_az_ua,
                  notes="salary at employment FTE by fiscal year; third-party newsroom"),
    "ok": dict(state="OK", system="Oklahoma OMES state payroll (higher-ed agencies), FY2026", catalog_url_like="%data.ok.gov%", parse=parse_ok,
               notes="monthly payment lines summed per agency + last name + initials per month (FY2026 files 2025-07..2026-06); names are initials only, so persons are ambiguous"),
    "nj": dict(state="NJ", system="NJ pension membership (active members, higher-ed employers)", catalog_url_like="%44xg-bswk%", parse=parse_nj,
               notes="pension-enrolled employees only (excludes ABP faculty); salary as reported to the pension system as of 2026-06-30; no title"),
    "il_graybook": dict(state="IL", system="University of Illinois Board of Trustees Gray Book 2026-27", catalog_url_like="%Graybook%", parse=parse_il_graybook,
                        file_filter=lambda f: f in ("UIUC.html", "UIC.html", "UIS.html", "SysOfc.html"),
                        notes="campus-level pages only (unit pages repeat the same rows); one row per job line as published (multi-job employees have several rows); base_pay = proposed FY2027 salary; present FY2026 salary in pay_components"),
    "sc": dict(state="SC", system="SC Dept of Administration state salaries (colleges and universities)", catalog_url_like="%admin.sc.gov%", parse=parse_sc,
               notes="current FY (last updated 2026-09-16 => FY2027); total compensation = annual salary or YTD earnings, whichever greater; employees under $50k omitted by the publisher"),
}

ORDER = ["ct", "ma", "nyc", "ga", "tx", "il_iccb", "oh_osu", "oh_ou", "mn", "ri", "wa", "ne", "me", "nm", "dc", "az_asu", "az_ua", "ks", "nj", "ok", "il_graybook", "sc"]
