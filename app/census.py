"""Census cross-reference pages (owner, 2026-11-12): /census and the "The area" section on entity pages.

The census tables are IPUMS NHGIS extracts (loader/nhgis.py, schema nhgis); loader/census.py ties them to every
FURP record that has an address (census_links) and keeps the headline measures per state, county, place and tract
in census_area. This module reads those tables only, so pages work (with less on them) while the nightly load is
still filling the census tables: a measure whose table has not loaded shows "not loaded yet".

Pages: /census (the states, a US map), /census/<st> (counties, a choropleth), /census/<st>/<county> (tracts and
places), /census/<st>/place/<place>, /census/tract/<geoid>, /census/tables (the NHGIS catalog), /census/area
(find an area by ZIP or city), and a map export (CSV or GeoJSON) under each page's /map. Every page lists the
FURP records in the area: nonprofits, their highest-paid people, contractors, schools, lobbying clients, Form D
issuers, federal recipients, committees... each linking to its FURP page.
Data: IPUMS NHGIS (the citation is CITATION, also on /data). Maps: app/census_map.py.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import db
from app.cache import ttl_lru
from loader.census import MEASURES, geoid_of, gisjoin, place_short

log = logging.getLogger("np.census")
router = APIRouter()
PUBLIC = os.environ.get("CENSUS_PUBLIC", "1") == "1"
CITATION = ("Jonathan Schroeder, David Van Riper, Steven Manson, Grace Cooper, Zachary Krause, Tracy Kugler, Tsu Zhu, "
            "and Steven Ruggles. IPUMS National Historical Geographic Information System: Version 21.0 [dataset]. "
            "Minneapolis, MN: IPUMS. 2026. http://doi.org/10.18128/D050.V21.0")
CITATION_URL = "http://doi.org/10.18128/D050.V21.0"
SOURCE = ("Census figures are from IPUMS NHGIS: the American Community Survey 2020-2024 five-year estimates (ACS table "
          "codes shown with each figure) and the 2020 decennial census (Demographic and Housing Characteristics), by "
          "state, county, place and census tract. FURP records are placed by ZIP code (the Census Bureau's 2020 "
          "ZCTA-to-county and ZCTA-to-tract relationship files: the county or tract holding most of the ZIP's land) "
          "and by city name (Census place names, normalized), so a record's tract is its ZIP's main tract, not its "
          "street's.")
ACS_YEAR = "2024"
ACS_LABEL = "ACS 2020-2024"
DEFAULT_MEASURE = "population"
MAP_MEASURES = ["population", "median_hh_income", "poverty_rate", "median_age", "bachelors_share", "median_home_value",
                "renter_share", "hispanic_share", "black_share", "white_share", "unemployment_rate", "over_65_share"]
LEVEL_LABEL = {"state": "state", "county": "county", "place": "place (city or town)", "tract": "census tract"}
TRACT_NOTE = "the tract holding most of the record's ZIP code (FURP does not geocode street addresses)"

# Record kinds in census_links (loader/census.py SOURCES): label, the page for a key, the value's label and format.
KINDS = {
    "org": ("Nonprofits", lambda k: f"/org/{k}", "Revenue (latest return)", "money"),
    "contractor": ("Nonprofit contractors", lambda k: f"/contractor/{k}", "Paid by nonprofits", "money"),
    "college": ("Colleges and schools", lambda k: f"/institution/{k}", "Enrollment", "num"),
    "formd": ("Form D issuers", lambda k: f"/corporate/form-d/cik/{k}", "Amount sold", "money"),
    "lda_client": ("Lobbying clients", lambda k: f"/lobbying/client/{k}", "Lobbying spent", "money"),
    "fec_committee": ("Political committees", lambda k: f"/politics/committee/{k}", "", "num"),
    "f5500": ("Form 5500 plan sponsors", lambda k: f"/form5500/sponsor/{k}", "Plans", "num"),
    "op_recipient": ("Open Payments recipients", lambda k: f"/openpayments/recipient/{k}", "Industry payments", "money"),
    "recallfirm": ("Food recall firms", lambda k: f"/recalls/firm/{k}", "Recalls", "num"),
    "ip_firm": ("Patent and trademark owners", lambda k: f"/business/USPTO/{k}", "Patents and marks", "num"),
    "ipo": ("IPO registrants", lambda k: f"/ipos/{k}", "Filings", "num"),
    "fed": ("Federal award recipients", lambda k: "/federal-spending?" + urlencode({"q": k.split("|")[0]}),
            "Federal awards", "money"),
    "biz": ("State business registrations", lambda k: "/business/" + k.split(":", 1)[0] + "/" + quote(k.split(":", 1)[1], safe=""),
            "", "num"),
}
KIND_ORDER = list(KINDS)
MEASURE_INFO = {m[0]: {"key": m[0], "table": m[1], "label": m[3], "fmt": m[4], "note": m[5]} for m in MEASURES}
FACT_GROUPS = [
    ("People", ["population", "pop2020", "median_age", "under_18_share", "over_65_share", "households", "foreign_born_share"]),
    ("Money", ["median_hh_income", "median_family_income", "per_capita_income", "poverty_rate", "unemployment_rate",
               "labor_force", "mean_commute"]),
    ("Education", ["bachelors_share"]),
    ("Housing", ["housing_units", "owner_share", "renter_share", "median_home_value", "median_rent"]),
    ("Race and ethnicity", ["white_share", "black_share", "hispanic_share", "asian_share", "native_share"]),
]
MEASURE_INFO["pop2020"] = {"key": "pop2020", "table": "P1", "label": "Population, 2020 census", "fmt": "num",
                           "note": "2020 decennial census count (DHC table P1)", "dhc": True}
_ST = re.compile(r"^[A-Za-z]{2}$")
_SLUG = re.compile(r"^[a-z0-9-]{1,90}$")
_GEOID = re.compile(r"^\d{11}$")
_ZIP = re.compile(r"^\s*(\d{5})(?:-\d{4})?\s*$")
TOP = 10


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    from app.main import render
    return render(request, template, census=sys.modules[__name__], **ctx)


# --- what is loaded -----------------------------------------------------------------------------------------------------

@ttl_lru(ttl=300)
def ready() -> bool:
    try:
        with db.conn() as conn:
            return bool(conn.execute("SELECT to_regclass('census_area') IS NOT NULL AND EXISTS (SELECT 1 FROM census_area) AS ok"
                                     ).fetchone()["ok"])
    except Exception:  # noqa: BLE001
        return False


@ttl_lru(ttl=300)
def loaded_measures() -> set[str]:
    """The measures whose census table has loaded (any value at the state level)."""
    if not ready():
        return set()
    cols = ["pop2020"] + [m[0] for m in MEASURES]
    try:
        with db.conn() as conn:
            r = conn.execute("SELECT " + ", ".join(f"count({c}) AS {c}" for c in cols)
                             + " FROM census_area WHERE level = 'state'").fetchone()
    except Exception:  # noqa: BLE001
        return set()
    return {c for c in cols if (r[c] or 0) > 0}


@ttl_lru(ttl=600)
def tables_loaded() -> list[dict]:
    """The NHGIS catalog: every census table loaded so far, with its description and universe."""
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('nhgis.tables') AS t").fetchone()["t"]:
                return []
            return [dict(r) for r in conn.execute(
                "SELECT dataset, source_code, nhgis_code, description, universe, n_variables FROM nhgis.tables "
                "ORDER BY dataset, source_code").fetchall()]
    except Exception:  # noqa: BLE001
        return []


# --- areas --------------------------------------------------------------------------------------------------------------

def url_for(a: dict | None) -> str | None:
    if not a:
        return None
    st = (a.get("stusab") or "").lower()
    if a["level"] == "state":
        return f"/census/{st}"
    if a["level"] == "county":
        return f"/census/{st}/{a['slug']}"
    if a["level"] == "place":
        return f"/census/{st}/place/{a['slug']}"
    return f"/census/tract/{a['geoid']}"


def display_name(a: dict | None) -> str:
    if not a:
        return ""
    if a["level"] == "place":
        return f"{place_short(a['short_name'])}, {a['stusab']}"
    if a["level"] == "county":
        return f"{a['short_name']}, {a['stusab']}"
    return a["name"] or a["gisjoin"]


def census_gov_url(a: dict, table: str) -> str:
    """The same table for the same area at data.census.gov, so every figure links to its census table."""
    prefix = {"state": "0400000US", "county": "0500000US", "place": "1600000US", "tract": "1400000US"}[a["level"]]
    if table == "P1":
        return f"https://data.census.gov/table/DECENNIALDHC2020.P1?g={prefix}{a['geoid']}"
    return f"https://data.census.gov/table/ACSDT5Y{ACS_YEAR}.{table}?g={prefix}{a['geoid']}"


@ttl_lru(ttl=600, maxsize=4096)
def area(gj: str) -> dict | None:
    if not gj or not ready():
        return None
    with db.conn() as conn:
        r = conn.execute("SELECT * FROM census_area WHERE gisjoin = %s", (gj,)).fetchone()
    return dict(r) if r else None


@ttl_lru(ttl=600, maxsize=4096)
def find(level: str, st: str | None = None, slug: str | None = None, geoid: str | None = None) -> dict | None:
    if not ready():
        return None
    with db.conn() as conn:
        if level == "tract":
            r = conn.execute("SELECT * FROM census_area WHERE level = 'tract' AND geoid = %s", (geoid,)).fetchone()
        else:
            r = conn.execute("SELECT * FROM census_area WHERE level = %s AND stusab = %s AND slug = %s",
                             (level, (st or "").upper(), slug)).fetchone()
    return dict(r) if r else None


def parents(a: dict) -> dict:
    """The state (and county) an area sits in."""
    out = {"state": None, "county": None}
    if a["level"] != "state":
        out["state"] = area(gisjoin("state", a["state_fips"]))
    if a["level"] in ("tract", "place") and a.get("county_fips"):
        out["county"] = area(gisjoin("county", a["state_fips"] + a["county_fips"]))
    return out


@ttl_lru(ttl=600, maxsize=512)
def children(level: str, state_fips: str | None = None, county_fips: str | None = None, limit: int | None = None,
             order: str = "name") -> list[dict]:
    """The states; a state's counties or places; a county's tracts or places."""
    if not ready():
        return []
    sql, params = "SELECT * FROM census_area WHERE level = %s", [level]
    if state_fips:
        sql += " AND state_fips = %s"
        params.append(state_fips)
    if county_fips:
        sql += " AND county_fips = %s"
        params.append(county_fips)
    sql += " ORDER BY " + ("population DESC NULLS LAST, name" if order == "population" else "name")
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    with db.conn(timeout="20s") as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@ttl_lru(ttl=600, maxsize=64)
def states() -> list[dict]:
    return children("state")


# --- the FURP records in an area ----------------------------------------------------------------------------------------

LEVEL_COL = {"state": "state_gj", "county": "county_gj", "place": "place_gj", "tract": "tract_gj"}


@ttl_lru(ttl=600, maxsize=4096)
def furp_summary(gj: str) -> list[dict]:
    """Per record kind: how many, their total, the biggest (census_area_furp)."""
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('census_area_furp') AS t").fetchone()["t"]:
                return []
            rows = conn.execute("SELECT * FROM census_area_furp WHERE gisjoin = %s", (gj,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    by = {r["kind"]: dict(r) for r in rows}
    out = []
    for kind in KIND_ORDER:
        r = by.get(kind)
        if not r or kind not in KINDS:
            continue
        label, url, vlabel, vfmt = KINDS[kind]
        out.append({**r, "label": label, "value_label": vlabel, "fmt": vfmt, "top_url": url(r["top_key"]) if r.get("top_key") else None})
    return out


@ttl_lru(ttl=600, maxsize=4096)
def furp_top(gj: str, level: str, kind: str, limit: int = TOP) -> list[dict]:
    """The biggest records of one kind in the area, each with its page."""
    if kind not in KINDS or level not in LEVEL_COL:
        return []
    label, url, vlabel, vfmt = KINDS[kind]
    try:
        with db.conn() as conn:
            rows = conn.execute(f"""SELECT key, name, city, state, value, how FROM census_links
                                    WHERE {LEVEL_COL[level]} = %s AND kind = %s
                                    ORDER BY value DESC NULLS LAST, name LIMIT %s""", (gj, kind, limit)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{**dict(r), "url": url(r["key"])} for r in rows]


@ttl_lru(ttl=600, maxsize=4096)
def top_people(gj: str, level: str, limit: int = TOP) -> list[dict]:
    """The highest-paid people on 990s in the area (latest year each; census_area_people)."""
    col = {"state": ("state_gj", "rank_state"), "county": ("county_gj", "rank_county"), "place": ("place_gj", "rank_place")}.get(level)
    if not col:
        return []
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('census_area_people') AS t").fetchone()["t"]:
                return []
            rows = conn.execute(f"SELECT * FROM census_area_people WHERE {col[0]} = %s AND {col[1]} <= %s ORDER BY {col[1]}",
                                (gj, limit)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [dict(r) for r in rows]


@ttl_lru(ttl=600, maxsize=1024)
def points(gj: str, level: str, kind: str = "org", limit: int = 1500) -> list[dict]:
    """The area's records of one kind grouped by ZIP code, at the ZIP's center, for the map."""
    if kind not in KINDS or level not in LEVEL_COL:
        return []
    try:
        with db.conn(timeout="10s") as conn:
            rows = conn.execute(f"""SELECT l.zip5, count(*) AS n, sum(l.value) AS total, z.lat, z.lon
                                    FROM census_links l JOIN geo_zips z ON z.zip5 = l.zip5
                                    WHERE l.{LEVEL_COL[level]} = %s AND l.kind = %s
                                    GROUP BY l.zip5, z.lat, z.lon ORDER BY n DESC LIMIT %s""", (gj, kind, limit)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    label = KINDS[kind][0].lower()
    return [{"lon": r["lon"], "lat": r["lat"], "n": r["n"], "url": f"/nearby?q={r['zip5']}" if kind == "org" else None,
             "label": f"ZIP {r['zip5']}: {r['n']:,} {label}" + (f", {_money(r['total'])}" if r["total"] else "")} for r in rows]


def _money(v) -> str:
    return f"${float(v):,.0f}"


# --- facts and comparisons ------------------------------------------------------------------------------------------------

def facts(a: dict, loaded: set[str] | None = None) -> list[dict]:
    """The area's headline figures in groups, each with the census table it came from and a link to that table."""
    loaded = loaded if loaded is not None else loaded_measures()
    out = []
    for group, keys in FACT_GROUPS:
        rows = []
        for k in keys:
            info = MEASURE_INFO[k]
            rows.append({**info, "value": a.get(k), "loaded": k in loaded, "url": census_gov_url(a, info["table"])})
        out.append({"group": group, "rows": rows})
    return out


