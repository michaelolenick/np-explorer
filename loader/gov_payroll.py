"""State and city payroll (owner, 2026-11-04): public-employee pay files that governments publish for download
with employee names, for jurisdictions the university payroll (scripts/unipay/) doesn't cover. Loaded into the
same staging tables (unipay.public_payroll_sources, unipay.public_payroll_records) under source keys gov_*, so
loader/colleges.py copies them into payroll_rows and payroll_person_years with everything else; link_rows() then
matches the people to person pages (a full name with a middle name or initial, on exactly one person page, in one
of that person's states), and app/pay.py shows them at /pay.

Each source below says where its file is, what each row is, and how pay is read. Pay is as published; where a
publisher gives only an hourly rate, pay is the rate times 2,080 hours and the row says so (pay_components).
Transaction-level files (Nevada, the MTA, Philadelphia's quarters) are summed per person, employer, title and year.

Not loaded (needs a login, a CAPTCHA, per-name search or scraping; see the owner's list): Washington state (bulk
file by email request), Ohio (DataOhio account), North Carolina, Arizona, Tennessee, Wisconsin, Kentucky,
Louisiana, Utah, Arkansas (WAF), Idaho, West Virginia, New Hampshire, South Dakota, North Dakota, Mississippi,
the University of California, Texas and others that publish no names (California state, Houston, Dallas,
Virginia, Oregon, San Diego) or no file at all.

Usage: .venv/bin/python -m loader.gov_payroll [KEY ...] | all | finish
  KEY ...   fetch and stage those sources (replacing their rows)
  all       every source
  finish    rebuild payroll_rows, person-years, labels and links (scripts/load.py colleges --only labels,payroll,summary,links)
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from app.names import normalize_name
from loader import db

UA = "furp.org research michael@furp.org"
HOURS = 2080
MA_UNIVERSITY_CODES = {"UMS", "BSC", "FSC", "FRC", "SSA", "WSC", "WOR", "MCA", "NAC", "MMA", "BCC", "BRC", "BHC", "CCC",
                       "GCC", "HCC", "MAS", "MBC", "MCC", "MWC", "NEC", "NSC", "QCC", "RCC", "STC"}   # scripts/unipay (ma)
TODAY = dt.date.today()


def _money(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    if s in ("", "null", "None", "NaN"):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _add(*vals) -> float | None:
    xs = [x for x in vals if x is not None]
    return round(sum(xs), 2) if xs else None


def _year(v) -> int | None:
    m = re.search(r"(19|20)\d\d", str(v or ""))
    return int(m[0]) if m else None


def _name(last, first, middle=None) -> str | None:
    last, first = (last or "").strip(), (first or "").strip()
    middle = (middle or "").strip()
    if not last and not first:
        return None
    given = (first + " " + middle).strip()
    return f"{last}, {given}" if last and given else (last or given)


def _s(v, n=200) -> str | None:
    v = (v or "").strip() if isinstance(v, str) else v
    return (str(v)[:n] or None) if v not in (None, "") else None


@dataclass
class Source:
    key: str
    state: str
    title: str
    publisher: str
    basis: str
    home: str                      # the publisher's page, shown as the source
    fetch: tuple                   # ("socrata", domain, id, where) | ("get", url) | ("years", [(year, url)...]) | ("post_json", url, data)
    parse: Callable                # row dict -> record dict or None (or a list of them)
    agg: str | None = None         # "sum": add pay across rows with the same agg key; "latest": keep the highest seq
    note: str = ""
    extra: dict = field(default_factory=dict)


# --- fetching ---------------------------------------------------------------------------------------------------

def _get(url: str, data: bytes | None = None, timeout: int = 900) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "*/*"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            time.sleep(10)
    raise RuntimeError("unreachable")


def _csv_rows(data: bytes):
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    for r in reader:
        yield {(k or "").strip(): v for k, v in r.items()}


def rows_of(src: Source, status=print):
    """Yield (row dict, file url) for every row of the source."""
    kind = src.fetch[0]
    if kind == "socrata":
        _, domain, dataset, where = src.fetch
        page, offset = 100000, 0
        while True:
            q = {"$limit": page, "$offset": offset, "$order": ":id"}
            if where:
                q["$where"] = where
            url = f"https://{domain}/resource/{dataset}.csv?" + urllib.parse.urlencode(q)
            rows = list(_csv_rows(_get(url)))
            for r in rows:
                yield r, f"https://{domain}/resource/{dataset}"
            status(f"{src.key}: {offset + len(rows):,} rows fetched")
            if len(rows) < page:
                break
            offset += page
    elif kind == "get":
        for r in _csv_rows(_get(src.fetch[1])):
            yield r, src.fetch[1]
    elif kind == "zip_csv":
        data = _get(src.fetch[1])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(m for m in z.namelist() if m.lower().endswith(".csv"))
            for r in _csv_rows(z.read(member)):
                yield r, src.fetch[1]
    elif kind == "years":
        for year, url in src.fetch[1]:
            try:
                data = _get(url)
            except Exception as e:  # noqa: BLE001
                status(f"{src.key}: {year}: {type(e).__name__}; skipped")
                continue
            n = 0
            for r in _csv_rows(data):
                r["_year"] = year
                n += 1
                yield r, url
            status(f"{src.key}: {year}: {n:,} rows")
    elif kind == "post_json":
        _, url, data = src.fetch
        payload = json.loads(_get(url, data=data.encode(), timeout=600))
        for r in payload["data"]:
            yield r, url
    else:
        raise ValueError(kind)


# --- parsers: a row -> {employer, name, title, department, base, other, total, year, components, key, seq} ----------

def p_nyc(r):
    ag = r.get("agency_name") or ""
    if ag.startswith("COMMUNITY COLLEGE") or ag == "GUTTMAN COMMUNITY COLLEGE":
        return None                         # loaded already as the CUNY community colleges (scripts/unipay nyc)
    ot, oth, reg = _money(r.get("total_ot_paid")), _money(r.get("total_other_pay")), _money(r.get("regular_gross_paid"))
    return {"employer": ag, "name": _name(r.get("last_name"), r.get("first_name"), r.get("mid_init")),
            "title": r.get("title_description"), "department": r.get("work_location_borough"),
            "base": _money(r.get("base_salary")) if (r.get("pay_basis") or "").startswith("per Annum") else None,
            "other": _add(ot, oth), "total": _add(reg, ot, oth), "year": _year(r.get("fiscal_year")),
            "components": {"regular_gross": reg, "overtime": ot, "other": oth, "pay_basis": r.get("pay_basis"),
                           "leave_status": r.get("leave_status_as_of_june_30")}}


def p_nj(r):
    if r.get("record_type") != "MASTER":
        return None
    y = _year(r.get("calendar_year"))
    return {"employer": r.get("master_department_agency_desc"), "name": r.get("full_name") or _name(r.get("last_name"), r.get("first_name"), r.get("middle_initial")),
            "title": r.get("master_title_desc"), "department": r.get("master_section_desc"),
            "base": _money(r.get("master_ytd_regular_pay")),
            "other": _add(_money(r.get("master_ytd_overtime_payments")), _money(r.get("master_ytd_all_other_payments"))),
            "total": _money(r.get("master_ytd_earnings")), "year": y,
            "components": {"overtime": _money(r.get("master_ytd_overtime_payments")), "other": _money(r.get("master_ytd_all_other_payments")),
                           "quarter": r.get("calendar_quarter"), "as_of": (r.get("as_of_date") or "")[:10]},
            "key": (y, r.get("payroll_id")), "seq": int(r.get("calendar_quarter") or 0)}


def p_ma(r):
    if (r.get("department_code") or "") in MA_UNIVERSITY_CODES:
        return None                         # loaded already as the university payroll (scripts/unipay ma)
    return {"employer": r.get("department_division"), "name": _name(r.get("name_last"), r.get("name_first")),
            "title": r.get("position_title"), "department": r.get("position_type"),
            "base": _money(r.get("pay_base_actual")),
            "other": _add(_money(r.get("pay_overtime_actual")), _money(r.get("pay_other_actual")), _money(r.get("pay_buyout_actual"))),
            "total": _money(r.get("pay_total_actual")), "year": _year(r.get("year")),
            "components": {"overtime": _money(r.get("pay_overtime_actual")), "other": _money(r.get("pay_other_actual")),
                           "buyout": _money(r.get("pay_buyout_actual")), "annual_rate": _money(r.get("annual_rate"))}}


def p_il(r):
    return {"employer": r.get("agency"), "name": r.get("employee_name"), "title": r.get("position_title"),
            "department": r.get("agency_division"), "base": None, "other": None, "total": _money(r.get("ytd_gross")),
            "year": _year(r.get("year")), "components": {"period_pay_rate": _money(r.get("period_pay_rate"))}}


def p_mo(r):
    return {"employer": r.get("agency_name"), "name": r.get("employee_name"), "title": r.get("position_title"),
            "department": None, "base": None, "other": None, "total": _money(r.get("ytd_gross_pay")),
            "year": _year(r.get("calendar_year")) or r.get("_year"), "components": {}}


def p_chicago(r):
    hourly = (r.get("salary_or_hourly") or "").upper() == "HOURLY"
    if hourly:
        rate, hrs = _money(r.get("hourly_rate")), _money(r.get("typical_hours")) or 40
        base = round(rate * hrs * 52, 2) if rate else None
        comp = {"annualized_from_hourly": rate, "typical_hours": hrs, "snapshot": TODAY.isoformat()}
    else:
        base, comp = _money(r.get("annual_salary")), {"snapshot": TODAY.isoformat()}
    return {"employer": r.get("department"), "name": r.get("name"), "title": r.get("job_titles"),
            "department": "Part time" if (r.get("full_or_part_time") or "") == "P" else None, "base": base, "other": None,
            "total": base, "year": TODAY.year, "components": comp}


def p_sf(r):
    if (r.get("year_type") or "") != "Fiscal":
        return None
    name = (r.get("employee_identifier") or "").strip()
    if not name or name.isdigit():
        return None                         # 2013-2016 rows carry an id, not a name
    return {"employer": r.get("department"), "name": name, "title": r.get("job"), "department": r.get("organization_group"),
            "base": _money(r.get("salaries")), "other": _add(_money(r.get("overtime")), _money(r.get("other_salaries"))),
            "total": _money(r.get("total_salary")), "year": _year(r.get("year")),
            "components": {"overtime": _money(r.get("overtime")), "other": _money(r.get("other_salaries")),
                           "benefits": _money(r.get("total_benefits")), "total_compensation": _money(r.get("total_compensation"))}}


def p_la(r):
    return {"employer": r.get("fms_department_title"), "name": _name(r.get("last_name"), r.get("first_name")),
            "title": r.get("job_title"), "department": r.get("employment_type"), "base": _money(r.get("regular_pay")),
            "other": _add(_money(r.get("overtime_pay")), _money(r.get("all_other_pay"))), "total": _money(r.get("total_pay")),
            "year": _year(r.get("pay_year")),
            "components": {"overtime": _money(r.get("overtime_pay")), "other": _money(r.get("all_other_pay")),
                           "benefits": _money(r.get("benefit_pay")), "job_status": r.get("job_status")}}


def p_nyauth(r):
    return {"employer": r.get("authority_name"), "name": _name(r.get("last_name"), r.get("first_name"), r.get("middle_initial")),
            "title": r.get("title"), "department": r.get("department") or r.get("group"),
            "base": _money(r.get("base_annualized_salary")),
            "other": _add(_money(r.get("overtime_paid")), _money(r.get("performance_bonus")), _money(r.get("extra_pay")),
                          _money(r.get("other_compensation"))),
            "total": _money(r.get("total_compensation")), "year": _year(r.get("fiscal_year_end_date")),
            "components": {"actual_salary_paid": _money(r.get("actual_salary_paid")), "overtime": _money(r.get("overtime_paid")),
                           "bonus": _money(r.get("performance_bonus")), "pay_type": r.get("pay_type")}}


def p_mta(r):
    y = _year(r.get("balance_year"))
    reg, ot = _money(r.get("regular_pay")), _add(_money(r.get("overtime_pay")), _money(r.get("overtime_bonus_pay")))
    oth = _add(_money(r.get("cash_outs")), _money(r.get("retro_pay")), _money(r.get("other_pay")))
    emp = "MTA " + (r.get("working_agency") or r.get("paying_agency") or "")
    return {"employer": emp.strip(), "name": r.get("name"), "title": r.get("working_title"), "department": r.get("working_paris_category"),
            "base": reg, "other": _add(ot, oth), "total": _add(reg, ot, oth), "year": y,
            "components": {"overtime": ot, "other": oth, "periods": 1},
            "key": (y, emp, r.get("name"), r.get("working_title"))}


def p_cincy(r):
    base = _money(r.get("annual_rt"))
    return {"employer": r.get("deptname"), "name": r.get("name"), "title": r.get("jobtitle"), "department": r.get("job_family"),
            "base": base, "other": None, "total": base, "year": TODAY.year,
            "components": {"snapshot": TODAY.isoformat(), "fte": _money(r.get("fte"))}}


def p_seattle(r):
    rate = _money(r.get("hourly_rate"))
    base = round(rate * HOURS, 2) if rate else None
    return {"employer": r.get("department"), "name": _name(r.get("last_name"), r.get("first_name")), "title": r.get("job_title"),
            "department": None, "base": base, "other": None, "total": base, "year": TODAY.year,
            "components": {"annualized_from_hourly": rate, "snapshot": TODAY.isoformat()}}


def p_vt(r):
    sal, hourly = _money(r.get("salary")), (r.get("salary_type") or "").lower().startswith("hour")
    base = round(sal * HOURS, 2) if (sal and hourly) else sal
    return {"employer": r.get("department"), "name": r.get("name"), "title": r.get("job_title"), "department": r.get("reg_temp"),
            "base": base, "other": None, "total": base, "year": _year(r.get("data_as_of")) or TODAY.year,
            "components": ({"annualized_from_hourly": sal} if hourly else {}) | {"snapshot": (r.get("data_as_of") or "")[:10]}}


def p_fl(r):
    sal, rate = _money(r.get("Salary")), _money(r.get("OPS Hourly Rate"))
    base = sal if sal else (round(rate * HOURS, 2) if rate else None)
    return {"employer": r.get("Agency Name"), "name": _name(r.get("Last Name"), r.get("First Name"), r.get("Middle Name")),
            "title": r.get("Class Title"), "department": r.get("Budget Entity"), "base": base, "other": None, "total": base,
            "year": TODAY.year, "components": ({"annualized_from_hourly": rate} if rate and not sal else {})
            | {"employee_type": r.get("Employee Type"), "full_part": r.get("Full/Part Time"), "snapshot": TODAY.isoformat()}}


def p_nv(r):
    y = _year(r.get("FISCAL_YEAR"))
    emp, title = r.get("DEPARTMENT_NAME"), r.get("POSITION_TITLE")
    name = _name(r.get("EMPL_LAST_NM"), r.get("EMPL_FIRST_NM"), r.get("EMPL_MIDDLE_NM"))
    return {"employer": emp, "name": name, "title": title, "department": r.get("POSITION_TYPE"),
            "base": _money(r.get("BASE_PAY")), "other": _money(r.get("OVERTIME_PAY")), "total": _money(r.get("PAY_AMOUNT")),
            "year": y, "components": {"overtime": _money(r.get("OVERTIME_PAY")), "fringe": _money(r.get("FRINGE_AMOUNT")), "periods": 1},
            "key": (y, r.get("Hashed Employee ID") or name, emp, title)}


def p_phila(r):
    y = _year(r.get("calendar_year"))
    base = _money(r.get("base_gross_pay_qtd"))
    oth = _add(_money(r.get("overtime_gross_pay_qtd")), _money(r.get("longevity_gross_pay_qtd")),
               _money(r.get("post_separation_gross_pay_qtd")), _money(r.get("miscellaneous_gross_pay_qtd")))
    return {"employer": r.get("department_name"), "name": _name(r.get("last_name"), r.get("first_name")), "title": r.get("title"),
            "department": r.get("employee_category"), "base": base, "other": oth, "total": _add(base, oth), "year": y,
            "components": {"overtime": _money(r.get("overtime_gross_pay_qtd")), "annual_rate": _money(r.get("base_salary")), "quarters": 1},
            "key": (y, r.get("public_id") or (r.get("last_name"), r.get("first_name"), r.get("title")))}


def _col(r, *names):
    for n in names:
        for k in r:
            if k.replace(" ", "_").upper() == n:
                return r[k]
    return None


def p_boston(r):
    total = _money(_col(r, "TOTAL_GROSS", "TOTAL_EARNINGS", "TOTAL"))
    reg = _money(_col(r, "REGULAR"))
    return {"employer": _col(r, "DEPARTMENT_NAME", "DEPARTMENT"), "name": _col(r, "NAME"), "title": _col(r, "TITLE"),
            "department": None, "base": reg, "other": _add(total, -reg) if total is not None and reg is not None else None,
            "total": total, "year": r.get("_year"),
            "components": {"overtime": _money(_col(r, "OVERTIME")), "detail": _money(_col(r, "DETAIL")), "other": _money(_col(r, "OTHER"))}}


def p_baltimore(r):
    return {"employer": r.get("AgencyName"), "name": r.get("Name"), "title": r.get("JobTitle"), "department": None,
            "base": _money(r.get("AnnualSalary")), "other": None, "total": _money(r.get("GrossPay")), "year": _year(r.get("FiscalYear")),
            "components": {"annual_salary": _money(r.get("AnnualSalary"))}}


def p_dc(r):
    base = _money(r.get("COMPRATE"))
    return {"employer": "DC government, " + (r.get("DESCRSHORT") or "").strip(), "name": _name(r.get("LAST_NAME"), r.get("FIRST_NAME")),
            "title": r.get("JOBTITLE"), "department": r.get("GVT_TYPE_OF_APPT"), "base": base, "other": None, "total": base,
            "year": 2024, "components": {"snapshot": "2024-09-26", "grade": r.get("GRADE")}}


def p_nashville(r):
    return {"employer": r.get("Home Business Unit"), "name": r.get("Employee Name"), "title": r.get("Job Class"), "department": None,
            "base": _money(r.get("Regular Pay")), "other": _add(_money(r.get("Overtime Pay")), _money(r.get("Supplemental Pay")),
                                                                _money(r.get("Longevity")), _money(r.get("Bonuses")),
                                                                _money(r.get("Payouts")), _money(r.get("Other Pay"))),
            "total": _money(r.get("Total Pay")), "year": _year(r.get("Fiscal Year")),
            "components": {"overtime": _money(r.get("Overtime Pay")), "supplemental": _money(r.get("Supplemental Pay"))}}


def p_phoenix(r):
    total = _money(r.get("Compensation"))
    return {"employer": r.get("Department"), "name": r.get("Name"), "title": r.get("Job Title"), "department": None,
            "base": None, "other": None, "total": total, "year": r.get("_year"), "components": {}}


def p_louisville(r):
    return {"employer": r.get("Department"), "name": r.get("Employee_Name"), "title": r.get("jobTitle"), "department": None,
            "base": _money(r.get("Regular_Rate")), "other": _add(_money(r.get("Overtime_Rate")), _money(r.get("Incentive_Allowance")), _money(r.get("Other"))),
            "total": _money(r.get("YTD_Total")), "year": _year(r.get("CalYear")),
            "components": {"annual_rate": _money(r.get("Annual_Rate")), "overtime": _money(r.get("Overtime_Rate"))}}


def p_pa(r):
    sal, rate, ind = _money(r.get("annualSalary")), _money(r.get("hourlyDailyRate")), (r.get("hourlyDailyRateIndicator") or "").strip()
    base = sal if sal else (round(rate * (260 if ind == "D" else HOURS), 2) if rate else None)
    return {"employer": r.get("businessAreaName"), "name": _name(r.get("lastName"), r.get("firstName")), "title": r.get("jobTitle"),
            "department": r.get("workContract"), "base": base, "other": None, "total": base, "year": _year(r.get("asOfDate")) or TODAY.year,
            "components": ({"annualized_from_" + ("daily" if ind == "D" else "hourly"): rate} if rate and not sal else {})
            | {"snapshot": (r.get("asOfDate") or "")[:10]}}


def _soc(domain, dataset, where=None):
    return ("socrata", domain, dataset, where)


MO_YEARS = {2025: "przm-8aj2", 2024: "nkgr-ek2r", 2023: "d5qn-3gs9", 2022: "7m33-xh7t", 2021: "7j8x-y8ki", 2020: "53ys-svak",
            2019: "wnyf-5ce9", 2018: "g8g2-6fyn", 2017: "mesr-3mki", 2016: "qy64-qzrf", 2015: "8yf2-bu4d", 2014: "i6tz-nkqw",
            2013: "a6nm-4wbm", 2012: "32yd-5xay", 2011: "hj93-xter", 2010: "8ama-dpbv", 2009: "j82q-875v", 2008: "uccy-42en",
            2007: "gapb-jve5"}
BOSTON = "https://data.boston.gov/dataset/418983dc-7cae-42bb-88e4-d56f5adcf869/resource/"
BOSTON_YEARS = {2025: "29b3544f-752a-4cb1-a6af-a1de153d20a0/download/employee-earnings-report-2025.csv",
                2024: "579a4be3-9ca7-4183-bc95-7d67ee715b6d/download/employee_earnings_report_2024.csv",
                2022: "63ac638b-36c4-487d-9453-1d83eb5090d2/download/finalconsolidatedcy22earnings_feb2023.xlsx-sheet1.csv",
                2021: "ec5aaf93-1509-4641-9310-28e62e028457/download/employee-earnings-report-2021.csv",
                2020: "e2e2c23a-6fc7-4456-8751-5321d8aa869b/download/city-of-boston-calendar-year-2020-earnings.csv",
                2019: "3bdfe6dc-3a81-49ce-accc-22161e2f7e74/download/allemployeescy2019_feb19_20final-all.csv",
                2018: "31358fd1-849a-48e0-8285-e813f6efbdf1/download/employeeearningscy18full.csv",
                2017: "70129b87-bd4e-49bb-aa09-77644da73503/download/employee-earnings-report-2017.csv",
                2016: "8368bd3d-3633-4927-8355-2a2f9811ab4f/download/employee-earnings-report-2016.csv",
                2015: "2ff6343f-850d-46e7-98d1-aca79b619fd6/download/employee-earnings-report-2015.csv",
                2014: "941c9de4-fb91-41bb-ad5a-43a35f5dc80f/download/employee-earnings-report-2014.csv",
                2013: "fac6a421-72fb-4f85-b4ac-4aca1e32d94e/download/employee-earnings-report-2013.csv",
                2012: "d96dd8ad-9396-484a-87af-4d15e9e2ccb2/download/employee-earnings-report-2012.csv",
                2011: "a861eff8-facc-4372-9b2d-262c2887b19e/download/employee-earnings-report-2011.csv"}
PHOENIX = "https://www.phoenixopendata.com/dataset/2b41f4f8-fe6f-48d3-8097-ad44ee5bd616/resource/"
PHOENIX_YEARS = {2016: "45ba7217-c1cf-4859-a40f-2c7f3220f5ba", 2017: "31c9219c-b5e9-41eb-a356-b8007eb8b9b8",
                 2018: "c69843c0-5885-47e7-8658-5c412825d533", 2019: "eb5a7b0f-e0d3-4769-9692-aaac697780a0",
                 2020: "50b3e8be-0691-442f-a1d8-1288376a36f4", 2021: "6b520e4b-84e5-4be2-9c20-2f84787fdd62",
                 2022: "8f46f810-986a-4eac-93d2-928805b139cb", 2023: "83331410-fa04-4ae0-89f5-e40dbca9154c",
                 2024: "3c521f8a-6dce-4341-a9a1-d71e6bc31490", 2025: "4fdc59c4-581f-4a64-9b98-e36f122b8143"}

SOURCES = [
    Source("gov_nyc", "NY", "New York City payroll (all agencies)", "NYC Office of Payroll Administration (NYC Open Data)",
           "Regular gross, overtime and other pay in the city fiscal year", "https://data.cityofnewyork.us/d/k397-673e",
           _soc("data.cityofnewyork.us", "k397-673e"), p_nyc, note="CUNY community colleges are the separate nyc source"),
    Source("gov_nj", "NJ", "New Jersey state agency payroll (YourMoney)", "State of New Jersey (data.nj.gov)",
           "Year-to-date earnings in the calendar year, from the latest quarter published", "https://data.nj.gov/d/iqwc-r2w7",
           _soc("data.nj.gov", "iqwc-r2w7", "record_type='MASTER'"), p_nj, agg="latest"),
    Source("gov_ma", "MA", "Massachusetts CTHRU statewide payroll (state departments)", "Massachusetts Office of the Comptroller (CTHRU)",
           "Total pay in the calendar year", "https://cthru.data.socrata.com/d/9ttk-7vz6", _soc("cthru.data.socrata.com", "9ttk-7vz6"), p_ma,
           note="the universities are the separate ma source"),
    Source("gov_il", "IL", "Illinois state employee pay (hired since 2011)", "State of Illinois (data.illinois.gov)",
           "Year-to-date gross pay in the calendar year", "https://data.illinois.gov/d/2ke2-x724", _soc("data.illinois.gov", "2ke2-x724"), p_il),
    Source("gov_mo", "MO", "Missouri state employee pay", "Missouri Office of Administration (data.mo.gov)",
           "Year-to-date gross pay in the calendar year", "https://data.mo.gov/browse?q=state%20employee%20pay",
           ("years", [(y, f"https://data.mo.gov/resource/{d}.csv?$limit=500000") for y, d in sorted(MO_YEARS.items())]), p_mo),
    Source("gov_chicago", "IL", "City of Chicago employee salaries", "City of Chicago (Chicago Data Portal)",
           "Annual salary as of the current list; hourly staff at the hourly rate times typical hours for 52 weeks",
           "https://data.cityofchicago.org/d/xzkq-xp2w", _soc("data.cityofchicago.org", "xzkq-xp2w"), p_chicago),
    Source("gov_sf", "CA", "San Francisco employee compensation", "San Francisco Controller (DataSF)",
           "Salaries, overtime and other pay in the fiscal year (names published from 2017)", "https://data.sf.gov/d/88g8-5mnd",
           _soc("data.sf.gov", "88g8-5mnd", "year_type='Fiscal'"), p_sf),
    Source("gov_la", "CA", "Los Angeles City employee payroll", "Los Angeles City Controller (Control Panel LA)",
           "Regular, overtime and other pay in the calendar year", "https://controllerdata.lacity.org/d/g9h8-fvhu",
           _soc("controllerdata.lacity.org", "g9h8-fvhu"), p_la),
    Source("gov_nyauth", "NY", "New York State public authorities payroll", "NYS Authorities Budget Office (data.ny.gov)",
           "Total compensation in the authority's fiscal year", "https://data.ny.gov/d/unag-2p27", _soc("data.ny.gov", "unag-2p27"), p_nyauth),
    Source("gov_nylocal", "NY", "New York local public authorities payroll", "NYS Authorities Budget Office (data.ny.gov)",
           "Total compensation in the authority's fiscal year", "https://data.ny.gov/d/fx93-cifz", _soc("data.ny.gov", "fx93-cifz"), p_nyauth),
    Source("gov_mta", "NY", "MTA employee payroll", "Metropolitan Transportation Authority (data.ny.gov)",
           "Regular, overtime and other pay, pay periods summed by calendar year", "https://data.ny.gov/d/kcjb-nf3e",
           _soc("data.ny.gov", "kcjb-nf3e"), p_mta, agg="sum"),
    Source("gov_cincinnati", "OH", "City of Cincinnati employee salaries", "City of Cincinnati (CincyInsights)",
           "Annual rate as of the current list", "https://data.cincinnati-oh.gov/d/wmj4-ygbf", _soc("data.cincinnati-oh.gov", "wmj4-ygbf"), p_cincy),
    Source("gov_seattle", "WA", "City of Seattle wage data", "City of Seattle (data.seattle.gov)",
           "Hourly rate times 2,080 hours (the city publishes only the rate)", "https://data.seattle.gov/d/2khk-5ukd",
           _soc("data.seattle.gov", "2khk-5ukd"), p_seattle),
    Source("gov_vt", "VT", "Vermont state employee salaries", "Vermont Department of Human Resources (data.vermont.gov)",
           "Annual salary as of the current list; hourly staff at the rate times 2,080 hours", "https://data.vermont.gov/d/jgqy-2smf",
           _soc("data.vermont.gov", "jgqy-2smf"), p_vt),
    Source("gov_fl", "FL", "Florida state employee salaries", "Florida Department of Management Services (salaries.myflorida.com)",
           "Annual salary as of the current list; OPS staff at the hourly rate times 2,080 hours", "https://salaries.myflorida.com/",
           ("get", "https://dms-media.ccplatform.net/api/search_salaries?format=csv"), p_fl),
    Source("gov_nv", "NV", "Nevada state payroll (Open Payroll)", "Nevada State Controller (Open Payroll)",
           "Pay transactions summed per person, department and title in the fiscal year", "https://nevada.payroll.socrata.com/",
           ("years", [(y, f"https://nevada-prod.payroll.socrata.com/api/dataset_download?year={y}") for y in (2024, 2025, 2026)]), p_nv, agg="sum"),
    Source("gov_phila", "PA", "City of Philadelphia employee earnings", "City of Philadelphia Office of Human Resources (OpenDataPhilly)",
           "Quarterly gross pay summed by calendar year", "https://opendataphilly.org/datasets/employee-earnings/",
           ("get", "https://phl.carto.com/api/v2/sql?q=SELECT+*+FROM+employee_earnings&filename=employee_earnings&format=csv&skipfields=cartodb_id,the_geom,the_geom_webmercator"),
           p_phila, agg="sum"),
    Source("gov_boston", "MA", "City of Boston employee earnings", "City of Boston (Analyze Boston)",
           "Total gross earnings in the calendar year", "https://data.boston.gov/dataset/employee-earnings-report",
           ("years", [(y, BOSTON + p) for y, p in sorted(BOSTON_YEARS.items())]), p_boston),
    Source("gov_baltimore", "MD", "City of Baltimore employee salaries", "City of Baltimore (Open Baltimore)",
           "Gross pay in the city fiscal year", "https://data.baltimorecity.gov/datasets/baltimore-city-employee-salaries",
           ("get", "https://data.baltimorecity.gov/api/download/v1/items/0bceed42ed994e65bec410bdf9c383c8/csv?layers=0"), p_baltimore),
    Source("gov_dc", "DC", "DC government employee salaries", "DC Department of Human Resources (Open Data DC)",
           "Compensation rate as of the 2024 list", "https://opendata.dc.gov/datasets/dc-government-employee-salaries",
           ("get", "https://opendata.dc.gov/api/download/v1/items/c9a03cab565b44849bcfc57e63fd3591/csv?layers=35"), p_dc,
           note="the University of the District of Columbia is the separate dc source"),
    Source("gov_nashville", "TN", "Metro Nashville employee earnings", "Metropolitan Government of Nashville (data.nashville.gov)",
           "Total pay in the fiscal year", "https://data.nashville.gov/",
           ("get", "https://data.nashville.gov/api/download/v1/items/e413edb1a0854c5ab58102b001249e24/csv?layers=0"), p_nashville),
    Source("gov_phoenix", "AZ", "City of Phoenix employee compensation", "City of Phoenix (phoenixopendata.com)",
           "Compensation in the calendar year", "https://www.phoenixopendata.com/dataset/employee-compensation",
           ("years", [(y, f"{PHOENIX}{rid}/download/employee-compensation-report-{y}.csv") for y, rid in sorted(PHOENIX_YEARS.items())]), p_phoenix),
    Source("gov_louisville", "KY", "Louisville Metro employee salaries", "Louisville Metro Government (Louisville Open Data)",
           "Year-to-date total pay in the calendar year", "https://data.louisvilleky.gov/",
           ("get", "https://hub.arcgis.com/api/v3/datasets/8bd82421c9b94c37925fb37edaa1c5e8_0/downloads/data?format=csv&spatialRefId=4326&where=1%3D1"),
           p_louisville),
    Source("gov_pa", "PA", "Pennsylvania state employee salaries (PennWATCH)", "Commonwealth of Pennsylvania (PennWATCH)",
           "Annual salary as of the current list; wage staff at the hourly rate times 2,080 hours", "https://pennwatch.pa.gov/employees",
           ("post_json", "https://pennwatch.pa.gov/service/Employee/searchall", "draw=1&start=0&length=200000&agency=&position="), p_pa),
]
BY_KEY = {s.key: s for s in SOURCES}
# What app/colleges.py's payroll copy shows for each source (title, publisher, pay basis).
SOURCE_INFO = {s.key: (s.title, s.publisher, s.basis) for s in SOURCES}

COLS = ("source_id", "state", "institution", "person_name", "name_norm", "title", "department", "base_pay", "other_pay",
        "total_pay", "pay_components", "fiscal_year", "source_url", "retrieved_at", "raw")


def records(src: Source, status=print):
    """Parsed, aggregated records of a source."""
    agg: dict = {}
    n = 0
    for row, url in rows_of(src, status):
        recs = src.parse(row)
        if not recs:
            continue
        for rec in (recs if isinstance(recs, list) else [recs]):
            if not rec or not rec.get("name") or not rec.get("employer"):
                continue
            rec["url"] = url
            n += 1
            if src.agg == "sum":
                k = rec["key"]
                if k in agg:
                    a = agg[k]
                    for f in ("base", "other", "total"):
                        a[f] = _add(a[f], rec[f])
                    for f in ("overtime", "other", "periods", "quarters"):
                        if f in a["components"] or f in rec["components"]:
                            a["components"][f] = _add(a["components"].get(f), rec["components"].get(f))
                else:
                    agg[k] = rec
            elif src.agg == "latest":
                k = rec["key"]
                if k not in agg or rec["seq"] > agg[k]["seq"]:
                    agg[k] = rec
            else:
                yield rec
    if src.agg:
        yield from agg.values()


def stage(keys: list[str], status=print) -> dict:
    out = {}
    with db.connect() as conn:
        conn.execute("SET statement_timeout = 0")
        for key in keys:
            src = BY_KEY[key]
            now = dt.datetime.now(dt.UTC)
            status(f"{key}: fetching")
            conn.execute("""DELETE FROM unipay.public_payroll_records WHERE source_id IN
                            (SELECT id FROM unipay.public_payroll_sources WHERE source_key = %s)""", (key,))
            conn.execute("DELETE FROM unipay.public_payroll_sources WHERE source_key = %s", (key,))
            sid = conn.execute("""INSERT INTO unipay.public_payroll_sources (source_key, state, institution_or_system, url,
                                  retrieved_at, notes) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                               (key, src.state, src.title, src.home, now, src.note or src.basis)).fetchone()[0]
            n = 0
            with conn.cursor() as cur, cur.copy(f"COPY unipay.public_payroll_records ({', '.join(COLS)}) FROM STDIN") as cp:
                for rec in records(src, status):
                    name = _s(rec["name"], 200)
                    comp = {k: v for k, v in (rec.get("components") or {}).items() if v not in (None, "")}
                    cp.write_row((sid, src.state, _s(rec["employer"], 200), name, normalize_name(name) or None, _s(rec.get("title")),
                                  _s(rec.get("department")), rec.get("base"), rec.get("other"), rec.get("total"),
                                  json.dumps(comp) if comp else None, rec.get("year"), rec["url"][:500], now, None))
                    n += 1
            conn.commit()
            out[key] = n
            status(f"{key}: {n:,} rows staged")
    return out


