"""FRED (Federal Reserve Economic Data, Federal Reserve Bank of St. Louis) into schema `fred` (owner, 2026-11-13:
"just realized good data from fred ... get api keys and load?").

What loads (loader.fred run):
  national  headline series for context and for deflating dollars (NATIONAL: CPI, unemployment, GDP, wages, home prices...)
  state     every state: unemployment rate (monthly), GDP, per capita personal income, population, house price index,
            minimum wage, real median household income (STATE_PATTERNS: the ids follow fixed patterns)
  county    every county (~3,200): unemployment rate and labor force (monthly, ids discovered through the API's tag
            search and matched to census_area by name), per capita and total personal income, GDP, population,
            house price index, SAIPE median household income and poverty (ids carry the county FIPS: COUNTY_PATTERNS)
  msa       metro areas: unemployment rate (monthly)
  summarize fred.cpi_annual, fred.real_dollars(), fred.area_latest (the latest value and the values one, five and ten
            years earlier per area and kind), fred.county_trend (income against nonprofit revenue), then the FRED boards

Tables: fred.series (metadata plus geo_level, state/county FIPS, geoid, the census_area gisjoin and a FURP kind such
as unemployment_rate), fred.observations (series_id, date, value), fred.loads (one row per series: the last date
loaded; reruns fetch only observations after it, so the nightly refresh is cheap), fred.meta.

The API needs FRED_API_KEY (.env). `run --wait-for-key` polls for it every ten minutes; until it is there the
national, state and FIPS-pattern county series load from FRED's public CSV endpoint (fredgraph.csv), which needs no key.
Every request carries a descriptive User-Agent, every raw response is kept under /bulk/fred, and the client stays under
RATE_PER_MIN requests a minute (FRED allows 120) with backoff on 429.

Terms: https://fred.stlouisfed.org/docs/api/terms_of_use.html. Attribution shown on the pages (app/fred.py):
"Source: FRED, Federal Reserve Bank of St. Louis", with links to each series.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from loader import db, offpeak

RAW = Path(os.environ.get("FRED_RAW_DIR", "/bulk/fred"))
API = "https://api.stlouisfed.org/fred/"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
UA = "FURP furp.org mfolenick@furp.org"
RATE_PER_MIN = 90                 # FRED's limit is 120 a minute; stay well under it
KEY_POLL_SECONDS = 600            # --wait-for-key: look for FRED_API_KEY every ten minutes
PAGE = 1000                       # the API's largest page
SEARCH_MAX_AGE = 6 * 24 * 3600    # discovery responses are reused for six days (weekly refresh re-discovers)
REFETCH_YEARS = 3                 # a rerun refetches this much history, so revisions of recent values land
OBS_START = "1960-01-01"          # observations before this are not kept (national CPI goes back to 1947; fine either way)
NA = "."                          # FRED's missing value

# --- what to load ------------------------------------------------------------------------------------------------------

# National headline series: id -> (kind, label). CPIAUCSL feeds fred.real_dollars().
NATIONAL = {
    "CPIAUCSL": ("cpi", "Consumer Price Index, all urban consumers, all items"),
    "CPILFESL": ("core_cpi", "Consumer Price Index less food and energy"),
    "PCEPI": ("pce_index", "Personal consumption expenditures price index"),
    "UNRATE": ("unemployment_rate", "Unemployment rate"),
    "CIVPART": ("participation_rate", "Labor force participation rate"),
    "PAYEMS": ("payrolls", "Total nonfarm payrolls"),
    "CES0500000003": ("hourly_earnings", "Average hourly earnings, all private employees"),
    "FEDFUNDS": ("fed_funds", "Federal funds effective rate"),
    "DGS10": ("treasury_10y", "10-year Treasury yield"),
    "MORTGAGE30US": ("mortgage_rate", "30-year fixed mortgage rate"),
    "GDP": ("gdp", "Gross domestic product"),
    "GDPC1": ("real_gdp", "Real gross domestic product"),
    "A939RX0Q048SBEA": ("real_gdp_per_capita", "Real GDP per capita"),
    "DSPIC96": ("real_disposable_income", "Real disposable personal income"),
    "MEHOINUSA672N": ("real_median_hh_income", "Real median household income"),
    "MEHOINUSA646N": ("median_hh_income", "Median household income"),
    "POPTHM": ("population", "Population"),
    "CSUSHPINSA": ("home_price_index", "S&P Case-Shiller U.S. national home price index"),
    "USSTHPI": ("hpi", "All-transactions house price index, United States"),
    "GFDEBTN": ("federal_debt", "Federal debt, total public debt"),
    "PCPI": ("per_capita_income", "Per capita personal income"),
}
# State series: kind -> id pattern ({st} = USPS abbreviation).
STATE_PATTERNS = [
    ("unemployment_rate", "{st}UR"), ("gdp", "{st}NGSP"), ("per_capita_income", "{st}PCPI"), ("population", "{st}POP"),
    ("hpi", "{st}STHPI"), ("min_wage", "STTMINWG{st}"), ("real_median_hh_income", "MEHOINUS{st}A672N"),
]
# County series whose ids carry the FIPS code: kind -> pattern ({fips} = 5 digits, {st} = USPS abbreviation).
COUNTY_PATTERNS = [
    ("per_capita_income", "PCPI{fips}"), ("population", None), ("hpi", "ATNHPIUS{fips}A"), ("personal_income", "PI{fips}"),
    ("gdp", "GDPALL{fips}"), ("median_hh_income", "MHI{st}{fips}A052NCEN"), ("poverty_rate", "PPAA{st}{fips}A156NCEN"),
    ("labor_force", None), ("employed", "LAUCN{fips}0000000005"),
]
# County series whose ids do not carry the FIPS (TXTRAV3URN, CALOSA7URN): found through the tag search and matched to
# census_area by the county name in the title; the same prefix then gives population (TXTRAV3POP) and labor force
# (TXTRAV3LFN).
DISCOVER = {
    "county": {"unemployment_rate": ("county;unemployment;rate;monthly;nsa", re.compile(r"^[A-Z]{2}[A-Z]{2,5}\d?URN$"),
                                     re.compile(r"^Unemployment Rate in (.+), ([A-Z]{2})$"))},
    "msa": {"unemployment_rate": ("msa;unemployment;rate;monthly;nsa", re.compile(r"^[A-Z0-9]{4,10}URN$"),
                                  re.compile(r"^Unemployment Rate in (.+), ([A-Z-]{2,8}) \(MSA\)$"))},
}
PREFIX_KINDS = [("population", "POP"), ("labor_force", "LFN")]     # from a county's URN prefix
# Metadata for the FIPS-pattern county series comes from one search a kind (a few pages each) instead of one call a series.
COUNTY_SEARCH = {
    "per_capita_income": "Per Capita Personal Income in County", "hpi": "All-Transactions House Price Index for County",
    "personal_income": "Personal Income in County", "gdp": "Gross Domestic Product: All Industries in County",
    "median_hh_income": "Estimate of Median Household Income for County",
    "poverty_rate": "Estimated Percent of People of All Ages in Poverty for County", "employed": "Employed Persons in County",
}
PHASES = ["national", "state", "county", "msa", "summarize"]
BOARD_SLUGS = ["fred-income-down-nonprofits-up", "fred-unemployment-big-nonprofits", "fred-pay-vs-county-income"]

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS fred;
CREATE TABLE IF NOT EXISTS fred.series (
    id text PRIMARY KEY, title text, units text, units_short text, frequency text, frequency_short text,
    seasonal_adjustment text, seasonal_adjustment_short text, observation_start date, observation_end date,
    last_updated timestamptz, popularity int, notes text, geo_level text, state_fips text, county_fips text, geoid text,
    gisjoin text, kind text, updated timestamptz DEFAULT now());
CREATE INDEX IF NOT EXISTS fred_series_geo ON fred.series (gisjoin, kind);
CREATE INDEX IF NOT EXISTS fred_series_level_kind ON fred.series (geo_level, kind);
CREATE TABLE IF NOT EXISTS fred.observations (
    series_id text NOT NULL, date date NOT NULL, value numeric, PRIMARY KEY (series_id, date));
CREATE TABLE IF NOT EXISTS fred.loads (
    series_id text PRIMARY KEY, last_date date, fetched_at timestamptz, n_obs bigint, status text, error text, source text);
CREATE TABLE IF NOT EXISTS fred.meta (key text PRIMARY KEY, value text, updated timestamptz DEFAULT now());
CREATE OR REPLACE VIEW fred.cpi_annual AS
    SELECT extract(year FROM date)::int AS year, avg(value) AS cpi, count(*) AS months
    FROM fred.observations WHERE series_id = 'CPIAUCSL' AND value IS NOT NULL GROUP BY 1;
-- real_dollars(amount, year) = the amount in the dollars of the latest full CPI year (or to_year): the FURP deflator.
-- A full year is a past year with at least eleven monthly values (October 2025 was never published: the shutdown).
CREATE OR REPLACE FUNCTION fred.cpi_latest_year() RETURNS int LANGUAGE sql STABLE AS $f$
    SELECT max(year) FROM fred.cpi_annual WHERE months >= 11 AND year < extract(year FROM now())
$f$;
CREATE OR REPLACE FUNCTION fred.real_dollars(amount numeric, yr int, to_year int DEFAULT NULL) RETURNS numeric
LANGUAGE sql STABLE AS $f$
    SELECT amount * t.cpi / f.cpi FROM fred.cpi_annual f, fred.cpi_annual t
    WHERE f.year = yr AND t.year = coalesce(to_year, fred.cpi_latest_year())
$f$;
"""


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# --- the key -------------------------------------------------------------------------------------------------------------

