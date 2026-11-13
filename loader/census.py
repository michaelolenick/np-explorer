"""Census cross-reference (owner, 2026-11-12: "FURP is all about x-ref, not just data pools"): ties the IPUMS NHGIS
tables (loader/nhgis.py, schema nhgis) to every FURP record that has a place, and prepares the pages, maps and
leaderboards under /census (app/census.py, app/census_map.py, app/census_boards.py).

Tables (all new, in the public schema; nothing existing is touched):
  census_zip_county    ZIP (ZCTA) -> county with the share of the ZCTA's land in each county, from the Census Bureau's
                       2020 ZCTA-to-county relationship file; `dominant` marks the county holding most of the ZIP.
  census_zip_tract     ZIP -> tract the same way (ZCTA-to-tract relationship file). FURP has no street geocoder, so
                       a record's tract is its ZIP's dominant tract, an approximation the pages say out loud.
  census_area          one row per state, county, place and tract: names, codes, URL slug, center point and the
                       headline measures (MEASURES: population, median household income, poverty rate, median age,
                       education, housing, race and ethnicity) read from whichever nhgis tables have loaded; a
                       measure whose table is not in yet is NULL and fills in on the next `facts` run.
  census_links         every FURP record with an address -> its state, county, place and tract GISJOINs, how it
                       was matched (zip, city, state) and a headline value (revenue, pay, amount) for rankings.
  census_area_furp     per area and record kind: how many records, their total, the biggest one.
  census_area_people   the highest-paid people on 990s in each state, county and place (latest year per person).
  census_shapes        simplified outlines (Census TIGER/Line 2026 shapefiles in /bulk/tiger, simplified with
                       shapely) for the server-rendered SVG maps, plus each area's internal point and land area.

    python -m loader.census xwalk                 download and load the two ZCTA relationship files
    python -m loader.census shapes [--levels ...]  download TIGER county and tract shapes, simplify, load
    python -m loader.census facts                 (re)build census_area from the nhgis tables now loaded
    python -m loader.census links [--kinds ...]    (re)build census_links (default: every kind but the two huge ones,
                                                  fed and biz, which need --kinds fed,biz and the quiet hours)
    python -m loader.census stats                 (re)build census_area_furp and census_area_people
    python -m loader.census all                   xwalk, shapes, facts, links, stats

Heavy steps wait for the quiet hours (loader/offpeak.py; NP_NOW=1 runs them now). Rebuilt tables are built beside
the live one and swapped in, so pages keep working. Rerunning is safe.
Sources: U.S. Census Bureau 2020 ZCTA relationship files (https://www.census.gov/geographies/reference-files/
time-series/geo/relationship-files.html) and TIGER/Line 2026 shapefiles (https://www.census.gov/geographies/
mapping-files/time-series/geo/tiger-line-file.html); data: IPUMS NHGIS (loader/nhgis.py CITATION).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from pathlib import Path

from loader import db, offpeak

TIGER = Path(os.environ.get("TIGER_DIR", "/bulk/tiger"))
CENSUS_DIR = Path(os.environ.get("CENSUS_DIR", "/bulk/census"))
TIGER_YEAR = "2026"
TIGER_URL = f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}"
REL_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520"
REL_FILES = {"county": "tab20_zcta520_county20_natl.txt", "tract": "tab20_zcta520_tract20_natl.txt"}
ACS = "2020_2024_ACS5a"
ACS_B = "2020_2024_ACS5b"   # the companion dataset NHGIS splits the ACS into: holds B17001 (poverty), B05002
                            # (nativity) and B08013 (commute minutes), which ACS5a does not (loaded 2026-11-13)
DHC = "2020_DHCa"
ACS_LABEL = "ACS 2020-2024 5-year"
USER_AGENT = "FURP furp.org census loader (info@furp.org)"
LEVELS = ("state", "county", "place", "tract")
# Simplification tolerance in degrees (about 111 km per degree): fine enough to look right at page width, coarse
# enough that a county's tracts stay a few hundred KB.
SIMPLIFY = {"state": 0.02, "county": 0.004, "place": 0.002, "tract": 0.0008}
HEAVY_KINDS = ("fed", "biz")       # tens of millions of source rows: only with --kinds, in the quiet hours

# The headline measures of census_area: column -> (ACS table, expression over its columns, label, format, note).
# {c} is the table's column prefix (NHGIS code + E), so "{c}001" is the first estimate column; "{c:B08303}001" is
# the first column of another table joined for the same area. The actual columns are looked up in nhgis.tables
# when the facts are built, never guessed.
MEASURES = [
    ("population", "B01003", "{c}001", "Population", "num", "Total population"),
    ("median_age", "B01002", "{c}001", "Median age", "years", "Median age, both sexes"),
    ("median_hh_income", "B19013", "{c}001", "Median household income", "money",
     "Median household income in the past 12 months (2024 dollars)"),
    ("per_capita_income", "B19301", "{c}001", "Per capita income", "money", "Per capita income in the past 12 months"),
    ("median_family_income", "B19113", "{c}001", "Median family income", "money", "Median family income"),
    ("households", "B11001", "{c}001", "Households", "num", "Households"),
    ("poverty_rate", "B17001", "100.0 * {c}002 / nullif({c}001, 0)", "Poverty rate", "pct",
     "Share of people whose poverty status is determined who live below the poverty line"),
    ("bachelors_share", "B15003", "100.0 * ({c}022 + {c}023 + {c}024 + {c}025) / nullif({c}001, 0)",
     "Bachelor's degree or higher", "pct", "Share of people 25 and over with a bachelor's, master's, professional or "
                                          "doctoral degree"),
    ("unemployment_rate", "B23025", "100.0 * {c}005 / nullif({c}003, 0)", "Unemployment rate", "pct",
     "Unemployed share of the civilian labor force, 16 and over"),
    ("labor_force", "B23025", "{c}003", "Civilian labor force", "num", "Civilian labor force, 16 and over"),
    ("housing_units", "B25001", "{c}001", "Housing units", "num", "Housing units"),
    ("owner_share", "B25003", "100.0 * {c}002 / nullif({c}001, 0)", "Owner-occupied", "pct",
     "Share of occupied housing units lived in by their owners"),
    ("renter_share", "B25003", "100.0 * {c}003 / nullif({c}001, 0)", "Renters", "pct",
     "Share of occupied housing units that are rented"),
    ("median_home_value", "B25077", "{c}001", "Median home value", "money", "Median value of owner-occupied homes"),
    ("median_rent", "B25064", "{c}001", "Median gross rent", "money", "Median gross rent, monthly"),
    ("white_share", "B03002", "100.0 * {c}003 / nullif({c}001, 0)", "White, not Hispanic", "pct",
     "White alone, not Hispanic or Latino"),
    ("black_share", "B03002", "100.0 * {c}004 / nullif({c}001, 0)", "Black", "pct",
     "Black or African American alone, not Hispanic or Latino"),
    ("native_share", "B03002", "100.0 * {c}005 / nullif({c}001, 0)", "American Indian and Alaska Native", "pct",
     "American Indian and Alaska Native alone, not Hispanic or Latino"),
    ("asian_share", "B03002", "100.0 * {c}006 / nullif({c}001, 0)", "Asian", "pct",
     "Asian alone, not Hispanic or Latino"),
    ("hispanic_share", "B03002", "100.0 * {c}012 / nullif({c}001, 0)", "Hispanic or Latino", "pct",
     "Hispanic or Latino, of any race"),
    ("foreign_born_share", "B05002", "100.0 * {c}013 / nullif({c}001, 0)", "Foreign born", "pct",
     "Share of the population born outside the United States"),
    ("under_18_share", "B01001", "100.0 * ({c}003 + {c}004 + {c}005 + {c}006 + {c}027 + {c}028 + {c}029 + {c}030) "
                                 "/ nullif({c}001, 0)", "Under 18", "pct", "Share of the population under 18"),
    ("over_65_share", "B01001", "100.0 * ({c}020 + {c}021 + {c}022 + {c}023 + {c}024 + {c}025 + {c}044 + {c}045 + "
                                "{c}046 + {c}047 + {c}048 + {c}049) / nullif({c}001, 0)", "65 and over", "pct",
     "Share of the population 65 and over"),
    ("mean_commute", "B08013", "round(({c}001 / nullif({c:B08303}001, 0))::numeric, 1)", "Mean commute (minutes)", "years",
     "Mean travel time to work in minutes: aggregate minutes (B08013) over workers who did not work from home (B08303)"),
]
MEASURE_COLUMNS = [m[0] for m in MEASURES]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS census_zip_county (
    zip5 text NOT NULL, county_geoid text NOT NULL, gisjoin text NOT NULL, share real, dominant boolean NOT NULL DEFAULT false,
    PRIMARY KEY (zip5, county_geoid));
CREATE INDEX IF NOT EXISTS census_zip_county_gj ON census_zip_county (gisjoin);
CREATE TABLE IF NOT EXISTS census_zip_tract (
    zip5 text NOT NULL, tract_geoid text NOT NULL, gisjoin text NOT NULL, share real, dominant boolean NOT NULL DEFAULT false,
    PRIMARY KEY (zip5, tract_geoid));
CREATE INDEX IF NOT EXISTS census_zip_tract_gj ON census_zip_tract (gisjoin);
CREATE TABLE IF NOT EXISTS census_shapes (
    gisjoin text PRIMARY KEY, level text NOT NULL, state_fips text NOT NULL, county_fips text, geoid text, name text,
    lon double precision, lat double precision, aland bigint, minx real, miny real, maxx real, maxy real, geom jsonb);
CREATE INDEX IF NOT EXISTS census_shapes_level_state ON census_shapes (level, state_fips, county_fips);
CREATE TABLE IF NOT EXISTS census_area (
    gisjoin text PRIMARY KEY, level text NOT NULL, name text, short_name text, stusab text, state_fips text,
    county_fips text, place_fips text, tract text, geoid text, slug text, lat double precision, lon double precision,
    aland bigint, pop2020 numeric, """ + ", ".join(f"{c} numeric" for c in MEASURE_COLUMNS) + """,
    updated timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS census_links (
    kind text NOT NULL, key text NOT NULL, name text, state text, zip5 text, city text, state_gj text, county_gj text,
    place_gj text, tract_gj text, how text, value numeric, PRIMARY KEY (kind, key));
-- The area pages read links by area and kind, biggest first (2026-11-13: without these every county page scanned 39M rows)
CREATE INDEX IF NOT EXISTS census_links_county_gj_kind_value ON census_links (county_gj, kind, value DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS census_links_place_gj_kind_value ON census_links (place_gj, kind, value DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS census_links_tract_gj_kind_value ON census_links (tract_gj, kind, value DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS census_links_state_gj_kind_value ON census_links (state_gj, kind, value DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS census_links_zip_kind ON census_links (zip5, kind);
CREATE TABLE IF NOT EXISTS census_area_furp (
    gisjoin text NOT NULL, kind text NOT NULL, n bigint, total numeric, top_key text, top_name text, top_value numeric,
    PRIMARY KEY (gisjoin, kind));
CREATE TABLE IF NOT EXISTS census_area_people (
    cluster_id bigint NOT NULL, name text, title text, ein text, org_name text, tax_year int, total numeric,
    state_gj text, county_gj text, place_gj text, rank_state int, rank_county int, rank_place int);
CREATE TABLE IF NOT EXISTS census_meta (key text PRIMARY KEY, value text, updated timestamptz DEFAULT now());
CREATE OR REPLACE FUNCTION census_city_norm(t text) RETURNS text LANGUAGE sql IMMUTABLE AS $f$
    SELECT regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
               trim(regexp_replace(regexp_replace(lower(coalesce(t, '')), '&', ' and ', 'g'), '[^a-z0-9 ]+', ' ', 'g')),
               '\\s+', ' ', 'g'),
             '^(st|ste) ', 'saint ', ''), '^ft ', 'fort ', ''), '^mt ', 'mount ', ''),
             ' (city|town|village|borough|township|cdp)$', '', '')
$f$;
"""

