"""FRED on the pages (owner, 2026-11-13): the "Economy now" block for a census area (county or state: latest
unemployment rate and the year-earlier figure, per capita personal income with its five-year change, population
trend, house price index change, each linking to its FRED series page, with a ten-year sparkline of the unemployment
rate), the same in compact form inside "The area" section of entity pages (app/census.py section()), the deflator
real_dollars() on CPI-U annual averages, the JSON for the API and MCP, and the dataset search.

Data: loader/fred.py (schema fred). Attribution required by FRED's terms: ATTRIBUTION, with links to each series."""

from __future__ import annotations

import datetime as dt
import logging
import os
from html import escape

from app import db
from app.cache import ttl_lru

log = logging.getLogger(__name__)
PUBLIC = os.environ.get("FRED_PUBLIC", "1") == "1"
SOURCE_NAME = "FRED, Federal Reserve Bank of St. Louis"
SOURCE_URL = "https://fred.stlouisfed.org/"
TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"
ATTRIBUTION = "Source: FRED, Federal Reserve Bank of St. Louis"
SOURCE = ("Economic figures are from FRED, the Federal Reserve Bank of St. Louis's data service, which republishes "
          "the Bureau of Labor Statistics (unemployment, CPI), the Bureau of Economic Analysis (personal income, GDP), the "
          "Census Bureau (population, SAIPE income and poverty) and the Federal Housing Finance Agency (house price "
          "index). Each figure links to its FRED series page. This product uses the FRED API but is not endorsed or "
          "certified by the Federal Reserve Bank of St. Louis.")
SPARK_YEARS = 10

# The block's rows, in order: kind -> label, format, the unit note, the shorter label for the compact form.
# fmt: pct (a rate), money, people (FRED's thousands of persons), index, money_m (millions of dollars), money_k.
ROWS = [
    ("unemployment_rate", "Unemployment rate", "pct", "monthly, not seasonally adjusted", "unemployment"),
    ("per_capita_income", "Per capita personal income", "money", "annual, BEA", "per capita personal income"),
    ("median_hh_income", "Median household income", "money", "annual, Census SAIPE estimate", None),
    ("poverty_rate", "Poverty rate", "pct", "annual, Census SAIPE estimate", None),
    ("population", "Population", "persons", "annual, Census estimate", "population"),
    ("hpi", "House price index", "index", "all-transactions, FHFA; county: annual, state: quarterly", "house prices"),
    ("gdp", "GDP", "money_big", "annual, BEA (current dollars)", None),
    ("labor_force", "Labor force", "persons", "monthly, not seasonally adjusted", None),
    ("min_wage", "State minimum wage", "money_hour", "annual, dollars an hour", None),
]
ROW_INFO = {k: {"kind": k, "label": label, "fmt": fmt, "note": note, "short": short} for k, label, fmt, note, short in ROWS}
COMPACT_KINDS = ["unemployment_rate", "per_capita_income"]
DELTA_FMT = {"pct": "points", "index": "pct", "money": "pct", "people": "pct", "persons": "pct", "money_k": "pct",
             "money_big": "pct", "money_hour": "pct"}
SCALED = ("money_big", "persons")        # FRED states these in thousands, millions or billions: units_short says which


def unit_scale(units_short: str | None) -> float:
    u = (units_short or "").lower()
    if u.startswith("bil"):
        return 1e9
    if u.startswith("mil"):
        return 1e6
    if u.startswith("thous"):
        return 1e3
    return 1.0


# --- what is loaded ---------------------------------------------------------------------------------------------------

@ttl_lru(ttl=300)
def ready() -> bool:
    if not PUBLIC:
        return False
    try:
        with db.conn() as conn:
            ok = conn.execute("SELECT to_regclass('fred.area_latest') IS NOT NULL AS ok").fetchone()["ok"]
            return bool(ok and conn.execute("SELECT 1 FROM fred.series LIMIT 1").fetchone())
    except Exception:  # noqa: BLE001 - never fail a page over an extra block
        log.exception("fred: ready")
        return False


