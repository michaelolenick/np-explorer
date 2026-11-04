"""FARA (Foreign Agents Registration Act) registrations, from the Justice Department's bulk data
(https://efile.fara.gov/ords/fara/f?p=1235:10, "FARA.gov API / Bulk Data Repository"; owner, 2026-11-04): the
primary registrants, their foreign principals, and the short-form registrants (the individuals who act for a
registrant). Three CSV zips, complete snapshots (active and terminated), updated daily, ISO-8859-1.

Tables (each load replaces them; the files are complete):
  fara_registrants   one row per registration number: name, business name, dates, address
  fara_principals    one row per foreign principal of a registrant: name, country, dates, the principal's address
  fara_short_forms   one row per short-form registrant (a person): name, dates, the registrant it acts for
  fara_person_links  short-form people -> person pages: the same normalized full name, with a middle name or
                     initial, held by exactly one person page, in one of that person's states (the registrant's)
  fara_org_links     registrants -> nonprofits (kind org: same name core and state, one on each side) and
                     federal lobbying registrants (kind lda: same name core, one on each side)

Every column of the three files is kept. Dates are MM/DD/YYYY in the files.

Usage: .venv/bin/python -m loader.fara [--no-download]
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import re
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from app.config import RAW_DIR
from app.names import normalize_name
from loader import db
from loader.recalls import core

BULK = "https://efile.fara.gov/bulk/zip/"
FILES = {"registrants": "FARA_All_Registrants.csv.zip", "principals": "FARA_All_ForeignPrincipals.csv.zip",
         "short_forms": "FARA_All_ShortForms.csv.zip"}
RAW = RAW_DIR / "fara"
UA = "furp.org research michael@furp.org"

DDL = """
CREATE TABLE IF NOT EXISTS fara_registrants (
    reg_number text PRIMARY KEY, name text NOT NULL, business_name text, name_core text,
    registration_date date, termination_date date, address1 text, address2 text, city text, state text, zip text,
    n_principals integer NOT NULL DEFAULT 0, n_people integer NOT NULL DEFAULT 0, loaded timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS fara_registrants_core ON fara_registrants (name_core);
CREATE INDEX IF NOT EXISTS fara_registrants_date ON fara_registrants (registration_date DESC);
CREATE TABLE IF NOT EXISTS fara_principals (
    id bigserial PRIMARY KEY, reg_number text NOT NULL, principal text NOT NULL, principal_core text,
    country text, registration_date date, termination_date date, registrant_date date, registrant_name text,
    address1 text, address2 text, city text, state text, zip text);
CREATE INDEX IF NOT EXISTS fara_principals_reg ON fara_principals (reg_number);
CREATE INDEX IF NOT EXISTS fara_principals_country ON fara_principals (country);
CREATE INDEX IF NOT EXISTS fara_principals_core ON fara_principals (principal_core);
CREATE TABLE IF NOT EXISTS fara_short_forms (
    id bigserial PRIMARY KEY, reg_number text NOT NULL, last_name text, first_name text, name text NOT NULL,
    name_norm text, form_date date, termination_date date, registration_date date, registrant_name text,
    address1 text, address2 text, city text, state text, zip text);
CREATE INDEX IF NOT EXISTS fara_short_forms_reg ON fara_short_forms (reg_number);
CREATE INDEX IF NOT EXISTS fara_short_forms_norm ON fara_short_forms (name_norm);
CREATE TABLE IF NOT EXISTS fara_person_links (
    short_form_id bigint PRIMARY KEY, reg_number text NOT NULL, name_norm text NOT NULL, cluster_id bigint NOT NULL,
    how text NOT NULL);
CREATE INDEX IF NOT EXISTS fara_person_links_cluster ON fara_person_links (cluster_id);
CREATE TABLE IF NOT EXISTS fara_org_links (
    reg_number text NOT NULL, kind text NOT NULL, key text NOT NULL, how text NOT NULL, PRIMARY KEY (reg_number, kind, key));
CREATE INDEX IF NOT EXISTS fara_org_links_key ON fara_org_links (kind, key);
"""


def _date(v: str | None) -> dt.date | None:
    v = (v or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)
    if not m:
        return None
    try:
        return dt.date(int(m[3]), int(m[1]), int(m[2]))
    except ValueError:
        return None


def _s(v: str | None, n: int = 300) -> str | None:
    v = (v or "").strip()
    return v[:n] or None


def download(status=print) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for key, name in FILES.items():
        req = urllib.request.Request(BULK + name, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        (RAW / name).write_bytes(data)
        status(f"fara: {name} {len(data):,} bytes")


def rows(key: str) -> list[dict]:
    with zipfile.ZipFile(RAW / FILES[key]) as z:
        name = z.namelist()[0]
        text = z.read(name).decode("iso-8859-1")
    return list(csv.DictReader(io.StringIO(text)))


def load(status=print) -> dict:
    """Replace the three tables from the downloaded files, then rebuild the links."""
    regs = rows("registrants")
    prins = rows("principals")
    shorts = rows("short_forms")
    now = dt.datetime.now(dt.UTC)
    n_pr, n_sf = defaultdict(int), defaultdict(int)
    for r in prins:
        n_pr[r["Registration Number"].strip()] += 1
    for r in shorts:
        n_sf[r["Registration Number"].strip()] += 1
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("TRUNCATE fara_registrants, fara_principals, fara_short_forms, fara_person_links, fara_org_links")
        with conn.cursor() as cur:
            seen = set()
            def reg_rows():
                for r in regs:
                    num = r["Registration Number"].strip()
                    name = _s(r["Name"])
                    if not num or not name or num in seen:
                        continue
                    seen.add(num)
                    yield (num, name, _s(r["Business Name"]), core(name)[:300], _date(r["Registration Date"]),
                           _date(r["Termination Date"]), _s(r["Address 1"]), _s(r["Address 2"]), _s(r["City"], 100),
                           _s(r["State"], 40), _s(r["Zip"], 20), n_pr.get(num, 0), n_sf.get(num, 0), now)
            n = db.copy_rows(cur, "fara_registrants", ["reg_number", "name", "business_name", "name_core", "registration_date",
                                                       "termination_date", "address1", "address2", "city", "state", "zip",
                                                       "n_principals", "n_people", "loaded"], reg_rows())
            def prin_rows():
                for r in prins:
                    num, name = r["Registration Number"].strip(), _s(r["Foreign Principal"])
                    if not num or not name:
                        continue
                    yield (num, name, core(name)[:300], _s(r["Country/Location Represented"], 100),
                           _date(r["Foreign Principal Registration Date"]), _date(r["Foreign Principal Termination Date"]),
                           _date(r["Registrant Date"]), _s(r["Registrant Name"]), _s(r["Address 1"]), _s(r["Address 2"]),
                           _s(r["City"], 100), _s(r["State"], 40), _s(r["Zip"], 20))
            p = db.copy_rows(cur, "fara_principals", ["reg_number", "principal", "principal_core", "country", "registration_date",
                                                      "termination_date", "registrant_date", "registrant_name", "address1",
                                                      "address2", "city", "state", "zip"], prin_rows())
            def sf_rows():
                for r in shorts:
                    num = r["Registration Number"].strip()
                    first, last = _s(r["Short Form First Name"], 100), _s(r["Short Form Last Name"], 100)
                    name = " ".join(x for x in (first, last) if x)
                    if not num or not name:
                        continue
                    yield (num, last, first, name, normalize_name(name) or None, _date(r["Short Form Date"]),
                           _date(r["Short Form Termination Date"]), _date(r["Registration Date"]), _s(r["Registrant Name"]),
                           _s(r["Address 1"]), _s(r["Address 2"]), _s(r["City"], 100), _s(r["State"], 40), _s(r["Zip"], 20))
            s = db.copy_rows(cur, "fara_short_forms", ["reg_number", "last_name", "first_name", "name", "name_norm", "form_date",
                                                       "termination_date", "registration_date", "registrant_name", "address1",
                                                       "address2", "city", "state", "zip"], sf_rows())
        conn.commit()
        status(f"fara: {n:,} registrants, {p:,} foreign principals, {s:,} short-form registrants")
        out = {"registrants": n, "principals": p, "short_forms": s}
        out.update(links(conn, status))
        conn.commit()
    return out


def links(conn, status=print) -> dict:
    """Short-form people to person pages; registrants to nonprofits and lobbying registrants."""
    conn.execute("SET work_mem = '256MB'")
    conn.execute("DELETE FROM fara_person_links")
    conn.execute("DELETE FROM fara_org_links")
    # People: a full name with a middle part, on exactly one person page, whose states include the registrant's.
    n_people = conn.execute("""
        INSERT INTO fara_person_links (short_form_id, reg_number, name_norm, cluster_id, how)
        SELECT s.id, s.reg_number, s.name_norm, u.id, 'full name with a middle part, and the registrant''s state'
        FROM fara_short_forms s
        JOIN (SELECT name_norm, min(id) AS id, min(states) AS states FROM person_clusters
              WHERE NOT coalesce(is_institution, false) GROUP BY name_norm HAVING count(*) = 1) u ON u.name_norm = s.name_norm
        WHERE s.name_norm IS NOT NULL AND array_length(string_to_array(s.name_norm, ' '), 1) >= 3
          AND s.state IS NOT NULL AND s.state = ANY(u.states)""").rowcount
    # Organizations: the registrant's name core and state, held by one registrant and one nonprofit.
    orgs = conn.execute("SELECT ein, name, state FROM organizations WHERE name IS NOT NULL AND state IS NOT NULL").fetchall()
    conn.execute("CREATE TEMP TABLE fara_oc (ein text, core text, state text) ON COMMIT DROP")
    with conn.cursor() as cur, cur.copy("COPY fara_oc FROM STDIN") as cp:
        for ein, name, st in orgs:
            c = core(name)
            if len(c) >= 4:
                cp.write_row((ein, c, st))
    conn.execute("CREATE INDEX ON fara_oc (core, state)")
    n_org = conn.execute("""
        INSERT INTO fara_org_links (reg_number, kind, key, how)
        SELECT r.reg_number, 'org', o.ein, 'name and state'
        FROM (SELECT name_core, state, min(reg_number) AS reg_number FROM fara_registrants
              WHERE length(name_core) >= 4 GROUP BY 1, 2 HAVING count(*) = 1) r
        JOIN (SELECT core, state, min(ein) AS ein FROM fara_oc GROUP BY 1, 2 HAVING count(*) = 1) o
             ON o.core = r.name_core AND o.state = r.state""").rowcount
    n_lda = 0
    if conn.execute("SELECT to_regclass('lda_filings') IS NOT NULL").fetchone()[0]:
        regs = conn.execute("SELECT registrant_id, min(registrant_name) FROM lda_filings WHERE registrant_name IS NOT NULL "
                            "GROUP BY 1").fetchall()
        conn.execute("CREATE TEMP TABLE fara_lc (registrant_id bigint, core text) ON COMMIT DROP")
        with conn.cursor() as cur, cur.copy("COPY fara_lc FROM STDIN") as cp:
            for rid, name in regs:
                c = core(name)
                if len(c) >= 4:
                    cp.write_row((rid, c))
        n_lda = conn.execute("""
            INSERT INTO fara_org_links (reg_number, kind, key, how)
            SELECT r.reg_number, 'lda', l.registrant_id::text, 'name'
            FROM (SELECT name_core, min(reg_number) AS reg_number FROM fara_registrants
                  WHERE length(name_core) >= 4 GROUP BY 1 HAVING count(*) = 1) r
            JOIN (SELECT core, min(registrant_id) AS registrant_id FROM fara_lc GROUP BY 1 HAVING count(*) = 1) l
                 ON l.core = r.name_core""").rowcount
    status(f"fara links: {n_people:,} people, {n_org:,} nonprofits, {n_lda:,} lobbying registrants")
    return {"person_links": n_people, "org_links": n_org, "lda_links": n_lda}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--no-download", action="store_true", help="load the files already in %s" % RAW)
    a = ap.parse_args(argv)
    if not a.no_download:
        download()
    load()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