# Where each kind of FURP record's address comes from: kind -> (page label, SQL giving key, name, state, zip, city,
# value). Pages: app/census.py KIND_URLS turns kind + key into the record's page. The two heavy kinds (fed: one row
# per federal recipient name and ZIP; biz: state business registrations with an EIN) run only when asked.
SOURCES = {
    "org": ("Nonprofits", """SELECT ein AS key, name, state, zip, city, latest_total_revenue::numeric AS value
                             FROM organizations"""),
    "contractor": ("Nonprofit contractors", """
        SELECT DISTINCT ON (vendor_key) id::text AS key, name_raw AS name, state, zip, city,
               sum(compensation) OVER (PARTITION BY vendor_key)::numeric AS value
        FROM contractors WHERE vendor_key IS NOT NULL AND (zip IS NOT NULL OR city IS NOT NULL)
        ORDER BY vendor_key, tax_year DESC, id DESC"""),
    "college": ("Colleges and schools", """SELECT unitid::text AS key, name, state::text AS state, zip, city,
                                                  enrollment::numeric AS value FROM colleges
                                           WHERE coalesce(international, false) = false"""),
    "formd": ("Form D issuers", """
        SELECT DISTINCT ON (cik) cik AS key, issuer_name AS name, state, zip, city,
               sum(amount_sold) OVER (PARTITION BY cik)::numeric AS value
        FROM sec_formd WHERE cik IS NOT NULL ORDER BY cik, filing_date DESC"""),
    "lda_client": ("Lobbying clients", """
        SELECT client_id::text AS key, max(client_name) AS name, max(state) AS state, NULL::text AS zip, NULL::text AS city,
               sum(spent)::numeric AS value FROM lda_client_years GROUP BY client_id"""),
    "fec_committee": ("Political committees", """
        SELECT DISTINCT ON (cmte_id) cmte_id AS key, name, state, zip, city, NULL::numeric AS value
        FROM fec_committees ORDER BY cmte_id, cycle DESC"""),
    "f5500": ("Form 5500 plan sponsors", """SELECT ein AS key, name, state, NULL::text AS zip, city,
                                                   plans::numeric AS value FROM form5500_sponsors"""),
    "op_recipient": ("Open Payments recipients", """SELECT key, name, state, NULL::text AS zip, city, total::numeric AS value
                                                    FROM op_recipients WHERE coalesce(country, 'US') IN ('US', 'United States')"""),
    "recallfirm": ("Food recall firms", """SELECT firm_id AS key, name, state, NULL::text AS zip, city, recalls::numeric AS value
                                           FROM food_recall_firms"""),
    "ip_firm": ("Patent and trademark owners", """SELECT firm_id AS key, name, state, NULL::text AS zip, city,
                                                         (coalesce(n_patents, 0) + coalesce(n_marks, 0))::numeric AS value
                                                  FROM ip_firms WHERE coalesce(hidden, false) = false
                                                    AND coalesce(country, 'US') IN ('US', 'USA', 'United States')"""),
    "ipo": ("IPO registrants", """SELECT cik AS key, name, state, zip, city, n_filings::numeric AS value FROM ipo_companies"""),
    "fed": ("Federal award recipients", """
        SELECT recipient_name || '|' || coalesce(zip5, '') AS key, max(recipient_name) AS name, max(state) AS state,
               max(zip5) AS zip, max(city) AS city, sum(total)::numeric AS value
        FROM usa_recipient_totals GROUP BY recipient_name, zip5"""),
    "biz": ("State business registrations", """
        SELECT state || ':' || entity_id AS key, name, coalesce(addr_state, state) AS state, zip, city, NULL::numeric AS value
        FROM biz_entities WHERE ein IS NOT NULL"""),
}