@ttl_lru(ttl=600, maxsize=4)
def summary() -> dict:
    """Series and observation counts (the data page and the API)."""
    try:
        with db.conn() as conn:
            rows = conn.execute("SELECT geo_level, count(*) AS n, max(observation_end) AS last FROM fred.series GROUP BY 1").fetchall()
            obs = conn.execute("SELECT count(*) AS n, max(date) AS last FROM fred.observations").fetchone()
        return {"series": {r["geo_level"]: r["n"] for r in rows}, "observations": obs["n"], "last_date": str(obs["last"] or "")}
    except Exception:  # noqa: BLE001
        return {}


def series_url(series_id: str) -> str:
    return f"https://fred.stlouisfed.org/series/{series_id}"


# --- the deflator ---------------------------------------------------------------------------------------------------------

@ttl_lru(ttl=3600, maxsize=2)
def cpi_annual() -> dict[int, float]:
    """Year -> CPI-U annual average (CPIAUCSL, months averaged); past years with at least eleven months (October 2025
    was never published: the shutdown)."""
    try:
        with db.conn() as conn:
            rows = conn.execute("SELECT year, cpi FROM fred.cpi_annual WHERE months >= 11 AND year < extract(year FROM now())").fetchall()
        return {int(r["year"]): float(r["cpi"]) for r in rows}
    except Exception:  # noqa: BLE001
        return {}


def cpi_latest_year(cpi: dict[int, float] | None = None) -> int | None:
    cpi = cpi_annual() if cpi is None else cpi
    return max(cpi) if cpi else None


def real_dollars(amount, year, to_year: int | None = None, cpi: dict[int, float] | None = None):
    """`amount` of `year` dollars in `to_year` dollars (default: the latest full CPI year), on CPI-U annual averages.
    None when either year's CPI is not loaded."""
    if amount is None or year is None:
        return None
    cpi = cpi_annual() if cpi is None else cpi
    to_year = to_year or cpi_latest_year(cpi)
    try:
        return float(amount) * cpi[int(to_year)] / cpi[int(year)]
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


# --- formatting --------------------------------------------------------------------------------------------------------------

def fmt(v, kind: str) -> str:
    if v is None:
        return "-"
    v = float(v)
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "money":
        return f"${v:,.0f}"
    if kind == "money_hour":
        return f"${v:,.2f}"
    if kind == "money_k":                      # thousands of dollars
        return short_money(v * 1000)
    if kind == "money_m":
        return short_money(v * 1e6)
    if kind == "money_big":
        return short_money(v)
    if kind == "people":                       # thousands of persons
        return f"{v * 1000:,.0f}"
    if kind == "persons":
        return f"{v:,.0f}"
    if kind == "index":
        return f"{v:,.1f}"
    if kind == "points":
        return f"{v:+.1f} pt"
    if kind == "pct_change":
        return f"{v:+.1f}%"
    return f"{v:,.1f}"


def short_money(v) -> str:
    from app.fmt import short_money as sm
    return sm(v)


def period(date, frequency: str | None) -> str:
    """"Sep 2026" for a month, "2024" for a year, "Q2 2026" for a quarter, else the date."""
    if date is None:
        return ""
    if isinstance(date, str):
        date = dt.date.fromisoformat(date[:10])
    f = (frequency or "").upper()
    if f.startswith("A"):
        return str(date.year)
    if f.startswith("Q"):
        return f"Q{(date.month - 1) // 3 + 1} {date.year}"
    if f.startswith("M"):
        return date.strftime("%b %Y")
    return date.isoformat()


# --- the block ---------------------------------------------------------------------------------------------------------------

def area_gisjoin(a: dict) -> str | None:
    """The FRED-covered area for a census area: the county itself, a place's or tract's county, else the state."""
    if not a:
        return None
    if a.get("level") in ("county", "state"):
        return a["gisjoin"]
    if a.get("level") == "nation":
        return "US"
    if a.get("county_fips") and a.get("state_fips"):
        return f"G{a['state_fips']}0{a['county_fips']}0"
    if a.get("state_fips"):
        return f"G{a['state_fips']}0"
    return None