def api_key() -> str | None:
    """FRED_API_KEY from the environment or .env (re-read each time, so a key dropped in while waiting is seen)."""
    from dotenv import dotenv_values
    from app.config import ROOT
    key = os.environ.get("FRED_API_KEY") or dotenv_values(ROOT / ".env").get("FRED_API_KEY")
    return key.strip() if key and key.strip() else None


def wait_for_key() -> str:
    key = api_key()
    while not key:
        log(f"no FRED_API_KEY yet; checking again in {KEY_POLL_SECONDS // 60} min")
        time.sleep(KEY_POLL_SECONDS)
        key = api_key()
    log("FRED_API_KEY present")
    return key


# --- HTTP client: throttled, retrying, caching every raw response ---------------------------------------------------------

class NotFound(Exception):
    """FRED answers 400 "Bad Request. The series does not exist" for an unknown id."""


class Client:
    def __init__(self, key: str | None = None, rate_per_min: int = RATE_PER_MIN):
        self.key = key
        self.gap = 60.0 / rate_per_min
        self.last = 0.0
        self.requests = 0

    def _throttle(self) -> None:
        wait = self.last + self.gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()

    def fetch(self, url: str, cache: Path | None = None, max_age: float | None = None) -> bytes:
        if cache and cache.exists() and (max_age is None or time.time() - cache.stat().st_mtime < max_age):
            return cache.read_bytes()
        delay = 30
        for attempt in range(8):
            self._throttle()
            self.requests += 1
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as r:
                    data = r.read()
                if cache:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(data)
                return data
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace") if e.fp else ""
                if e.code == 400 and ("does not exist" in body or "Bad Request" in body):
                    raise NotFound(url.split("?")[0] + " " + body[:120]) from None
                if e.code == 404:
                    raise NotFound(url) from None
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                log(f"HTTP {e.code}; waiting {delay}s ({url.split('?')[0]})")
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                log(f"network error {e}; waiting {delay}s")
            time.sleep(delay)
            delay = min(delay * 2, 600)
        raise RuntimeError("FRED: giving up on " + url.split("?")[0])

    def api(self, path: str, cache: Path | None = None, max_age: float | None = None, **params) -> dict:
        if not self.key:
            raise RuntimeError("FRED_API_KEY needed for " + path)
        q = {k: v for k, v in params.items() if v is not None}
        q.update(api_key=self.key, file_type="json")
        data = self.fetch(API + path + "?" + urllib.parse.urlencode(q), cache, max_age)
        return json.loads(data)

    def csv(self, series_id: str, start: str | None = None) -> str:
        q = {"id": series_id}
        if start:
            q["cosd"] = start
        cache = RAW / "csv" / series_id[:2] / f"{series_id}.csv"
        data = self.fetch(CSV_URL + "?" + urllib.parse.urlencode(q), cache)
        text = data.decode("utf-8", "replace")
        if not re.match(r"^(DATE|observation_date)\b", text.lstrip("﻿")):
            raise NotFound(series_id + " (no CSV)")
        return text


