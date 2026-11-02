"""USDA FSIS meat, poultry and egg recalls and public health alerts (https://www.fsis.usda.gov/recalls), loaded
into food_recalls as source 'fsis' beside the FDA reports (loader/recalls.py), so they share the recalling firms,
the links to the rest of the site, the pages, the search and the leaderboards.

The agreement with FSIS (owner, 2026-11-02): FSIS allows our two server IPs; we send the User-Agent
"furp.org research michael@furp.org", made one full download, and make ONE request a night to the recall endpoint,
nothing else. So this loader makes a single GET with no retries and no redirect following, keeps a done-marker per
UTC day, never asks for anything per recall, and every recall shown on the site credits FSIS and links to the
official notice (field_recall_url).

The API returns every recall in one JSON list, in English and Spanish (langcode); only the English records are
loaded (the Spanish ones repeat the recall number). What FSIS gives only in text is read from the text:
  recalling firm   field_establishment, else the title ("X Recalls ..."), else the summary ("X, a City, St.
                   establishment"); alerts naming no establishment share one firm row (PHA_FIRM, kept off the boards)
  city and state   the summary ("a McCook, Ill., establishment"; AP state abbreviations)
  quantity         the summary ("is recalling approximately 946 pounds")
  reason           FSIS's category ("Product Contamination"), then the specific reason from the title
                   ("Due to Possible Listeria Contamination")
Status: Active Recall = Ongoing, Closed Recall = Completed, Public Health Alert stays (no class; not a recall).
Not mapped: the recovered quantity, label and retail-list PDFs, media contacts, processing category, outbreak flag,
closed year, the Spanish versions.

Usage: .venv/bin/python -m loader.fsis_recalls [--file saved.json] [--force] [--no-rebuild]
  --file       load a saved download instead of asking FSIS (the initial full download; tests)
  --force      ask FSIS even if tonight's done-marker exists
  --no-rebuild skip rebuilding the firms, links and boards after changes
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import time
from pathlib import Path

from loader import db
from loader.recalls import COLS, build_firms, firm_id

API = "https://www.fsis.usda.gov/fsis/api/recall/v/1"
UA = "furp.org research michael@furp.org"
RAW = Path("/data/raw/fsis")
PHA_FIRM_ID = "fsis-pha"
PHA_FIRM = "USDA FSIS public health alerts naming no establishment"
STATUS = {"Active Recall": "Ongoing", "Closed Recall": "Completed", "Public Health Alert": "Public health alert"}
CLASSES = {"Class I", "Class II", "Class III"}
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
          "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
          "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
          "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
          "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
          "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
          "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
          "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
          "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico"}
# AP-style abbreviations as FSIS writes them ("Calif.", "Ill.", "N.Y."), plus the variants seen in the summaries.
_AP = {"ala": "AL", "ariz": "AZ", "ark": "AR", "calif": "CA", "colo": "CO", "col": "CO", "conn": "CT", "del": "DE",
       "fla": "FL", "ill": "IL", "ind": "IN", "kan": "KS", "kans": "KS", "ky": "KY", "md": "MD", "mass": "MA",
       "mich": "MI", "minn": "MN", "miss": "MS", "mo": "MO", "mont": "MT", "neb": "NE", "nebr": "NE", "nev": "NV",
       "okla": "OK", "ore": "OR", "pa": "PA", "penn": "PA", "tenn": "TN", "tex": "TX", "va": "VA", "wash": "WA",
       "wis": "WI", "wisc": "WI", "wyo": "WY", "wva": "WV"}
_AP.update({k.lower(): k for k in STATES})
_AP.update({re.sub(r"[^a-z]", "", v.lower()): k for k, v in STATES.items()})
COUNTRIES = {"canada": "Canada", "ontario": "Canada", "quebec": "Canada", "mexico": "Mexico"}

TITLE_FIRM = re.compile(r"^\s*(.*?)\s+(?:Recalls?|Issues|Expands|Announces)\b", re.I)
SUMMARY_FIRM = re.compile(r"\d{4}\s*[–—-]+\s*([A-Z][^,]{2,80}?),\s+an?\s+")
PLACE = re.compile(r"\b(?:an?|the)\s+([A-Z][A-Za-z.'’ -]{1,40}?),\s+([A-Z][A-Za-z.]{1,12}\.?)\s*,?\s+"
                   r"(?:establishment|firm|company|facility|retailer|distributor|processor|packer|importer|business)")
QUANTITY = re.compile(r"recall(?:ing|ed)?\s+(?:approximately|about|an estimated|roughly)?\s*([\d,]+(?:\.\d+)?)\s*(?:-\s*)?"
                      r"(pounds|lbs?\.?|lb\.?|units|cases|packages)", re.I)
DETAIL = re.compile(r"\b(?:due to|because of|for)\s+(.+?)\s*\.?\s*$", re.I)


def text(s: str | None) -> str:
    """Plain text from FSIS's HTML: tags out, entities decoded, whitespace folded."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def place(summary: str) -> tuple[str | None, str | None, str]:
    """(city, state, country) from "..., a McCook, Ill., establishment, ..."; the state as a postal code."""
    m = PLACE.search(text(summary)[:800])
    if not m:
        return None, None, "United States"
    city, token = m.group(1).strip(), re.sub(r"[^a-z]", "", m.group(2).lower())
    if token in COUNTRIES:
        return city, None, COUNTRIES[token]
    return city, _AP.get(token), "United States"


