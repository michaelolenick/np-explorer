"""Form 5500 and 5500-SF annual returns of employee benefit plans, from the Department of Labor's EFAST2 bulk
datasets (https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets;
owner, 2026-11-04): names and states only, plus the record id, as a supplement to the state business registries.

Files: F_5500_{year}_Latest.zip and F_5500_SF_{year}_Latest.zip, plan years 2009 (the first EFAST2 year) to now,
one CSV each, updated by DOL around the first of each month. Kept in /bulk/form5500/.

Tables (each file replaces its own rows; ACK_ID, the EFAST2 record id, is the key, so an amended filing is its
own record and a re-run never duplicates one):
  form5500_filings   one row per filing: form, plan year, date received, plan name, the sponsor (name, DBA, EIN,
                     state, city), the plan administrator (name, EIN, state), the sponsor and EIN last reported
                     under, and the names that signed and prepared the return
  form5500_names     the filing's other named entities, one row each with the state they gave: the sponsor's
                     care-of name, the DBA, the administrator's care-of name, the preparer and the preparer's
                     firm, the signers (people, with name_norm), the last-reported sponsor, and on the 5500-SF
                     the fiduciary trust and the trustee or custodian

Dropped: every other field: addresses beyond city and state (street, zip, foreign addresses), phone numbers,
business codes, participant counts, all financial amounts, the yes/no indicators (amended, final, schedules
attached, funding and benefit arrangements, 401(k) questions, the SF compliance questions), filing status and
signature validity flags, pension and welfare benefit codes, dates other than the plan year and date received.

Then `supplement` adds the sponsors to the business registry tables (biz_entities, biz_people, biz_names, source
'form5500'; one entity per sponsor EIN, keyed f5500-{EIN} in the sponsor's latest state) and rebuilds biz_links
(loader/business_registry.links: nonprofits by EIN, SEC filers and Form D issuers by name, officers to person pages
by full name and state), so Form 5500 sponsors and their signers join the people and name clusters.

Usage: .venv/bin/python -m loader.form5500 [download] [load [YEAR ...]] [summarize] [supplement]
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

from app.names import normalize_name
from loader import db

RAW = Path("/bulk/form5500")
BASE = "https://www.askebsa.dol.gov/FOIA%20Files/{year}/Latest/{name}"
FIRST_YEAR = 2009
UA = "furp.org research michael@furp.org"
FORMS = {"5500": "F_5500_{year}_Latest.zip", "5500-SF": "F_5500_SF_{year}_Latest.zip"}

DDL = """
CREATE TABLE IF NOT EXISTS form5500_filings (
    ack_id text PRIMARY KEY, form text NOT NULL, year smallint NOT NULL, plan_year smallint, date_received date,
    plan_name text, plan_num text, sponsor_name text, sponsor_dba text, sponsor_ein text, sponsor_state text,
    sponsor_city text, sponsor_country text, admin_name text, admin_ein text, admin_state text,
    last_sponsor_name text, last_sponsor_ein text, preparer_name text, preparer_firm text, preparer_state text,
    admin_signed_name text, sponsor_signed_name text, dfe_signed_name text, trust_name text, trust_ein text,
    trustee_name text, loaded timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS form5500_filings_ein ON form5500_filings (sponsor_ein);
CREATE INDEX IF NOT EXISTS form5500_filings_year ON form5500_filings (year, form);
CREATE TABLE IF NOT EXISTS form5500_names (
    ack_id text NOT NULL, kind text NOT NULL, name text NOT NULL, name_norm text, state text, ein text);
CREATE INDEX IF NOT EXISTS form5500_names_ack ON form5500_names (ack_id);
CREATE INDEX IF NOT EXISTS form5500_names_norm ON form5500_names (name_norm) WHERE name_norm IS NOT NULL;
CREATE TABLE IF NOT EXISTS form5500_files (
    file text PRIMARY KEY, form text NOT NULL, year smallint NOT NULL, bytes bigint, rows integer, loaded timestamptz);
"""

FILING_COLS = ["ack_id", "form", "year", "plan_year", "date_received", "plan_name", "plan_num", "sponsor_name", "sponsor_dba",
               "sponsor_ein", "sponsor_state", "sponsor_city", "sponsor_country", "admin_name", "admin_ein", "admin_state",
               "last_sponsor_name", "last_sponsor_ein", "preparer_name", "preparer_firm", "preparer_state",
               "admin_signed_name", "sponsor_signed_name", "dfe_signed_name", "trust_name", "trust_ein", "trustee_name",
               "loaded"]
NAME_COLS = ["ack_id", "kind", "name", "name_norm", "state", "ein"]
PEOPLE = {"preparer", "admin_signer", "sponsor_signer", "dfe_signer"}   # kinds that are individuals: name_norm set

# Column names in the two files (the 5500-SF prefixes most of its columns with SF_ and names a few differently).
F = {"5500": dict(plan_year="FORM_PLAN_YEAR_BEGIN_DATE", plan_name="PLAN_NAME", plan_num="SPONS_DFE_PN",
                  sponsor="SPONSOR_DFE_NAME", dba="SPONS_DFE_DBA_NAME", care_of="SPONS_DFE_CARE_OF_NAME",
                  mail_state="SPONS_DFE_MAIL_US_STATE", mail_city="SPONS_DFE_MAIL_US_CITY", loc_state="SPONS_DFE_LOC_US_STATE",
                  loc_city="SPONS_DFE_LOC_US_CITY", country="SPONS_DFE_MAIL_FOREIGN_CNTRY", ein="SPONS_DFE_EIN",
                  admin="ADMIN_NAME", admin_care_of="ADMIN_CARE_OF_NAME", admin_state="ADMIN_US_STATE", admin_ein="ADMIN_EIN",
                  last_sponsor="LAST_RPT_SPONS_NAME", last_ein="LAST_RPT_SPONS_EIN", preparer="PREPARER_NAME",
                  preparer_firm="PREPARER_FIRM_NAME", preparer_state="PREPARER_US_STATE",
                  admin_signed=("ADMIN_SIGNED_NAME", "ADMIN_MANUAL_SIGNED_NAME"),
                  sponsor_signed=("SPONS_SIGNED_NAME", "SPONS_MANUAL_SIGNED_NAME"),
                  dfe_signed=("DFE_SIGNED_NAME", "DFE_MANUAL_SIGNED_NAME"), trust=None, trust_ein=None, trustee=None),
     "5500-SF": dict(plan_year="SF_PLAN_YEAR_BEGIN_DATE", plan_name="SF_PLAN_NAME", plan_num="SF_PLAN_NUM",
                     sponsor="SF_SPONSOR_NAME", dba="SF_SPONSOR_DFE_DBA_NAME", care_of="SF_SPONS_CARE_OF_NAME",
                     mail_state="SF_SPONS_US_STATE", mail_city="SF_SPONS_US_CITY", loc_state="SF_SPONS_LOC_US_STATE",
                     loc_city="SF_SPONS_LOC_US_CITY", country="SF_SPONS_FOREIGN_CNTRY", ein="SF_SPONS_EIN",
                     admin="SF_ADMIN_NAME", admin_care_of="SF_ADMIN_CARE_OF_NAME", admin_state="SF_ADMIN_US_STATE",
                     admin_ein="SF_ADMIN_EIN", last_sponsor="SF_LAST_RPT_SPONS_NAME", last_ein="SF_LAST_RPT_SPONS_EIN",
                     preparer="SF_PREPARER_NAME", preparer_firm="SF_PREPARER_FIRM_NAME", preparer_state="SF_PREPARER_US_STATE",
                     admin_signed=("SF_ADMIN_SIGNED_NAME", "SF_ADMIN_MANUAL_SIGNED_NAME"),
                     sponsor_signed=("SF_SPONS_SIGNED_NAME", "SF_SPONS_MANUAL_SIGNED_NAME"), dfe_signed=(),
                     trust="SF_FDCRY_TRUST_NAME", trust_ein="SF_FDCRY_TRUST_EIN", trustee="SF_FDCRY_TRUSTE_CUST_NAME")}


def _s(v, n=300):
    v = (v or "").strip()
    return v[:n] or None


def _ein(v):
    v = re.sub(r"\D", "", v or "")
    return v if len(v) == 9 and v != "000000000" else None


def _state(v):
    v = (v or "").strip().upper()
    return v if re.fullmatch(r"[A-Z]{2}", v) else None


def _year(v):
    m = re.match(r"(\d{4})-\d\d-\d\d", (v or "").strip())
    return int(m[1]) if m else None


def _date(v):
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", (v or "").strip())
    if not m:
        return None
    try:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def _first(r, keys):
    for k in keys or ():
        v = _s(r.get(k))
        if v:
            return v
    return None


def parse(form: str, r: dict, year: int, now) -> tuple[tuple, list[tuple]]:
    """One CSV row -> (filing row, name rows)."""
    f = F[form]
    ack = r["ACK_ID"].strip()
    sponsor = _s(r.get(f["sponsor"]), 200)
    state = _state(r.get(f["mail_state"])) or _state(r.get(f["loc_state"]))
    city = _s(r.get(f["mail_city"]), 100) or _s(r.get(f["loc_city"]), 100)
    admin = _s(r.get(f["admin"]), 200)
    admin_state = _state(r.get(f["admin_state"]))
    preparer, firm = _s(r.get(f["preparer"]), 100), _s(r.get(f["preparer_firm"]), 200)
    preparer_state = _state(r.get(f["preparer_state"]))
    a_sign, s_sign, d_sign = _first(r, f["admin_signed"]), _first(r, f["sponsor_signed"]), _first(r, f["dfe_signed"])
    trust = _s(r.get(f["trust"]), 200) if f["trust"] else None
    trust_ein = _ein(r.get(f["trust_ein"])) if f["trust_ein"] else None
    trustee = _s(r.get(f["trustee"]), 200) if f["trustee"] else None
    last_sponsor, last_ein = _s(r.get(f["last_sponsor"]), 200), _ein(r.get(f["last_ein"]))
    filing = (ack, form, year, _year(r.get(f["plan_year"])), _date(r.get("DATE_RECEIVED")), _s(r.get(f["plan_name"]), 200),
              _s(r.get(f["plan_num"]), 3), sponsor, _s(r.get(f["dba"]), 200), _ein(r.get(f["ein"])), state, city,
              _s(r.get(f["country"]), 2), admin, _ein(r.get(f["admin_ein"])), admin_state, last_sponsor, last_ein,
              preparer, firm, preparer_state, a_sign, s_sign, d_sign, trust, trust_ein, trustee, now)
    names = []

    def add(kind, name, st=None, ein=None):
        if name:
            names.append((ack, kind, name, (normalize_name(name) or None) if kind in PEOPLE else None, st, ein))
    add("sponsor_care_of", _s(r.get(f["care_of"]), 200), state)
    add("sponsor_dba", _s(r.get(f["dba"]), 200), state)
    add("admin_care_of", _s(r.get(f["admin_care_of"]), 200), admin_state)
    if last_sponsor and (last_sponsor != sponsor or (last_ein and last_ein != _ein(r.get(f["ein"])))):
        add("last_sponsor", last_sponsor, state, last_ein)
    add("preparer", preparer, preparer_state)
    add("preparer_firm", firm, preparer_state)
    add("admin_signer", a_sign, admin_state or state)
    add("sponsor_signer", s_sign, state)
    add("dfe_signer", d_sign, state)
    add("trust", trust, state, trust_ein)
    add("trustee", trustee, state)
    return filing, names


def download(years=None, status=print) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for year in years or range(FIRST_YEAR, dt.date.today().year + 1):
        for form, pat in FORMS.items():
            name = pat.format(year=year)
            path = RAW / name
            if path.exists() and path.stat().st_size > 10000:
                continue
            req = urllib.request.Request(BASE.format(year=year, name=name), headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=600) as r, open(path.with_suffix(".part"), "wb") as out:
                    while chunk := r.read(1 << 20):
                        out.write(chunk)
            except Exception as e:  # noqa: BLE001 - a year not published yet
                status(f"form5500: {name}: {type(e).__name__}")
                path.with_suffix(".part").unlink(missing_ok=True)
                continue
            path.with_suffix(".part").rename(path)
            status(f"form5500: {name} {path.stat().st_size:,} bytes")


def load_file(conn, form: str, year: int, status=print) -> int:
    name = FORMS[form].format(year=year)
    path = RAW / name
    if not path.exists():
        return 0
    now = dt.datetime.now(dt.UTC)
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS f5_f (LIKE form5500_filings)")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS f5_n (LIKE form5500_names)")
    conn.execute("TRUNCATE f5_f, f5_n")
    n = 0
    with zipfile.ZipFile(path) as z:
        member = next(m for m in z.namelist() if m.lower().endswith(".csv"))
        with z.open(member) as raw, conn.cursor() as cur:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
            reader = csv.DictReader(text)
            with cur.copy(f"COPY f5_f ({', '.join(FILING_COLS)}) FROM STDIN") as cf:
                names = []
                for r in reader:
                    if not r.get("ACK_ID", "").strip():
                        continue
                    filing, nm = parse(form, r, year, now)
                    cf.write_row(filing)
                    names.extend(nm)
                    n += 1
            with cur.copy(f"COPY f5_n ({', '.join(NAME_COLS)}) FROM STDIN") as cn:
                for row in names:
                    cn.write_row(row)
    # Replace this file's rows (and any earlier copy of the same record from another file).
    conn.execute("DELETE FROM form5500_names WHERE ack_id IN (SELECT ack_id FROM form5500_filings WHERE form = %s AND year = %s)",
                 (form, year))
    conn.execute("DELETE FROM form5500_filings WHERE form = %s AND year = %s", (form, year))
    conn.execute("DELETE FROM form5500_names WHERE ack_id IN (SELECT ack_id FROM f5_f)")
    conn.execute("DELETE FROM form5500_filings WHERE ack_id IN (SELECT ack_id FROM f5_f)")
    conn.execute(f"INSERT INTO form5500_filings ({', '.join(FILING_COLS)}) SELECT DISTINCT ON (ack_id) {', '.join(FILING_COLS)} "
                 f"FROM f5_f ORDER BY ack_id")
    conn.execute(f"INSERT INTO form5500_names ({', '.join(NAME_COLS)}) SELECT {', '.join(NAME_COLS)} FROM f5_n "
                 f"WHERE ack_id IN (SELECT ack_id FROM form5500_filings WHERE form = %s AND year = %s)", (form, year))
    conn.execute("""INSERT INTO form5500_files (file, form, year, bytes, rows, loaded) VALUES (%s, %s, %s, %s, %s, now())
                    ON CONFLICT (file) DO UPDATE SET bytes = excluded.bytes, rows = excluded.rows, loaded = now()""",
                 (name, form, year, path.stat().st_size, n))
    conn.commit()
    status(f"form5500: {name}: {n:,} filings")
    return n


def load(years=None, status=print) -> int:
    total = 0
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("SET statement_timeout = 0")
        conn.commit()
        for year in years or range(FIRST_YEAR, dt.date.today().year + 1):
            for form in FORMS:
                total += load_file(conn, form, year, status)
    return total


def summarize(status=print) -> int:
    """form5500_sponsors: one row per sponsor EIN (the latest name, state and city; filings, plans and years), for
    the search and sponsor pages and the registry supplement."""
    from loader.recalls import core
    with db.connect() as conn:
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '1GB'")
        conn.execute("""CREATE TABLE IF NOT EXISTS form5500_sponsors (ein text PRIMARY KEY, name text, name_core text, state text,
                        city text, filings integer, plans integer, first_year smallint, last_year smallint, plan_names text[])""")
        conn.execute("DROP TABLE IF EXISTS form5500_sponsors_new")
        conn.execute("""
            CREATE TABLE form5500_sponsors_new AS
            WITH latest AS (SELECT DISTINCT ON (sponsor_ein) sponsor_ein AS ein, sponsor_name AS name, sponsor_state AS state,
                                   sponsor_city AS city FROM form5500_filings
                            WHERE sponsor_ein IS NOT NULL AND sponsor_name IS NOT NULL
                            ORDER BY sponsor_ein, plan_year DESC NULLS LAST, date_received DESC NULLS LAST),
                 agg AS (SELECT sponsor_ein AS ein, count(*) AS filings, count(DISTINCT plan_num) AS plans, min(plan_year) AS first_year,
                                max(plan_year) AS last_year, (array_agg(DISTINCT plan_name))[1:5] AS plan_names
                         FROM form5500_filings WHERE sponsor_ein IS NOT NULL GROUP BY 1)
            SELECT l.ein, l.name, ''::text AS name_core, l.state, l.city, a.filings::int, a.plans::int, a.first_year, a.last_year, a.plan_names
            FROM latest l JOIN agg a USING (ein)""")
        rows = conn.execute("SELECT ein, name FROM form5500_sponsors_new").fetchall()
        conn.execute("CREATE TEMP TABLE f5_core (ein text, core text) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy("COPY f5_core FROM STDIN") as cp:
            for ein, name in rows:
                cp.write_row((ein, core(name)[:300]))
        conn.execute("UPDATE form5500_sponsors_new s SET name_core = c.core FROM f5_core c WHERE c.ein = s.ein")
        conn.execute("ALTER TABLE form5500_sponsors_new ADD PRIMARY KEY (ein)")
        conn.execute("CREATE INDEX ON form5500_sponsors_new (name_core text_pattern_ops)")
        conn.execute("CREATE INDEX ON form5500_sponsors_new (state, filings DESC)")
        db.swap_table(conn, "form5500_sponsors")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM form5500_sponsors").fetchone()[0]
    status(f"form5500: {n:,} sponsors")
    return n


def supplement(status=print) -> dict:
    """Sponsors into the business registry tables as source 'form5500', then the registry links."""
    from loader import business_registry
    from loader.recalls import core
    with db.connect() as conn:
        conn.execute("SET statement_timeout = 0")
        conn.execute("SET work_mem = '512MB'")
        conn.execute("DELETE FROM biz_people WHERE source = 'form5500'")
        conn.execute("DELETE FROM biz_names WHERE source = 'form5500'")
        conn.execute("DELETE FROM biz_entities WHERE source = 'form5500'")
        conn.commit()
        # One entity per sponsor EIN: the latest filing's name, state and city; the span of plan years and plans.
        conn.execute("""
            CREATE TEMP TABLE f5_sp AS
            SELECT DISTINCT ON (sponsor_ein) sponsor_ein AS ein, sponsor_name AS name, sponsor_state AS state, sponsor_city AS city,
                   sponsor_dba AS dba
            FROM form5500_filings WHERE sponsor_ein IS NOT NULL AND sponsor_name IS NOT NULL AND sponsor_state IS NOT NULL
            ORDER BY sponsor_ein, plan_year DESC NULLS LAST, date_received DESC NULLS LAST""")
        conn.execute("""
            CREATE TEMP TABLE f5_sum AS
            SELECT sponsor_ein AS ein, min(plan_year) AS y0, max(plan_year) AS y1, count(*) AS filings,
                   count(DISTINCT plan_num) AS plans, (array_agg(DISTINCT plan_name))[1:3] AS plan_names
            FROM form5500_filings WHERE sponsor_ein IS NOT NULL GROUP BY 1""")
        rows = conn.execute("SELECT s.ein, s.name, s.state, s.city, m.y0, m.y1, m.filings, m.plans, m.plan_names "
                            "FROM f5_sp s JOIN f5_sum m USING (ein)").fetchall()
        conn.execute("CREATE TEMP TABLE f5_be (LIKE biz_entities INCLUDING DEFAULTS)")
        cols = ["state", "entity_id", "name", "name_core", "entity_type", "status", "city", "addr_state", "jurisdiction",
                "source", "loaded", "ein", "provenance", "extra"]
        with conn.cursor() as cur, cur.copy(f"COPY f5_be ({', '.join(cols)}) FROM STDIN") as cp:
            for ein, name, st, city, y0, y1, nf, np_, pnames in rows:
                cp.write_row((st, f"f5500-{ein}", name[:500], core(name)[:500], "Employee benefit plan sponsor (Form 5500)",
                              f"Filed for plan year {y1}" if y1 else None, city, st,
                              f"Plan years {y0} to {y1}" if y0 and y1 and y0 != y1 else (f"Plan year {y1}" if y1 else None),
                              "form5500", dt.datetime.now(dt.UTC), ein,
                              "Form 5500 and 5500-SF filings (Department of Labor EFAST2 bulk data), plan sponsor",
                              json.dumps({"filings": nf, "plans": np_, "first_year": y0, "last_year": y1,
                                          "plan_names": [p for p in (pnames or []) if p]})))
        n_ent = conn.execute(f"INSERT INTO biz_entities ({', '.join(cols)}) SELECT {', '.join(cols)} FROM f5_be "
                             "ON CONFLICT (state, entity_id) DO NOTHING").rowcount
        # People and other entities named on the sponsor's filings: signers and preparers (people), the administrator,
        # the preparer's firm, the trust and the trustee (organizations). One row per sponsor, name and role.
        n_people = conn.execute("""
            INSERT INTO biz_people (state, entity_id, name, name_norm, role, is_entity, address, source)
            SELECT x.state, 'f5500-' || x.ein, x.name, x.name_norm, x.role || CASE WHEN min(x.plan_year) = max(x.plan_year)
                       THEN ', plan year ' || max(x.plan_year) ELSE ', plan years ' || min(x.plan_year) || ' to ' || max(x.plan_year) END,
                   x.is_entity, max(x.where_), 'form5500'
            FROM (
                SELECT sp.state, sp.ein, n.name, n.name_norm, f.plan_year, NOT (n.kind IN ('preparer', 'admin_signer', 'sponsor_signer', 'dfe_signer')) AS is_entity,
                       CASE n.kind WHEN 'sponsor_signer' THEN 'Signed the Form 5500 for the plan sponsor'
                                   WHEN 'admin_signer' THEN 'Signed the Form 5500 as plan administrator'
                                   WHEN 'dfe_signer' THEN 'Signed the Form 5500 for the direct filing entity'
                                   WHEN 'preparer' THEN 'Preparer of the Form 5500'
                                   WHEN 'preparer_firm' THEN 'Preparer''s firm (Form 5500)'
                                   WHEN 'trust' THEN 'Fiduciary trust (Form 5500-SF)'
                                   WHEN 'trustee' THEN 'Trustee or custodian (Form 5500-SF)'
                                   WHEN 'sponsor_care_of' THEN 'Care-of name (Form 5500)'
                                   WHEN 'admin_care_of' THEN 'Administrator''s care-of name (Form 5500)' END AS role,
                       n.state AS where_
                FROM form5500_filings f JOIN f5_sp sp ON sp.ein = f.sponsor_ein
                JOIN form5500_names n ON n.ack_id = f.ack_id
                WHERE n.kind IN ('preparer', 'admin_signer', 'sponsor_signer', 'dfe_signer', 'preparer_firm', 'trust', 'trustee',
                                 'sponsor_care_of', 'admin_care_of')
                UNION ALL
                SELECT sp.state, sp.ein, f.admin_name, NULL, f.plan_year, true, 'Plan administrator (Form 5500)', f.admin_state
                FROM form5500_filings f JOIN f5_sp sp ON sp.ein = f.sponsor_ein
                WHERE f.admin_name IS NOT NULL AND f.admin_name <> f.sponsor_name
                      AND (f.admin_ein IS NULL OR f.admin_ein <> f.sponsor_ein)
            ) x WHERE x.role IS NOT NULL
            GROUP BY x.state, x.ein, x.name, x.name_norm, x.role, x.is_entity""").rowcount
        n_names = conn.execute("""
            INSERT INTO biz_names (state, entity_id, name, name_core, kind, source)
            SELECT DISTINCT ON (sp.state, sp.ein, n.name) sp.state, 'f5500-' || sp.ein, n.name, '', 'DBA (Form 5500)', 'form5500'
            FROM form5500_filings f JOIN f5_sp sp ON sp.ein = f.sponsor_ein
            JOIN form5500_names n ON n.ack_id = f.ack_id AND n.kind = 'sponsor_dba'
            WHERE n.name <> sp.name ON CONFLICT DO NOTHING""").rowcount
        # name_core for the DBAs (the registry computes it in Python).
        dbas = conn.execute("SELECT state, entity_id, name FROM biz_names WHERE source = 'form5500' AND name_core = ''").fetchall()
        with conn.cursor() as cur:
            for st, eid, name in dbas:
                cur.execute("UPDATE biz_names SET name_core = %s WHERE state = %s AND entity_id = %s AND name = %s AND source = 'form5500'",
                            (core(name)[:300], st, eid, name))
        conn.execute("""INSERT INTO biz_runs (source, rows) VALUES ('form5500', %s)""", (n_ent,))
        conn.commit()
        status(f"form5500 supplement: {n_ent:,} sponsors, {n_people:,} people and named entities, {n_names:,} DBAs into the registry")
    out = {"entities": n_ent, "people": n_people, "names": n_names}
    out["links"] = business_registry.links(status=status)
    return out


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        argv = ["download", "load", "summarize"]
    i = 0
    while i < len(argv):
        cmd = argv[i]
        i += 1
        years = []
        while i < len(argv) and argv[i].isdigit():
            years.append(int(argv[i]))
            i += 1
        if cmd == "download":
            download(years or None)
        elif cmd == "load":
            load(years or None)
        elif cmd == "summarize":
            summarize()
        elif cmd == "supplement":
            supplement()
        else:
            raise SystemExit(f"unknown command {cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