def fmt(v, kind: str) -> str:
    if v is None:
        return "-"
    v = float(v)
    if kind == "money":
        return f"${v:,.0f}"
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "years":
        return f"{v:.1f}"
    if kind == "multiple":
        return f"{v:,.1f}x"
    return f"{v:,.0f}"


def compare(a: dict, numbers: dict) -> list[dict]:
    """FURP-style cross-references between an entity's numbers and its area: pay as a multiple of the local median
    household income, revenue per resident, the budget as a share of the area's household income, employees per
    1,000 residents. numbers: revenue, pay, pay_name, employees, awards, spent (any may be missing)."""
    out = []
    pop, inc, hh, pov = a.get("population"), a.get("median_hh_income"), a.get("households"), a.get("poverty_rate")
    where = display_name(a)
    pay = numbers.get("pay")
    if pay and inc:
        out.append({"text": f"{numbers.get('pay_name') or 'The top-paid person'} was paid {fmt(pay, 'money')}, "
                            f"{float(pay) / float(inc):,.1f} times the median household income in {where} "
                            f"({fmt(inc, 'money')})" + (f", where {fmt(pov, 'pct')} of residents live in poverty" if pov is not None else "")
                            + ".", "value": float(pay) / float(inc), "kind": "pay_vs_income"})
    rev = numbers.get("revenue")
    if rev and pop:
        out.append({"text": f"Revenue of {fmt(rev, 'money')} is {fmt(float(rev) / float(pop), 'money')} per resident of "
                            f"{where} (population {fmt(pop, 'num')}).", "value": float(rev) / float(pop), "kind": "revenue_per_resident"})
    if rev and inc and hh:
        total_income = float(inc) * float(hh)
        if total_income > 0:
            out.append({"text": f"That revenue equals {100 * float(rev) / total_income:.2f}% of all household income in "
                                f"{where} ({fmt(hh, 'num')} households at the median {fmt(inc, 'money')}, about "
                                f"{fmt(total_income, 'money')}).", "value": 100 * float(rev) / total_income, "kind": "revenue_vs_income"})
    emp = numbers.get("employees")
    if emp and pop:
        out.append({"text": f"{fmt(emp, 'num')} employees is {1000 * float(emp) / float(pop):,.1f} per 1,000 residents of {where}.",
                    "value": 1000 * float(emp) / float(pop), "kind": "employees_per_1000"})
    awards = numbers.get("awards")
    if awards and pop:
        out.append({"text": f"Federal awards of {fmt(awards, 'money')} come to {fmt(float(awards) / float(pop), 'money')} "
                            f"per resident of {where}.", "value": float(awards) / float(pop), "kind": "awards_per_resident"})
    spent = numbers.get("spent")
    if spent and inc:
        out.append({"text": f"Lobbying spending of {fmt(spent, 'money')} is {float(spent) / float(inc):,.0f} times the "
                            f"median household income in {where}.", "value": float(spent) / float(inc), "kind": "spent_vs_income"})
    return out


