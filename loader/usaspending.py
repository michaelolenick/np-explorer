"""Federal awards from USAspending: grants and other assistance, and contracts, by fiscal year.

Source: the Award Data Archive (https://files.usaspending.gov/award_data_archive/), one zip per fiscal year and
kind (FYyyyy_All_Assistance_Full_*.zip, FYyyyy_All_Contracts_Full_*.zip), transaction-level CSVs. A file is read
once: the columns we use go into usa_stage, then one row per award and fiscal year is written to usa_awards
(obligations summed over that year's transactions) and the officer pay the recipient reported to usa_officers.
Re-loading a year replaces that year and kind. Assistance records for individuals and county-level aggregates
(record_type_code 1 and 3) are left out: only awards to organizations are kept.

Every award links to its source: usaspending_permalink, the award's page on usaspending.gov.
"""

from __future__ import annotations

import csv
import io
import re
import time
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

from loader import db

ARCHIVE = "https://files.usaspending.gov/award_data_archive/"
RAW = Path("/data/raw/usaspending")
FIRST_FY = 2007
KINDS = {"Assistance": "assistance", "Contracts": "contract"}
csv.field_size_limit(10_000_000)

STAGE_COLS = ["award_key", "kind", "fiscal_year", "obligation", "action_date", "agency", "sub_agency",
              "recipient_uei", "recipient_duns", "recipient_name", "parent_name", "street", "city", "state", "zip5",
              "program_code", "program_title", "award_type", "description", "business_types", "nonprofit",
              "permalink", "officers"]


def _files(fy: int) -> dict[str, str]:
    """{kind: latest archive file name} for one fiscal year."""
    for attempt in range(4):                     # the listing times out now and then
        try:
            with urllib.request.urlopen(f"{ARCHIVE}?prefix=FY{fy}_All_", timeout=60) as r:
                xml = r.read().decode()
            break
        except (OSError, TimeoutError):
            if attempt == 3:
                raise
            time.sleep(30 * (attempt + 1))
    out = {}
    for key in sorted(re.findall(r"<Key>([^<]+\.zip)</Key>", xml)):
        m = re.match(rf"FY{fy}_All_(Assistance|Contracts)_Full_\d+\.zip$", key)
        if m:
            out[KINDS[m.group(1)]] = key          # sorted: the latest date wins
    return out


def _download(name: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / name
    if dest.exists():
        return dest
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(ARCHIVE + name, timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 22):
            f.write(chunk)
    tmp.rename(dest)
    return dest


def _f(v: str) -> str | None:
    v = (v or "").strip()
    return v or None


def _rows(path: Path, kind: str):
    """Staging rows from every CSV in the zip."""
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not info.filename.endswith(".csv"):
                continue
            with z.open(info) as raw:
                r = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline=""))
                h = {k: i for i, k in enumerate(next(r))}
                g = lambda row, k: row[h[k]] if k in h and h[k] < len(row) else ""   # noqa: E731
                for row in r:
                    if kind == "assistance" and g(row, "record_type_code") in ("1", "3"):
                        continue
                    key = g(row, "assistance_award_unique_key" if kind == "assistance" else "contract_award_unique_key")
                    fy = g(row, "action_date_fiscal_year")
                    if not key or not fy.isdigit():
                        continue
                    try:
                        ob = float(g(row, "federal_action_obligation") or 0)
                    except ValueError:
                        ob = 0.0
                    z5 = re.sub(r"\D", "", g(row, "recipient_zip_code") or g(row, "recipient_zip_4_code"))[:5]
                    officers = "|".join(f"{g(row, f'highly_compensated_officer_{i}_name')}~"
                                        f"{g(row, f'highly_compensated_officer_{i}_amount')}"
                                        for i in range(1, 6) if g(row, f"highly_compensated_officer_{i}_name"))
                    if kind == "assistance":
                        prog, title, atype = g(row, "cfda_number"), g(row, "cfda_title"), g(row, "assistance_type_code")
                        btypes = g(row, "business_types_description")
                        nonprofit = "NONPROFIT" in btypes.upper() or "HIGHER EDUCATION" in btypes.upper() and "PRIVATE" in btypes.upper()
                    else:
                        prog, title, atype = g(row, "naics_code"), g(row, "naics_description"), g(row, "award_type")
                        btypes = g(row, "organizational_type")
                        nonprofit = g(row, "nonprofit_organization") == "t" or g(row, "other_not_for_profit_organization") == "t"
                    yield (key, kind, int(fy), ob, _f(g(row, "action_date")), _f(g(row, "awarding_agency_name")),
                           _f(g(row, "awarding_sub_agency_name")), _f(g(row, "recipient_uei")),
                           _f(g(row, "recipient_duns")), _f(g(row, "recipient_name")),
                           _f(g(row, "recipient_parent_name")), _f(g(row, "recipient_address_line_1")),
                           _f(g(row, "recipient_city_name")), _f(g(row, "recipient_state_code")), z5 or None,
                           _f(prog), _f(title), _f(atype),
                           _f((g(row, "prime_award_base_transaction_description") or g(row, "transaction_description"))[:1000]),
                           _f(btypes), nonprofit, _f(g(row, "usaspending_permalink")), officers or None)