# --- parsing (tested from fixtures: tests/test_fred.py) ---------------------------------------------------------------------

def _value(s: str | None):
    s = (s or "").strip()
    if s in ("", NA):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv(text: str) -> list[tuple[str, float | None]]:
    """fredgraph.csv: a DATE (or observation_date) column and one value column; "." is missing."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or rows[0][0].strip().lower() not in ("date", "observation_date"):
        raise ValueError("not a FRED CSV")
    out = []
    for r in rows[1:]:
        if len(r) < 2 or not re.match(r"^\d{4}-\d{2}-\d{2}$", r[0].strip()):
            continue
        out.append((r[0].strip(), _value(r[1])))
    return out


def parse_observations(obj: dict) -> list[tuple[str, float | None]]:
    """series/observations JSON: {"observations": [{"date": ..., "value": ...}, ...]}."""
    return [(o["date"], _value(o.get("value"))) for o in obj.get("observations", []) if re.match(r"^\d{4}-\d{2}-\d{2}$", o.get("date", ""))]


# --- county names: a FRED title to a census_area county ---------------------------------------------------------------------

COUNTY_TYPES = ("city and borough", "county/city", "census area", "municipality", "municipio", "borough", "parish",
                "county", "city")


def county_key(name: str) -> tuple[str, str]:
    """"Doña Ana County" -> ("dona ana", "county"); "St. Louis city" -> ("st louis", "city"); "Philadelphia County/City"
    -> ("philadelphia", "county/city")."""
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.'’]", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    for t in COUNTY_TYPES:
        if n.endswith(" " + t):
            return n[:-len(t) - 1].strip(), t
    return n, ""


def county_index(areas: list[dict]) -> dict:
    """(stusab, base, type) -> area, plus (stusab, base) -> area when that pair is unique, for census_area counties."""
    by_type, by_base = {}, {}
    for a in areas:
        base, t = county_key(a["short_name"])
        by_type[(a["stusab"], base, t)] = a
        by_base.setdefault((a["stusab"], base), []).append(a)
    return {"typed": by_type, "base": {k: v[0] for k, v in by_base.items() if len(v) == 1}}


def match_county(index: dict, name: str, st: str) -> dict | None:
    base, t = county_key(name)
    types = ["county", "city"] if t == "county/city" else [t]
    for tt in types:
        a = index["typed"].get((st, base, tt))
        if a:
            return a
    return index["base"].get((st, base))


# --- the database --------------------------------------------------------------------------------------------------------

def ensure_schema(conn) -> None:
    conn.execute(SCHEMA_SQL)
    conn.commit()


def set_meta(conn, key: str, value) -> None:
    conn.execute("INSERT INTO fred.meta (key, value, updated) VALUES (%s, %s, now()) ON CONFLICT (key) DO UPDATE SET "
                 "value = EXCLUDED.value, updated = now()", (key, json.dumps(value) if not isinstance(value, str) else value))


def upsert_series(conn, sid: str, meta: dict | None, geo: dict) -> None:
    """Insert or update a fred.series row: metadata (from the API when known) and the FURP geography/kind."""
    m = meta or {}
    conn.execute("""
        INSERT INTO fred.series (id, title, units, units_short, frequency, frequency_short, seasonal_adjustment,
                                 seasonal_adjustment_short, observation_start, observation_end, last_updated, popularity,
                                 notes, geo_level, state_fips, county_fips, geoid, gisjoin, kind, updated)
        VALUES (%(id)s, %(title)s, %(units)s, %(units_short)s, %(frequency)s, %(frequency_short)s, %(sa)s, %(sa_short)s,
                %(obs_start)s, %(obs_end)s, %(last_updated)s, %(popularity)s, %(notes)s, %(geo_level)s, %(state_fips)s,
                %(county_fips)s, %(geoid)s, %(gisjoin)s, %(kind)s, now())
        ON CONFLICT (id) DO UPDATE SET
            title = coalesce(EXCLUDED.title, fred.series.title), units = coalesce(EXCLUDED.units, fred.series.units),
            units_short = coalesce(EXCLUDED.units_short, fred.series.units_short),
            frequency = coalesce(EXCLUDED.frequency, fred.series.frequency),
            frequency_short = coalesce(EXCLUDED.frequency_short, fred.series.frequency_short),
            seasonal_adjustment = coalesce(EXCLUDED.seasonal_adjustment, fred.series.seasonal_adjustment),
            seasonal_adjustment_short = coalesce(EXCLUDED.seasonal_adjustment_short, fred.series.seasonal_adjustment_short),
            observation_start = coalesce(EXCLUDED.observation_start, fred.series.observation_start),
            observation_end = coalesce(EXCLUDED.observation_end, fred.series.observation_end),
            last_updated = coalesce(EXCLUDED.last_updated, fred.series.last_updated),
            popularity = coalesce(EXCLUDED.popularity, fred.series.popularity), notes = coalesce(EXCLUDED.notes, fred.series.notes),
            geo_level = EXCLUDED.geo_level, state_fips = EXCLUDED.state_fips, county_fips = EXCLUDED.county_fips,
            geoid = EXCLUDED.geoid, gisjoin = EXCLUDED.gisjoin, kind = EXCLUDED.kind, updated = now()""",
                 {"id": sid, "title": m.get("title") or geo.get("title"), "units": m.get("units"), "units_short": m.get("units_short"),
                  "frequency": m.get("frequency"), "frequency_short": m.get("frequency_short"),
                  "sa": m.get("seasonal_adjustment"), "sa_short": m.get("seasonal_adjustment_short"),
                  "obs_start": m.get("observation_start") or None, "obs_end": m.get("observation_end") or None,
                  "last_updated": _ts(m.get("last_updated")), "popularity": m.get("popularity"), "notes": m.get("notes"),
                  "geo_level": geo["geo_level"], "state_fips": geo.get("state_fips"), "county_fips": geo.get("county_fips"),
                  "geoid": geo.get("geoid"), "gisjoin": geo.get("gisjoin"), "kind": geo.get("kind")})


def _ts(s: str | None):
    if not s:
        return None
    try:                                   # "2026-10-14 07:46:02-05"
        return dt.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone(dt.timedelta(hours=int(s[19:22] or 0))))
    except ValueError:
        return None


def store_observations(conn, sid: str, obs: list[tuple[str, float | None]], source: str) -> int:
    rows = [(sid, d, v) for d, v in obs if d >= OBS_START]
    if rows:
        conn.cursor().executemany("INSERT INTO fred.observations (series_id, date, value) VALUES (%s, %s, %s) "
                                  "ON CONFLICT (series_id, date) DO UPDATE SET value = EXCLUDED.value", rows)
    last = max((d for d, v in obs if v is not None), default=None)
    conn.execute("""INSERT INTO fred.loads (series_id, last_date, fetched_at, n_obs, status, error, source)
                    VALUES (%s, %s, now(), %s, 'ok', NULL, %s)
                    ON CONFLICT (series_id) DO UPDATE SET last_date = greatest(EXCLUDED.last_date, fred.loads.last_date),
                        fetched_at = now(), n_obs = coalesce(fred.loads.n_obs, 0) + EXCLUDED.n_obs, status = 'ok',
                        error = NULL, source = EXCLUDED.source""", (sid, last, len(rows), source))
    conn.commit()
    return len(rows)


def mark_missing(conn, sid: str, err: str) -> None:
    conn.execute("""INSERT INTO fred.loads (series_id, fetched_at, n_obs, status, error) VALUES (%s, now(), 0, 'missing', %s)
                    ON CONFLICT (series_id) DO UPDATE SET fetched_at = now(), status = 'missing', error = EXCLUDED.error""",
                 (sid, err[:300]))
    conn.commit()


def load_state(conn) -> dict[str, dict]:
    return {r[0]: {"last_date": r[1], "status": r[2], "fetched_at": r[3]}
            for r in conn.execute("SELECT series_id, last_date, status, fetched_at FROM fred.loads")}


# --- fetching one series -------------------------------------------------------------------------------------------------

class Loader:
    def __init__(self, conn, client: Client, full: bool = False, retry_missing: bool = False):
        self.conn, self.client, self.full, self.retry_missing = conn, client, full, retry_missing
        self.state = load_state(conn)
        self.done = self.skipped = self.missing = self.rows = 0

    def wants(self, sid: str, updated_after: dt.datetime | None = None, cadence_days: int | None = None) -> bool:
        """Whether a series needs a fetch: never loaded, or loaded before FRED last updated it, or (no metadata) long
        enough ago for a new observation to be likely."""
        st = self.state.get(sid)
        if not st:
            return True
        if st["status"] == "missing":
            return self.retry_missing
        if self.full:
            return True
        if updated_after and st["fetched_at"]:
            return updated_after > st["fetched_at"]
        if cadence_days and st["fetched_at"]:
            return (dt.datetime.now(dt.timezone.utc) - st["fetched_at"]).days >= cadence_days
        return True

    def start_for(self, sid: str) -> str | None:
        st = self.state.get(sid)
        if self.full or not st or not st.get("last_date"):
            return None
        return (st["last_date"] - dt.timedelta(days=365 * REFETCH_YEARS)).isoformat()

    def fetch(self, sid: str, meta: dict | None, geo: dict, use_csv: bool = False) -> bool:
        start = self.start_for(sid)
        try:
            if use_csv or not self.client.key:
                obs = parse_csv(self.client.csv(sid, start))
                source = "csv"
            else:
                cache = RAW / "obs" / sid[:2] / f"{sid}__{start or 'all'}.json"
                obj = self.client.api("series/observations", cache=cache, series_id=sid, observation_start=start or OBS_START)
                obs = parse_observations(obj)
                source = "api"
        except NotFound as e:
            mark_missing(self.conn, sid, str(e))
            self.state[sid] = {"status": "missing", "last_date": None, "fetched_at": dt.datetime.now(dt.timezone.utc)}
            self.missing += 1
            return False
        upsert_series(self.conn, sid, meta, geo)
        n = store_observations(self.conn, sid, obs, source)
        self.state[sid] = {"status": "ok", "last_date": max((d for d, v in obs if v is not None), default=None),
                           "fetched_at": dt.datetime.now(dt.timezone.utc)}
        self.done += 1
        self.rows += n
        return True

    def progress(self, label: str, every: int = 100) -> None:
        if (self.done + self.missing) % every == 0:
            log(f"{label}: {self.done} loaded, {self.skipped} current, {self.missing} missing, {self.rows:,} rows, "
                f"{self.client.requests} requests")


# --- metadata discovery through the API ----------------------------------------------------------------------------------

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def search_all(client: Client, search_text: str, **params) -> list[dict]:
    """Every page of a series/search (cached six days)."""
    out, offset = [], 0
    while True:
        cache = RAW / "search" / f"{_slug(search_text)}-{offset}.json"
        obj = client.api("series/search", cache=cache, max_age=SEARCH_MAX_AGE, search_text=search_text, limit=PAGE,
                         offset=offset, order_by="series_id", **params)
        rows = obj.get("seriess", [])
        out.extend(rows)
        offset += PAGE
        if len(rows) < PAGE or offset >= int(obj.get("count", 0)):
            return out


def tags_all(client: Client, tag_names: str) -> list[dict]:
    """Every page of a tags/series listing (cached six days)."""
    out, offset = [], 0
    while True:
        cache = RAW / "tags" / f"{_slug(tag_names)}-{offset}.json"
        obj = client.api("tags/series", cache=cache, max_age=SEARCH_MAX_AGE, tag_names=tag_names, limit=PAGE, offset=offset,
                         order_by="series_id")
        rows = obj.get("seriess", [])
        out.extend(rows)
        offset += PAGE
        if len(rows) < PAGE or offset >= int(obj.get("count", 0)):
            return out


def series_meta(client: Client, sid: str, max_age: float | None = SEARCH_MAX_AGE) -> dict | None:
    try:
        obj = client.api("series", cache=RAW / "series" / sid[:2] / f"{sid}.json", max_age=max_age, series_id=sid)
    except NotFound:
        return None
    rows = obj.get("seriess") or []
    return rows[0] if rows else None


# --- the phases ------------------------------------------------------------------------------------------------------------

def states(conn) -> list[dict]:
    return [dict(stusab=r[0], state_fips=r[1], gisjoin=r[2], name=r[3]) for r in conn.execute(
        "SELECT stusab, state_fips, gisjoin, name FROM census_area WHERE level = 'state' ORDER BY stusab")]


def counties(conn) -> list[dict]:
    return [dict(stusab=r[0], state_fips=r[1], county_fips=r[2], gisjoin=r[3], geoid=r[4], short_name=r[5]) for r in conn.execute(
        "SELECT stusab, state_fips, county_fips, gisjoin, geoid, short_name FROM census_area WHERE level = 'county' ORDER BY geoid")]


def _meta_by_id(client: Client, ids: list[str], search_text: str | None) -> dict[str, dict]:
    """Metadata for many ids from one search (pages of 1000) when the key is there; else nothing (filled later)."""
    if not client.key or not search_text:
        return {}
    want = set(ids)
    return {s["id"]: s for s in search_all(client, search_text) if s["id"] in want}


def run_national(conn, client: Client, ld: Loader) -> None:
    log(f"national: {len(NATIONAL)} series")
    for sid, (kind, label) in NATIONAL.items():
        if not ld.wants(sid, cadence_days=1):
            ld.skipped += 1
            continue
        meta = series_meta(client, sid, max_age=0) if client.key else None
        ld.fetch(sid, meta, {"geo_level": "nation", "geoid": "", "gisjoin": "US", "kind": kind, "title": label})
    log(f"national done: {ld.done} loaded, {ld.missing} missing, {ld.rows:,} rows")


def run_state(conn, client: Client, ld: Loader) -> None:
    sts = states(conn)
    log(f"state: {len(sts)} states x {len(STATE_PATTERNS)} kinds")
    for s in sts:
        for kind, pat in STATE_PATTERNS:
            sid = pat.format(st=s["stusab"])
            if not ld.wants(sid, cadence_days=6):
                ld.skipped += 1
                continue
            meta = series_meta(client, sid, max_age=0) if client.key else None
            ld.fetch(sid, meta, {"geo_level": "state", "state_fips": s["state_fips"], "geoid": s["state_fips"],
                                 "gisjoin": s["gisjoin"], "kind": kind, "title": f"{kind} in {s['name']}"})
    log(f"state done: {ld.done} loaded, {ld.missing} missing, {ld.rows:,} rows")


def discover_counties(conn, client: Client, cos: list[dict]) -> dict[str, dict]:
    """The county unemployment-rate series (URN) matched to census_area by name: gisjoin -> metadata row with the
    prefix for the POP and LFN series. Unmatched titles are looked up through the FIPS-coded annual series' titles."""
    tag_names, id_re, title_re = DISCOVER["county"]["unemployment_rate"]
    rows = [s for s in tags_all(client, tag_names) if id_re.match(s["id"]) and title_re.match(s["title"])]
    index = county_index(cos)
    found, unmatched = {}, []
    for s in rows:
        name, st = title_re.match(s["title"]).groups()
        a = match_county(index, name, st)
        if a and a["gisjoin"] not in found:
            found[a["gisjoin"]] = {**s, "prefix": s["id"][:-3]}
        else:
            unmatched.append(s)
    log(f"county discovery: {len(rows)} unemployment series, {len(found)} matched by name, {len(unmatched)} not")
    if unmatched:
        # The annual series LAUCN<FIPS>0000000003A carries the same title: one call a county still unmatched.
        by_title = {s["title"]: s for s in unmatched}
        for a in cos:
            if a["gisjoin"] in found:
                continue
            m = series_meta(client, f"LAUCN{a['geoid']}0000000003A")
            if m and m["title"] in by_title:
                s = by_title[m["title"]]
                found[a["gisjoin"]] = {**s, "prefix": s["id"][:-3]}
        log(f"county discovery: {len(found)} matched after the FIPS lookup")
    set_meta(conn, "county_urn", {"series": len(rows), "matched": len(found), "counties": len(cos)})
    return found


