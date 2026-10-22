"""Map-ready exports: every row placed at its ZIP code's center (organizations, contractors, recipients), or its
city's (individuals, and anything without a ZIP), with the congressional district (119th Congress, the members
now serving), state senate and state house district there. Tables from loader/geo.py.

Two formats, both built to drop straight into Datawrapper, Google My Maps and Mapshaper:
  CSV      header row, one row per record, latitude/longitude columns, no footer (the credit is a column)
  GeoJSON  a FeatureCollection of points; rows that can't be placed are left out and counted in "metadata"
"""

from __future__ import annotations

import datetime as dt
import io
import json
import re

from app import db
from app.config import SITE_URL

GEO_FIELDS = ["city", "state", "zip", "congressional_district", "state_senate_district", "state_house_district",
              "latitude", "longitude", "location_level"]
ZIP_KEYS = ("zip", "zip5", "postal_code", "zip_code")


_ready: list = []


def ready() -> bool:
    """True once loader/geo.py has filled the tables (checked every ten minutes): until then pages show no map
    buttons, rather than exports without coordinates."""
    import time
    if not _ready or time.time() - _ready[0] > 600:
        try:
            with db.conn() as conn:
                ok = conn.execute("SELECT EXISTS (SELECT 1 FROM geo_zips) AS x").fetchone()["x"]
        except Exception:  # noqa: BLE001 - tables not there yet
            ok = False
        _ready[:] = [time.time(), bool(ok)]
    return _ready[1]


def place_norm(name):
    from loader.geo import place_norm as pn
    return pn(name)


def _zip5(v) -> str | None:
    m = re.match(r"\s*(\d{5})", str(v or ""))
    return m.group(1) if m else None


def _fill_from_records(rows: list[dict]) -> None:
    """Rows that name an organization, vendor or recalling firm but carry no address get its address."""
    eins = {r["ein"] for r in rows if r.get("ein") and not r.get("_zip") and not r.get("_city")}
    vendors = {r["subject_key"] for r in rows if r.get("subject_kind") == "vendor" and not r.get("_zip")}
    firms = {r.get("firm_id") or r.get("subject_key") for r in rows
             if (r.get("subject_kind") == "recallfirm" or r.get("firm_id")) and not r.get("_zip")}
    with db.conn() as conn:
        orgs = {x["ein"]: x for x in conn.execute(
            "SELECT ein, left(zip, 5) AS zip, city, state FROM organizations WHERE ein = ANY(%s)",
            (sorted(eins),)).fetchall()} if eins else {}
        vend = {x["name_norm"]: x for x in conn.execute(
            """SELECT DISTINCT ON (name_norm) name_norm, left(zip, 5) AS zip, city, state FROM contractors
               WHERE name_norm = ANY(%s) AND zip IS NOT NULL ORDER BY name_norm, id DESC""",
            (sorted(vendors),)).fetchall()} if vendors else {}
        frm = {x["firm_id"]: x for x in conn.execute(
            """SELECT DISTINCT ON (firm_id) firm_id, left(postal_code, 5) AS zip, city, state FROM food_recalls
               WHERE firm_id = ANY(%s) ORDER BY firm_id, recall_initiation_date DESC NULLS LAST""",
            (sorted(f for f in firms if f),)).fetchall()} if firms else {}
    for r in rows:
        src = (orgs.get(r.get("ein")) or (vend.get(r.get("subject_key")) if r.get("subject_kind") == "vendor" else None)
               or frm.get(r.get("firm_id") or (r.get("subject_key") if r.get("subject_kind") == "recallfirm" else None)))
        if src and not r.get("_zip") and not r.get("_city"):
            r["_zip"], r["_city"], r["_state"] = _zip5(src["zip"]), src["city"], src["state"] or r.get("_state")


