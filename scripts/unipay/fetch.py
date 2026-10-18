"""Download raw files for each unipay source into ~/unipay-data/<key>/ (once each), with a manifest.

Usage: fetch.py <key> [<key> ...]   (or 'all').  Network only; no database access.
"""
import datetime as dt
import json
import re
import sys
import urllib.parse

from common import DATA, UA, polite_get, sha256_file, socrata_pages  # noqa: F401

UTC = dt.timezone.utc


def _manifest_path(key):
    return DATA / key / "manifest.json"


def manifest(key):
    p = _manifest_path(key)
    return json.loads(p.read_text()) if p.exists() else {"files": {}}


def save_manifest(key, m):
    _manifest_path(key).write_text(json.dumps(m, indent=1))


def get_file(key, url, name, notes=None, **kw):
    """Download url to DATA/key/name unless already present."""
    d = DATA / key
    d.mkdir(parents=True, exist_ok=True)
    m = manifest(key)
    dest = d / name
    if dest.exists() and name in m["files"]:
        print("  have", name)
        return dest
    print("  GET", url, flush=True)
    polite_get(url, dest=dest, **kw)
    m["files"][name] = {"url": url, "retrieved_at": dt.datetime.now(UTC).isoformat(),
                        "sha256": sha256_file(dest), "bytes": dest.stat().st_size, "notes": notes}
    save_manifest(key, m)
    return dest


