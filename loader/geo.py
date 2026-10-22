"""Map-ready places from Census files (downloaded to /data/tiger): where each record is, at the ZIP or city level,
and which districts that is in.

- ZIP points: the internal point of each ZIP Code Tabulation Area (2026 Gazetteer).
- City points: the internal point of each Census place, by state and normalized name (2026 Gazetteer); a city
  and a CDP of the same name: the incorporated one.
- Districts (TIGER/Line shapes): congressional for the 119th Congress (TIGER 2025; the members now serving) and
  the 120th (TIGER 2026; the November 2026 election), state senate (SLDU) and state house (SLDL), 2026.
- geo_zip_districts: each ZIP's share of land in every district it crosses, from the shapes (the Census
  relationship files do this for 2020 districts only; many states have redrawn since). A ZIP's district is the
  one holding most of it; a city's is the one its point falls in.

Records join these by ZIP (zip5), else city and state (app/geo.py). Nothing here is per person: individuals are
placed at their city, organizations at their ZIP.

Usage: .venv/bin/python -m loader.geo [--rates]
"""

from __future__ import annotations

import csv
import io
import re
import sys
import time
import zipfile
from pathlib import Path

from loader import db

TIGER = Path("/data/tiger")
GAZ = TIGER / "gazetteer" / "2026"
LAYERS = {   # kind: (folder, glob, district code field)
    "cd119": ("2025/CD", "tl_2025_*_cd119.zip", "CD119FP"),
    "cd120": ("2026/CD", "tl_2026_*_cd120.zip", "CD120FP"),
    "sldu": ("2026/SLDU", "tl_2026_*_sldu.zip", "SLDUST"),
    "sldl": ("2026/SLDL", "tl_2026_*_sldl.zip", "SLDLST"),
}
SIMPLIFY = 0.0003          # degrees (about 30 m): district outlines lose detail no share could notice
PLACE_TYPES = r"(city and borough|consolidated government \(balance\)|metropolitan government \(balance\)|" \
              r"unified government \(balance\)|metro government \(balance\)|\(balance\)|city|town|township|village|" \
              r"borough|municipality|cdp|comunidad|zona urbana|corporation|plantation|urban county)$"


def place_norm(name: str | None) -> str:
    """ "St. Louis city" and "SAINT LOUIS" are "saint louis"; "Ft Worth" is "fort worth"."""
    s = re.sub(r"\s+", " ", (name or "").lower().replace("&", " and ")).strip()
    s = re.sub(PLACE_TYPES, "", s).strip()                  # "... (balance)": before punctuation goes
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(PLACE_TYPES, "", s).strip()
    s = re.sub(r"^(st|ste)\b", "saint", s)
    s = re.sub(r"^ft\b", "fort", s)
    s = re.sub(r"^mt\b", "mount", s)
    return s