AGGREGATE = """
INSERT INTO usa_awards (award_key, kind, fiscal_year, obligation, n_actions, first_date, last_date, agency,
                        sub_agency, recipient_uei, recipient_duns, recipient_name, parent_name, street, city, state,
                        zip5, program_code, program_title, award_type, description, business_types, nonprofit,
                        permalink)
SELECT award_key, kind, fiscal_year, sum(obligation), count(*), min(action_date), max(action_date),
       (array_agg(agency ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(sub_agency ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(recipient_uei ORDER BY action_date DESC NULLS LAST) FILTER (WHERE recipient_uei IS NOT NULL))[1],
       (array_agg(recipient_duns ORDER BY action_date DESC NULLS LAST) FILTER (WHERE recipient_duns IS NOT NULL))[1],
       (array_agg(recipient_name ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(parent_name ORDER BY action_date DESC NULLS LAST) FILTER (WHERE parent_name IS NOT NULL))[1],
       (array_agg(street ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(city ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(state ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(zip5 ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(program_code ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(program_title ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(award_type ORDER BY action_date DESC NULLS LAST))[1],
       (array_agg(description ORDER BY action_date ASC NULLS LAST) FILTER (WHERE description IS NOT NULL))[1],
       (array_agg(business_types ORDER BY action_date DESC NULLS LAST))[1],
       bool_or(nonprofit), (array_agg(permalink ORDER BY action_date DESC NULLS LAST))[1]
FROM usa_stage WHERE abs(hashtext(award_key)) % {parts} = {part} GROUP BY award_key, kind, fiscal_year
ON CONFLICT (award_key, fiscal_year) DO UPDATE SET obligation = usa_awards.obligation + excluded.obligation,
    n_actions = usa_awards.n_actions + excluded.n_actions"""

OFFICERS = """
INSERT INTO usa_officers (award_key, fiscal_year, n, name, amount)
SELECT award_key, fiscal_year, o.n, split_part(o.v, '~', 1),
       -- some filings carry impossible amounts (over $10 billion): those are typos, kept as not reported
       CASE WHEN nullif(regexp_replace(split_part(o.v, '~', 2), '[^0-9.]', '', 'g'), '')::numeric < 1e10
            THEN nullif(regexp_replace(split_part(o.v, '~', 2), '[^0-9.]', '', 'g'), '')::numeric END
FROM (SELECT DISTINCT ON (award_key, fiscal_year) award_key, fiscal_year, officers FROM usa_stage
      WHERE officers IS NOT NULL AND abs(hashtext(award_key)) % {parts} = {part}
      ORDER BY award_key, fiscal_year, action_date DESC NULLS LAST) s,
     unnest(string_to_array(s.officers, '|')) WITH ORDINALITY o(v, n)
ON CONFLICT DO NOTHING"""


PARTS = 20                    # the aggregate is written in this many batches, each committed (bounded WAL)
PAUSE_FILE = Path("/tmp/load_pause")   # a monitor creates this while the database's disk or CPU is over 70%


def _gate(status=print) -> None:
    """Wait while the load monitor says the shared database is busy, then a short breather."""
    waited = 0
    while PAUSE_FILE.exists():
        if waited % 300 == 0:
            status("usaspending: database busy, waiting")
        time.sleep(30)
        waited += 30
    time.sleep(2)