def firm_name(r: dict) -> str | None:
    est = [text(x) for x in (r.get("field_establishment") or []) if text(x)]
    if est:
        return est[0]
    m = TITLE_FIRM.match(text(r.get("field_title")))
    if m and len(m.group(1)) > 2 and not m.group(1).lower().startswith(("fsis", "usda", "u.s. department")):
        return m.group(1)
    m = SUMMARY_FIRM.search(text(r.get("field_summary"))[:400])
    return m.group(1).strip() if m else None


def quantity(summary: str) -> str | None:
    m = QUANTITY.search(text(summary))
    if not m:
        return None
    unit = m.group(2).lower().rstrip(".")
    return f"{m.group(1)} {'pounds' if unit in ('lb', 'lbs') else unit}"


def reason(r: dict) -> str | None:
    cats = ", ".join(text(x) for x in (r.get("field_recall_reason") or []) if text(x))
    m = DETAIL.search(text(r.get("field_title")))
    detail = m.group(1) if m else ""
    return (f"{cats}: {detail}" if cats and detail else cats or detail) or None


def _date(v: str | None) -> dt.date | None:
    v = (v or "").strip()[:10]
    return dt.date.fromisoformat(v) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else None


def row(r: dict) -> tuple | None:
    """One food_recalls row (loader.recalls.COLS order) from an English FSIS record, or None to skip it."""
    number = (r.get("field_recall_number") or "").strip()
    if not number or r.get("langcode") != "English":
        return None
    name = firm_name(r)
    city, state, country = place(r.get("field_summary") or "")
    if name:
        fid = firm_id(name, state)
    else:
        name, fid, city, state = PHA_FIRM, PHA_FIRM_ID, None, None
    kind = r.get("field_recall_type") or ""
    cls = (r.get("field_recall_classification") or "").strip()
    processing = [text(x) for x in (r.get("field_processing") or [])]
    items = "; ".join(text(x) for x in (r.get("field_product_items") or []) if text(x)) or None
    states = [text(x) for x in (r.get("field_states") or []) if text(x)]
    url = (r.get("field_recall_url") or "").strip().replace("http://", "https://", 1) or None
    values = {
        "source": "fsis", "recall_number": number, "event_id": number, "status": STATUS.get(kind, kind or None),
        "classification": cls if cls in CLASSES else None,
        "product_type": "Egg products" if "Eggs/Egg Products" in processing else "Meat and poultry",
        "recalling_firm": name, "firm_id": fid, "address": None, "city": city, "state": state, "country": country,
        "postal_code": None, "product_description": items, "product_quantity": quantity(r.get("field_summary") or ""),
        "reason_for_recall": reason(r), "distribution_pattern": ", ".join(states) or None, "voluntary_mandated": None,
        "initial_firm_notification": None, "code_info": None, "recall_initiation_date": _date(r.get("field_recall_date")),
        "center_classification_date": None, "report_date": _date(r.get("field_last_modified_date")),
        "termination_date": None, "source_url": url, "data_url": None}
    return tuple(values[c] for c in COLS)