def _status(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def _ensure(conn) -> None:
    conn.execute(SCHEMA_SQL)
    conn.commit()


def _meta(conn, key: str, value: str) -> None:
    conn.execute("INSERT INTO census_meta (key, value, updated) VALUES (%s, %s, now()) ON CONFLICT (key) DO UPDATE SET "
                 "value = EXCLUDED.value, updated = now()", (key, value))


def _download(url: str, dest: Path, status=_status) -> Path:
    """Fetch url to dest unless it is already there (a .part file while it downloads)."""
    import httpx
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    status(f"census: downloading {url}")
    # census.gov's front door answers a burst of requests with a 200 "Request Rejected" HTML page: check the file
    # is what it should be, wait and try again (a few minutes at most), and pause between files.
    for attempt in range(5):
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=300, follow_redirects=True) as c, \
                c.stream("GET", url) as r, open(tmp, "wb") as f:
            r.raise_for_status()
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
        ok = zipfile.is_zipfile(tmp) if dest.suffix == ".zip" else tmp.stat().st_size > 1000
        if ok:
            break
        tmp.unlink(missing_ok=True)
        pause = 30 * (attempt + 1)
        status(f"census: {url}: not the file expected (rejected?); retrying in {pause}s")
        time.sleep(pause)
    else:
        raise RuntimeError(f"census: could not download {url}")
    tmp.rename(dest)
    status(f"census: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
    time.sleep(3)
    return dest


# --- GISJOIN codes -------------------------------------------------------------------------------------------------

def gisjoin(level: str, geoid: str) -> str:
    """NHGIS GISJOIN from a Census GEOID: state SS -> GSS0; county SSCCC -> GSS0CCC0; place SSPPPPP -> GSS0PPPPP;
    tract SSCCCTTTTTT -> GSS0CCC0TTTTTT."""
    g = geoid.strip()
    if level == "state":
        return f"G{g[:2]}0"
    if level == "county":
        return f"G{g[:2]}0{g[2:5]}0"
    if level == "place":
        return f"G{g[:2]}0{g[2:7]}"
    if level == "tract":
        return f"G{g[:2]}0{g[2:5]}0{g[5:11]}"
    raise ValueError(level)


def geoid_of(level: str, gj: str) -> str:
    """The inverse of gisjoin()."""
    if level == "state":
        return gj[1:3]
    if level == "county":
        return gj[1:3] + gj[4:7]
    if level == "place":
        return gj[1:3] + gj[4:9]
    if level == "tract":
        return gj[1:3] + gj[4:7] + gj[8:14]
    raise ValueError(level)


PLACE_TYPE = re.compile(r"\s+(city and borough|consolidated government \(balance\)|metropolitan government \(balance\)|"
                        r"unified government \(balance\)|metro government \(balance\)|urban county|city|town|township|"
                        r"village|borough|municipality|CDP|comunidad|zona urbana|corporation|plantation|\(balance\))$",
                        re.I)


def slugify(name: str | None) -> str:
    name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()   # Doña Ana -> Dona Ana (2026-11-13)
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:80] or "x"