def run_county(conn, client: Client, ld: Loader, only_kinds: set[str] | None = None) -> None:
    cos = counties(conn)
    log(f"county: {len(cos)} counties")
    geo = lambda a, kind, title=None: {"geo_level": "county", "state_fips": a["state_fips"], "county_fips": a["county_fips"],
                                       "geoid": a["geoid"], "gisjoin": a["gisjoin"], "kind": kind,
                                       "title": title or f"{kind} in {a['short_name']}, {a['stusab']}"}
    urn = discover_counties(conn, client, cos) if client.key and (not only_kinds or {"unemployment_rate", "population", "labor_force"} & only_kinds) else {}
    # 1. unemployment rate (monthly), the series everyone asks for first
    if urn and (not only_kinds or "unemployment_rate" in only_kinds):
        for a in cos:
            s = urn.get(a["gisjoin"])
            if not s:
                continue
            if ld.wants(s["id"], updated_after=_ts(s.get("last_updated"))):
                ld.fetch(s["id"], s, geo(a, "unemployment_rate"))
            else:
                ld.skipped += 1
            ld.progress("county unemployment")
        log(f"county unemployment done: {ld.done} loaded, {ld.skipped} current, {ld.missing} missing")
    # 2. the FIPS-pattern kinds, in the order the pages need them
    for kind, pat in COUNTY_PATTERNS:
        if only_kinds and kind not in only_kinds:
            continue
        if pat is None:
            suffix = dict(PREFIX_KINDS).get(kind)
            if not urn or not suffix:
                continue
            ids = {a["gisjoin"]: urn[a["gisjoin"]]["prefix"] + suffix for a in cos if a["gisjoin"] in urn}
            search = "Resident Population in County" if kind == "population" else "Civilian Labor Force in County"
        else:
            ids = {a["gisjoin"]: pat.format(fips=a["geoid"], st=a["stusab"]) for a in cos}
            search = COUNTY_SEARCH.get(kind)
        metas = _meta_by_id(client, list(ids.values()), search)
        log(f"county {kind}: {len(ids)} ids, metadata for {len(metas)}")
        cadence = 25 if kind in ("labor_force", "employed") else 60
        for a in cos:
            sid = ids.get(a["gisjoin"])
            if not sid:
                continue
            m = metas.get(sid)
            if ld.wants(sid, updated_after=_ts(m.get("last_updated")) if m else None, cadence_days=cadence):
                ld.fetch(sid, m, geo(a, kind))
            else:
                ld.skipped += 1
            ld.progress(f"county {kind}")
        log(f"county {kind} done: {ld.done} loaded, {ld.skipped} current, {ld.missing} missing, {ld.rows:,} rows")