def _change(now, then, kind: str):
    if now is None or then is None:
        return None
    now, then = float(now), float(then)
    if DELTA_FMT.get(kind) == "points":
        return {"value": now - then, "fmt": "points"}
    if then == 0:
        return None
    return {"value": 100 * (now - then) / then, "fmt": "pct_change"}


def _with_level(level: str) -> str:
    return {"county": "county", "state": "state", "nation": "country"}.get(level, level)


@ttl_lru(ttl=900, maxsize=4096)
def economy(gj: str | None, level_hint: str | None = None) -> dict | None:
    """The block for one FRED area (a county or state gisjoin): rows per kind with the latest value, its period, the
    year-earlier and five-year-earlier changes, the FRED link; a ten-year sparkline of the unemployment rate."""
    if not gj or not ready():
        return None
    try:
        with db.conn() as conn:
            rows = conn.execute("""SELECT l.kind, l.series_id, l.frequency, l.date, l.value, l.value_1y, l.value_5y, l.value_10y,
                                          l.geo_level, s.title, s.units_short
                                   FROM fred.area_latest l JOIN fred.series s ON s.id = l.series_id
                                   WHERE l.gisjoin = %s""", (gj,)).fetchall()
            if not rows:
                return None
            by_kind = {r["kind"]: r for r in rows}
            spark = None
            u = by_kind.get("unemployment_rate")
            if u:
                since = (u["date"] - dt.timedelta(days=365 * SPARK_YEARS)).replace(day=1)
                pts = conn.execute("SELECT date, value FROM fred.observations WHERE series_id = %s AND date >= %s AND value IS NOT NULL "
                                   "ORDER BY date", (u["series_id"], since)).fetchall()
                spark = {"svg": sparkline([(p["date"], float(p["value"])) for p in pts], label="Unemployment rate"),
                         "from": period(pts[0]["date"], "M") if pts else None, "to": period(pts[-1]["date"], "M") if pts else None,
                         "series_id": u["series_id"], "url": series_url(u["series_id"]), "n": len(pts)}
        items = []
        cpi = cpi_annual()
        for kind, info in ROW_INFO.items():
            r = by_kind.get(kind)
            if not r or r["value"] is None:
                continue
            if info["fmt"] in SCALED:
                k = unit_scale(r["units_short"])
                r = {**r, **{c: (float(r[c]) * k if r[c] is not None else None) for c in ("value", "value_1y", "value_5y", "value_10y")}}
            item = {**info, "series_id": r["series_id"], "url": series_url(r["series_id"]), "title": r["title"],
                    "date": r["date"], "period": period(r["date"], r["frequency"]), "frequency": r["frequency"],
                    "value": float(r["value"]), "text": fmt(r["value"], info["fmt"]),
                    "value_1y": float(r["value_1y"]) if r["value_1y"] is not None else None,
                    "value_5y": float(r["value_5y"]) if r["value_5y"] is not None else None,
                    "value_10y": float(r["value_10y"]) if r["value_10y"] is not None else None,
                    "change_1y": _change(r["value"], r["value_1y"], info["fmt"]),
                    "change_5y": _change(r["value"], r["value_5y"], info["fmt"]),
                    "change_10y": _change(r["value"], r["value_10y"], info["fmt"]), "real_change_5y": None}
            if item["change_1y"]:
                item["change_1y"]["text"] = fmt(item["change_1y"]["value"], item["change_1y"]["fmt"])
                item["text_1y"] = fmt(r["value_1y"], info["fmt"])
            if item["change_5y"]:
                item["change_5y"]["text"] = fmt(item["change_5y"]["value"], item["change_5y"]["fmt"])
                item["text_5y"] = fmt(r["value_5y"], info["fmt"])
            if item["change_10y"]:
                item["change_10y"]["text"] = fmt(item["change_10y"]["value"], item["change_10y"]["fmt"])
            # Dollar figures: the five-year change after inflation (CPI-U annual averages), the deflator in use.
            if info["fmt"] in ("money", "money_k", "money_big", "money_hour") and r["value_5y"] is not None and cpi:
                then_real = real_dollars(r["value_5y"], r["date"].year - 5, r["date"].year, cpi)
                if then_real:
                    item["real_change_5y"] = {"value": 100 * (float(r["value"]) - then_real) / then_real, "fmt": "pct_change",
                                              "text": fmt(100 * (float(r["value"]) - then_real) / then_real, "pct_change"),
                                              "then_real": then_real, "then_real_text": fmt(then_real, info["fmt"])}
            items.append(item)
        if not items:
            return None
        level = rows[0]["geo_level"]
        return {"gisjoin": gj, "level": level, "level_word": _with_level(level), "rows": items,
                "by_kind": {i["kind"]: i for i in items}, "spark": spark,
                "compact": [i for i in items if i["kind"] in COMPACT_KINDS], "attribution": ATTRIBUTION,
                "source_url": SOURCE_URL, "as_of": max(i["date"] for i in items).isoformat()}
    except Exception:  # noqa: BLE001 - an extra block; never fail the page
        log.exception("fred: economy %s", gj)
        return None