def _gaz(name: str) -> list[dict]:
    z = zipfile.ZipFile(GAZ / name)
    text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(text), delimiter="|"))
    return [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def _states() -> dict[str, str]:
    import shapefile
    r = shapefile.Reader(str(TIGER / "2026/STATE/tl_2026_us_state.zip"))
    return {rec["STATEFP"]: rec["STUSPS"] for rec in r.records()}


def _code(kind: str, usps: str, raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw or set(raw) <= {"Z"}:
        return None                                   # water or undefined
    if kind.startswith("cd"):
        return f"{usps}-AL" if raw in ("00", "98") else f"{usps}-{int(raw):02d}"
    return f"{usps}-{'U' if kind == 'sldu' else 'L'}-{raw.lstrip('0') or '0'}"


def districts(kind: str, states: dict, status=print) -> list[tuple]:
    """[(code, state, name, lat, lon, shapely geometry)] for one district layer."""
    import shapefile
    from shapely.geometry import shape
    folder, pattern, field = LAYERS[kind]
    out = []
    for path in sorted((TIGER / folder).glob(pattern)):
        r = shapefile.Reader(str(path))
        for sr in r.iterShapeRecords():
            rec = sr.record.as_dict()
            usps = states.get(rec["STATEFP"])
            code = _code(kind, usps, rec.get(field)) if usps else None
            if not code or not sr.shape.points:
                continue
            g = shape(sr.shape.__geo_interface__).simplify(SIMPLIFY, preserve_topology=True)
            out.append((code, usps, rec.get("NAMELSAD") or code, float(rec["INTPTLAT"]), float(rec["INTPTLON"]), g))
    status(f"geo: {kind}: {len(out):,} districts")
    return out


def build(status=print) -> dict:
    import shapefile
    from shapely import STRtree
    from shapely.geometry import Point, shape
    t0 = time.time()
    states = _states()
    zips = {r["GEOID"]: (float(r["INTPTLAT"]), float(r["INTPTLONG"])) for r in _gaz("2026_Gaz_zcta_national.zip")}
    places: dict[tuple, dict] = {}
    for r in _gaz("2026_Gaz_place_national.zip"):
        key = (r["USPS"], place_norm(r["NAME"]))
        rank = (r["FUNCSTAT"] == "A", int(r["ALAND"] or 0))
        if key[1] and (key not in places or rank > places[key]["rank"]):
            places[key] = {"name": r["NAME"], "geoid": r["GEOID"], "lat": float(r["INTPTLAT"]),
                           "lon": float(r["INTPTLONG"]), "rank": rank}
    # "Nashville-Davidson" and "Louisville/Jefferson County" are filed as Nashville and Louisville: their first part
    # is a second key, unless a place already has that name.
    for (st, pn), p in list(places.items()):
        first = place_norm(re.split(r"[-/]", p["name"])[0])
        if first and first != pn and (st, first) not in places:
            places[(st, first)] = dict(p)
    status(f"geo: {len(zips):,} ZIPs, {len(places):,} places")
    zip_primary: dict[str, dict] = {z: {} for z in zips}
    place_d: dict[tuple, dict] = {k: {} for k in places}
    shares, dist_rows = [], []
    for kind in LAYERS:
        ds = districts(kind, states, status)
        dist_rows += [(kind, d[0], d[1], d[2], d[3], d[4]) for d in ds]
        tree = STRtree([d[5] for d in ds])
        for key, p in places.items():                               # a city's district: where its point falls
            for i in tree.query(Point(p["lon"], p["lat"]), predicate="within"):
                if ds[i][1] == key[0]:
                    place_d[key][kind] = ds[i][0]
                    break
        zr = shapefile.Reader(str(TIGER / "2026/ZCTA520/tl_2026_us_zcta520.zip"))
        n = 0
        for sr in zr.iterShapeRecords():                            # a ZIP's districts: its land in each
            z = sr.record.as_dict()["ZCTA5CE20"]
            g = shape(sr.shape.__geo_interface__)
            if g.area <= 0:
                continue
            parts = []
            for i in tree.query(g, predicate="intersects"):
                a = g.intersection(ds[i][5]).area / g.area
                if a >= 0.01:
                    parts.append((a, ds[i][0]))
            if parts:
                parts.sort(reverse=True)
                if z in zip_primary:
                    zip_primary[z][kind] = parts[0][1]
                shares += [(z, kind, c, round(a, 4)) for a, c in parts]
            n += 1
        status(f"geo: {kind}: {n:,} ZIPs placed ({time.time() - t0:.0f}s)")
        del ds, tree
    with db.connect() as conn:
        conn.execute("TRUNCATE geo_districts, geo_zips, geo_places, geo_zip_districts")
        with conn.cursor() as cur:
            with cur.copy("COPY geo_districts (kind, code, state, name, lat, lon) FROM STDIN") as cp:
                for r in dist_rows:
                    cp.write_row(r)
            with cur.copy("COPY geo_zips (zip5, lat, lon, cd119, cd120, sldu, sldl) FROM STDIN") as cp:
                for z, (lat, lon) in zips.items():
                    d = zip_primary.get(z, {})
                    cp.write_row((z, lat, lon, d.get("cd119"), d.get("cd120"), d.get("sldu"), d.get("sldl")))
            with cur.copy("COPY geo_places (state, place_norm, name, geoid, lat, lon, cd119, cd120, sldu, sldl) "
                          "FROM STDIN") as cp:
                for (st, pn), p in places.items():
                    d = place_d[(st, pn)]
                    cp.write_row((st, pn, p["name"], p["geoid"], p["lat"], p["lon"], d.get("cd119"), d.get("cd120"),
                                  d.get("sldu"), d.get("sldl")))
            with cur.copy("COPY geo_zip_districts (zip5, kind, code, share) FROM STDIN") as cp:
                for r in shares:
                    cp.write_row(r)
        conn.commit()
        for t in ("geo_districts", "geo_zips", "geo_places", "geo_zip_districts"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
    out = {"zips": len(zips), "places": len(places), "districts": len(dist_rows), "zip_district_rows": len(shares)}
    status(f"geo: built {out} in {time.time() - t0:.0f}s")
    return out


# Where each kind of record's location comes from (ZIP first for organizations; city first for individuals).
SOURCES = {
    "nonprofits": ("SELECT left(zip, 5) AS zip5, city, state FROM organizations", "zip"),
    "contractors": ("SELECT left(zip, 5) AS zip5, city, state FROM contractors", "zip"),
    "federal recipients": ("SELECT zip5, city, state FROM usa_awards TABLESAMPLE SYSTEM (0.5)", "zip"),
    "political donors": ("SELECT zip5, city, state FROM fec_contributions TABLESAMPLE SYSTEM (0.2)", "city"),
}


def rates(status=print) -> dict:
    """Share of each kind of record placed at its ZIP, at its city, or at all (federal recipients and donors from
    a random sample of rows). Matching here is the same as app/geo.py's."""
    out = {}
    with db.connect() as conn:
        conn.execute("SET statement_timeout = '20min'")
        zipset = {r[0] for r in conn.execute("SELECT zip5 FROM geo_zips").fetchall()}
        placeset = {(r[0], r[1]) for r in conn.execute("SELECT state, place_norm FROM geo_places").fetchall()}
        for kind, (sql, first) in SOURCES.items():
            n = by_zip = by_city = placed = 0
            with conn.cursor(name=f"geo_rates_{n}_{len(out)}") as cur:
                cur.itersize = 100_000
                cur.execute(sql)
                for z, c, st in cur:
                    n += 1
                    zi = z in zipset
                    ci = (st, place_norm(c)) in placeset
                    by_zip += zi
                    by_city += ci
                    placed += zi or ci
            out[kind] = {"rows": n, "zip_pct": round(100 * by_zip / max(1, n), 1),
                         "city_pct": round(100 * by_city / max(1, n), 1),
                         "placed_pct": round(100 * placed / max(1, n), 1), "first": first}
            status(f"geo: {kind}: {n:,} rows; ZIP {out[kind]['zip_pct']}%, city {out[kind]['city_pct']}%, "
                   f"placed {out[kind]['placed_pct']}% ({first} first)")
    return out


if __name__ == "__main__":
    if "--rates" in sys.argv:
        rates()
    else:
        build()