def run_msa(conn, client: Client, ld: Loader) -> None:
    tag_names, id_re, title_re = DISCOVER["msa"]["unemployment_rate"]
    rows = [s for s in tags_all(client, tag_names) if id_re.match(s["id"]) and title_re.match(s["title"])]
    log(f"msa: {len(rows)} unemployment series")
    for s in rows:
        if ld.wants(s["id"], updated_after=_ts(s.get("last_updated"))):
            ld.fetch(s["id"], s, {"geo_level": "msa", "kind": "unemployment_rate"})
        else:
            ld.skipped += 1
        ld.progress("msa unemployment")
    log(f"msa done: {ld.done} loaded, {ld.skipped} current, {ld.missing} missing")


def fill_metadata(conn, client: Client, limit: int = 5000) -> int:
    """Titles and units for series loaded without metadata (the key-less CSV path): one `series` call each."""
    ids = [r[0] for r in conn.execute("SELECT id FROM fred.series WHERE units IS NULL ORDER BY id LIMIT %s", (limit,))]
    n = 0
    for sid in ids:
        m = series_meta(client, sid)
        if m:
            row = conn.execute("SELECT geo_level, state_fips, county_fips, geoid, gisjoin, kind FROM fred.series WHERE id = %s", (sid,)).fetchone()
            upsert_series(conn, sid, m, dict(zip(("geo_level", "state_fips", "county_fips", "geoid", "gisjoin", "kind"), row)))
            conn.commit()
            n += 1
    log(f"metadata filled for {n} of {len(ids)} series")
    return n


