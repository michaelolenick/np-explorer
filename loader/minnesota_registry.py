"""Minnesota business registry: the Secretary of State's business bulk order file (Minnesota Business & Lien System),
every business Minnesota has on record, active and inactive: corporations, LLCs, partnerships, cooperatives,
nonprofits, assumed names, name reservations and trademarks, with each one's filing history and named parties
(registered agents, officers, organizers, incorporators, applicants, markholders). Layout:
docs/minnesota-business-layout.md (the state's implementation guide, Rev08012025, checked against the data).

- Getting the file: there is no fixed URL. Each order is a one-time file, free for journalists, researchers and
  non-commercial use: email the request form to business.services@state.mn.us; the order is filled within 10 days and
  downloaded from the MBLS Portal's Transaction History. Put the zip (or the CSV in it) in
  /bulk/registry/mn/YYYY-MM-DD/ (the download date). Steps: docs/minnesota-business-layout.md.
- Reading it: one CSV (about 3.5 GB, 26 million lines, no header, Windows-1252, every field double-quoted) holding
  three record types tied together by Master ID: 01 business master, 02 filing history, 03 names and addresses. A
  zip is streamed with `unzip -p` (nothing is extracted to disk).
- The newest dated folder is used. `--if-new` (the nightly run) loads only when that file isn't the one last loaded
  (/bulk/registry/mn/.loaded).
- Every row records where it came from (provenance: file, export date, download date, load date). A full run
  replaces Minnesota's people and filings and removes Minnesota entities the new file no longer lists.

Usage: .venv/bin/python -m loader.minnesota_registry [--if-new] [--limit N] [--file PATH]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import subprocess
import time
from pathlib import Path

from app.names import normalize_name
from loader import db
from loader.virginia_registry import COLS, abbr, clean, day

DIR = Path("/bulk/registry/mn")
MARK = DIR / ".loaded"
STATE = "MN"
SOURCE = "mn"
csv.field_size_limit(1 << 30)
# Appendix II of the state's guide.
BUSINESS_TYPES = {"38": "Cooperative association", "39": "Cooperative (foreign)", "41": "Nonprofit corporation (domestic)",
                  "42": "Nonprofit corporation (foreign)", "43": "Business corporation (foreign)",
                  "44": "Limited liability company (domestic)", "46": "Limited liability company (foreign)",
                  "48": "Limited partnership (domestic)", "49": "Limited partnership (foreign)",
                  "50": "Limited liability partnership (domestic)", "52": "Limited liability partnership (foreign)",
                  "57": "Trademark", "59": "Assumed name", "60": "Name reservation",
                  "66": "Business corporation (domestic)", "104": "Cooperative (domestic)", "161": "Housing cooperative"}
ROLES = {"1": "Applicant", "2": "Markholder", "4": "Registered agent", "7": "Organizer", "8": "Incorporator",
         "11": "Filing contact", "12": "President", "13": "Manager", "14": "Chief executive officer",
         "19": "Individual contact for agent"}
ADDRESS_TYPES = {"2": "Principal place of business", "3": "Registered office", "4": "Home office",
                 "5": "Principal office", "6": "Chief executive office", "7": "Office", "8": "Designated office",
                 "9": "Service address", "11": "Business mailing address", "14": "Party primary address",
                 "16": "Principal office mailing address", "17": "Principal executive office",
                 "18": "Designated office mailing address", "19": "Registered agent mailing address",
                 "21": "Registered agent address", "204": "Individual contact for agent mailing address",
                 "9999": "Mailing address"}
# The business's own address, best first (a party's own address, 14, is never the business's).
PRINCIPAL = ["2", "17", "5", "6", "4", "7", "8", "3", "11", "16", "18", "9999"]
# Filing actions that end a business (latest one kept as the dissolution, for inactive businesses only).
ENDS = ["Administrative Dissolution", "Involuntary Dissolution", "Dissolution", "Statement of Dissolution",
        "Voluntary Dissolution", "Immediate Dissolution", "Court Ordered Dissolution", "Notice of Dissolution",
        "Administrative Dissolution due to Resignation of Agent", "Administrative Termination", "Termination",
        "Statement of Termination", "Revocation", "Revocation Due to Resignation of Agent", "Cancellation",
        "Statement of Cancellation", "Cancellation Statement", "Withdrawal", "Expired", "Expiration"]
MASTER = ["master_id", "record_type", "business_type", "original_filing_number", "name", "status", "filing_date",
          "expiration_date", "next_renewal_due", "home_jurisdiction", "governing_statute", "llc_nonprofit", "lllp",
          "professional", "home_business_name", "number_of_shares", "mark_type", "mark_first_use", "mark_class",
          "mark_logo", "blank", "export_date"]
FILING = ["master_id", "record_type", "business_type", "original_filing_number", "filing_number", "action", "rank",
          "filing_date", "effective_date"]
PARTY = ["master_id", "record_type", "business_type", "original_filing_number", "filing_number", "name_type",
         "address_type", "party_name", "street1", "street2", "city", "region", "postal_code", "postal_ext", "country"]
_ORG = re.compile(r"\b(llc|inc|incorporated|corp|corporation|company|co|ltd|limited|llp|lllp|lp|pllc|plc|pa|chartered|"
                  r"bank|trust|trustees?|association|assn|society|foundation|church|services?|group|partners|"
                  r"partnership|holdings|agency|agents|enterprises?|associates|cooperative|coop|university|college|"
                  r"council|club|fund|institute|organization|ministries|department|county|city of|state of|"
                  r"registered agent|incorporating|corporate)\b")


def newest(root: Path = DIR) -> Path | None:
    """The file in the newest dated folder: the CSV when it's been extracted there, otherwise the zip."""
    for d in sorted((p for p in root.glob("*") if p.is_dir() and re.fullmatch(r"\d{4}-\d\d-\d\d", p.name)), reverse=True):
        csvs = sorted(d.glob("*.[cC][sS][vV]"), key=lambda p: p.stat().st_size, reverse=True)
        zips = sorted(d.glob("*.[zZ][iI][pP]"), key=lambda p: p.stat().st_mtime, reverse=True)
        if csvs or zips:
            return (csvs or zips)[0]
    return None