# --- an entity's area (the "The area" section) ----------------------------------------------------------------------------

@ttl_lru(ttl=600, maxsize=8192)
def link_for(kind: str, key: str) -> dict | None:
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('census_links') AS t").fetchone()["t"]:
                return None
            r = conn.execute("SELECT * FROM census_links WHERE kind = %s AND key = %s", (kind, str(key))).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return dict(r) if r else None


def link_for_address(zip5: str | None, city: str | None, state: str | None) -> dict | None:
    """The same link computed on the fly from an address (records not in census_links: registry entities,
    people's own addresses...)."""
    from app.geo import place_norm
    st = (state or "").strip().upper()[:2]
    z = (re.match(r"\s*(\d{5})", str(zip5 or "")) or [None, None])[1]
    if not ready() or not (st or z):
        return None
    out = {"kind": "address", "key": None, "state": st or None, "zip5": z, "city": city, "state_gj": None, "county_gj": None,
           "place_gj": None, "tract_gj": None, "how": None}
    try:
        with db.conn() as conn:
            if st:
                r = conn.execute("SELECT gisjoin FROM census_area WHERE level = 'state' AND stusab = %s", (st,)).fetchone()
                out["state_gj"] = r["gisjoin"] if r else None
            if z:
                r = conn.execute("SELECT gisjoin FROM census_zip_county WHERE zip5 = %s AND dominant", (z,)).fetchone()
                out["county_gj"] = r["gisjoin"] if r else None
                r = conn.execute("SELECT gisjoin FROM census_zip_tract WHERE zip5 = %s AND dominant", (z,)).fetchone()
                out["tract_gj"] = r["gisjoin"] if r else None
            if city and st:
                r = conn.execute("""SELECT a.gisjoin, a.county_fips, a.state_fips FROM geo_places gp
                                    JOIN census_area a ON a.level = 'place' AND a.gisjoin = 'G' || left(gp.geoid, 2) || '0' || substr(gp.geoid, 3)
                                    WHERE gp.state = %s AND gp.place_norm = %s""", (st, place_norm(city))).fetchone()
                if r:
                    out["place_gj"] = r["gisjoin"]
                    if not out["county_gj"] and r["county_fips"]:
                        out["county_gj"] = gisjoin("county", r["state_fips"] + r["county_fips"])
    except Exception:  # noqa: BLE001
        log.exception("census: address lookup")
        return None
    out["how"] = ("zip+city" if out["county_gj"] and out["place_gj"] and z else "zip" if z and out["county_gj"]
                  else "city" if out["place_gj"] else "state" if out["state_gj"] else None)
    return out if out["how"] else None


