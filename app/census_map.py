"""Server-rendered SVG maps for the census pages (owner, 2026-11-12: "display with the geo map stuff we already
downloaded"). No JavaScript and no tile server: the Content Security Policy allows scripts from 'self' only, so the
maps are inline SVG drawn from the simplified TIGER/Line outlines in census_shapes (loader/census.py shapes), each
area a link to its page, shaded by a census measure with a legend, and the FURP records in the area as circles at
their ZIP code centers (geo_zips, as app/geo.py places them).

Projections: the United States map is an Albers equal-area conic with Alaska, Hawaii and Puerto Rico moved in as
insets (the usual "Albers USA"); a state's or county's map is a plate carree scaled by the cosine of its middle
latitude, which looks right at this size. Everything is computed from numbers already in memory: the outlines of a
state's counties or a county's tracts come from one query, cached an hour.
"""

from __future__ import annotations

import math
from html import escape

from markupsafe import Markup

from app import db
from app.cache import ttl_lru

WIDTH = 820
LOCATOR_WIDTH = 320
PALETTE = ["#eef3f8", "#c6dbef", "#85bcdb", "#3e8ec4", "#0b559f"]       # five classes, light to dark
NO_DATA = "#e6e6e6"
POINT = "#c0392b"
HIGHLIGHT = "#e67e22"
OUTLINE = "#ffffff"
INSETS = {"02": (0.35, 0.02, 0.63), "15": (1.0, 0.30, 0.80), "72": (1.0, 0.86, 0.80)}   # AK, HI, PR: scale, x, y (as shares)


# --- the outlines ----------------------------------------------------------------------------------------------------

@ttl_lru(ttl=3600, maxsize=256)
def shapes(level: str, state_fips: str | None = None, county_fips: str | None = None) -> list[dict]:
    """The outlines at one level: every state, a state's counties or places, a county's tracts or places."""
    sql = "SELECT gisjoin, level, name, geoid, lon, lat, minx, miny, maxx, maxy, geom FROM census_shapes WHERE level = %s"
    params: list = [level]
    if state_fips:
        sql += " AND state_fips = %s"
        params.append(state_fips)
    if county_fips:
        sql += " AND county_fips = %s"
        params.append(county_fips)
    try:
        with db.conn(timeout="20s") as conn:
            return [dict(r) for r in conn.execute(sql + " ORDER BY gisjoin", params).fetchall()]
    except Exception:  # noqa: BLE001 - shapes not loaded yet
        return []