def load_file(fy: int, kind: str, name: str, status=print) -> int:
    t0 = time.time()
    p = _download(name)
    status(f"usaspending FY{fy} {kind}: downloaded {p.stat().st_size / 1e9:.2f} GB in {time.time() - t0:.0f}s")
    with db.connect() as conn:
        conn.execute("TRUNCATE usa_stage")
        conn.commit()
        n = 0
        with conn.cursor().copy(f"COPY usa_stage ({', '.join(STAGE_COLS)}) FROM STDIN") as cp:
            for row in _rows(p, kind):
                cp.write_row(row)
                n += 1
                if n % 2_000_000 == 0:
                    status(f"usaspending FY{fy} {kind}: {n:,} transactions ({time.time() - t0:.0f}s)")
        conn.commit()
        # Transactions dated in other fiscal years stay in this file's load; the year comes from each row.
        years = [r[0] for r in conn.execute("SELECT DISTINCT fiscal_year FROM usa_stage").fetchall()]
        conn.execute("SET work_mem = '256MB'")
        # Replace the year in batches, each committed, waiting whenever the database is busy (prod shares it).
        for part in range(PARTS):
            _gate(status)
            conn.execute(f"""DELETE FROM usa_officers o USING usa_awards a WHERE a.award_key = o.award_key
                             AND a.fiscal_year = o.fiscal_year AND a.kind = %s AND a.fiscal_year = %s
                             AND abs(hashtext(a.award_key)) %% {PARTS} = {part}""", (kind, fy))
            conn.execute(f"""DELETE FROM usa_awards WHERE kind = %s AND fiscal_year = %s
                             AND abs(hashtext(award_key)) %% {PARTS} = {part}""", (kind, fy))
            conn.commit()
        for part in range(PARTS):
            _gate(status)
            conn.execute(AGGREGATE.format(parts=PARTS, part=part))
            conn.execute(OFFICERS.format(parts=PARTS, part=part))
            conn.commit()
        conn.execute("INSERT INTO usa_runs (fiscal_year, kind, file, transactions, finished) VALUES (%s, %s, %s, %s, now())",
                     (fy, kind, name, n))
        conn.execute("TRUNCATE usa_stage")
        conn.commit()
    p.unlink()
    status(f"usaspending FY{fy} {kind}: {n:,} transactions, years {sorted(years)[:3]}..., in {time.time() - t0:.0f}s")
    return n


def load(years: list[int] | None = None, kinds: tuple[str, ...] = ("assistance", "contract"), status=print) -> None:
    today = date.today()
    current = today.year + (1 if today.month >= 10 else 0)
    for fy in years or range(current, FIRST_FY - 1, -1):
        files = _files(fy)
        for kind in kinds:
            if kind in files:
                load_file(fy, kind, files[kind], status)


def refresh(status=print) -> list[tuple[int, str]]:
    """The archive is regenerated each month (around the 6th): reload the current and previous fiscal year, both
    kinds, wherever the archive holds a newer file than the one loaded. Returns the (year, kind) pairs reloaded."""
    today = date.today()
    current = today.year + (1 if today.month >= 10 else 0)
    with db.connect() as conn:
        loaded = {r[0] for r in conn.execute("SELECT file FROM usa_runs").fetchall()}
    out = []
    for fy in (current, current - 1):
        for kind, name in sorted(_files(fy).items()):
            if name not in loaded:
                load_file(fy, kind, name, status)
                out.append((fy, kind))
    return out


def link_orgs(status=print) -> None:
    """Recipients that are filing organizations: normalized name (np_name_core) and zip5 equal, exactly one EIN.
    Sets usa_awards.recipient_ein."""
    from loader.fec_links import ensure_function
    with db.connect() as conn:
        ensure_function(conn)
        conn.execute("""CREATE TEMP TABLE org_keys AS
                        SELECT np_name_core(name) AS core, left(regexp_replace(zip, '\\D', '', 'g'), 5) AS z5,
                               min(ein) AS ein
                        FROM organizations WHERE name IS NOT NULL AND zip IS NOT NULL GROUP BY 1, 2
                        HAVING count(*) = 1""")
        conn.execute("CREATE INDEX ON org_keys (core, z5)")
        conn.execute("""CREATE TEMP TABLE rec AS
                        SELECT DISTINCT recipient_name, zip5, np_name_core(recipient_name) AS core FROM usa_awards
                        WHERE recipient_name IS NOT NULL AND zip5 IS NOT NULL""")
        conn.execute("""UPDATE usa_awards a SET recipient_ein = k.ein FROM rec r JOIN org_keys k
                        ON k.core = r.core AND k.z5 = r.zip5
                        WHERE a.recipient_name = r.recipient_name AND a.zip5 = r.zip5
                          AND a.recipient_ein IS DISTINCT FROM k.ein""")
        conn.commit()
        r = conn.execute("""SELECT count(DISTINCT (recipient_name, zip5)) FILTER (WHERE recipient_ein IS NOT NULL),
                                   count(DISTINCT (recipient_name, zip5)),
                                   count(DISTINCT (recipient_name, zip5)) FILTER (WHERE nonprofit),
                                   count(DISTINCT (recipient_name, zip5)) FILTER (WHERE nonprofit AND recipient_ein IS NOT NULL)
                            FROM usa_awards""").fetchone()
    status(f"usaspending: recipients linked {r[0]:,} of {r[1]:,}; nonprofit recipients linked {r[3]:,} of {r[2]:,}")