def section(kind: str, key=None, zip5: str | None = None, city: str | None = None, state: str | None = None,
            numbers: dict | None = None, map: bool = True) -> dict | None:
    """Everything the "The area" section of an entity page needs: the areas it sits in (finest first), the facts
    at each level, the cross-reference comparisons and a locator map. None when nothing can be placed."""
    if not PUBLIC or not ready():
        return None
    try:
        link = link_for(kind, str(key)) if key is not None else None
        if not link:
            link = link_for_address(zip5, city, state)
        if not link:
            return None
        levels = [(lv, area(link.get(LEVEL_COL[lv]))) for lv in ("tract", "place", "county", "state")]
        levels = [(lv, a) for lv, a in levels if a]
        if not levels:
            return None
        finest = levels[0]
        loaded = loaded_measures()
        cols = [{"level": lv, "label": LEVEL_LABEL[lv], "area": a, "url": url_for(a), "name": display_name(a)} for lv, a in levels]
        rows = []
        for group, keys in FACT_GROUPS:
            for k in keys:
                if k not in loaded:
                    continue
                info = MEASURE_INFO[k]
                rows.append({**info, "vals": [{"v": a.get(k), "url": census_gov_url(a, info["table"])} for _, a in levels]})
        comp_area = next((a for lv, a in levels if lv in ("place", "county")), finest[1])
        comps = compare(comp_area, numbers or {}) if numbers else []
        locator = None
        if map:
            from app import census_map
            county = next((a for lv, a in levels if lv == "county"), None)
            cshape = census_map.shape(county["gisjoin"]) if county else None
            pshape = census_map.shape(link["place_gj"]) if link.get("place_gj") else None
            tshape = census_map.shape(link["tract_gj"]) if link.get("tract_gj") else None
            pt = None
            if link.get("zip5"):
                with db.conn() as conn:
                    z = conn.execute("SELECT lon, lat FROM geo_zips WHERE zip5 = %s", (link["zip5"],)).fetchone()
                pt = (z["lon"], z["lat"]) if z else None
            locator = census_map.locator(cshape, pshape, tshape, pt) if cshape else None
        how = {"zip+city": "placed by its ZIP code (county and tract) and city name (place)",
               "zip": "placed by its ZIP code", "city": "placed by its city name",
               "state": "placed by its state only"}.get(link.get("how"), "")
        return {"finest": finest[1], "finest_level": finest[0], "finest_url": url_for(finest[1]),
                "finest_name": display_name(finest[1]), "cols": cols, "rows": rows, "compare": comps, "map": locator,
                "how": how, "tract_note": TRACT_NOTE if finest[0] == "tract" else None, "link": link,
                "missing": [MEASURE_INFO[k]["label"] for k in ("median_hh_income", "poverty_rate", "bachelors_share",
                                                                "median_home_value") if k not in loaded]}
    except Exception:  # noqa: BLE001 - an extra section; never fail the page
        log.exception("census: section %s %s", kind, key)
        return None


def org_numbers(ein: str) -> dict:
    """The figures an organization page compares with its area: latest revenue and employees, the top-paid person."""
    out = {}
    try:
        with db.conn() as conn:
            o = conn.execute("SELECT latest_total_revenue, latest_num_employees FROM organizations WHERE ein = %s", (ein,)).fetchone()
            if o:
                out = {"revenue": o["latest_total_revenue"], "employees": o["latest_num_employees"]}
            p = conn.execute("""SELECT name_raw, coalesce(comp_org, 0) + coalesce(comp_related, 0) + coalesce(other_comp, 0) AS total
                                FROM people WHERE ein = %s AND NOT is_duplicate
                                  AND tax_year = (SELECT max(tax_year) FROM people WHERE ein = %s AND NOT is_duplicate)
                                ORDER BY 2 DESC LIMIT 1""", (ein, ein)).fetchone()
            if p and p["total"]:
                out.update({"pay": p["total"], "pay_name": p["name_raw"]})
    except Exception:  # noqa: BLE001
        pass
    return out


