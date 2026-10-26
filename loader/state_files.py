"""State business registries published as free downloadable files (no login, no CAPTCHA), one file per state:

  IA  Iowa Secretary of State, "Active Iowa Business Entities" (data.iowa.gov dataset 554, CC BY 4.0): active
      entities only, with registered agent and home office; monthly. A zip holding one CSV.
  DC  DC Department of Licensing and Consumer Protection, corporate registrations (opendata.dc.gov item
      5238c4fd99c843a1bd7679a243747a8c): every status, with registered agent; daily.
  AK  Alaska Division of Corporations, CorporationsDownload.CSV (commerce.alaska.gov/cbp/DBDownloads): entities in
      good standing or non-compliant, with registered agent; name reservations are skipped.

None of these files lists officers. Files go to /bulk/registry/<state>/ with the server's publish date kept (curl -R),
and every row records the file, its date and the load date (provenance). A full run of a state removes that state's
entities the new file no longer lists. Virginia has its own loader (loader/virginia_registry.py).

Usage: .venv/bin/python -m loader.state_files [fetch|load] [ia dc ak ...] [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import subprocess
import time
import zipfile
from pathlib import Path

from loader import db
from loader.uspto import STATES
from loader.virginia_registry import COLS, clean

UA = "furp.org research michael@furp.org"
ROOT = Path("/bulk/registry")
csv.field_size_limit(1 << 30)


def _date(v) -> dt.date | None:
    s = clean(v)
    if not s:
        return None
    s = s[:10].replace("/", "-") if s[:4].isdigit() else s.split()[0]
    try:
        if "-" in s:
            return dt.date.fromisoformat(s)
        m, d, y = s.split("/")
        return dt.date(int(y), int(m), int(d))
    except ValueError:
        return None


def _st(v) -> str | None:
    s = clean(v)
    return None if not s else s.upper() if len(s) == 2 else STATES.get(s.upper(), s[:30])


def _addr(*parts) -> str | None:
    return " ".join(x for x in (clean(p) for p in parts) if x) or None


def ia(r):
    t = clean(r.get("corporation_type")) or ""
    return {"entity_id": clean(r.get("corp_number")), "name": clean(r.get("legal_name")),
            "entity_type": t.split(" - ", 1)[-1].title() or None, "status": "Active", "formed": _date(r.get("effective_date")),
            "street": _addr(r.get("ho_address_1"), r.get("ho_address_2")), "city": clean(r.get("ho_city")),
            "addr_state": _st(r.get("ho_state")), "zip": clean(r.get("ho_zip")), "agent_name": clean(r.get("registered_agent")),
            "agent_address": _addr(r.get("ra_address_1"), r.get("ra_city"), r.get("ra_state"), r.get("ra_zip")),
            "jurisdiction": "IA" if "DOMESTIC" in t.upper() else None,
            "extra": {"corporation_type_code": t.split(" - ", 1)[0] if " - " in t else None}}


def dc(r):
    return {"entity_id": clean(r.get("FILE_NUMBER")), "name": clean(r.get("BUSINESS_NAME")),
            "entity_type": clean(r.get("MODELTYPE")), "status": clean(r.get("ENTITY_STATUS")),
            "formed": _date(r.get("EFFECTIVE_DATE")),
            "street": _addr(r.get("BUSNIESS_ADDRESS_LINE1"), r.get("BUSNIESS_ADDRESS_LINE2")),
            "city": clean(r.get("BUSINESS_CITY")), "addr_state": _st(r.get("BUSINESS_STATE")), "zip": clean(r.get("ZIPCODE")),
            "agent_name": clean(r.get("RA_NAME")),
            "agent_address": _addr(r.get("RA_ADDRESS1"), r.get("RA_CITY"), r.get("RA_STATE"), r.get("RA_ZIPCODE")),
            "jurisdiction": "DC" if clean(r.get("LOCALE")) == "Domestic" else None,
            "extra": {"locale": clean(r.get("LOCALE")), "foreign_formed": (_date(r.get("FOREIGN_DATEOF_ORGANIZATION")) or "") and
                      _date(r.get("FOREIGN_DATEOF_ORGANIZATION")).isoformat(),
                      "last_report_filed": (_date(r.get("DATE_LAST_REPORT_FILED")) or "") and
                      _date(r.get("DATE_LAST_REPORT_FILED")).isoformat()}}


def ak(r):
    if clean(r.get("CORPTYPE")) == "Name Reservation":
        return None
    phys = clean(r.get("ENTITYPHYSADDRESS1"))
    p = "ENTITYPHYS" if phys else "ENTITYMAILING"
    home = clean(r.get("HOMESTATE"))
    return {"entity_id": clean(r.get("ENTITYNUMBER")), "name": clean(r.get("LEGALNAME")),
            "entity_type": clean(r.get("CORPTYPE")), "status": clean(r.get("STATUS")), "formed": _date(r.get("AKFORMEDDATE")),
            "street": _addr(r.get(p + "ADDRESS1"), r.get(p + "ADDRESS2")), "city": clean(r.get(p + "CITY")),
            "addr_state": _st(r.get(p + "STATEPROVINCE")), "zip": clean(r.get(p + "ZIP")),
            "agent_name": clean(r.get("REGISTEREDAGENT")),
            "agent_address": _addr(r.get("REGISTEREDPHYSADDRESS1") or r.get("REGISTEREDMAILADDRESS1"),
                                   r.get("REGISTEREDPHYSCITY") or r.get("REGISTEREDMAILCITY"),
                                   r.get("REGISTEREDPHYSSTATEPROVINCE") or r.get("REGISTEREDMAILSTATEPROVINCE")),
            "jurisdiction": _st(home) if home else None,
            "extra": {"assumed_name": clean(r.get("ASSUMEDNAME")), "next_report_due": clean(r.get("NEXTBRDUEDATE"))}}


# state: (file, URL, label, mapper, zipped)
SOURCES = {
    "ia": ("ia.zip", "https://idh-be.iowa.gov/api/v1/datasets/554/rows.csv",
           "Iowa Secretary of State, Active Iowa Business Entities (data.iowa.gov 554, CC BY 4.0)", ia, True),
    "dc": ("dc.csv", "https://opendata.dc.gov/api/download/v1/items/5238c4fd99c843a1bd7679a243747a8c/csv?layers=0",
           "DC Department of Licensing and Consumer Protection, corporate registrations (opendata.dc.gov)", dc, False),
    "ak": ("ak.csv", "https://www.commerce.alaska.gov/cbp/DBDownloads/CorporationsDownload.CSV",
           "Alaska Division of Corporations, CorporationsDownload.CSV", ak, False),
}


def path(src: str) -> Path:
    return ROOT / src / SOURCES[src][0]


def fetch(src: str, status=print) -> None:
    p = path(src)
    p.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-sSfLR", "-A", UA, "-o", str(p), SOURCES[src][1]], check=True)
    status(f"{src}: {p.stat().st_size:,} bytes, published {dt.date.fromtimestamp(p.stat().st_mtime)}")


def rows(src: str):
    p = path(src)
    if SOURCES[src][4]:
        z = zipfile.ZipFile(p)
        f = io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8-sig", errors="replace", newline="")
    else:
        f = p.open(encoding="utf-8-sig", errors="replace", newline="")
    with f:
        yield from csv.DictReader(f)


def load(src: str, limit: int | None = None, status=print) -> dict:
    from loader.recalls import core
    file, _, label, mapper, _ = SOURCES[src]
    state = src.upper()
    p = path(src)
    prov = f"{label}, file {file} (published {dt.date.fromtimestamp(p.stat().st_mtime)}), loaded {dt.date.today()}"
    t0, start = time.time(), dt.datetime.now(dt.timezone.utc)
    stats = {"entities": 0, "skipped": 0}
    ents = {}
    with db.connect() as conn:
        def flush():
            if not ents:
                return
            conn.execute("CREATE TEMP TABLE IF NOT EXISTS se (LIKE biz_entities INCLUDING DEFAULTS)")
            conn.execute("TRUNCATE se")
            with conn.cursor() as cur, cur.copy(f"COPY se ({', '.join(COLS)}) FROM STDIN") as cp:
                for e in ents.values():
                    extra = {k: v for k, v in (e.get("extra") or {}).items() if v}
                    cp.write_row((state, e["entity_id"], e["name"][:500], core(e["name"])[:500],
                                  *[(str(e[c])[:500] if e.get(c) is not None and not isinstance(e[c], dt.date) else e.get(c))
                                    for c in COLS[4:14]], src, None, prov, json.dumps(extra)))
            conn.execute(f"""INSERT INTO biz_entities ({', '.join(COLS)}, loaded) SELECT {', '.join(COLS)}, now() FROM se
                             ON CONFLICT (state, entity_id) DO UPDATE SET
                             {', '.join(f'{c} = excluded.{c}' for c in COLS[2:])}, loaded = now()""")
            conn.commit()
            ents.clear()

        for r in rows(src):
            e = mapper(r)
            if not e or not e.get("entity_id") or not e.get("name"):
                stats["skipped"] += 1
                continue
            ents[e["entity_id"]] = e
            stats["entities"] += 1
            if len(ents) >= 20000:
                flush()
            if limit and stats["entities"] >= limit:
                break
        flush()
        if not limit:
            stats["removed"] = conn.execute("DELETE FROM biz_entities WHERE source = %s AND loaded < %s",
                                            (src, start)).rowcount
        conn.execute("""INSERT INTO biz_runs (source, rows) VALUES (%s, %s)
                        ON CONFLICT (source) DO UPDATE SET loaded = now(), rows = excluded.rows""", (src, stats["entities"]))
        conn.commit()
    status(f"{src}: {stats} in {time.time() - t0:.0f}s")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "load"])
    ap.add_argument("states", nargs="*", default=list(SOURCES))
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    for s in a.states:
        fetch(s) if a.cmd == "fetch" else load(s, a.limit)