def put_json_file(key, name, url, rows, notes=None):
    d = DATA / key
    d.mkdir(parents=True, exist_ok=True)
    dest = d / name
    with open(dest, "w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    m = manifest(key)
    m["files"][name] = {"url": url, "retrieved_at": dt.datetime.now(UTC).isoformat(),
                        "sha256": sha256_file(dest), "bytes": dest.stat().st_size, "notes": notes}
    save_manifest(key, m)


# ---------------------------------------------------------------- Socrata sources
CT_AGENCIES = [
    "University of Connecticut", "UConn Health Center", "Connecticut Board of Regents",
    "Connecticut State Universities", "CT Community Colleges", "Comm. College System Office",
    "Charter Oak State College", "CSU - Central", "CSU - Eastern", "CSU - Southern", "CSU - Western",
    "CCC - Asnuntuck", "CCC - Capital", "CCC - Gateway", "CCC - Housatonic", "CCC - Manchester",
    "CCC - Middlesex", "CCC - Naugatuck Valley", "CCC - Northwestern", "CCC - Norwalk",
    "CCC - Quinebaug Valley", "CCC - Three Rivers", "CCC - Tunxis",
]


def fetch_ct():
    """Server-side SoQL aggregation: one row per employee record per agency per payroll fiscal year."""
    base = "https://data.ct.gov/resource/9m78-yc88.json"
    agencies = ",".join("'" + a.replace("'", "''") + "'" for a in CT_AGENCIES)
    for fy in range(2010, 2028):
        name = f"ct_fy{fy}.jsonl"
        if (DATA / "ct" / name).exists() and name in manifest("ct")["files"]:
            print("  have", name)
            continue
        params = {
            "$select": "pyrl_fiscal_yr,agency,emplid_empl_rcd,first_name,middle_initial,last_name,name_suffix,"
                       "max(department) as department,max(job_cd_descr) as job_cd_descr,max(annual_rate) as annual_rate,"
                       "max(full_part) as full_part,max(ee_class_descr) as ee_class_descr,"
                       "sum(salaries_wages) as salaries_wages,sum(overtime) as overtime,sum(other) as other,"
                       "sum(tot_gross) as tot_gross,count(*) as checks,min(check_dt) as first_check,max(check_dt) as last_check",
            "$where": f"pyrl_fiscal_yr='{fy}' AND agency in({agencies})",
            "$group": "pyrl_fiscal_yr,agency,emplid_empl_rcd,first_name,middle_initial,last_name,name_suffix",
            "$order": "agency,emplid_empl_rcd,first_name,middle_initial,last_name,name_suffix",
        }
        rows = []
        for page in socrata_pages(base, params, page=50000):
            rows.extend(page)
            print(f"  ct fy{fy}: {len(rows)}", flush=True)
        url = base + "?" + urllib.parse.urlencode({k: v for k, v in params.items()})
        put_json_file("ct", name, url, rows, notes="SoQL server-side aggregation of paycheck rows per employee record/agency/payroll FY")


CT_SYSTEM_AGENCIES = ["CT Community Colleges", "Connecticut State Universities", "Connecticut Board of Regents"]


def fetch_ct2():
    """Follow-up refetch. Same aggregation as fetch_ct, plus the campus code (deptid characters 4-6) and city.
    System-level agencies (CT Community Colleges / Connecticut State Universities in FY2010-2014, and the Board of
    Regents, which absorbed every CSCU campus in FY2024) are grouped by campus code so campuses stay separate.
    Adds 'Board for Academic Awards' (Charter Oak State College's agency before FY2014)."""
    base = "https://data.ct.gov/resource/9m78-yc88.json"
    single = [a for a in CT_AGENCIES if a not in CT_SYSTEM_AGENCIES] + ["Board for Academic Awards"]
    sel = ("pyrl_fiscal_yr,agency,emplid_empl_rcd,first_name,middle_initial,last_name,name_suffix,"
           "max(department) as department,max(job_cd_descr) as job_cd_descr,max(annual_rate) as annual_rate,"
           "max(full_part) as full_part,max(ee_class_descr) as ee_class_descr,"
           "sum(salaries_wages) as salaries_wages,sum(overtime) as overtime,sum(other) as other,"
           "sum(tot_gross) as tot_gross,count(*) as checks,min(check_dt) as first_check,max(check_dt) as last_check,"
           "max(deptid) as deptid_max,max(city) as city_max")
    grp = "pyrl_fiscal_yr,agency,emplid_empl_rcd,first_name,middle_initial,last_name,name_suffix"
    for fy in range(2010, 2028):
        for part, ags, extra in (("agency", single, ""), ("system", CT_SYSTEM_AGENCIES, ",campus_cd")):
            name = f"ct2_fy{fy}_{part}.jsonl"
            if (DATA / "ct" / name).exists() and name in manifest("ct")["files"]:
                print("  have", name)
                continue
            agl = ",".join("'" + a.replace("'", "''") + "'" for a in ags)
            params = {"$select": sel + (",substring(deptid,4,3) as campus_cd" if extra else ""),
                      "$where": f"pyrl_fiscal_yr='{fy}' AND agency in({agl})",
                      "$group": grp + extra, "$order": grp + extra}
            rows = []
            for page in socrata_pages(base, params, page=50000):
                rows.extend(page)
                print(f"  ct2 fy{fy} {part}: {len(rows)}", flush=True)
            url = base + "?" + urllib.parse.urlencode(params)
            put_json_file("ct", name, url, rows, notes="SoQL server-side aggregation of paycheck rows per employee record/agency"
                          + ("/campus code" if extra else "") + "/payroll FY")


MA_CODES = ["UMS", "BSC", "FSC", "FRC", "SSA", "WSC", "WOR", "MCA", "NAC", "MMA", "BCC", "BRC", "BHC", "CCC",
            "GCC", "HCC", "MAS", "MBC", "MCC", "MWC", "NEC", "NSC", "QCC", "RCC", "STC"]


def fetch_ma():
    base = "https://cthru.data.socrata.com/resource/9ttk-7vz6.json"
    codes = ",".join(f"'{c}'" for c in MA_CODES)
    for yr in range(2009, 2027):
        name = f"ma_{yr}.jsonl"
        if (DATA / "ma" / name).exists() and name in manifest("ma")["files"]:
            print("  have", name)
            continue
        params = {"$where": f"year='{yr}' AND department_code in({codes})", "$order": "id"}
        rows = []
        for page in socrata_pages(base, params, page=50000):
            rows.extend(page)
            print(f"  ma {yr}: {len(rows)}", flush=True)
        url = base + "?" + urllib.parse.urlencode(params)
        put_json_file("ma", name, url, rows)


def fetch_nyc():
    base = "https://data.cityofnewyork.us/resource/k397-673e.json"
    name = "nyc_cuny_cc.jsonl"
    if (DATA / "nyc" / name).exists() and name in manifest("nyc")["files"]:
        print("  have", name)
        return
    params = {"$where": "agency_name like 'COMMUNITY COLLEGE%' OR agency_name='GUTTMAN COMMUNITY COLLEGE'",
              "$order": "fiscal_year,agency_name,last_name,first_name,payroll_number,title_description,agency_start_date,work_location_borough,regular_gross_paid"}
    rows = []
    for page in socrata_pages(base, params, page=50000):
        rows.extend(page)
        print(f"  nyc: {len(rows)}", flush=True)
    put_json_file("nyc", name, base + "?" + urllib.parse.urlencode(params), rows)


def fetch_wa():
    get_file("wa", "https://data.wa.gov/api/views/y3ds-rkew/rows.csv?accessType=DOWNLOAD", "wa_salaries_2010_2013.csv")


# ---------------------------------------------------------------- plain files
def fetch_ga():
    get_file("ga", "https://open.ga.gov/export/SalaryTravelDataExportAllYears.zip", "SalaryTravelDataExportAllYears.zip")


def fetch_tx():
    get_file("tx", "https://drive.usercontent.google.com/download?id=1OgAy1oMlwYjDwbwzFM-mRUYpKX-anzrq&export=download&confirm=t",
             "TCS_Export_05_25_2026.csv", notes="Google Drive file 'TCS Export 05_25_2026.csv' in public folder 1RHnj46y3B5X8T4siwudKJOBmuJYDAMRF",
             check_robots=False)


def _links(page_url, pattern):
    r = polite_get(page_url)
    out = []
    for h in re.findall(r'href="([^"]+)"', r.text):
        u = urllib.parse.urljoin(str(r.url), h.replace("&amp;", "&"))
        if re.search(pattern, u, re.I) and u not in out:
            out.append(u)
    return out


def fetch_il_iccb():
    for u in _links("https://iccbdbsrv.iccb.org/salarysearch/", r"fiscalyr/.*\.xlsx$"):
        fy = re.search(r"Fiscal Year (\d{4})", urllib.parse.unquote(u)).group(1)
        get_file("il_iccb", u.replace(" ", "%20"), f"iccb_fy{fy}.xlsx")


def fetch_oh_osu():
    for y in range(2021, 2026):
        for kind in ("Salaries", "Earnings"):
            ok = False
            for suffix in ("-v3", "-v2", ""):
                u = f"https://apps.hr.osu.edu/public/documents/salaries/{y}-{kind}-Combined{suffix}.xlsx"
                try:
                    get_file("oh_osu", u, f"osu_{y}_{kind.lower()}.xlsx")
                    ok = True
                    break
                except Exception as e:  # noqa: BLE001
                    print("   miss", u, e)
            if not ok:
                print("  no file for", y, kind)


def fetch_oh_ou():
    get_file("oh_ou", "https://www.ohio.edu/sites/default/files/2026-03/2025%20Annual%20Salary%20W2%20report.xlsx", "ou_2025_salary_w2.xlsx")


def fetch_mn():
    for fy in range(2011, 2027):
        get_file("mn", f"https://mn.gov/mmb-stat/transparency/employee-salary-data/fiscal-year-{fy}.xlsx", f"mn_fy{fy}.xlsx")


def fetch_ri():
    get_file("ri", "https://transparency.ri.gov/payroll/sendtocsvall.php", "ri_payroll_all.csv")


def fetch_ks():
    get_file("ks", "https://kansasopengov.org/wp-content/uploads/2023/07/State-Payroll-2021-to-2025.csv", "ks_state_payroll_2021_2025.csv")


def fetch_ne():
    for u in _links("https://nebraska.edu/offices/business-finance/budget-and-planning/archive", r"budget-salary/.*\.xlsx$"):
        y = re.search(r"(20\d\d)[-_](20\d\d)", urllib.parse.unquote(u))
        get_file("ne", u, f"ne_{y.group(1)}_{y.group(2)}.xlsx")
    get_file("ne", "https://docs.nebraska.edu/unop/docs/Business%20and%20Finance/budget-salary/2026-2027/Budgeted%20Employees%20as%20of%20July%201%202026.xlsx", "ne_2026_2027.xlsx")


def fetch_me():
    get_file("me", "https://umainesystem.sharepoint.com/:x:/s/USERVICES-OnlineDocs/IQDqj_BhiQonQYDtctkano9vAR0sfdWOg5CFpMSk7PO7JV4?download=1",
             "ume_regular_employee_compensation_june_2026.xlsx", check_robots=False,
             notes="anonymous SharePoint share link (robots.txt of sharepoint tenant not applicable to share links)")


def fetch_nm():
    get_file("nm", "https://sunshine.unm.edu/cache/salary-book.json", "unm_salary_book.json")


def fetch_dc():
    base = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/35/query"
    rows, off = [], 0
    while True:
        r = polite_get(base, params={"where": "DESCRSHORT='UDC'", "outFields": "*", "returnGeometry": "false", "f": "json",
                                     "resultOffset": off, "resultRecordCount": 1000, "orderByFields": "OBJECTID"})
        feats = r.json().get("features", [])
        rows.extend(f["attributes"] for f in feats)
        if len(feats) < 1000:
            break
        off += 1000
    put_json_file("dc", "dc_udc_snapshot.jsonl", base + "?where=DESCRSHORT%3D%27UDC%27&outFields=*&f=json", rows)


def fetch_az_asu():
    r = polite_get("https://api.github.com/repos/thestatepress/SalaryList/contents/data-csv")
    names = [x["name"] for x in r.json() if x["name"].endswith(".csv")]
    by_year = {}
    for n in names:
        y = n[:4]
        if "revised" in n or y not in by_year:
            by_year[y] = n
    for y, n in sorted(by_year.items()):
        get_file("az_asu", "https://raw.githubusercontent.com/TheStatePress/SalaryList/master/data-csv/" + urllib.parse.quote(n), f"asu_{y}.csv")


def fetch_az_ua():
    get_file("az_ua", "https://flo.uri.sh/visualisation/16806493/embed", "ua_flourish_embed.html")


def fetch_ok():
    """FY2026 (Jul 2025-Jun 2026) monthly payroll CSVs. The CKAN /api/ path is disallowed by robots.txt, so links come from the dataset page."""
    for u in _links("https://data.ok.gov/dataset/state-of-oklahoma-payroll-fiscal-year-2026", r"/download/payroll_public_\d{6}.*\.csv$"):
        ym = re.search(r"payroll_public_(\d{6})", u).group(1)
        if "202507" <= ym <= "202606":
            get_file("ok", u, f"ok_payroll_{ym}.csv")


def fetch_nj():
    base = "https://data.nj.gov/resource/44xg-bswk.json"
    name = "nj_pension_higher_ed.jsonl"
    if (DATA / "nj" / name).exists() and name in manifest("nj")["files"]:
        print("  have", name)
        return
    params = {"$where": "upper(employer_name) like '%COLL%' OR upper(employer_name) like '%UNIV%' OR upper(employer_name) like '%RUTGERS%' OR upper(employer_name) like '%INST%TECH%' OR upper(employer_name) like '%COMM%COL%'",
              "$order": ":id"}
    rows = []
    for page in socrata_pages(base, params, page=50000):
        rows.extend(page)
        print(f"  nj: {len(rows)}", flush=True)
    put_json_file("nj", name, base + "?" + urllib.parse.urlencode(params), rows)


def fetch_il_graybook():
    """University of Illinois Gray Book 2026-27: clean per-unit HTML tables (B-rated source, reliable markup)."""
    base = "https://www.trustees.uillinois.edu/trustees/resources/26-27-Graybook/"
    seen = set()
    for u in _links(base + "TOC.html", r"26-27-Graybook/[A-Za-z0-9_-]+\.html$"):
        name = u.rsplit("/", 1)[1]
        if name == "TOC.html" or name in seen:
            continue
        seen.add(name)
        get_file("il_graybook", u, name)


SC_AGENCIES = {"43026": "AIKEN TECHNICAL COLLEGE", "43106": "CENTRAL CAROLINA TECH COLLEGE", "42091": "CLEMSON UNIVERSITY",
               "42681": "COASTAL CAROLINA UNIVERSITY", "43051": "DENMARK TECHNICAL COLLEGE", "43056": "FLO DARLINGTON TECH COLLEGE",
               "42746": "FRANCIS MARION UNIVERSITY", "43061": "GREENVILLE TECHNICAL COLLEGE", "43071": "HORRY GEORGETOWN TECH COLLEGE",
               "42776": "LANDER UNIVERSITY", "42981": "MEDICAL UNIVERSITY OF SC", "43076": "MIDLANDS TECHNICAL COLLEGE",
               "43046": "NORTHEASTERN TECHNICAL COLLEGE", "43091": "ORANGEBURG CALHOUN TEC COLLEGE", "43096": "PIEDMONT TECHNICAL COLLEGE",
               "43101": "SPARTANBURG TECHNICAL COLLEGE", "43036": "TECH COLL OF LOW COUNTRY", "41876": "THE CITADEL",
               "43111": "TRI COUNTY TECHNICAL COLLEGE", "43116": "TRIDENT TECHNICAL COLLEGE", "42616": "UNIVERSITY OF CHARLESTON",
               "42806": "UNIVERSITY OF SOUTH CAROLINA", "43126": "WILLIAMSBURG TECHNICAL COLLEGE", "42956": "WINTHROP UNIVERSITY",
               "43131": "YORK TECHNICAL COLLEGE"}


def fetch_sc():
    """SC state salaries (B): plain-GET paged Drupal table, one agency at a time. All pages of an agency are
    concatenated into one saved HTML file (pages separated by a marker comment) so rows trace to a file + SHA."""
    base = "https://admin.sc.gov/transparency/state-salaries"
    d = DATA / "sc"
    d.mkdir(parents=True, exist_ok=True)
    for ag, name in SC_AGENCIES.items():
        fname = f"sc_{ag}.html"
        if fname in manifest("sc")["files"]:
            print("  have", fname)
            continue
        parts, page = [], 0
        while True:
            r = polite_get(base, params={"agency": ag, "job": "All", "firstname": "", "lastname": "", "page": page})
            if "views-field-label" not in r.text.split("<tbody", 1)[-1]:
                break
            parts.append(f"<!-- UNIPAY PAGE {page} {r.url} -->\n" + r.text)
            page += 1
            if page > 400:
                break
        tmp = d / fname
        tmp.write_text("\n".join(parts))
        m = manifest("sc")
        m["files"][fname] = {"url": f"{base}?agency={ag}&job=All&firstname=&lastname=&page=0..{page - 1}",
                             "retrieved_at": dt.datetime.now(UTC).isoformat(), "sha256": sha256_file(tmp), "bytes": tmp.stat().st_size,
                             "notes": f"{name}: {page} pages concatenated"}
        save_manifest("sc", m)
        print(f"  sc {name}: {page} pages", flush=True)


def fetch_md():
    """UMD Diamondback salary guide API (A): GET-only JSON, fixed 10 rows/page (page-size params are ignored), so
    ~1,100 pages per year. Sorted by employee name for stable paging. One JSONL file per year label; each line keeps
    the API row plus the page it came from. Resumable per year."""
    base = "https://api.dbknews.com/salary/year/{}"
    years = polite_get("https://api.dbknews.com/salary/years", check_robots=False, delay=1.2).json()["data"]
    import httpx
    client = httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=60)  # one connection; new clients cost ~2 s each
    for y in sorted(years, reverse=True):  # newest first
        name = f"md_{y}.jsonl"
        if name in manifest("md")["files"]:
            print("  have", name)
            continue
        rows, page, count = [], 1, None
        while True:
            r = polite_get(base.format(y), params={"page": page, "sortby": "employee", "order": "asc", "search": ""},
                           check_robots=False, delay=1.2, timeout=60, client=client).json()
            count = int(r.get("count") or 0)
            if not r["data"]:
                break
            rows.extend({**x, "_page": page} for x in r["data"])
            if page % 100 == 0:
                print(f"  md {y}: page {page}, {len(rows)}/{count}", flush=True)
            if len(rows) >= count:
                break
            page += 1
        put_json_file("md", name, base.format(y) + "?page=1.." + str(page) + "&sortby=employee&order=asc&search=", rows,
                      notes=f"API count={count}; fetched {len(rows)} rows over {page} pages (10/page); api.dbknews.com has no robots.txt (404)")
        print(f"  md {y}: {len(rows)}/{count}", flush=True)