def place_short(name: str | None) -> str:
    """"Austin city" -> "Austin"; "Nashville-Davidson metropolitan government (balance)" -> "Nashville-Davidson"."""
    return PLACE_TYPE.sub("", name or "").strip() or (name or "")


# --- 1. ZCTA crosswalks ---------------------------------------------------------------------------------------------

def load_xwalk(status=_status) -> dict:
    out = {}
    with db.connect() as conn:
        _ensure(conn)
        for level, fname in REL_FILES.items():
            path = _download(f"{REL_URL}/{fname}", CENSUS_DIR / fname, status)
            table = f"census_zip_{level}"
            geo_col = "GEOID_COUNTY_20" if level == "county" else "GEOID_TRACT_20"
            rows: dict[str, list] = {}
            with open(path, encoding="latin-1", newline="") as f:
                rd = csv.DictReader(f, delimiter="|")
                for r in rd:
                    z, g = (r.get("GEOID_ZCTA5_20") or "").strip(), (r.get(geo_col) or "").strip()
                    if not z or not g:
                        continue
                    part = float(r.get("AREALAND_PART") or 0) + 0.001 * float(r.get("AREAWATER_PART") or 0)
                    whole = float(r.get("AREALAND_ZCTA5_20") or 0) + 0.001 * float(r.get("AREAWATER_ZCTA5_20") or 0)
                    rows.setdefault(z, []).append([g, gisjoin(level, g), part / whole if whole > 0 else 0.0])
            n = 0
            with conn.cursor() as cur:
                cur.execute(f"CREATE TEMP TABLE xw_in (LIKE {table}) ON COMMIT DROP")
                with cur.copy("COPY xw_in (zip5, " + ("county_geoid" if level == "county" else "tract_geoid")
                              + ", gisjoin, share, dominant) FROM STDIN") as cp:
                    for z, parts in rows.items():
                        parts.sort(key=lambda p: -p[2])
                        for i, (g, gj, share) in enumerate(parts):
                            cp.write_row((z, g, gj, round(share, 4), i == 0))
                            n += 1
                cur.execute(f"DELETE FROM {table}")
                cur.execute(f"INSERT INTO {table} SELECT * FROM xw_in")
            _meta(conn, f"xwalk_{level}", f"{len(rows)} ZIPs, {n} rows, {fname}")
            conn.commit()
            conn.execute(f"ANALYZE {table}")
            conn.commit()
            out[level] = {"zips": len(rows), "rows": n}
            status(f"census: {table}: {len(rows):,} ZIPs, {n:,} rows")
    return out


# --- 2. shapes (TIGER/Line) ------------------------------------------------------------------------------------------

def _state_fips() -> list[str]:
    import shapefile
    r = shapefile.Reader(str(TIGER / TIGER_YEAR / "STATE" / f"tl_{TIGER_YEAR}_us_state.zip"))
    return sorted({rec["STATEFP"] for rec in r.records()})


def _rings(geom, tol: float) -> list:
    """The exterior rings of a (multi)polygon after simplification, coordinates rounded to 4 decimals (11 m)."""
    g = geom.simplify(tol, preserve_topology=True)
    polys = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
    out = []
    for p in polys:
        if p.is_empty:
            continue
        ring = [[round(x, 4), round(y, 4)] for x, y in p.exterior.coords]
        if len(ring) >= 4:
            out.append(ring)
    return out