SUMMARY_SQL = """
DROP TABLE IF EXISTS fred.area_latest_new;
CREATE TABLE fred.area_latest_new AS
WITH s AS (SELECT id, gisjoin, geo_level, kind, frequency_short FROM fred.series WHERE gisjoin IS NOT NULL AND kind IS NOT NULL),
latest AS (SELECT DISTINCT ON (o.series_id) o.series_id, o.date, o.value
           FROM fred.observations o JOIN s ON s.id = o.series_id WHERE o.value IS NOT NULL ORDER BY o.series_id, o.date DESC)
SELECT s.gisjoin, s.geo_level, s.kind, s.id AS series_id, s.frequency_short AS frequency, l.date, l.value,
       y1.value AS value_1y, y5.value AS value_5y, y10.value AS value_10y,
       CASE WHEN y1.value <> 0 THEN 100 * (l.value - y1.value) / y1.value END AS pct_1y,
       CASE WHEN y5.value <> 0 THEN 100 * (l.value - y5.value) / y5.value END AS pct_5y,
       CASE WHEN y10.value <> 0 THEN 100 * (l.value - y10.value) / y10.value END AS pct_10y
FROM s JOIN latest l ON l.series_id = s.id
LEFT JOIN LATERAL (SELECT value FROM fred.observations o WHERE o.series_id = s.id AND o.date = (l.date - interval '1 year')::date AND o.value IS NOT NULL) y1 ON true
LEFT JOIN LATERAL (SELECT value FROM fred.observations o WHERE o.series_id = s.id AND o.date = (l.date - interval '5 years')::date AND o.value IS NOT NULL) y5 ON true
LEFT JOIN LATERAL (SELECT value FROM fred.observations o WHERE o.series_id = s.id AND o.date = (l.date - interval '10 years')::date AND o.value IS NOT NULL) y10 ON true;
CREATE INDEX ON fred.area_latest_new (gisjoin, kind);
CREATE INDEX ON fred.area_latest_new (geo_level, kind);
DROP TABLE IF EXISTS fred.area_latest;
ALTER TABLE fred.area_latest_new RENAME TO area_latest;
"""