def person_section(cluster_id: int) -> dict | None:
    """A person's area: through the organization of their latest filing, with their pay against its median income."""
    if not PUBLIC or not ready():
        return None
    try:
        with db.conn() as conn:
            r = conn.execute("""SELECT p.ein, p.name_raw, p.tax_year,
                                       coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total
                                FROM people p JOIN person_cluster_members m ON m.person_id = p.id
                                WHERE m.cluster_id = %s AND NOT p.is_duplicate ORDER BY p.tax_year DESC, total DESC LIMIT 1""",
                             (cluster_id,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not r:
        return None
    s = section("org", r["ein"], numbers={"pay": r["total"], "pay_name": r["name_raw"]} if r["total"] else None)
    if s:
        s["via_org"] = r["ein"]
    return s


# --- lookups for search and the API -----------------------------------------------------------------------------------

STATE_NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
               "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
               "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
               "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
               "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
               "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
               "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
               "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
               "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico"}
_STATE_BY_NAME = {v.lower(): k for k, v in STATE_NAMES.items()}


def state_code(s: str | None) -> str | None:
    s = (s or "").strip()
    if _ST.match(s) and s.upper() in STATE_NAMES:
        return s.upper()
    return _STATE_BY_NAME.get(s.lower())


def lookup(q: str, state: str | None = None, limit: int = 10) -> list[dict]:
    """Areas by name: "Austin, TX", "Cook County", "Texas", a ZIP, an 11-digit tract GEOID."""
    q = (q or "").strip()[:120]
    if not q or not ready():
        return []
    m = _ZIP.match(q)
    if m:
        with db.conn() as conn:
            rows = conn.execute("""SELECT a.* FROM census_zip_county zc JOIN census_area a ON a.gisjoin = zc.gisjoin
                                   WHERE zc.zip5 = %s ORDER BY zc.share DESC LIMIT %s""", (m.group(1), limit)).fetchall()
        return [dict(r) for r in rows]
    if _GEOID.match(q):
        a = find("tract", geoid=q)
        return [a] if a else []
    st = state_code(state)
    name = q
    m = re.match(r"^(.+?)[,\s]+([A-Za-z]{2}|[A-Za-z ]{4,20})$", q)
    if m and state_code(m.group(2)):
        name, st = m.group(1).strip(" ,"), state_code(m.group(2))
    if not st and state_code(name):
        a = find("state", state_code(name), state_code(name).lower())
        return [a] if a else []
    from app.geo import place_norm
    norm = place_norm(name)
    county = re.sub(r"\s+(county|parish|borough|census area|municipio)$", "", name.strip(), flags=re.I)
    with db.conn(timeout="10s") as conn:
        rows = conn.execute("""
            SELECT a.*, CASE WHEN a.level = 'county' THEN 0 ELSE 1 END AS lv
            FROM census_area a
            WHERE a.level IN ('county', 'place') AND (%(st)s::text IS NULL OR a.stusab = %(st)s)
              AND (a.slug = %(slug)s OR (a.level = 'county' AND lower(a.short_name) IN (%(cty)s, %(cty)s || ' county', %(cty)s || ' parish'))
                   OR (a.level = 'place' AND census_city_norm(a.short_name) = %(norm)s)
                   OR (a.level = 'county' AND census_city_norm(a.short_name) = %(norm)s))
            ORDER BY (a.slug = %(slug)s) DESC, a.population DESC NULLS LAST LIMIT %(lim)s""",
            {"st": st, "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), "cty": county.lower(), "norm": norm,
             "lim": limit}).fetchall()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    # One exact match by slug in a named state is the answer ("Austin, TX" is Austin city, not Austin County).
    return [{**dict(r), "exact": bool(st) and r["slug"] == slug and r["level"] == "place"} for r in rows]


def area_out(a: dict, with_records: bool = True) -> dict:
    """An area for the JSON API and MCP: facts, each with its table, and the FURP records in it."""
    from app.public_api import SITE_URL
    loaded = loaded_measures()
    p = parents(a)
    out = {"name": display_name(a), "level": a["level"], "gisjoin": a["gisjoin"], "geoid": a["geoid"], "state": a["stusab"],
           "url": SITE_URL + (url_for(a) or ""), "state_url": SITE_URL + url_for(p["state"]) if p["state"] else None,
           "county": display_name(p["county"]) if p["county"] else (a["short_name"] if a["level"] == "county" else None),
           "county_url": SITE_URL + url_for(p["county"]) if p["county"] else None,
           "facts": {k: {"value": float(a[k]) if a.get(k) is not None else None, "label": MEASURE_INFO[k]["label"],
                         "unit": MEASURE_INFO[k]["fmt"], "table": MEASURE_INFO[k]["table"],
                         "table_url": census_gov_url(a, MEASURE_INFO[k]["table"])}
                     for k in MEASURE_INFO if k in loaded},
           "measures_not_loaded_yet": [MEASURE_INFO[k]["label"] for k in MEASURE_INFO if k not in loaded],
           "source": SOURCE, "citation": CITATION}
    if with_records:
        out["furp_records"] = [{"kind": s["kind"], "label": s["label"], "count": s["n"], "total": float(s["total"]) if s["total"] else None,
                                "biggest": {"name": s["top_name"], "url": SITE_URL + s["top_url"] if s["top_url"] else None,
                                            "value": float(s["top_value"]) if s["top_value"] else None}}
                               for s in furp_summary(a["gisjoin"])]
        out["top_nonprofits"] = [{"name": r["name"], "city": r["city"], "revenue": float(r["value"]) if r["value"] else None,
                                  "url": SITE_URL + r["url"]} for r in furp_top(a["gisjoin"], a["level"], "org")]
        out["highest_paid_people"] = [{"name": r["name"], "title": r["title"], "organization": r["org_name"], "year": r["tax_year"],
                                       "pay": float(r["total"]), "url": SITE_URL + f"/person/{r['cluster_id']}",
                                       "pay_vs_median_household_income": round(float(r["total"]) / float(a["median_hh_income"]), 1)
                                       if a.get("median_hh_income") else None}
                                      for r in top_people(a["gisjoin"], a["level"])]
    return out


def api_area(q: str | None = None, zip5: str | None = None, city: str | None = None, state: str | None = None,
             gisjoin_: str | None = None) -> dict:
    """The JSON API's area lookup: by GISJOIN, ZIP, city and state, or a free-text name."""
    if not PUBLIC or not ready():
        raise HTTPException(503, "the census tables are still loading; try again later")
    a = None
    if gisjoin_:
        a = area(gisjoin_)
    elif zip5 or (city and state):
        link = link_for_address(zip5, city, state)
        if link:
            for lv in ("place", "county", "state") if city else ("county", "state"):
                a = area(link.get(LEVEL_COL[lv]))
                if a:
                    break
    elif q:
        hits = lookup(q, state)
        a = hits[0] if hits else None
    if not a:
        raise HTTPException(404, "no such area; pass a ZIP, a city and state, a county or place name, or a GISJOIN")
    return area_out(a)


def api_search(q: str, limit: int = 10) -> list[dict]:
    """Dataset search for app/public_api.py: areas by name, each with its URL."""
    from app.public_api import SITE_URL
    return [{"name": display_name(a), "level": a["level"], "state": a["stusab"], "gisjoin": a["gisjoin"],
             "population": float(a["population"]) if a.get("population") else None, "url": SITE_URL + url_for(a)}
            for a in lookup(q, limit=limit)]


def entity_area(kind: str, key) -> dict | None:
    """The API's census_area block on a profile: the finest area the record was placed in, with the facts."""
    if not PUBLIC or not ready():
        return None
    link = link_for(kind, str(key))
    if not link:
        return None
    for lv in ("place", "county", "state"):
        a = area(link.get(LEVEL_COL[lv]))
        if a:
            out = area_out(a, with_records=False)
            out["placed_by"] = link.get("how")
            t = area(link.get("tract_gj")) if link.get("tract_gj") else None
            if t:
                out["tract"] = {"geoid": t["geoid"], "name": t["name"], "note": TRACT_NOTE,
                                "facts": {k: float(t[k]) for k in ("population", "median_hh_income", "poverty_rate", "median_age")
                                          if t.get(k) is not None}}
            return out
    return None


# --- search: "median income in Cook County", "population of Austin, Texas" ----------------------------------------------

QUESTION = re.compile(r"^\s*(?:what(?:'s| is| are| was)\s+(?:the\s+)?)?(?P<m>population|people|residents|median (?:household |family )?"
                      r"income|household income|income|poverty(?: rate)?|median age|age|median home value|home values?|"
                      r"median rent|rents?|education|bachelor'?s|unemployment(?: rate)?|census|demographics|census data|"
                      r"census facts|race|ethnicity|renters?|homeowners?)\s+(?:of|in|for|at)\s+(?P<place>[^?]+?)\s*\??\s*$", re.I)
MEASURE_WORDS = {"population": "population", "people": "population", "residents": "population", "income": "median_hh_income",
                 "household income": "median_hh_income", "median income": "median_hh_income", "median household income": "median_hh_income",
                 "median family income": "median_family_income", "poverty": "poverty_rate", "poverty rate": "poverty_rate",
                 "median age": "median_age", "age": "median_age", "median home value": "median_home_value", "home value": "median_home_value",
                 "home values": "median_home_value", "median rent": "median_rent", "rent": "median_rent", "rents": "median_rent",
                 "education": "bachelors_share", "bachelor's": "bachelors_share", "bachelors": "bachelors_share",
                 "unemployment": "unemployment_rate", "unemployment rate": "unemployment_rate", "renters": "renter_share",
                 "renter": "renter_share", "homeowners": "owner_share", "homeowner": "owner_share", "race": "white_share",
                 "ethnicity": "hispanic_share"}


def question(q: str) -> dict | None:
    """A census question as an intent for app/ask.py, or None."""
    if not PUBLIC:
        return None
    m = QUESTION.match(q or "")
    if not m:
        return None
    measure = MEASURE_WORDS.get(m.group("m").lower().replace("’", "'"))
    return {"intent": "census_area", "place": m.group("place").strip(" ,"), "measure": measure}


def answer(intent: dict) -> dict:
    """The search result for a census question: the area, its facts and the FURP records in it."""
    hits = lookup(intent.get("place") or "", intent.get("state"))
    if not hits:
        return {"kind": "none"}
    a = hits[0]
    return {"kind": "census", "area": a, "url": url_for(a), "facts": facts(a), "measure": intent.get("measure"),
            "summary": furp_summary(a["gisjoin"]), "top_orgs": furp_top(a["gisjoin"], a["level"], "org", 10),
            "people": top_people(a["gisjoin"], a["level"], 10), "others": hits[1:6], "total": 1, "name": display_name(a)}


def place_facts(city: str | None, state: str | None) -> dict | None:
    """For an organizations-in-a-place search result: the place's (or state's) headline facts, in one line."""
    if not PUBLIC or not ready() or not (state or city):
        return None
    try:
        a = None
        if city and state:
            link = link_for_address(None, city, state)
            a = area(link["place_gj"]) if link and link.get("place_gj") else None
        if not a and state and state_code(state):
            a = find("state", state_code(state), state_code(state).lower())
        if not a:
            return None
        loaded = loaded_measures()
        keys = [k for k in ("population", "median_hh_income", "poverty_rate", "median_age", "bachelors_share") if k in loaded]
        return {"area": a, "name": display_name(a), "url": url_for(a), "summary": furp_summary(a["gisjoin"]),
                "lines": [{"label": MEASURE_INFO[k]["label"], "value": fmt(a.get(k), MEASURE_INFO[k]["fmt"]),
                           "url": census_gov_url(a, MEASURE_INFO[k]["table"])} for k in keys if a.get(k) is not None]}
    except Exception:  # noqa: BLE001
        return None


# --- the Browse entries ----------------------------------------------------------------------------------------------------

def more_group() -> list[dict]:
    if not PUBLIC:
        return []
    return [{"title": "Places and the census", "links": [
        ("/census", "Census: every state, county, city and tract", "population, income, poverty, housing and more from IPUMS NHGIS, "
                                                                   "with the nonprofits, people, contractors and other FURP records in each place"),
        ("/census/area", "Find an area by ZIP or city", ""),
        ("/boards/census-revenue-per-resident", "Counties with the most nonprofit revenue per resident", ""),
        ("/boards/census-nonprofits-per-10k", "Counties with the most nonprofits per 10,000 residents", ""),
        ("/boards/census-pay-vs-income", "Nonprofit pay against the local median income", ""),
        ("/boards/census-poor-counties-rich-nonprofits", "High-poverty counties with big nonprofits", ""),
        ("/boards/census-places-revenue-per-resident", "Cities with the most nonprofit revenue per resident", ""),
        ("/boards/census-federal-per-resident", "Counties with the most federal money per resident", ""),
        ("/census/tables", "The census tables loaded", "")]}]


# --- pages -----------------------------------------------------------------------------------------------------------------

def _measure(request: Request) -> str:
    m = (request.query_params.get("m") or DEFAULT_MEASURE).strip()
    return m if m in MEASURE_INFO and m != "pop2020" else DEFAULT_MEASURE


def _kind(request: Request) -> str:
    k = (request.query_params.get("k") or "org").strip()
    return k if k in KINDS else "org"


def _map_ctx(request: Request, features: list[dict], areas: list[dict], us: bool, pts: list[dict] | None = None,
             labels: dict | None = None, highlight: set | None = None) -> dict:
    """The choropleth for a page: the measure chosen (?m=), the values and links per area."""
    from app import census_map
    m = _measure(request)
    info = MEASURE_INFO[m]
    by = {a["gisjoin"]: a for a in areas}
    values = {gj: (float(a[m]) if a.get(m) is not None else None) for gj, a in by.items()}
    links = {gj: url_for(a) for gj, a in by.items()}
    loaded = loaded_measures()
    svg = census_map.render(features, values if m in loaded else {}, info["fmt"], links, us=us, points=pts,
                            legend=info["label"] + (f" ({ACS_LABEL})" if m in loaded else " (not loaded yet)"),
                            labels=labels, highlight=highlight, point_label=KINDS[_kind(request)][0].lower())
    choices = [(k, MEASURE_INFO[k]["label"]) for k in MAP_MEASURES if k in loaded]
    return {"map_svg": svg, "measure": m, "measure_info": info, "measure_choices": choices, "map_kind": _kind(request),
            "kind_choices": [(k, v[0]) for k, v in KINDS.items() if k not in ("biz", "fec_committee")]}


def _common(request: Request) -> dict:
    return {"loaded": loaded_measures(), "ready": ready(), "source": SOURCE, "citation": CITATION, "citation_url": CITATION_URL,
            "kinds": KINDS, "measure_catalog": MEASURE_INFO, "fact_groups": FACT_GROUPS}


@router.get("/census", response_class=HTMLResponse)
def census_index(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    from app import census_map
    sts = states()
    feats = census_map.shapes("state") if sts else []
    ctx = _map_ctx(request, feats, sts, us=True) if feats else {"map_svg": "", "measure": DEFAULT_MEASURE,
                                                                 "measure_info": MEASURE_INFO[DEFAULT_MEASURE], "measure_choices": [],
                                                                 "map_kind": "org", "kind_choices": []}
    summary = {}
    try:
        with db.conn() as conn:
            if conn.execute("SELECT to_regclass('census_area_furp') AS t").fetchone()["t"]:
                summary = {(r["gisjoin"]): r for r in conn.execute(
                    "SELECT f.gisjoin, f.n, f.total FROM census_area_furp f JOIN census_area a USING (gisjoin) "
                    "WHERE a.level = 'state' AND f.kind = 'org'").fetchall()}
    except Exception:  # noqa: BLE001
        summary = {}
    rows = [{**s, "url": url_for(s), "orgs": (summary.get(s["gisjoin"]) or {}).get("n"),
             "org_revenue": (summary.get(s["gisjoin"]) or {}).get("total")} for s in sts]
    return _render(request, "census.html", states=rows, tables=tables_loaded(), **ctx, **_common(request))


@router.get("/census/tables", response_class=HTMLResponse)
def census_tables(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    return _render(request, "census_tables.html", tables=tables_loaded(), measures=[MEASURE_INFO[m[0]] for m in MEASURES],
                   **_common(request))


@router.get("/census/area", response_class=HTMLResponse)
def census_area_lookup(request: Request, q: str = Query("", max_length=120), zip: str = Query("", max_length=10),
                       city: str = Query("", max_length=80), state: str = Query("", max_length=30)):
    """Find an area: a ZIP, "City, ST", a county, a state. One hit goes straight to its page."""
    if not PUBLIC:
        raise HTTPException(404)
    hits = []
    if zip.strip() or (city.strip() and state.strip()):
        link = link_for_address(zip.strip() or None, city.strip() or None, state.strip() or None)
        if link:
            for lv in ("place", "county", "state") if city.strip() else ("county", "state"):
                a = area(link.get(LEVEL_COL[lv]))
                if a:
                    hits = [a]
                    break
    elif q.strip():
        hits = lookup(q, state or None, 25)
    if hits and (q or zip or city) and (len(hits) == 1 or hits[0].get("exact")):
        return RedirectResponse(url_for(hits[0]), status_code=302)
    return _render(request, "census_area.html", q=q, zip=zip, city=city, state=state, hits=hits, url_for=url_for,
                   display_name=display_name, **_common(request))


def _state_or_404(st: str) -> dict:
    if not PUBLIC or not _ST.match(st or ""):
        raise HTTPException(404)
    a = find("state", st.upper(), st.lower())
    if not a:
        raise HTTPException(404)
    return a


def _records(a: dict) -> dict:
    """The FURP records sections of an area page."""
    summary = furp_summary(a["gisjoin"])
    tops = {s["kind"]: furp_top(a["gisjoin"], a["level"], s["kind"]) for s in summary if s["kind"] != "biz"}
    return {"summary": summary, "tops": tops, "people": top_people(a["gisjoin"], a["level"]),
            "facts": facts(a), "parents": parents(a)}


@router.get("/census/map", include_in_schema=False)
def census_us_map(request: Request):
    if not PUBLIC:
        raise HTTPException(404)
    from app import census_map
    return _export(request, census_map.shapes("state"), states(), "United States", "/census")


@router.get("/census/{st}", response_class=HTMLResponse)
def census_state(request: Request, st: str):
    a = _state_or_404(st)
    from app import census_map
    counties = children("county", a["state_fips"])
    feats = census_map.shapes("county", a["state_fips"])
    pts = points(a["gisjoin"], "state", _kind(request))
    ctx = _map_ctx(request, feats, counties, us=False, pts=pts)
    places = children("place", a["state_fips"], limit=50, order="population")
    return _render(request, "census_state.html", a=a, counties=counties, places=places, url_for=url_for,
                   display_name=display_name, fmt=fmt, place_short=place_short, **_records(a), **ctx, **_common(request))


@router.get("/census/{st}/map", include_in_schema=False)
def census_state_map(request: Request, st: str):
    a = _state_or_404(st)
    from app import census_map
    return _export(request, census_map.shapes("county", a["state_fips"]), children("county", a["state_fips"]),
                   f"{a['name']} counties", f"/census/{st.lower()}")


@router.get("/census/tract/{geoid}", response_class=HTMLResponse)
def census_tract(request: Request, geoid: str):
    if not PUBLIC or not _GEOID.match(geoid):
        raise HTTPException(404)
    a = find("tract", geoid=geoid)
    if not a:
        raise HTTPException(404)
    from app import census_map
    county = parents(a)["county"]
    feats = census_map.shapes("tract", a["state_fips"], a["county_fips"])
    tracts = children("tract", a["state_fips"], a["county_fips"])
    ctx = _map_ctx(request, feats, tracts, us=False, highlight={a["gisjoin"]})
    return _render(request, "census_tract.html", a=a, county=county, url_for=url_for, display_name=display_name, fmt=fmt,
                   tract_note=TRACT_NOTE, **_records(a), **ctx, **_common(request))


@router.get("/census/tract/{geoid}/map", include_in_schema=False)
def census_tract_map(request: Request, geoid: str):
    if not PUBLIC or not _GEOID.match(geoid):
        raise HTTPException(404)
    a = find("tract", geoid=geoid)
    if not a:
        raise HTTPException(404)
    from app import census_map
    return _export(request, [s for s in [census_map.shape(a["gisjoin"])] if s], [a], a["name"], f"/census/tract/{geoid}")


@router.get("/census/{st}/place/{slug}", response_class=HTMLResponse)
def census_place(request: Request, st: str, slug: str):
    state = _state_or_404(st)
    if not _SLUG.match(slug):
        raise HTTPException(404)
    a = find("place", st.upper(), slug)
    if not a:
        raise HTTPException(404)
    from app import census_map
    p = parents(a)
    feats = [s for s in [census_map.shape(a["gisjoin"])] if s]
    pts = points(a["gisjoin"], "place", _kind(request))
    ctx = _map_ctx(request, feats, [a], us=False, pts=pts)
    return _render(request, "census_place.html", a=a, state=state, county=p["county"], url_for=url_for, display_name=display_name,
                   fmt=fmt, place_short=place_short, **_records(a), **ctx, **_common(request))


@router.get("/census/{st}/place/{slug}/map", include_in_schema=False)
def census_place_map(request: Request, st: str, slug: str):
    _state_or_404(st)
    a = find("place", st.upper(), slug) if _SLUG.match(slug) else None
    if not a:
        raise HTTPException(404)
    from app import census_map
    return _export(request, [s for s in [census_map.shape(a["gisjoin"])] if s], [a], display_name(a),
                   f"/census/{st.lower()}/place/{slug}")


@router.get("/census/{st}/{slug}", response_class=HTMLResponse)
def census_county(request: Request, st: str, slug: str):
    state = _state_or_404(st)
    if not _SLUG.match(slug):
        raise HTTPException(404)
    a = find("county", st.upper(), slug)
    if not a:
        raise HTTPException(404)
    from app import census_map
    tracts = children("tract", a["state_fips"], a["county_fips"])
    feats = census_map.shapes("tract", a["state_fips"], a["county_fips"])
    places = children("place", a["state_fips"], a["county_fips"], order="population")
    labels = {p["gisjoin"]: place_short(p["short_name"]) for p in places[:12]}
    pts = points(a["gisjoin"], "county", _kind(request))
    # Places as labels over the tracts: their internal points are in census_area (lat, lon).
    place_feats = [{"gisjoin": p["gisjoin"], "name": p["name"], "lon": p["lon"], "lat": p["lat"], "geom": []} for p in places[:12]
                   if p.get("lon") is not None]
    ctx = _map_ctx(request, feats + place_feats, tracts, us=False, pts=pts, labels=labels)
    tracts_top = sorted(tracts, key=lambda t: -(t["population"] or 0))[:300]
    return _render(request, "census_county.html", a=a, state=state, tracts=tracts, tracts_top=tracts_top, places=places, url_for=url_for,
                   display_name=display_name, fmt=fmt, place_short=place_short, **_records(a), **ctx, **_common(request))


@router.get("/census/{st}/{slug}/map", include_in_schema=False)
def census_county_map(request: Request, st: str, slug: str):
    _state_or_404(st)
    a = find("county", st.upper(), slug) if _SLUG.match(slug) else None
    if not a:
        raise HTTPException(404)
    from app import census_map
    return _export(request, census_map.shapes("tract", a["state_fips"], a["county_fips"]),
                   children("tract", a["state_fips"], a["county_fips"]), display_name(a), f"/census/{st.lower()}/{slug}")


def _export(request: Request, features: list[dict], areas: list[dict], name: str, page_path: str) -> Response:
    """The map export: GeoJSON polygons with the measures as properties, or a CSV with each area's center point
    and measures (Datawrapper, Google My Maps and Mapshaper take both), as app/geo.py does for record lists."""
    import datetime as dt
    import json
    from app import census_map, geo
    from app.config import SITE_URL
    fmt_ = (request.query_params.get("format") or "csv").lower()
    loaded = loaded_measures()
    cols = ["pop2020"] + [m[0] for m in MEASURES]
    props = {a["gisjoin"]: {"url": SITE_URL + (url_for(a) or ""), "level": a["level"], "state": a["stusab"],
                            **{c: (float(a[c]) if a.get(c) is not None else None) for c in cols if c in loaded}} for a in areas}
    today = dt.date.today().isoformat()
    source = f"furp.org, {SITE_URL}{page_path}, retrieved {today}; data: IPUMS NHGIS ({CITATION_URL}), outlines: Census TIGER/Line 2026"
    safe = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "census"
    if fmt_ == "geojson":
        fc = census_map.geojson(features, props)
        fc["metadata"] = {"source": source, "areas": len(features), "measures": [c for c in cols if c in loaded]}
        return Response(json.dumps(fc, default=str), media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="furp-census-{safe}-{today}.geojson"'})
    rows = [{"name": a["name"], "level": a["level"], "state": a["stusab"], "geoid": a["geoid"], "gisjoin": a["gisjoin"],
             "url": props[a["gisjoin"]]["url"], **{c: props[a["gisjoin"]].get(c) for c in cols if c in loaded},
             "latitude": a.get("lat"), "longitude": a.get("lon")} for a in areas]
    fields = ["name", "level", "state", "geoid", "gisjoin", "url"] + [c for c in cols if c in loaded] + ["latitude", "longitude", "source"]
    return Response(geo.to_csv(rows, fields, source), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="furp-census-{safe}-map-{today}.csv"'})


def person_area(cluster_id: int) -> dict | None:
    """The API's census_area block on a person's profile: through the organization of their latest filing, with
    their pay as a multiple of that area's median household income."""
    if not PUBLIC or not ready():
        return None
    try:
        with db.conn() as conn:
            r = conn.execute("""SELECT p.ein, p.tax_year,
                                       coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total
                                FROM people p JOIN person_cluster_members m ON m.person_id = p.id
                                WHERE m.cluster_id = %s AND NOT p.is_duplicate ORDER BY p.tax_year DESC, total DESC LIMIT 1""",
                             (cluster_id,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    if not r:
        return None
    out = entity_area("org", r["ein"])
    if out:
        out["via_organization_ein"] = r["ein"]
        inc = (out.get("facts") or {}).get("median_hh_income", {}).get("value")
        if r["total"] and inc:
            out["pay_vs_median_household_income"] = {"pay": float(r["total"]), "year": r["tax_year"],
                                                    "multiple": round(float(r["total"]) / inc, 1)}
    return out