def _shape_rows(path: Path, level: str, tol: float):
    """(gisjoin, level, state_fips, county_fips, geoid, name, lon, lat, aland, minx, miny, maxx, maxy, geom json)."""
    import shapefile
    from shapely.geometry import shape
    r = shapefile.Reader(str(path))
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        geoid = rec.get("GEOID") or rec.get("GEOID20")
        if not geoid or not sr.shape.points:
            continue
        g = shape(sr.shape.__geo_interface__)
        rings = _rings(g, tol)
        if not rings:
            continue
        minx, miny, maxx, maxy = g.bounds
        yield (gisjoin(level, geoid), level, rec.get("STATEFP"), rec.get("COUNTYFP"), geoid,
               rec.get("NAMELSAD") or rec.get("NAME"), float(rec["INTPTLON"]), float(rec["INTPTLAT"]),
               int(rec.get("ALAND") or 0), round(minx, 4), round(miny, 4), round(maxx, 4), round(maxy, 4),
               json.dumps(rings, separators=(",", ":")))


def _copy_shapes(conn, rows, status, label: str) -> int:
    n = 0
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE sh_in (LIKE census_shapes) ON COMMIT DROP")
        with cur.copy("COPY sh_in (gisjoin, level, state_fips, county_fips, geoid, name, lon, lat, aland, minx, miny, "
                      "maxx, maxy, geom) FROM STDIN") as cp:
            for row in rows:
                cp.write_row(row)
                n += 1
        cur.execute("INSERT INTO census_shapes SELECT * FROM sh_in ON CONFLICT (gisjoin) DO UPDATE SET level = EXCLUDED.level, "
                    "state_fips = EXCLUDED.state_fips, county_fips = EXCLUDED.county_fips, geoid = EXCLUDED.geoid, "
                    "name = EXCLUDED.name, lon = EXCLUDED.lon, lat = EXCLUDED.lat, aland = EXCLUDED.aland, minx = EXCLUDED.minx, "
                    "miny = EXCLUDED.miny, maxx = EXCLUDED.maxx, maxy = EXCLUDED.maxy, geom = EXCLUDED.geom")
    conn.commit()
    status(f"census: shapes {label}: {n:,}")
    return n


def _place_counties(conn, status) -> None:
    """Each place's county: the county its internal point falls in (places can straddle counties; this picks one)."""
    from shapely import STRtree
    from shapely.geometry import Point, Polygon
    rows = conn.execute("SELECT gisjoin, geom FROM census_shapes WHERE level = 'county'").fetchall()
    polys, keys = [], []
    for gj, geom in rows:
        for ring in geom:
            polys.append(Polygon(ring))
            keys.append(gj)
    tree = STRtree(polys)
    places = conn.execute("SELECT gisjoin, lon, lat FROM census_shapes WHERE level = 'place'").fetchall()
    found = []
    for gj, lon, lat in places:
        pt = Point(lon, lat)
        hit = tree.query(pt, predicate="within")
        if len(hit) == 0:
            hit = [tree.nearest(pt)]
        found.append((keys[hit[0]][4:7], gj))
    with conn.cursor() as cur:
        cur.executemany("UPDATE census_shapes SET county_fips = %s WHERE gisjoin = %s", found)
    conn.commit()
    status(f"census: shapes: {len(found):,} places given a county")


def load_shapes(levels: tuple[str, ...] = LEVELS, status=_status, states: list[str] | None = None) -> dict:
    out = {}
    with db.connect() as conn:
        _ensure(conn)
        if "state" in levels:
            out["state"] = _copy_shapes(conn, _shape_rows(TIGER / TIGER_YEAR / "STATE" / f"tl_{TIGER_YEAR}_us_state.zip",
                                                          "state", SIMPLIFY["state"]), status, "states")
        if "county" in levels:
            path = _download(f"{TIGER_URL}/COUNTY/tl_{TIGER_YEAR}_us_county.zip",
                             TIGER / TIGER_YEAR / "COUNTY" / f"tl_{TIGER_YEAR}_us_county.zip", status)
            out["county"] = _copy_shapes(conn, _shape_rows(path, "county", SIMPLIFY["county"]), status, "counties")
        fips = states or _state_fips()
        failed = []
        for level, folder in (("place", "PLACE"), ("tract", "TRACT")):
            if level not in levels:
                continue
            n = 0
            for sf in fips:
                p = TIGER / TIGER_YEAR / folder / f"tl_{TIGER_YEAR}_{sf}_{level}.zip"
                try:
                    if not p.exists() or not zipfile.is_zipfile(p):
                        p.unlink(missing_ok=True)
                        _download(f"{TIGER_URL}/{folder}/{p.name}", p, status)
                    n += _copy_shapes(conn, _shape_rows(p, level, SIMPLIFY[level]), status, f"{level}s {sf}")
                except Exception as ex:  # noqa: BLE001 - one state's file must not stop the rest
                    conn.rollback()
                    failed.append(f"{level} {sf}")
                    status(f"census: shapes {level} {sf} failed: {ex}")
            out[level] = n
            if level == "place":
                _place_counties(conn, status)
        if failed:
            out["failed"] = failed
            status(f"census: shapes failed for {', '.join(failed)}: run `shapes` again later")
        _meta(conn, "shapes", json.dumps(out))
        conn.commit()
        conn.execute("ANALYZE census_shapes")
        conn.commit()
    return out


# --- 3. facts: census_area ------------------------------------------------------------------------------------------

def _catalog(conn) -> dict[str, dict]:
    """ACS source code -> {nhgis_code, pg_table} for the tables loaded so far."""
    if not conn.execute("SELECT to_regclass('nhgis.tables')").fetchone()[0]:
        return {}
    out = {}
    for sc, code, pg in conn.execute("SELECT source_code, nhgis_code, pg_table FROM nhgis.tables "
                                     "WHERE dataset IN (%s, %s) ORDER BY (dataset = %s) DESC", (ACS, ACS_B, ACS)).fetchall():
        if code and sc not in out and conn.execute("SELECT to_regclass(%s)", (f'nhgis."{pg}"',)).fetchone()[0]:
            out[sc] = {"nhgis_code": code, "pg_table": pg}
    return out