TREND_SQL = """
-- Nonprofit revenue placed in each county by tax year (census_links: organizations by ZIP), for the income-vs-charity board.
DROP TABLE IF EXISTS fred.county_nonprofit_years_new;
CREATE TABLE fred.county_nonprofit_years_new AS
SELECT l.county_gj AS gisjoin, f.tax_year, sum(f.total_revenue)::numeric AS revenue, count(*) AS filings
FROM filings f JOIN census_links l ON l.kind = 'org' AND l.key = f.ein
WHERE NOT f.superseded AND f.tax_year BETWEEN 2008 AND 2035 AND f.total_revenue > 0 AND l.county_gj IS NOT NULL
GROUP BY 1, 2;
CREATE INDEX ON fred.county_nonprofit_years_new (gisjoin, tax_year);
DROP TABLE IF EXISTS fred.county_nonprofit_years;
ALTER TABLE fred.county_nonprofit_years_new RENAME TO county_nonprofit_years;
-- Five-year change in real per capita personal income against real nonprofit revenue per resident, county by county.
-- year_b = the latest per capita income year minus one (returns for the latest year are still arriving), year_a = five
-- years before; both dollar figures in year_b dollars (fred.real_dollars, CPI-U annual averages).
DROP TABLE IF EXISTS fred.county_trend_new;
CREATE TABLE fred.county_trend_new AS
WITH yb AS (SELECT (extract(year FROM max(o.date)) - 1)::int AS year_b
            FROM fred.observations o JOIN fred.series s ON s.id = o.series_id
            WHERE s.kind = 'per_capita_income' AND s.geo_level = 'county' AND o.value IS NOT NULL),
pc AS (SELECT s.gisjoin, extract(year FROM o.date)::int AS year, o.value
       FROM fred.observations o JOIN fred.series s ON s.id = o.series_id
       WHERE s.kind = 'per_capita_income' AND s.geo_level = 'county' AND o.value IS NOT NULL),
pop AS (SELECT s.gisjoin, extract(year FROM o.date)::int AS year, o.value * 1000 AS persons
        FROM fred.observations o JOIN fred.series s ON s.id = o.series_id
        WHERE s.kind = 'population' AND s.geo_level = 'county' AND o.value IS NOT NULL)
SELECT a.gisjoin, yb.year_b, yb.year_b - 5 AS year_a,
       pb.value AS pcpi_b, pa.value AS pcpi_a, fred.real_dollars(pa.value, yb.year_b - 5, yb.year_b) AS pcpi_a_real,
       rb.revenue AS rev_b, ra.revenue AS rev_a, fred.real_dollars(ra.revenue, yb.year_b - 5, yb.year_b) AS rev_a_real,
       rb.filings AS filings_b, ra.filings AS filings_a, popb.persons AS pop_b, popa.persons AS pop_a
FROM census_area a CROSS JOIN yb
JOIN pc pb ON pb.gisjoin = a.gisjoin AND pb.year = yb.year_b
JOIN pc pa ON pa.gisjoin = a.gisjoin AND pa.year = yb.year_b - 5
JOIN fred.county_nonprofit_years rb ON rb.gisjoin = a.gisjoin AND rb.tax_year = yb.year_b
JOIN fred.county_nonprofit_years ra ON ra.gisjoin = a.gisjoin AND ra.tax_year = yb.year_b - 5
LEFT JOIN pop popb ON popb.gisjoin = a.gisjoin AND popb.year = yb.year_b
LEFT JOIN pop popa ON popa.gisjoin = a.gisjoin AND popa.year = yb.year_b - 5
WHERE a.level = 'county';
CREATE INDEX ON fred.county_trend_new (gisjoin);
DROP TABLE IF EXISTS fred.county_trend;
ALTER TABLE fred.county_trend_new RENAME TO county_trend;
"""