@ttl_lru(ttl=3600, maxsize=4096)
def shape(gisjoin: str) -> dict | None:
    try:
        with db.conn() as conn:
            r = conn.execute("SELECT gisjoin, level, name, geoid, lon, lat, minx, miny, maxx, maxy, geom FROM census_shapes "
                             "WHERE gisjoin = %s", (gisjoin,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return dict(r) if r else None


# --- projections --------------------------------------------------------------------------------------------------------

def _albers(lon: float, lat: float, lon0=-96.0, lat0=23.0, p1=29.5, p2=45.5) -> tuple[float, float]:
    """Albers equal-area conic (the conterminous United States' usual parameters), in abstract units."""
    lon, lat, lon0, lat0, p1, p2 = (math.radians(v) for v in (lon, lat, lon0, lat0, p1, p2))
    n = (math.sin(p1) + math.sin(p2)) / 2
    c = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    rho = math.sqrt(c - 2 * n * math.sin(lat)) / n
    rho0 = math.sqrt(c - 2 * n * math.sin(lat0)) / n
    theta = n * (lon - lon0)
    return rho * math.sin(theta), -(rho0 - rho * math.cos(theta))


def _fix_lon(lon: float) -> float:
    return lon - 360 if lon > 0 else lon        # the Aleutians cross the antimeridian


class _Flat:
    """Plate carree around a center, x scaled by cos(latitude): fine for one state or county."""

    def __init__(self, lon0: float, lat0: float):
        self.lon0, self.lat0, self.k = lon0, lat0, max(math.cos(math.radians(lat0)), 0.2)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        return (_fix_lon(lon) - self.lon0) * self.k, -(lat - self.lat0)


def _bounds(points) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


class _Frame:
    """Projected coordinates -> pixel coordinates in a viewBox of the given width (height follows the shape)."""

    def __init__(self, bounds, width: int, pad: int = 6, max_height: int | None = None):
        x0, y0, x1, y1 = bounds
        w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        self.scale = (width - 2 * pad) / w
        self.height = int(h * self.scale) + 2 * pad
        if max_height and self.height > max_height:
            self.scale = (max_height - 2 * pad) / h
            self.height = max_height
        self.width = int(w * self.scale) + 2 * pad if max_height and self.height == max_height else width
        self.x0, self.y0, self.pad = x0, y0, pad

    def px(self, x: float, y: float) -> tuple[float, float]:
        return self.pad + (x - self.x0) * self.scale, self.pad + (y - self.y0) * self.scale


# --- drawing --------------------------------------------------------------------------------------------------------------

def _path(rings, proj, frame, decimals: int = 1) -> str:
    """An SVG path (relative moves, duplicates dropped) for a list of lon/lat rings."""
    parts = []
    for ring in rings:
        pts = []
        for lon, lat in ring:
            x, y = frame.px(*proj(lon, lat))
            x, y = round(x, decimals), round(y, decimals)
            if not pts or (x, y) != pts[-1]:
                pts.append((x, y))
        if len(pts) < 3:
            continue
        d = [f"M{pts[0][0]:g} {pts[0][1]:g}"]
        px, py = pts[0]
        for x, y in pts[1:]:
            d.append(f"l{round(x - px, decimals):g} {round(y - py, decimals):g}")
            px, py = x, y
        d.append("z")
        parts.append("".join(d))
    return "".join(parts)


def breaks(values: list[float], n: int = 5) -> list[float]:
    """Quantile class breaks (upper bounds of the first n-1 classes) over the values that exist."""
    vs = sorted(v for v in values if v is not None)
    if len(vs) < 2:
        return []
    out = []
    for i in range(1, n):
        q = vs[min(len(vs) - 1, int(len(vs) * i / n))]
        if (not out or q > out[-1]) and q < vs[-1]:     # the top class is never empty
            out.append(q)
    return out


def shade(v, cuts: list[float]) -> str:
    if v is None or not cuts:
        return NO_DATA if v is None else PALETTE[2]
    for i, c in enumerate(cuts):
        if v <= c:
            return PALETTE[i]
    return PALETTE[len(cuts)]


def _fmt(v, kind: str) -> str:
    if v is None:
        return "no data"
    v = float(v)
    if kind == "money":
        return f"${v:,.0f}"
    if kind == "pct":
        return f"{v:.1f}%"
    if kind == "years":
        return f"{v:.1f}"
    if kind == "multiple":
        return f"{v:.1f}x"
    return f"{v:,.0f}"


def _projection(features: list[dict], us: bool):
    if us:
        return None
    lons = [f["lon"] for f in features if f.get("lon") is not None]
    lats = [f["lat"] for f in features if f.get("lat") is not None]
    if not lons:
        return _Flat(-96, 38)
    return _Flat(sum(_fix_lon(x) for x in lons) / len(lons), sum(lats) / len(lats))


def _us_project(frame_pts: dict, f: dict):
    """Albers for the lower 48; AK, HI and PR scaled and moved into the usual inset positions."""
    st = f["gisjoin"][1:3]
    def proj(lon, lat):
        x, y = _albers(lon, lat)
        if st in INSETS:
            k, sx, sy = INSETS[st]
            cx, cy = frame_pts[st]
            x, y = (x - cx[0]) * k + cx[1], (y - cy[0]) * k + cy[1]
        return x, y
    return proj


def render(features: list[dict], values: dict, fmt: str = "num", links: dict | None = None, us: bool = False,
           width: int = WIDTH, points: list[dict] | None = None, highlight: set | None = None, legend: str = "",
           max_height: int = 620, labels: dict | None = None, decimals: int | None = None,
           point_label: str = "records") -> Markup:
    """The SVG: features (census_shapes rows) shaded by values[gisjoin] with a legend, each wrapped in a link from
    links[gisjoin], circles for points ({lon, lat, n, label, url?}), highlighted areas outlined in orange."""
    if not features:
        return Markup("")
    links, points, highlight, labels = links or {}, points or [], highlight or set(), labels or {}
    if us:
        # Project the lower 48 first for the frame, then place the insets relative to it.
        main = [f for f in features if f["gisjoin"][1:3] not in INSETS]
        pts = [_albers(x, y) for f in main for ring in f["geom"] for x, y in ring[::3]]
        if not pts:
            return Markup("")
        b = _bounds(pts)
        w, h = b[2] - b[0], b[3] - b[1]
        frame_pts = {}
        for st, (k, sx, sy) in INSETS.items():
            fs = [f for f in features if f["gisjoin"][1:3] == st]
            if not fs:
                continue
            ipts = [_albers(_fix_lon(x), y) for f in fs for ring in f["geom"] for x, y in ring[::2]]
            ib = _bounds(ipts)
            icx, icy = (ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2
            frame_pts[st] = ((icx, b[0] + sx * w + k * (ib[2] - ib[0]) / 2), (icy, b[1] + sy * h))
        frame = _Frame((b[0], b[1], b[2], b[3] + 0.12 * h), width, max_height=max_height)
        proj_for = lambda f: _us_project(frame_pts, f)   # noqa: E731
    else:
        proj = _projection(features, False)
        pts = [proj(x, y) for f in features for ring in f["geom"] for x, y in ring[::2]]
        if not pts:
            return Markup("")
        frame = _Frame(_bounds(pts), width, max_height=max_height)
        proj_for = lambda f: proj   # noqa: E731
    dec = decimals if decimals is not None else (0 if len(features) > 600 else 1)
    cuts = breaks([values.get(f["gisjoin"]) for f in features])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {frame.width} {frame.height}" class="census-map" '
           f'role="img" aria-label="{escape(legend or "map")}">']
    out.append(f'<g stroke="{OUTLINE}" stroke-width="{0.4 if len(features) > 600 else 0.7}" stroke-linejoin="round">')
    for f in features:
        v = values.get(f["gisjoin"])
        d = _path(f["geom"], proj_for(f), frame, dec)
        if not d:
            continue
        fill = shade(v, cuts) if values else "#d9e4ee"
        title = escape(f'{f["name"]}: {_fmt(v, fmt)}' if values else f["name"])
        path = f'<path d="{d}" fill="{fill}"><title>{title}</title></path>'
        href = links.get(f["gisjoin"])
        out.append(f'<a href="{escape(href)}">{path}</a>' if href else path)
    out.append("</g>")
    if highlight:
        out.append(f'<g fill="none" stroke="{HIGHLIGHT}" stroke-width="2">')
        for f in features:
            if f["gisjoin"] in highlight:
                out.append(f'<path d="{_path(f["geom"], proj_for(f), frame, 1)}"/>')
        out.append("</g>")
    for f in features:
        lab = labels.get(f["gisjoin"])
        if lab and f.get("lon") is not None:
            x, y = frame.px(*proj_for(f)(f["lon"], f["lat"]))
            out.append(f'<text x="{x:.0f}" y="{y:.0f}" font-size="10" text-anchor="middle" fill="#222" '
                       f'stroke="#fff" stroke-width="2.5" paint-order="stroke">{escape(lab)}</text>')
    if points:
        biggest = max(p.get("n") or 1 for p in points)
        out.append(f'<g fill="{POINT}" fill-opacity="0.55" stroke="#7b241c" stroke-width="0.5">')
        for p in points:
            if p.get("lon") is None or p.get("lat") is None:
                continue
            pf = proj_for({"gisjoin": "G" + (p.get("state_fips") or "00") + "0"}) if us else proj_for(None)
            x, y = frame.px(*pf(p["lon"], p["lat"]))
            r = 2 + 8 * math.sqrt((p.get("n") or 1) / biggest)
            c = f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"><title>{escape(p.get("label") or "")}</title></circle>'
            out.append(f'<a href="{escape(p["url"])}">{c}</a>' if p.get("url") else c)
        out.append("</g>")
    if values and cuts:
        lx, ly = 8, frame.height - 14
        out.append(f'<g font-size="10" fill="#333">')
        out.append(f'<text x="{lx}" y="{ly - 16}" font-weight="bold">{escape(legend)}</text>')
        x = lx
        edges = [None] + cuts + [None]
        for i in range(len(cuts) + 1):
            lo, hi = edges[i], edges[i + 1]
            lab = (f"up to {_fmt(hi, fmt)}" if lo is None else f"over {_fmt(lo, fmt)}" if hi is None
                   else f"{_fmt(lo, fmt)} to {_fmt(hi, fmt)}")
            out.append(f'<rect x="{x}" y="{ly - 10}" width="12" height="12" fill="{PALETTE[i]}" stroke="#999" stroke-width="0.5"/>')
            out.append(f'<text x="{x + 15}" y="{ly}">{escape(lab)}</text>')
            x += 15 + 6.2 * len(lab) + 10
        if points:
            out.append(f'<circle cx="{x + 6}" cy="{ly - 4}" r="5" fill="{POINT}" fill-opacity="0.55"/>')
            out.append(f'<text x="{x + 15}" y="{ly}">{escape(point_label)} (circle size: how many)</text>')
        out.append("</g>")
    out.append("</svg>")
    return Markup("".join(out))


def locator(county: dict | None, place: dict | None, tract: dict | None, point: tuple | None,
            width: int = LOCATOR_WIDTH) -> Markup:
    """A small map for an entity page: the county outline, the place and tract it was matched to, and a dot at
    its ZIP center."""
    if not county:
        return Markup("")
    feats = [county]
    proj = _projection(feats, False)
    pts = [proj(x, y) for ring in county["geom"] for x, y in ring[::2]]
    frame = _Frame(_bounds(pts), width, max_height=280)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {frame.width} {frame.height}" class="census-locator" '
           f'role="img" aria-label="{escape(county["name"])}">']
    out.append(f'<path d="{_path(county["geom"], proj, frame)}" fill="#eef3f8" stroke="#8aa" stroke-width="1"><title>'
               f'{escape(county["name"])}</title></path>')
    if place:
        out.append(f'<path d="{_path(place["geom"], proj, frame)}" fill="#c6dbef" stroke="#3e8ec4" stroke-width="0.8">'
                   f'<title>{escape(place["name"])}</title></path>')
    if tract:
        out.append(f'<path d="{_path(tract["geom"], proj, frame)}" fill="{HIGHLIGHT}" fill-opacity="0.6" stroke="#b35900" '
                   f'stroke-width="0.8"><title>{escape(tract["name"])}</title></path>')
    if point and point[0] is not None:
        x, y = frame.px(*proj(point[0], point[1]))
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{POINT}" stroke="#fff" stroke-width="1.2"/>')
    out.append("</svg>")
    return Markup("".join(out))


def geojson(features: list[dict], props: dict[str, dict]) -> dict:
    """A FeatureCollection of the outlines (polygons from the simplified rings) with props[gisjoin] as properties."""
    feats = []
    for f in features:
        rings = f["geom"]
        geom = ({"type": "Polygon", "coordinates": [rings[0]]} if len(rings) == 1 else
                {"type": "MultiPolygon", "coordinates": [[r] for r in rings]})
        feats.append({"type": "Feature", "geometry": geom,
                      "properties": {"gisjoin": f["gisjoin"], "name": f["name"], "geoid": f.get("geoid"),
                                     **(props.get(f["gisjoin"]) or {})}})
    return {"type": "FeatureCollection", "features": feats}