def facts_sql(catalog: dict, have_dhc: bool) -> tuple[str, list[str]]:
    """The SELECT that builds census_area from the loaded tables, and the measures it could fill."""
    joins, cols, filled = [], [], []
    used = {}
    def join(table: str) -> str:
        if table not in used:
            used[table] = f"t{len(used)}"
            joins.append(f'LEFT JOIN nhgis."{catalog[table]["pg_table"]}" {used[table]} ON {used[table]}.gisjoin = g.gisjoin')
        return f"{used[table]}.{catalog[table]['nhgis_code'].lower()}e"
    for col, table, expr, *_ in MEASURES:
        others = re.findall(r"\{c:([A-Z0-9]+)\}", expr)
        if table not in catalog or any(o not in catalog for o in others):
            cols.append(f"NULL::numeric AS {col}")
            continue
        sql_expr = expr.replace("{c}", join(table))
        for o in others:
            sql_expr = sql_expr.replace("{c:" + o + "}", join(o))
        cols.append(f"({sql_expr})::numeric AS {col}")
        filled.append(col)
    dhc = ("LEFT JOIN nhgis.d_2020_dhca_p1 dhc ON dhc.gisjoin = g.gisjoin" if have_dhc else "")
    pop2020 = "dhc.u7h001" if have_dhc else "NULL::numeric"
    sql = f"""
        WITH g AS (
            SELECT DISTINCT ON (gisjoin) gisjoin, geog_level, name, stusab, context
            FROM nhgis.geo WHERE dataset IN ('{ACS}', '{DHC}') AND geog_level IN ('state', 'county', 'place', 'tract')
            ORDER BY gisjoin, (dataset = '{ACS}') DESC)
        SELECT g.gisjoin, g.geog_level AS level, g.name,
               CASE g.geog_level WHEN 'state' THEN g.context->>'STATE' WHEN 'county' THEN g.context->>'COUNTY'
                    WHEN 'place' THEN g.context->>'PLACE' ELSE split_part(g.name, ',', 1) END AS short_name,
               coalesce(g.stusab, g.context->>'STUSAB') AS stusab, g.context->>'STATEA' AS state_fips,
               g.context->>'COUNTYA' AS county_fips, g.context->>'PLACEA' AS place_fips, g.context->>'TRACTA' AS tract,
               coalesce(g.context->>'TL_GEO_ID', g.context->>'GEOCODE') AS geoid, NULL::text AS slug,
               NULL::double precision AS lat, NULL::double precision AS lon, NULL::bigint AS aland,
               ({pop2020})::numeric AS pop2020, {", ".join(cols)}, now() AS updated
        FROM g {" ".join(joins)} {dhc}"""
    return sql, filled


def _slugs(conn) -> None:
    """URL slugs: states by postal code, counties by name (travis-county), places by name without the type
    (austin); a name used twice in a state gets its FIPS code appended (oak-grove-54560)."""
    rows = conn.execute("SELECT gisjoin, level, stusab, short_name, county_fips, place_fips, geoid FROM census_area "
                        "WHERE level IN ('state', 'county', 'place')").fetchall()
    by_key: dict[tuple, list] = {}
    for gj, level, st, short, cf, pf, geoid in rows:
        if level == "state":
            slug = (st or geoid or gj).lower()
        elif level == "county":
            slug = slugify(short)
        else:
            slug = slugify(place_short(short))
        by_key.setdefault((level, st, slug), []).append((gj, cf if level == "county" else pf))
    out = []
    for (level, st, slug), items in by_key.items():
        if len(items) == 1:
            out.append((slug, items[0][0]))
        else:
            for gj, code in items:
                out.append((f"{slug}-{code}", gj))
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE slug_in (slug text, gisjoin text) ON COMMIT DROP")
        with cur.copy("COPY slug_in (slug, gisjoin) FROM STDIN") as cp:
            for r in out:
                cp.write_row(r)
        cur.execute("UPDATE census_area a SET slug = s.slug FROM slug_in s WHERE s.gisjoin = a.gisjoin")
        cur.execute("UPDATE census_area SET slug = geoid WHERE level = 'tract'")
    conn.commit()


def build_facts(status=_status) -> dict:
    with db.connect() as conn:
        _ensure(conn)
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '512MB'")
        if not conn.execute("SELECT to_regclass('nhgis.geo')").fetchone()[0]:
            status("census: nhgis.geo is not loaded yet; nothing to build")
            return {}
        catalog = _catalog(conn)
        have_dhc = bool(conn.execute("SELECT to_regclass('nhgis.d_2020_dhca_p1')").fetchone()[0])
        sql, filled = facts_sql(catalog, have_dhc)
        conn.execute("DROP TABLE IF EXISTS census_area_new")
        conn.execute("CREATE TABLE census_area_new (LIKE census_area INCLUDING ALL)")
        conn.execute("INSERT INTO census_area_new " + sql)
        conn.execute("""UPDATE census_area_new a SET lat = s.lat, lon = s.lon, aland = s.aland,
                            county_fips = CASE WHEN a.level = 'place' THEN coalesce(s.county_fips, a.county_fips) ELSE a.county_fips END
                        FROM census_shapes s WHERE s.gisjoin = a.gisjoin""")
        conn.execute("CREATE INDEX ON census_area_new (level, stusab, slug)")
        conn.execute("CREATE INDEX ON census_area_new (level, state_fips, county_fips)")
        conn.execute("CREATE INDEX ON census_area_new (level, population DESC)")
        conn.commit()
        db.swap_table(conn, "census_area")
        _slugs(conn)
        n = {r[0]: r[1] for r in conn.execute("SELECT level, count(*) FROM census_area GROUP BY 1").fetchall()}
        _meta(conn, "facts", json.dumps({"rows": n, "measures": filled, "missing": [c for c in MEASURE_COLUMNS
                                                                                    if c not in filled]}))
        conn.commit()
        conn.execute("ANALYZE census_area")
        conn.commit()
    status(f"census: census_area {n}; measures filled: {len(filled)}/{len(MEASURES)} "
           f"(missing: {', '.join(c for c in MEASURE_COLUMNS if c not in filled) or 'none'})")
    return {"rows": n, "filled": filled}