def fetch(status=print) -> list[dict]:
    """The one request: a single GET, no retries, no redirects followed. The response is kept in RAW."""
    import httpx
    t0 = time.time()
    resp = httpx.get(API, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=300, follow_redirects=False)
    status(f"fsis recalls: GET {API} -> {resp.status_code}, {len(resp.content):,} bytes ({time.time() - t0:.0f}s)")
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"fsis recalls: unexpected response shape {type(data).__name__}")
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "latest.json").write_bytes(resp.content)
    return data


def upsert(data: list[dict], status=print) -> dict:
    """New and changed recalls into food_recalls (nothing is deleted); returns the counts."""
    rows = [x for x in (row(r) for r in data) if x]
    with db.connect() as conn:
        have = {r[1]: tuple(r) for r in conn.execute(f"SELECT {', '.join(COLS)} FROM food_recalls WHERE source = 'fsis'")}
        new = [r for r in rows if r[1] not in have]
        changed = [r for r in rows if r[1] in have and have[r[1]] != r]
        sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLS if c not in ("source", "recall_number"))
        with conn.cursor() as cur:
            cur.executemany(f"""INSERT INTO food_recalls ({', '.join(COLS)}) VALUES ({', '.join('%s' for _ in COLS)})
                                ON CONFLICT (source, recall_number) DO UPDATE SET {sets}, loaded = now()""", new + changed)
        conn.commit()
        if new or changed:
            conn.execute("ANALYZE food_recalls")
            conn.commit()
    counts = {"records": len(data), "english": len(rows), "new": len(new), "changed": len(changed),
              "total": len(have) + len(new)}
    status(f"fsis recalls: {counts['records']:,} records, {counts['english']:,} English recalls and alerts; "
           f"{counts['new']:,} new, {counts['changed']:,} changed; {counts['total']:,} FSIS rows in all")
    return counts


def rebuild(status=print) -> None:
    """The recalling firms, their links and the recall boards, as loader.recalls does after an FDA load."""
    build_firms(status)
    from app import boards as B
    from loader import boards as LB
    with db.connect() as conn:
        for b in B.BOARDS:
            if b.group == "recalls":
                status(f"fsis recalls: board {b.slug}: {LB.refresh_board(conn, b)} rows")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", help="load this saved download instead of asking FSIS")
    ap.add_argument("--force", action="store_true", help="ask FSIS even if tonight's done-marker exists")
    ap.add_argument("--no-rebuild", action="store_true", help="skip rebuilding firms, links and boards")
    a = ap.parse_args(argv)
    if a.file:
        data = json.loads(Path(a.file).read_text())
        print(f"fsis recalls: {len(data):,} records from {a.file}")
    else:
        marker = RAW / f".done-{dt.datetime.now(dt.timezone.utc):%Y-%m-%d}"
        if marker.exists() and not a.force:
            print(f"fsis recalls: already fetched today ({marker.name}); one request a night, as agreed with FSIS")
            return 0
        data = fetch()
        RAW.mkdir(parents=True, exist_ok=True)
        marker.touch()
    counts = upsert(data)
    if (counts["new"] or counts["changed"]) and not a.no_rebuild:
        rebuild()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