def locate(rows: list[dict], individuals: bool = False) -> list[dict]:
    """Copies of rows with GEO_FIELDS added. individuals=True places at the city first (people), otherwise at the
    ZIP first."""
    work = []
    for r in rows:
        w = dict(r)
        w["_zip"] = next((_zip5(r.get(k)) for k in ZIP_KEYS if _zip5(r.get(k))), None)
        w["_city"] = r.get("city")
        w["_state"] = (r.get("state") or "").upper()[:2] or None
        work.append(w)
    _fill_from_records(work)
    zips = {w["_zip"] for w in work if w["_zip"]}
    places = {(w["_state"], place_norm(w["_city"])) for w in work if w["_city"] and w["_state"]}
    with db.conn() as conn:
        zrows = {x["zip5"]: x for x in conn.execute("SELECT * FROM geo_zips WHERE zip5 = ANY(%s)",
                                                    (sorted(zips),)).fetchall()} if zips else {}
        prows = {}
        if places:
            st, pn = zip(*sorted(places))
            prows = {(x["state"], x["place_norm"]): x for x in conn.execute(
                """SELECT g.* FROM geo_places g JOIN unnest(%s::text[], %s::text[]) AS q(state, place_norm)
                   USING (state, place_norm)""", (list(st), list(pn))).fetchall()}
    out = []
    for w in work:
        z = zrows.get(w["_zip"])
        p = prows.get((w["_state"], place_norm(w["_city"]))) if w["_city"] else None
        pick, level = ((p, "city") if p else (z, "ZIP")) if individuals else ((z, "ZIP") if z else (p, "city"))
        if not pick:
            level = None
        o = {k: v for k, v in w.items() if not k.startswith("_")}
        o.update({"city": (w["_city"] or "").title() or None, "state": w["_state"], "zip": w["_zip"],
                  "congressional_district": pick["cd119"] if pick else None,
                  "state_senate_district": pick["sldu"] if pick else None,
                  "state_house_district": pick["sldl"] if pick else None,
                  "latitude": round(pick["lat"], 6) if pick else None,
                  "longitude": round(pick["lon"], 6) if pick else None, "location_level": level})
        out.append(o)
    return out


def _scalar(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return None
    return float(v) if v.__class__.__name__ == "Decimal" else v


def fields_for(rows: list[dict], first: list[str] | None = None) -> list[str]:
    """The columns: the given ones first, then every other plain field the rows have, then the location."""
    seen = list(first or [])
    for r in rows[:50]:
        for k, v in r.items():
            if k not in seen and k not in GEO_FIELDS and not k.startswith("_") and not isinstance(v, dict):
                seen.append(k)
    return [k for k in seen if k not in GEO_FIELDS] + GEO_FIELDS + ["source"]


def to_csv(rows: list[dict], fields: list[str], source: str) -> str:
    import csv
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({**{k: _scalar(r.get(k)) for k in fields}, "source": source})
    return buf.getvalue()


def to_geojson(rows: list[dict], fields: list[str], source: str) -> str:
    feats, missing = [], 0
    for r in rows:
        if r.get("latitude") is None:
            missing += 1
            continue
        props = {k: _scalar(r.get(k)) for k in fields if k not in ("latitude", "longitude")}
        props["source"] = source
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
                      "properties": props})
    return json.dumps({"type": "FeatureCollection", "features": feats,
                       "metadata": {"source": source, "rows_without_location": missing,
                                    "location": "ZIP code or city center points (Census 2026 Gazetteer); districts "
                                                "from Census TIGER/Line shapes"}}, default=str)


def response(rows: list[dict], fields: list[str], fmt: str, name: str, page_path: str):
    from fastapi.responses import Response
    today = dt.date.today().isoformat()
    source = f"furp.org, {SITE_URL}{page_path}, retrieved {today}"
    safe = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "data"
    if fmt == "geojson":
        return Response(to_geojson(rows, fields, source), media_type="application/geo+json",
                        headers={"Content-Disposition": f'attachment; filename="furp-{safe}-{today}.geojson"'})
    return Response(to_csv(rows, fields, source), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="furp-{safe}-map-{today}.csv"'})