# --- 4. links: every FURP record -> its areas --------------------------------------------------------------------------

CITY_MATCH_SQL = """
    CREATE TEMP TABLE city_match AS
    SELECT gp.state, gp.place_norm, 'G' || left(gp.geoid, 2) || '0' || substr(gp.geoid, 3) AS place_gj,
           a.county_fips, CASE WHEN a.county_fips IS NOT NULL THEN 'G' || left(gp.geoid, 2) || '0' || a.county_fips || '0' END AS county_gj
    FROM geo_places gp
    JOIN census_area a ON a.gisjoin = 'G' || left(gp.geoid, 2) || '0' || substr(gp.geoid, 3) AND a.level = 'place'
    WHERE gp.geoid IS NOT NULL AND length(gp.geoid) = 7;
    CREATE INDEX ON city_match (state, place_norm);
    ANALYZE city_match;
"""

LINK_SQL = """
    INSERT INTO {target} (kind, key, name, state, zip5, city, state_gj, county_gj, place_gj, tract_gj, how, value)
    SELECT %(kind)s, s.key, left(s.name, 200), s.st, s.zip5, left(s.city, 80),
           CASE WHEN st.gisjoin IS NOT NULL THEN st.gisjoin END,
           coalesce(zc.gisjoin, cm.county_gj), cm.place_gj, zt.gisjoin,
           CASE WHEN zc.gisjoin IS NOT NULL AND cm.place_gj IS NOT NULL THEN 'zip+city'
                WHEN zc.gisjoin IS NOT NULL THEN 'zip' WHEN cm.place_gj IS NOT NULL THEN 'city'
                WHEN st.gisjoin IS NOT NULL THEN 'state' END,
           s.value
    FROM (SELECT x.key, x.name, upper(left(trim(x.state), 2)) AS st,
                 CASE WHEN x.zip ~ '^[0-9]{{5}}' THEN left(x.zip, 5) END AS zip5, x.city, x.value
          FROM ({source}) x WHERE x.key IS NOT NULL) s
    LEFT JOIN census_area st ON st.level = 'state' AND st.stusab = s.st
    LEFT JOIN census_zip_county zc ON zc.zip5 = s.zip5 AND zc.dominant
    LEFT JOIN census_zip_tract zt ON zt.zip5 = s.zip5 AND zt.dominant
    LEFT JOIN city_match cm ON s.city IS NOT NULL AND cm.state = s.st AND cm.place_norm = census_city_norm(s.city)
    WHERE s.st IS NOT NULL OR s.zip5 IS NOT NULL
    ON CONFLICT (kind, key) DO NOTHING
"""


def build_links(kinds: list[str] | None = None, status=_status, rebuild: bool = True) -> dict:
    """census_links for the given kinds (default: every kind but the heavy ones). With rebuild, the table is built
    beside the live one and swapped in; without, the given kinds are replaced in place (for the heavy kinds, added
    after the first build)."""
    kinds = kinds or [k for k in SOURCES if k not in HEAVY_KINDS]
    bad = [k for k in kinds if k not in SOURCES]
    if bad:
        raise SystemExit(f"unknown kinds: {bad}; known: {', '.join(SOURCES)}")
    out = {}
    with db.connect() as conn:
        _ensure(conn)
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '1GB'")
        if not conn.execute("SELECT count(*) FROM census_area WHERE level = 'place'").fetchone()[0]:
            raise SystemExit("census_area has no places yet: run `facts` first")
        conn.execute(CITY_MATCH_SQL)
        target = "census_links_new" if rebuild else "census_links"
        if rebuild:
            conn.execute("DROP TABLE IF EXISTS census_links_new")
            conn.execute("CREATE TABLE census_links_new (LIKE census_links INCLUDING ALL)")
            # The heavy kinds already built stay (they cost a quiet night each).
            conn.execute("INSERT INTO census_links_new SELECT * FROM census_links WHERE kind = ANY(%s) AND NOT (kind = ANY(%s))",
                         (list(HEAVY_KINDS), kinds))
        conn.commit()
        for kind in kinds:
            t0 = time.time()
            label, source = SOURCES[kind]
            if not rebuild:
                conn.execute("DELETE FROM census_links WHERE kind = %s", (kind,))
            conn.execute(LINK_SQL.format(target=target, source=source), {"kind": kind})
            n = conn.execute(f"SELECT count(*), count(county_gj), count(place_gj), count(tract_gj) FROM {target} WHERE kind = %s",
                             (kind,)).fetchone()
            conn.commit()
            out[kind] = {"rows": n[0], "county": n[1], "place": n[2], "tract": n[3]}
            status(f"census: links {kind} ({label}): {n[0]:,} rows, county {n[1]:,}, place {n[2]:,}, tract {n[3]:,} "
                   f"({time.time() - t0:.0f}s)")
        if rebuild:
            conn.execute("CREATE INDEX ON census_links_new (county_gj, kind, value DESC NULLS LAST)")
            conn.execute("CREATE INDEX ON census_links_new (place_gj, kind, value DESC NULLS LAST)")
            conn.execute("CREATE INDEX ON census_links_new (tract_gj, kind)")
            conn.execute("CREATE INDEX ON census_links_new (state_gj, kind, value DESC NULLS LAST)")
            conn.commit()
            db.swap_table(conn, "census_links")
        _meta(conn, "links", json.dumps(out))
        conn.commit()
        conn.execute("ANALYZE census_links")
        conn.commit()
    return out