def rows(path: Path):
    """Every record of the file as a list of fields (Windows-1252 decoded; a zip streamed with unzip -p)."""
    if path.suffix.lower() == ".zip":
        p = subprocess.Popen(["unzip", "-p", str(path)], stdout=subprocess.PIPE)
        raw = p.stdout
    else:
        p, raw = None, path.open("rb")
    try:
        yield from csv.reader(io.TextIOWrapper(raw, encoding="cp1252", errors="replace", newline=""))
    finally:
        raw.close()
        if p:
            p.wait()


def text(v) -> str | None:
    return clean((v or "").replace("\x00", ""))


def region(v) -> str | None:
    """The state's region codes, cleaned: "MNMN" and "MnMN" (doubled in some records) are MN; full names are coded."""
    s = (text(v) or "").upper()
    if not s:
        return None
    if len(s) == 4 and s[:2] == s[2:]:
        return s[:2]
    return abbr(s)


def entity_type(code: str | None) -> str | None:
    return BUSINESS_TYPES.get(code or "", f"Business type {code}" if code else None)


def is_org(name: str) -> bool:
    """A party that is a company or organization, not a person (the file doesn't say which): a legal ending or an
    organization word in the name."""
    return bool(_ORG.search(re.sub(r"[.,]", "", name.lower())))


def master(f: list) -> dict:
    """A business master record (01) as the entity's own fields and its Minnesota-only fields (extra)."""
    r = dict(zip(MASTER, f + [""] * (len(MASTER) - len(f))))
    name = text(r["name"])
    extra = {"original_filing_number": text(r["original_filing_number"]), "business_type_code": text(r["business_type"]),
             "expiration_date": day(r["expiration_date"]), "next_renewal_due": day(r["next_renewal_due"]),
             "governing_statute": text(r["governing_statute"]), "llc_nonprofit": r["llc_nonprofit"] == "1" or None,
             "lllp": r["lllp"] == "1" or None, "professional": r["professional"] == "1" or None,
             "home_business_name": text(r["home_business_name"]), "number_of_shares": text(r["number_of_shares"]),
             "mark_type": text(r["mark_type"]), "mark_first_use": day(r["mark_first_use"]),
             "mark_class": text(r["mark_class"]), "mark_logo": text(r["mark_logo"])}
    extra = {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in extra.items() if v not in (None, "", "0")}
    juris = text(r["home_jurisdiction"])
    # A few records have no name (mostly design-only trademarks): shown by what they are, never matched by name.
    unnamed = not name
    if unnamed:
        kind = entity_type(text(r["business_type"])) or "Record"
        logo = text(r["mark_logo"])
        name = f"{kind} with no name" + (f": {logo}" if logo else f", file {text(r['original_filing_number'])}")
        extra["no_name"] = True
    return {"entity_id": text(r["master_id"]), "name": name, "unnamed": unnamed, "entity_type": entity_type(text(r["business_type"])),
            "status": text(r["status"]), "formed": day(r["filing_date"]), "jurisdiction": abbr(juris) if juris else None,
            "extra": extra, "export_date": day(r["export_date"])}