NE_CC_ORGS = {7392: "Metropolitan Community College", 6367: "Mid-Plains Community College", 5950: "Southeast Community College"}


def fetch_ne_cc():
    """Nebraska community colleges from the Flatwater Free Press 'Nebraska Public Payrolls' site (B). Its WordPress
    REST API is plain GET (`/wp-json/wp/v2/employee?organization=<id>`, 100 per page) and carries the same records as
    the paginated HTML pages, with structured pay fields. robots.txt allows all paths with Crawl-delay: 10 (honored)."""
    base = "https://salaries.flatwaterfreepress.org/wp-json/wp/v2/employee"
    for oid, oname in NE_CC_ORGS.items():
        name = f"ne_cc_{oid}.jsonl"
        if name in manifest("ne_cc")["files"]:
            print("  have", name)
            continue
        rows, page = [], 1
        while True:
            r = polite_get(base, params={"organization": oid, "per_page": 100, "page": page, "orderby": "id", "order": "asc"}, delay=10)
            data = r.json()
            rows.extend(data)
            total_pages = int(r.headers.get("x-wp-totalpages", "1"))
            total = int(r.headers.get("x-wp-total", "0"))
            print(f"  ne_cc {oname}: page {page}/{total_pages} ({len(rows)}/{total})", flush=True)
            if page >= total_pages or not data:
                break
            page += 1
        put_json_file("ne_cc", name, f"{base}?organization={oid}&per_page=100&page=1..{page}&orderby=id&order=asc", rows,
                      notes=f"{oname}: X-WP-Total={total}; fetched {len(rows)}")