# --- 5. stats: per-area summaries and the top people ------------------------------------------------------------------

STATS_SQL = """
    INSERT INTO census_area_furp_new (gisjoin, kind, n, total, top_key, top_name, top_value)
    SELECT {col}, kind, count(*), sum(value),
           (array_agg(key ORDER BY value DESC NULLS LAST))[1], (array_agg(name ORDER BY value DESC NULLS LAST))[1],
           max(value)
    FROM census_links WHERE {col} IS NOT NULL GROUP BY {col}, kind
"""

PEOPLE_SQL = """
    CREATE TABLE census_area_people_new AS
    WITH p AS (
        SELECT m.cluster_id, p.name_raw AS name, p.title, p.ein, p.tax_year,
               (coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0))::numeric AS total,
               row_number() OVER (PARTITION BY m.cluster_id ORDER BY p.tax_year DESC,
                                  coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) DESC) AS rn
        FROM people p JOIN person_cluster_members m ON m.person_id = p.id
        WHERE NOT p.is_duplicate AND coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) >= %(min_pay)s
          AND p.tax_year >= %(min_year)s),
    j AS (
        SELECT p.cluster_id, p.name, p.title, p.ein, l.name AS org_name, p.tax_year, p.total,
               l.state_gj, l.county_gj, l.place_gj
        FROM p JOIN census_links l ON l.kind = 'org' AND l.key = p.ein WHERE p.rn = 1 {where}),
    r AS (
        SELECT j.*, row_number() OVER (PARTITION BY state_gj ORDER BY total DESC) AS rank_state,
               row_number() OVER (PARTITION BY county_gj ORDER BY total DESC) AS rank_county,
               row_number() OVER (PARTITION BY place_gj ORDER BY total DESC) AS rank_place
        FROM j)
    SELECT cluster_id, name, title, ein, org_name, tax_year, total, state_gj, county_gj, place_gj,
           rank_state::int, rank_county::int, rank_place::int
    FROM r WHERE rank_state <= %(keep)s OR rank_county <= %(keep)s OR rank_place <= %(keep)s
"""


def build_stats(status=_status, state: str | None = None, min_pay: int = 50_000, keep: int = 100) -> dict:
    out = {}
    with db.connect() as conn:
        _ensure(conn)
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '1GB'")
        conn.execute("DROP TABLE IF EXISTS census_area_furp_new")
        conn.execute("CREATE TABLE census_area_furp_new (LIKE census_area_furp INCLUDING ALL)")
        for col in ("state_gj", "county_gj", "place_gj", "tract_gj"):
            conn.execute(STATS_SQL.format(col=col))
            conn.commit()
        db.swap_table(conn, "census_area_furp")
        out["area_furp"] = conn.execute("SELECT count(*) FROM census_area_furp").fetchone()[0]
        status(f"census: census_area_furp {out['area_furp']:,} rows")
        conn.execute("DROP TABLE IF EXISTS census_area_people_new")
        where = "AND l.state = %(state)s" if state else ""
        conn.execute(PEOPLE_SQL.format(where=where), {"min_pay": min_pay, "min_year": 2018, "keep": keep, "state": state})
        conn.execute("CREATE INDEX ON census_area_people_new (county_gj, rank_county)")
        conn.execute("CREATE INDEX ON census_area_people_new (place_gj, rank_place)")
        conn.execute("CREATE INDEX ON census_area_people_new (state_gj, rank_state)")
        conn.execute("CREATE INDEX ON census_area_people_new (cluster_id)")
        conn.commit()
        db.swap_table(conn, "census_area_people")
        out["area_people"] = conn.execute("SELECT count(*) FROM census_area_people").fetchone()[0]
        _meta(conn, "stats", json.dumps(out))
        conn.commit()
        for t in ("census_area_furp", "census_area_people"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
        status(f"census: census_area_people {out['area_people']:,} rows")
    return out


# --- the command line ---------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("xwalk")
    s = sub.add_parser("shapes")
    s.add_argument("--levels", nargs="+", default=list(LEVELS), choices=LEVELS)
    s.add_argument("--states", nargs="+", help="state FIPS codes (default: all)")
    sub.add_parser("facts")
    lk = sub.add_parser("links")
    lk.add_argument("--kinds", help="comma-separated kinds (default: every kind but " + ", ".join(HEAVY_KINDS) + ")")
    lk.add_argument("--add", action="store_true", help="replace just these kinds in the live table (no rebuild)")
    st = sub.add_parser("stats")
    st.add_argument("--state", help="only organizations in this state (for a quick test build)")
    sub.add_parser("all")
    a = p.parse_args(argv)
    if a.cmd == "xwalk":
        load_xwalk()
    elif a.cmd == "shapes":
        offpeak.wait("census shapes")
        load_shapes(tuple(a.levels), states=a.states)
    elif a.cmd == "facts":
        build_facts()
    elif a.cmd == "links":
        kinds = [k.strip() for k in a.kinds.split(",")] if a.kinds else None
        if kinds is None or any(k in HEAVY_KINDS for k in kinds) or not a.add:
            offpeak.wait("census links")
        build_links(kinds, rebuild=not a.add)
    elif a.cmd == "stats":
        offpeak.wait("census stats")
        build_stats(state=a.state)
    else:
        load_xwalk()
        offpeak.wait("census shapes")
        load_shapes()
        build_facts()
        build_links()
        build_stats()
    return 0


if __name__ == "__main__":
    sys.exit(main())