def summarize(conn, boards: bool = True) -> None:
    """The derived tables the pages and boards read, then the FRED leaderboards."""
    offpeak.wait("fred summary", log)
    t = time.time()
    conn.execute(SUMMARY_SQL)
    conn.commit()
    n = conn.execute("SELECT count(*) FROM fred.area_latest").fetchone()[0]
    log(f"fred.area_latest: {n:,} rows ({time.time() - t:.0f}s)")
    t = time.time()
    conn.execute(TREND_SQL)
    conn.commit()
    n = conn.execute("SELECT count(*) FROM fred.county_trend").fetchone()[0]
    log(f"fred.county_trend: {n:,} counties ({time.time() - t:.0f}s)")
    counts = {r[0]: r[1] for r in conn.execute("SELECT geo_level, count(*) FROM fred.series GROUP BY 1")}
    obs = conn.execute("SELECT count(*), max(date) FROM fred.observations").fetchone()
    set_meta(conn, "summary", {"series": counts, "observations": obs[0], "last_date": str(obs[1]), "at": dt.datetime.now().isoformat()})
    if boards:
        from loader import boards as lb

        class _Status:
            phase = "boards"

            @staticmethod
            def emit(text=None):
                log(text or "")

        lb.refresh(_Status(), only=BOARD_SLUGS)
        log("fred boards refreshed")


def status(conn) -> None:
    for r in conn.execute("""SELECT s.geo_level, s.kind, count(*) AS series, min(l.last_date), max(l.last_date),
                                    sum(CASE WHEN l.status = 'missing' THEN 1 ELSE 0 END) AS missing
                             FROM fred.series s LEFT JOIN fred.loads l ON l.series_id = s.id GROUP BY 1, 2 ORDER BY 1, 2"""):
        print(*r)
    print("observations:", conn.execute("SELECT count(*) FROM fred.observations").fetchone()[0])
    for r in conn.execute("SELECT key, value, updated FROM fred.meta ORDER BY key"):
        print(*r)


# --- main --------------------------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="load everything (resumable)")
    r.add_argument("--phases", default=",".join(PHASES), help="comma-separated: " + ", ".join(PHASES))
    r.add_argument("--kinds", help="county: only these kinds (comma-separated)")
    r.add_argument("--wait-for-key", action="store_true", help="poll for FRED_API_KEY every ten minutes; load what the "
                                                                "public CSV endpoint gives meanwhile")
    r.add_argument("--full", action="store_true", help="refetch every observation, not just the recent years")
    r.add_argument("--retry-missing", action="store_true", help="try series marked missing again")
    r.add_argument("--no-boards", action="store_true")
    sub.add_parser("refresh", help="new observations for every series (weekly from scripts/nightly.sh), then summarize")
    sub.add_parser("summarize", help="rebuild the derived tables and the FRED boards")
    sub.add_parser("metadata", help="fill titles and units for series loaded without the key")
    sub.add_parser("status")
    args = p.parse_args(argv)

    RAW.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    ensure_schema(conn)
    if args.command == "status":
        status(conn)
        return 0
    if args.command == "summarize":
        summarize(conn)
        return 0
    key = api_key()
    if args.command == "metadata":
        if not key:
            log("no FRED_API_KEY")
            return 2
        fill_metadata(conn, Client(key))
        return 0
    phases = PHASES if args.command == "refresh" else [x for x in args.phases.split(",") if x]
    only_kinds = set(args.kinds.split(",")) if getattr(args, "kinds", None) else None
    full = getattr(args, "full", False)
    client = Client(key)
    ld = Loader(conn, client, full=full, retry_missing=getattr(args, "retry_missing", False))
    log(f"fred {args.command}: phases {phases}; key {'present' if key else 'absent'}; raw files under {RAW}")
    if not key and not getattr(args, "wait_for_key", False) and args.command == "run":
        log("no FRED_API_KEY: loading what the public CSV endpoint gives (national, state, FIPS-pattern county series)")
    # Without the key: what the CSV endpoint can give, then wait for the key for the rest.
    if not key:
        if "national" in phases:
            run_national(conn, client, ld)
        if "state" in phases:
            run_state(conn, client, ld)
        if "county" in phases:
            run_county(conn, client, ld, {k for k, pat in COUNTY_PATTERNS if pat} & (only_kinds or {k for k, _ in COUNTY_PATTERNS}))
        if "summarize" in phases:
            summarize(conn, boards=not getattr(args, "no_boards", False))
        if not getattr(args, "wait_for_key", False):
            log("done without the key; rerun with the key (or --wait-for-key) for the rest")
            return 0
        key = wait_for_key()
        client.key = key
        ld.state = load_state(conn)
    if "national" in phases:
        run_national(conn, client, ld)
    if "state" in phases:
        run_state(conn, client, ld)
    if "county" in phases:
        run_county(conn, client, ld, only_kinds)
    if "msa" in phases:
        run_msa(conn, client, ld)
    fill_metadata(conn, client)
    if "summarize" in phases:
        summarize(conn, boards=not getattr(args, "no_boards", False))
    log(f"fred {args.command} done: {ld.done} series loaded, {ld.skipped} already current, {ld.missing} missing, "
        f"{ld.rows:,} observation rows, {client.requests} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