def filing(f: list) -> tuple:
    r = dict(zip(FILING, f + [""] * (len(FILING) - len(f))))
    return (text(r["master_id"]), text(r["filing_number"]), text(r["original_filing_number"]), text(r["action"]),
            text(r["rank"]), day(r["filing_date"]), day(r["effective_date"]))


def party(f: list) -> tuple:
    """A name and address record (03): (master id, filing number, name type, address type, name, normalized name,
    is an organization, street, city, region, zip, country)."""
    r = dict(zip(PARTY, f + [""] * (len(PARTY) - len(f))))
    name = text(r["party_name"])
    org = bool(name) and is_org(name)
    norm = (normalize_name(name[:300]) or "")[:200] or None if name and not org else None
    zip_ = text(r["postal_code"])
    if zip_ and text(r["postal_ext"]):
        zip_ = f"{zip_}-{text(r['postal_ext'])}"
    street = " ".join(x for x in (text(r["street1"]), text(r["street2"])) if x) or None
    return (text(r["master_id"]), text(r["filing_number"]), text(r["name_type"]), text(r["address_type"]),
            name[:300] if name else None, norm, org, street, (text(r["city"]) or "").rstrip(", ") or None,
            region(r["region"]), zip_,
            text(r["country"]))


def _case(col: str, labels: dict) -> str:
    return "CASE " + " ".join(f"WHEN {col} = '{k}' THEN '{v}'" for k, v in labels.items()) + " END"