def for_area(a: dict | None) -> dict | None:
    """The block for a census area: its own figures (county, state) or its county's (place, tract)."""
    if not a or not ready():
        return None
    gj = area_gisjoin(a)
    econ = economy(gj) if gj else None
    if econ and a.get("level") not in ("county", "state", "nation"):
        econ = {**econ, "borrowed": econ["level"]}
    return econ


def for_link(link: dict | None) -> dict | None:
    """The compact block for an entity's census link (census_links row): the county, else the state."""
    if not link or not ready():
        return None
    for col in ("county_gj", "state_gj"):
        if link.get(col):
            econ = economy(link[col])
            if econ:
                return econ
    return None


def sentence(econ: dict | None) -> str:
    """One line for the compact form: "unemployment 3.4% in Sep 2026 (3.1% a year earlier); per capita personal income
    $78,000 in 2024, up 23% in five years (+5% after inflation)"."""
    if not econ:
        return ""
    parts = []
    for i in econ["compact"]:
        s = f"{i['short'] or i['label'].lower()} {i['text']} in {i['period']}"
        if i.get("change_1y") and i["kind"] == "unemployment_rate":
            s += f" ({i['text_1y']} a year earlier)"
        elif i.get("change_5y"):
            c = i["change_5y"]["value"]
            s += f", {'up' if c >= 0 else 'down'} {abs(c):.0f}% in five years"
            if i.get("real_change_5y"):
                s += f" ({i['real_change_5y']['text']} after inflation)"
        parts.append(s)
    return "; ".join(parts)


# --- the sparkline (inline SVG, like app/census_map.py) --------------------------------------------------------------------

def sparkline(points: list[tuple], width: int = 240, height: int = 48, label: str = "") -> str:
    """A small line chart of (date, value) points with the last value marked and min/max in the title."""
    pts = [(d, float(v)) for d, v in points if v is not None]
    if len(pts) < 2:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pad = 4
    n = len(pts)
    coords = []
    for i, (_, v) in enumerate(pts):
        x = pad + (width - 2 * pad) * i / (n - 1)
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        coords.append(f"{x:.1f},{y:.1f}")
    first, last = pts[0], pts[-1]
    title = (f"{label}: {first[1]:.1f}% in {period(first[0], 'M')} to {last[1]:.1f}% in {period(last[0], 'M')}; "
             f"low {lo:.1f}%, high {hi:.1f}%")
    lx, ly = coords[-1].split(",")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'class="fred-spark" role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
            f'<polyline fill="none" stroke="#3e8ec4" stroke-width="1.5" points="{" ".join(coords)}"/>'
            f'<circle cx="{lx}" cy="{ly}" r="2.5" fill="#1f5f8b"/></svg>')


# --- API and search ---------------------------------------------------------------------------------------------------------