def finish(status=print) -> None:
    """Copy the staging rows into the site's payroll tables and rebuild labels, summaries and links."""
    import subprocess
    from app.config import ROOT
    subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/load.py"), "colleges", "--only", "labels,payroll,summary,links"],
                   check=True)
    with db.connect() as conn:
        conn.execute("SET statement_timeout = 0")
        conn.execute("CREATE INDEX IF NOT EXISTS payroll_person_years_norm ON payroll_person_years (name_norm text_pattern_ops)")
        conn.execute("CREATE INDEX IF NOT EXISTS payroll_person_years_src ON payroll_person_years (source_key, fiscal_year, total_pay DESC)")
        conn.commit()
    status("gov payroll: finished")


def link_rows(conn, commons: set) -> list[tuple]:
    """Person-page links for payroll people with no institution (state and city staff): the same normalized full
    name with a middle name or initial, held by exactly one person page, in one of that person's states (the
    payroll state); never a common name, an initials-only name, or a name two people share at one employer.
    Returns rows for payroll_person_links (loader/colleges.py link_people appends them)."""
    rows = conn.execute("""
        WITH pp AS (
            SELECT state, label, name_norm, min(person_name) AS person_name, min(fiscal_year) AS y0, max(fiscal_year) AS y1,
                   count(DISTINCT title) AS titles, count(*) AS n, count(DISTINCT fiscal_year) AS years
            FROM payroll_person_years
            WHERE unitid IS NULL AND NOT withheld AND name_norm IS NOT NULL AND source_key LIKE 'gov\\_%'
              AND array_length(string_to_array(name_norm, ' '), 1) >= 3
            GROUP BY 1, 2, 3),
        u AS (SELECT name_norm, min(id) AS id, min(states) AS states FROM person_clusters
              WHERE NOT coalesce(is_institution, false) GROUP BY name_norm HAVING count(*) = 1)
        SELECT pp.state, pp.label, pp.name_norm, pp.person_name, pp.y0, pp.y1, u.id
        FROM pp JOIN u ON u.name_norm = pp.name_norm
        WHERE pp.state = ANY(u.states) AND pp.n <= pp.years * 2""").fetchall()
    out = []
    for st, label, nn, pname, y0, y1, cid in rows:
        t = nn.split()
        if nn in commons or len(t[0]) < 2 or len(t[-1]) < 2:
            continue
        ev = {"payroll_name": pname, "payroll_years": f"{y0}-{y1}" if y0 != y1 else str(y0), "label": label,
              "rule": "same full name with a middle name or initial, on one person page, in the payroll state"}
        out.append((st, label, nn, None, cid, "FUZZY", json.dumps(ev)))
    return out


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        print(__doc__)
        return 2
    if argv == ["finish"]:
        finish()
        return 0
    keys = [s.key for s in SOURCES] if argv == ["all"] else argv
    bad = [k for k in keys if k not in BY_KEY]
    if bad:
        raise SystemExit(f"unknown source {bad}")
    stage(keys)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