def run(path: Path | None = None, limit: int | None = None, if_new: bool = False, status=print) -> dict:
    t0, start = time.time(), dt.datetime.now(dt.timezone.utc)
    path = path or newest()
    if not path:
        status("minnesota: no file in /bulk/registry/mn/<date>/ yet")
        return {}
    if if_new and MARK.exists() and MARK.read_text().strip() == str(path):
        status(f"minnesota: {path.name} already loaded")
        return {}
    m = re.search(r"RunOn(\d{4})(\d\d)(\d\d)", path.name)
    exported = dt.date(int(m[1]), int(m[2]), int(m[3])) if m else None
    downloaded = path.parent.name if re.fullmatch(r"\d{4}-\d\d-\d\d", path.parent.name) else "unknown date"
    stats = {"lines": 0, "masters": 0, "filings": 0, "parties": 0, "other_lines": 0, "short_lines": 0, "no_master_id": 0, "no_name": 0}
    keep: set | None = set() if limit else None
    with db.connect() as conn:
        conn.execute("SET work_mem = '256MB'")
        conn.execute("""CREATE TEMP TABLE mn_m (line bigint, master_id text, name text, name_core text, entity_type text,
                        status text, formed date, jurisdiction text, extra jsonb)""")
        conn.execute("""CREATE TEMP TABLE mn_f (master_id text, filing_number text, original_filing_number text,
                        action text, rank text, filing_date date, effective_date date)""")
        conn.execute("""CREATE TEMP TABLE mn_p (master_id text, filing_number text, name_type text, address_type text,
                        name text, name_norm text, is_entity boolean, street text, city text, region text, zip text,
                        country text)""")
        tables = {"01": ("mn_m", None), "02": ("mn_f", None), "03": ("mn_p", None)}
        from loader.recalls import core
        cur, ctx, cp, kind = conn.cursor(), None, None, None
        try:
            for i, f in enumerate(rows(path), 1):
                stats["lines"] = i
                rt = f[1] if len(f) > 1 else ""
                if rt not in tables:
                    stats["other_lines"] += 1
                    continue
                if len(f) < {"01": 21, "02": 8, "03": 15}[rt]:
                    stats["short_lines"] += 1
                if rt != kind:                       # the file is grouped by record type: one COPY per group
                    if ctx:
                        ctx.__exit__(None, None, None)
                    kind = rt
                    ctx = cur.copy(f"COPY {tables[rt][0]} FROM STDIN")
                    cp = ctx.__enter__()
                if rt == "01":
                    if limit and stats["masters"] >= limit:
                        continue
                    e = master(f)
                    if not e["entity_id"]:
                        stats["no_master_id"] += 1
                        continue
                    stats["no_name"] += e["unnamed"]
                    exported = e.pop("export_date") or exported
                    cp.write_row((i, e["entity_id"], e["name"][:500], "" if e["unnamed"] else core(e["name"])[:500],
                                  e["entity_type"],
                                  e["status"], e["formed"], e["jurisdiction"], json.dumps(e["extra"])))
                    stats["masters"] += 1
                    if keep is not None:
                        keep.add(e["entity_id"])
                elif rt == "02":
                    r = filing(f)
                    if keep is None or r[0] in keep:
                        cp.write_row(r)
                        stats["filings"] += 1
                else:
                    r = party(f)
                    if keep is None or r[0] in keep:
                        cp.write_row(r)
                        stats["parties"] += 1
                if i % 1000000 == 0:
                    status(f"minnesota: {i:,} lines ({time.time() - t0:.0f}s)")
        finally:
            if ctx:
                ctx.__exit__(None, None, None)
        conn.commit()
        status(f"minnesota: read {stats} ({time.time() - t0:.0f}s)")
        prov = (f"MN Secretary of State business bulk order file {path.name} (exported {exported or 'unknown date'}, "
                f"downloaded {downloaded}), loaded {dt.date.today()}")

        # The business's address, its registered agent and the agent's address, and how it ended.
        conn.execute("ANALYZE mn_m")
        conn.execute("ANALYZE mn_p")
        conn.execute("ANALYZE mn_f")
        conn.execute("""CREATE TEMP TABLE mn_addr AS SELECT DISTINCT ON (master_id) master_id, address_type, street, city,
                        region, zip FROM mn_p WHERE address_type = ANY(%s) AND (street IS NOT NULL OR city IS NOT NULL)
                        ORDER BY master_id, array_position(%s::text[], address_type), filing_number DESC""",
                     (PRINCIPAL, PRINCIPAL))
        conn.execute("""CREATE TEMP TABLE mn_agent AS SELECT DISTINCT ON (master_id) master_id, name FROM mn_p
                        WHERE name_type = '4' AND name IS NOT NULL ORDER BY master_id, filing_number DESC""")
        conn.execute("""CREATE TEMP TABLE mn_ra AS SELECT DISTINCT ON (master_id) master_id, street, city, region, zip
                        FROM mn_p WHERE address_type IN ('21', '3') AND (street IS NOT NULL OR city IS NOT NULL)
                        ORDER BY master_id, (address_type = '21') DESC, filing_number DESC""")
        conn.execute("""CREATE TEMP TABLE mn_end AS SELECT DISTINCT ON (master_id) master_id, filing_date, action
                        FROM mn_f WHERE action = ANY(%s) ORDER BY master_id, filing_date DESC NULLS LAST""", (ENDS,))
        for t in ("mn_addr", "mn_agent", "mn_ra", "mn_end"):
            conn.execute(f"CREATE INDEX ON {t} (master_id)")
            conn.execute(f"ANALYZE {t}")
        conn.commit()
        status(f"minnesota: addresses and agents ({time.time() - t0:.0f}s)")

        # Entities, in 17 batches by the first character of the Master ID (a GUID).
        sets = ", ".join(f"{c} = excluded.{c}" for c in COLS[2:])
        heads = list("0123456789abcdef")
        batches = [("left(m.master_id, 1) = %s", (h,)) for h in heads] + [("NOT left(m.master_id, 1) = ANY(%s)", (heads,))]
        stats["entities"] = 0
        for where, args in batches:
            stats["entities"] += conn.execute(f"""
                INSERT INTO biz_entities ({', '.join(COLS)}, loaded)
                SELECT DISTINCT ON (m.master_id) %s, m.master_id, m.name, m.name_core, m.entity_type, m.status, m.formed,
                       a.street, a.city, a.region, a.zip, ag.name,
                       nullif(concat_ws(' ', ra.street, ra.city, ra.region, ra.zip), ''), m.jurisdiction, %s, NULL, %s,
                       m.extra || jsonb_strip_nulls(jsonb_build_object(
                           'address_type', {_case('a.address_type', ADDRESS_TYPES)},
                           'dissolved', CASE WHEN m.status = 'Inactive' THEN en.filing_date END,
                           'dissolved_by', CASE WHEN m.status = 'Inactive' THEN en.action END)),
                       now()
                FROM mn_m m LEFT JOIN mn_addr a USING (master_id) LEFT JOIN mn_agent ag USING (master_id)
                LEFT JOIN mn_ra ra USING (master_id) LEFT JOIN mn_end en USING (master_id)
                WHERE {where}
                ORDER BY m.master_id, m.line DESC
                ON CONFLICT (state, entity_id) DO UPDATE SET {sets}, loaded = now()""",
                (STATE, SOURCE, prov, *args)).rowcount
            conn.commit()
        status(f"minnesota: {stats['entities']:,} entities ({time.time() - t0:.0f}s)")

        # People and filings: replaced as a whole on a full run (only the businesses read, on a test run).
        only = "" if keep is None else " AND entity_id IN (SELECT master_id FROM mn_m)"
        conn.execute(f"DELETE FROM biz_people WHERE source = %s{only}", (SOURCE,))
        stats["people"] = conn.execute(f"""
            INSERT INTO biz_people (state, entity_id, name, name_norm, role, is_entity, address, source, provenance)
            SELECT DISTINCT ON (p.master_id, p.name_type, upper(p.name)) %s, p.master_id, p.name, p.name_norm,
                   {_case('p.name_type', ROLES)}, p.is_entity,
                   nullif(concat_ws(', ', coalesce(p.city, CASE WHEN p.name_type = '4' THEN ra.city END),
                                    coalesce(p.region, CASE WHEN p.name_type = '4' THEN ra.region END)), ''), %s, %s
            FROM mn_p p LEFT JOIN mn_ra ra USING (master_id)
            WHERE p.name IS NOT NULL AND p.name_type = ANY(%s) AND p.master_id IN (SELECT master_id FROM mn_m)
            ORDER BY p.master_id, p.name_type, upper(p.name), p.filing_number DESC""",
            (STATE, SOURCE, prov, list(ROLES))).rowcount
        stats["parties_unnamed_or_other_type"] = stats["parties"] - conn.execute(
            "SELECT count(*) FROM mn_p WHERE name IS NOT NULL AND name_type = ANY(%s)", (list(ROLES),)).fetchone()[0]
        conn.commit()
        status(f"minnesota: {stats['people']:,} people ({time.time() - t0:.0f}s)")
        conn.execute(f"DELETE FROM biz_filings WHERE source = %s{only}", (SOURCE,))
        stats["filings_loaded"] = conn.execute("""
            INSERT INTO biz_filings (state, entity_id, filing_number, original_filing_number, action, rank, filing_date,
                                     effective_date, source, provenance)
            SELECT %s, master_id, filing_number, original_filing_number, action, rank, filing_date, effective_date, %s, %s
            FROM mn_f""", (STATE, SOURCE, prov)).rowcount
        stats["filings_without_entity"] = conn.execute(
            "SELECT count(*) FROM mn_f f WHERE NOT EXISTS (SELECT 1 FROM mn_m m WHERE m.master_id = f.master_id)").fetchone()[0]
        conn.commit()
        status(f"minnesota: {stats['filings_loaded']:,} filings ({time.time() - t0:.0f}s)")

        if not limit:
            stats["removed"] = conn.execute("DELETE FROM biz_entities WHERE source = %s AND loaded < %s",
                                            (SOURCE, start)).rowcount
        conn.execute("""INSERT INTO biz_runs (source, rows) VALUES (%s, %s)
                        ON CONFLICT (source) DO UPDATE SET loaded = now(), rows = excluded.rows""",
                     (SOURCE, stats["entities"]))
        conn.commit()
        for t in ("biz_entities", "biz_people", "biz_filings"):
            conn.execute(f"ANALYZE {t}")
        conn.commit()
    if not limit:
        MARK.write_text(str(path) + "\n")
    status(f"minnesota: {stats} in {time.time() - t0:.0f}s")
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--if-new", action="store_true", help="only when the newest file isn't the one last loaded")
    ap.add_argument("--limit", type=int, help="business master records (a test run)")
    ap.add_argument("--file", type=Path, help="this file instead of the newest one")
    a = ap.parse_args()
    run(a.file, a.limit, a.if_new)
