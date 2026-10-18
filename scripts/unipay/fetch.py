"""Download raw files for each unipay source into ~/unipay-data/<key>/ (once each), with a manifest.

Usage: fetch.py <key> [<key> ...]   (or 'all').  Network only; no database access.
"""
import datetime as dt
import json
import re
import sys
import urllib.parse

from common import DATA, UA, polite_get, sha256_file, socrata_pages

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
    print("  OK: see notes (initials only); not fetched by default")


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