STL_BASE = "https://graphics.stltoday.com/apps/payrolls/salaries_2026/"
STL_AGENCIES = {117: "University of Missouri-Columbia", 118: "University of Missouri-Kansas City", 119: "University of Missouri-St. Louis",
                120: "Missouri University of Science and Technology", 116: "University of Missouri System", 115: "University of Missouri Health Care",
                87: "St. Louis Community College", 78: "St. Charles Community College", 136: "Southern Illinois University Edwardsville",
                111: "University of Illinois Administration", 112: "University of Illinois-Chicago", 113: "University of Illinois-Springfield",
                114: "University of Illinois-Urbana-Champaign"}


def fetch_mo_stl():
    """St. Louis Post-Dispatch 'Public Pay' 2026 edition (actual 2025 gross pay), universities group (B). Plain GET HTML:
    agency page -> department pages (50 rows, ?page=N). robots.txt has no rule for our agent (crawl-delay 10 applies to
    named bots only); we wait 5 s between requests anyway. Each agency is saved as one HTML file of concatenated pages
    with marker comments (dept id, dept name, page) so rows trace to a file + SHA."""
    d = DATA / "mo_stl"
    d.mkdir(parents=True, exist_ok=True)
    for aid, aname in STL_AGENCIES.items():
        fname = f"stl_{aid}.html"
        if fname in manifest("mo_stl")["files"]:
            print("  have", fname)
            continue
        r = polite_get(f"{STL_BASE}{aid}/", delay=5)
        depts = []
        for m in re.finditer(r'<a href="(?:https://graphics\.stltoday\.com)?/apps/payrolls/salaries_2026/(%d_\d+)/"[^>]*>(.*?)</a>' % aid, r.text, re.S):
            did, dname = m.group(1), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
            if did not in [x[0] for x in depts]:
                depts.append((did, dname))
        parts = [f"<!-- UNIPAY AGENCY {aid} {aname} {r.url} -->\n" + r.text]
        npages = 1
        for did, dname in depts:
            page, last = 1, 1
            while page <= last:
                url = f"{STL_BASE}{did}/" + (f"?page={page}" if page > 1 else "")
                rr = polite_get(url, delay=5)
                npages += 1
                mm = re.search(r"Page\s+\d+\s+of\s+(\d+)", re.sub(r"<[^>]+>", " ", rr.text))
                last = int(mm.group(1)) if mm else 1
                parts.append(f"<!-- UNIPAY DEPT {did} PAGE {page} NAME {dname} URL {rr.url} -->\n" + rr.text)
                page += 1
        tmp = d / fname
        tmp.write_text("\n".join(parts))
        m = manifest("mo_stl")
        m["files"][fname] = {"url": f"{STL_BASE}{aid}/ (+ {len(depts)} department pages)", "retrieved_at": dt.datetime.now(UTC).isoformat(),
                             "sha256": sha256_file(tmp), "bytes": tmp.stat().st_size,
                             "notes": f"{aname}: {len(depts)} departments, {npages} pages concatenated"}
        save_manifest("mo_stl", m)
        print(f"  mo_stl {aname}: {len(depts)} depts, {npages} pages", flush=True)


def fetch_ipeds():
    for f in ("SAL2023_IS", "HD2023", "SAL2023_IS_Dict" ):
        try:
            get_file("ipeds", f"https://nces.ed.gov/ipeds/datacenter/data/{f}.zip", f"{f}.zip")
        except Exception as e:  # noqa: BLE001
            print("   miss", f, e)


FETCHERS = {k[6:]: v for k, v in globals().items() if k.startswith("fetch_")}

if __name__ == "__main__":
    keys = sys.argv[1:]
    if keys == ["all"]:
        keys = list(FETCHERS)
    for k in keys:
        print("==", k, dt.datetime.now().strftime("%H:%M:%S"), flush=True)
        try:
            FETCHERS[k]()
        except Exception as e:  # noqa: BLE001
            print(f"!! {k} failed: {type(e).__name__}: {e}", flush=True)
            (DATA / k).mkdir(parents=True, exist_ok=True)
            (DATA / k / "FETCH_ERROR.txt").write_text(f"{dt.datetime.now().isoformat()} {type(e).__name__}: {e}\n")