def api_out(econ: dict | None) -> dict | None:
    """The JSON form of a block (the API's area and profile responses, MCP)."""
    if not econ:
        return None
    out = {"level": econ["level"], "as_of": econ["as_of"], "source": SOURCE_NAME, "attribution": ATTRIBUTION,
           "source_url": SOURCE_URL, "measures": {}}
    if econ.get("borrowed"):
        out["note"] = f"figures for the {econ['borrowed']} this area is in"
    for i in econ["rows"]:
        m = {"label": i["label"], "value": i["value"], "unit": i["fmt"], "period": i["period"], "date": i["date"].isoformat(),
             "series_id": i["series_id"], "series_url": i["url"], "series_title": i["title"], "note": i["note"]}
        for k in ("change_1y", "change_5y", "change_10y", "real_change_5y"):
            if i.get(k):
                m[k] = {"value": round(i[k]["value"], 2), "unit": i[k]["fmt"]}
        for k in ("value_1y", "value_5y", "value_10y"):
            if i.get(k) is not None:
                m[k] = i[k]
        out["measures"][i["kind"]] = m
    if econ.get("spark"):
        out["unemployment_history"] = {"series_id": econ["spark"]["series_id"], "series_url": econ["spark"]["url"],
                                       "from": econ["spark"]["from"], "to": econ["spark"]["to"], "months": econ["spark"]["n"]}
    return out


def api_search(q: str, limit: int = 10) -> list[dict]:
    """The `fred` dataset's name search: series whose title matches (a place name, a measure), latest value first."""
    if not ready() or not (q or "").strip():
        return []
    from app.public_api import SITE_URL
    q = q.strip()
    try:
        with db.conn() as conn:
            rows = conn.execute("""
                SELECT s.id, s.title, s.units_short, s.frequency_short, s.geo_level, s.kind, s.gisjoin, l.date, l.value,
                       a.stusab, a.slug, a.level
                FROM fred.series s LEFT JOIN fred.area_latest l ON l.series_id = s.id
                LEFT JOIN census_area a ON a.gisjoin = s.gisjoin
                WHERE s.title ILIKE %s OR s.id = upper(%s)
                ORDER BY s.popularity DESC NULLS LAST, s.id LIMIT %s""", (f"%{q}%", q, limit)).fetchall()
    except Exception:  # noqa: BLE001
        log.exception("fred: search")
        return []
    out = []
    for r in rows:
        url = None
        if r["level"] == "county":
            url = f"/census/{r['stusab'].lower()}/{r['slug']}"
        elif r["level"] == "state":
            url = f"/census/{r['stusab'].lower()}"
        out.append({"series_id": r["id"], "title": r["title"], "units": r["units_short"], "frequency": r["frequency_short"],
                    "level": r["geo_level"], "kind": r["kind"], "latest": {"date": r["date"].isoformat() if r["date"] else None,
                                                                          "value": float(r["value"]) if r["value"] is not None else None},
                    "series_url": series_url(r["id"]), "url": SITE_URL + url if url else None, "source": SOURCE_NAME})
    return out


def observations(series_id: str, since: str | None = None, limit: int = 2000) -> list[dict]:
    """One series' observations (the API's /fred/{series_id})."""
    with db.conn() as conn:
        rows = conn.execute("SELECT date, value FROM fred.observations WHERE series_id = %s AND (%s::date IS NULL OR date >= %s::date) "
                            "ORDER BY date DESC LIMIT %s", (series_id, since, since, limit)).fetchall()
    return [{"date": r["date"].isoformat(), "value": float(r["value"]) if r["value"] is not None else None} for r in reversed(rows)]


def series(series_id: str) -> dict | None:
    with db.conn() as conn:
        r = conn.execute("SELECT * FROM fred.series WHERE id = %s", (series_id,)).fetchone()
    if not r:
        return None
    out = {k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v) for k, v in r.items()}
    out["series_url"] = series_url(series_id)
    out["attribution"] = ATTRIBUTION
    return out
