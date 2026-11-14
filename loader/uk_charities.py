"""UK charities: the Charity Commission for England and Wales register of charities, into schema `uk`
(owner, 2026-11-14: "UK 990s ... treat it like the American nonprofit data").

Source: https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download -- daily tab-delimited
extracts at https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.<name>.zip. The page says "All content
is available under the Open Government Licence v3.0, except where otherwise stated" (checked 2026-11-14), so the data may be
reused with attribution. Attribution shown on the pages (app/uk_charities.py):
"Contains public sector information licensed under the Open Government Licence v3.0. Source: Charity Commission for England and Wales."
Scope: England and Wales only (Scotland's OSCR and Northern Ireland's CCNI keep their own registers, not loaded).

What loads (python -m loader.uk_charities download load summarize; nightly = the scheduled run):
  download   one conditional GET per extract (If-None-Match / If-Modified-Since against uk.meta), raw zips kept in
             /bulk/uk_charities/raw, fixed User-Agent, a pause between files; nothing is fetched when the Commission's
             Last-Modified has not changed
  load       each changed extract into its table in one transaction (TRUNCATE + COPY), restartable per table:
               uk.charity            every registered, removed and linked charity (399,178 rows; main charity = linked_number 0)
               uk.return_history     one row per financial year per charity: income, expenditure, dates received
               uk.parta              Part A of the annual return: fundraising, government income, trustee benefits, staff earning over 60k, volunteers
               uk.partb              Part B (charities over 500k income): income and spending breakdowns, assets, funds, employees
               uk.trustee            current trustees (individuals P and organisations O)
               uk.classification     what / how / who codes; uk.area  areas of operation; uk.other_name  working and previous names
               uk.governing          governing document, charitable objects, area of benefit; uk.policy; uk.event  history (mergers, transfers...)
               uk.regulator; uk.report  (inquiries and other published reports)
  summarize  uk.charity_main (one row per registered number with its latest figures, postcode area and region, web domain),
             uk.trustee_count, search index rows (uk.search), counts in uk.meta

Every table is rebuilt from the whole extract (the Commission republishes the whole register daily); a rerun with an
unchanged Last-Modified does nothing. Status line style: "uk charities: <step>: <detail>".
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from loader import db

RAW = Path(os.environ.get("UK_CHARITIES_RAW_DIR", "/bulk/uk_charities/raw"))
BASE = "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.{}.zip"
PAGE = "https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download"
UA = "furp.org data loader (info@furp.org)"
PAUSE = 3                      # seconds between downloads
ATTRIBUTION = ("Contains public sector information licensed under the Open Government Licence v3.0. "
               "Source: Charity Commission for England and Wales.")

FILES = ["charity", "charity_annual_return_history", "charity_annual_return_parta", "charity_annual_return_partb",
         "charity_trustee", "charity_classification", "charity_area_of_operation", "charity_other_names",
         "charity_governing_document", "charity_policy", "charity_event_history", "charity_other_regulators",
         "charity_published_report"]

# --- postcode area -> region (offline, approximate: the letters before the first digit say where the postcode is) -----
_REGIONS = {
    "North East": "DH DL NE SR TS".split(),
    "North West": "BB BL CA CH CW FY L LA M OL PR SK WA WN".split(),
    "Yorkshire and The Humber": "BD DN HD HG HU HX LS S WF YO".split(),
    "East Midlands": "DE LE LN NG NN".split(),
    "West Midlands": "B CV DY HR ST TF WR WS WV".split(),
    "East of England": "AL CB CM CO IP LU NR PE SG SS WD".split(),
    "London": "E EC N NW SE SW W WC BR CR EN HA IG RM SM TW UB".split(),
    "South East": "BN CT GU HP KT ME MK OX PO RG RH SL SO TN".split(),
    "South West": "BA BH BS DT EX GL PL SN SP TA TQ TR".split(),
    "Wales": "CF LD LL NP SA SY".split(),
}
AREA_REGION: dict[str, str] = {}
for _r, _areas in _REGIONS.items():
    for _a in _areas:
        AREA_REGION.setdefault(_a, _r)
# Postcode areas that straddle regions are put where most of their addresses are; the outer London areas (BR, CR, DA, HA,
# KT, RM, SM, TW, UB) are mostly Greater London, so they are labelled London; GU, KT also reach Surrey (South East).
AREA_REGION.update({"KT": "South East", "GU": "South East", "DA": "South East", "SY": "West Midlands", "HR": "West Midlands",
                    "CH": "North West", "TD": "Scotland", "DG": "Scotland", "BT": "Northern Ireland",
                    "IM": "Isle of Man", "JE": "Jersey", "GY": "Guernsey", "ZE": "Scotland", "EH": "Scotland", "G": "Scotland"})
_PC = re.compile(r"^\s*([A-Za-z]{1,2})\d")


def postcode_area(pc: str | None) -> str | None:
    m = _PC.match(pc or "")
    return m.group(1).upper() if m else None


def region_of(area: str | None) -> str | None:
    return AREA_REGION.get(area) if area else None


# --- parsing --------------------------------------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} uk charities: {msg}", flush=True)


def d10(v: str) -> str | None:
    v = (v or "").strip()
    return v[:10] if re.match(r"^\d{4}-\d\d-\d\d", v) else None


def num(v: str):
    v = (v or "").strip()
    if not v:
        return None
    try:
        float(v)
        return v
    except ValueError:
        return None


def intv(v: str):
    v = num(v)
    return None if v is None else str(int(float(v)))


def boo(v: str):
    v = (v or "").strip().lower()
    return "t" if v in ("true", "1") else ("f" if v in ("false", "0") else None)


def txt(v: str):
    v = (v or "").replace("\x00", "").strip()
    return v or None


def read_rows(zpath: Path, name: str):
    """Yield dicts for each record of the extract's tab-delimited text (UTF-8, optional BOM, no quoting; a record that
    ends early because a field holds a line break is joined with the next line)."""
    with zipfile.ZipFile(zpath) as z:
        member = next(n for n in z.namelist() if n.endswith(".txt"))
        with z.open(member) as raw:
            f = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            header = f.readline().rstrip("\r\n").split("\t")
            width = len(header)
            buf = ""
            for line in f:
                line = line.rstrip("\r\n")
                buf = line if not buf else buf + " " + line
                parts = buf.split("\t")
                if len(parts) < width:
                    continue
                if len(parts) > width:                     # stray tabs inside the last text field
                    parts = parts[:width - 1] + [" ".join(parts[width - 1:])]
                buf = ""
                yield dict(zip(header, parts))


# --- tables ---------------------------------------------------------------------------------------------------------

DDL = """
CREATE SCHEMA IF NOT EXISTS uk;
CREATE TABLE IF NOT EXISTS uk.meta (key text PRIMARY KEY, etag text, last_modified text, rows bigint, loaded timestamptz,
                                    checked timestamptz, note text);
CREATE TABLE IF NOT EXISTS uk.charity (
    organisation_number bigint PRIMARY KEY, reg_number bigint NOT NULL, linked_number integer NOT NULL, name text, name_core text,
    charity_type text, status text, registered date, removed date, reporting_status text, fin_start date, fin_end date,
    income numeric, expenditure numeric, address1 text, address2 text, address3 text, address4 text, address5 text,
    postcode text, phone text, email text, web text, company_number text, insolvent boolean, in_administration boolean,
    previously_excepted boolean, cdf_or_cif text, is_cio boolean, cio_dissolved boolean, cio_dissolution_notice date,
    activities text, gift_aid boolean, has_land boolean);
CREATE INDEX IF NOT EXISTS uk_charity_reg ON uk.charity (reg_number, linked_number);
CREATE TABLE IF NOT EXISTS uk.return_history (
    organisation_number bigint, reg_number bigint, fin_start date, fin_end date, cycle text, due date, ar_received date,
    accounts_received date, income numeric, expenditure numeric, qualified boolean, suppressed boolean, suppression_type text);
CREATE INDEX IF NOT EXISTS uk_rh_org ON uk.return_history (organisation_number, fin_end);
CREATE TABLE IF NOT EXISTS uk.parta (
    organisation_number bigint, reg_number bigint, latest boolean, cycle text, fin_start date, fin_end date, income numeric,
    expenditure numeric, raises_from_public boolean, professional_fundraiser boolean, commercial_participator boolean,
    grant_making_main boolean, govt_contracts boolean, govt_contracts_n integer, govt_grants boolean, govt_grants_n integer,
    govt_contracts_income numeric, govt_grants_income numeric, trading_subsidiary boolean, trustee_benefit boolean,
    trustee_paid_as_trustee boolean, trustee_paid_services boolean, staff_over_60k boolean, staff_over_60k_n integer,
    volunteers integer);
CREATE INDEX IF NOT EXISTS uk_parta_org ON uk.parta (organisation_number, fin_end);
CREATE TABLE IF NOT EXISTS uk.partb (
    organisation_number bigint, reg_number bigint, latest boolean, cycle text, fin_start date, fin_end date,
    inc_donations numeric, inc_trading numeric, inc_charitable numeric, inc_investments numeric, inc_other numeric,
    inc_total numeric, inc_legacies numeric, inc_endowments numeric, exp_raising_funds numeric, exp_charitable numeric,
    exp_other numeric, exp_total numeric, exp_investment_mgmt numeric, exp_grants_institutions numeric,
    exp_governance numeric, exp_support numeric, exp_depreciation numeric, gain_investments numeric, reserves numeric,
    assets_fixed numeric, assets_own_use numeric, assets_investments numeric, assets_other numeric, liabilities numeric,
    assets_current_investments numeric, net_assets numeric, creditors_1y numeric, creditors_after_1y numeric, cash numeric,
    funds_endowment numeric, funds_unrestricted numeric, funds_restricted numeric, funds_total numeric, employees integer,
    charity_only boolean, consolidated boolean);
CREATE INDEX IF NOT EXISTS uk_partb_org ON uk.partb (organisation_number, fin_end);
CREATE TABLE IF NOT EXISTS uk.trustee (
    organisation_number bigint, reg_number bigint, linked_number integer, trustee_id bigint, name text, name_norm text,
    is_chair boolean, kind text, appointed date);
CREATE INDEX IF NOT EXISTS uk_trustee_org ON uk.trustee (organisation_number);
CREATE INDEX IF NOT EXISTS uk_trustee_reg ON uk.trustee (reg_number);
CREATE INDEX IF NOT EXISTS uk_trustee_norm ON uk.trustee (name_norm) WHERE kind = 'P';
CREATE INDEX IF NOT EXISTS uk_trustee_id ON uk.trustee (trustee_id);
CREATE TABLE IF NOT EXISTS uk.classification (organisation_number bigint, reg_number bigint, linked_number integer,
    code text, kind text, description text);
CREATE INDEX IF NOT EXISTS uk_class_org ON uk.classification (organisation_number);
CREATE INDEX IF NOT EXISTS uk_class_code ON uk.classification (kind, code);
CREATE TABLE IF NOT EXISTS uk.area (organisation_number bigint, reg_number bigint, linked_number integer, area_type text,
    area text, parent_type text, parent_area text, welsh boolean);
CREATE INDEX IF NOT EXISTS uk_area_org ON uk.area (organisation_number);
CREATE INDEX IF NOT EXISTS uk_area_area ON uk.area (area_type, area);
CREATE TABLE IF NOT EXISTS uk.other_name (organisation_number bigint, reg_number bigint, linked_number integer,
    name_id bigint, name_type text, name text, name_core text);
CREATE INDEX IF NOT EXISTS uk_othername_org ON uk.other_name (organisation_number);
CREATE INDEX IF NOT EXISTS uk_othername_core ON uk.other_name (name_core);
CREATE TABLE IF NOT EXISTS uk.governing (organisation_number bigint PRIMARY KEY, reg_number bigint, linked_number integer,
    document text, objects text, area_of_benefit text);
CREATE TABLE IF NOT EXISTS uk.policy (organisation_number bigint, reg_number bigint, linked_number integer, policy text);
CREATE INDEX IF NOT EXISTS uk_policy_org ON uk.policy (organisation_number);
CREATE TABLE IF NOT EXISTS uk.event (organisation_number bigint, reg_number bigint, linked_number integer, name text,
    event_order integer, event_type text, event_date date, reason text, assoc_organisation_number bigint,
    assoc_reg_number bigint, assoc_name text);
CREATE INDEX IF NOT EXISTS uk_event_org ON uk.event (organisation_number);
CREATE INDEX IF NOT EXISTS uk_event_assoc ON uk.event (assoc_organisation_number);
CREATE TABLE IF NOT EXISTS uk.regulator (organisation_number bigint, reg_number bigint, regulator_order integer,
    regulator text, url text);
CREATE INDEX IF NOT EXISTS uk_regulator_org ON uk.regulator (organisation_number);
CREATE TABLE IF NOT EXISTS uk.report (organisation_number bigint, reg_number bigint, linked_number integer, report text,
    location text, published date);
CREATE INDEX IF NOT EXISTS uk_report_org ON uk.report (organisation_number);
"""


def core_name(s):
    from loader.recalls import core
    return core(s)[:200] or None


def norm_person(s: str | None) -> str | None:
    """A trustee's name for matching with person_clusters.name_norm: lower-case ASCII, no honorifics or punctuation."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace("'", "")
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", s).split()
             if w not in ("mr", "mrs", "ms", "miss", "dr", "prof", "professor", "sir", "dame", "lord", "lady", "rev", "revd", "rt",
                          "reverend", "cllr", "councillor", "canon", "fr", "hon", "the", "mbe", "obe", "cbe", "kc", "qc", "jp", "dl")]
    return " ".join(words) or None


def row_charity(r):
    a = lambda k: txt(r.get(k, ""))
    web = a("charity_contact_web")
    return (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
            a("charity_name"), core_name(r.get("charity_name")), a("charity_type"), a("charity_registration_status"),
            d10(r["date_of_registration"]), d10(r["date_of_removal"]), a("charity_reporting_status"),
            d10(r["latest_acc_fin_period_start_date"]), d10(r["latest_acc_fin_period_end_date"]), num(r["latest_income"]),
            num(r["latest_expenditure"]), a("charity_contact_address1"), a("charity_contact_address2"),
            a("charity_contact_address3"), a("charity_contact_address4"), a("charity_contact_address5"),
            a("charity_contact_postcode"), a("charity_contact_phone"), (a("charity_contact_email") or "").lower() or None,
            web, a("charity_company_registration_number"), boo(r["charity_insolvent"]), boo(r["charity_in_administration"]),
            boo(r["charity_previously_excepted"]), a("charity_is_cdf_or_cif"), boo(r["charity_is_cio"]), boo(r["cio_is_dissolved"]),
            d10(r["date_cio_dissolution_notice"]), a("charity_activities"), boo(r["charity_gift_aid"]), boo(r["charity_has_land"]))


def _salary_n(r):
    t, any_ = 0, False
    for k, v in r.items():
        if k.startswith("count_salary_band_"):
            n = intv(v)
            if n is not None:
                t += int(n)
                any_ = True
    return str(t) if any_ else None


def row_parta(r):
    return (intv(r["organisation_number"]), intv(r["registered_charity_number"]), boo(r["latest_fin_period_submitted_ind"]),
            txt(r["ar_cycle_reference"]), d10(r["fin_period_start_date"]), d10(r["fin_period_end_date"]),
            num(r["total_gross_income"]), num(r["total_gross_expenditure"]), boo(r["charity_raises_funds_from_public"]),
            boo(r["charity_professional_fundraiser"]), boo(r["charity_commercial_participator"]),
            boo(r["grant_making_is_main_activity"]), boo(r["charity_receives_govt_funding_contracts"]),
            intv(r["count_govt_contracts"]), boo(r["charity_receives_govt_funding_grants"]), intv(r["count_govt_grants"]),
            num(r["income_from_government_contracts"]), num(r["income_from_government_grants"]),
            boo(r["charity_has_trading_subsidiary"]), boo(r["does_trustee_receive_any_benefit"]),
            boo(r["trustee_payments_acting_as_trustee"]), boo(r["trustee_receives_payments_services"]),
            boo(r["employees_salary_over_60k"]), _salary_n(r), intv(r["count_volunteers"]))


PARTB_MAP = [("income_donations_and_legacies", num), ("income_other_trading_activities", num), ("income_charitable_activities", num),
             ("income_investments", num), ("income_other", num), ("income_total_income_and_endowments", num),
             ("income_legacies", num), ("income_endowments", num), ("expenditure_raising_funds", num),
             ("expenditure_charitable_expenditure", num), ("expenditure_other", num), ("expenditure_total", num),
             ("expenditure_investment_management", num), ("expenditure_grants_institution", num), ("expenditure_governance", num),
             ("expenditure_support_costs", num), ("expenditure_depreciation", num), ("gain_loss_investment", num), ("reserves", num),
             ("assets_total_fixed", num), ("assets_own_use", num), ("assets_long_term_investment", num), ("assets_other_assets", num),
             ("assets_total_liabilities", num), ("assets_current_investment", num), ("assets_total_assets_and_liabilities", num),
             ("creditors_one_year_total_current", num), ("creditors_falling_due_after_one_year", num), ("assets_cash", num),
             ("funds_endowment", num), ("funds_unrestricted", num), ("funds_restricted", num), ("funds_total", num),
             ("count_employees", intv), ("charity_only_accounts", boo), ("consolidated_accounts", boo)]


def row_partb(r):
    return (intv(r["organisation_number"]), intv(r["registered_charity_number"]), boo(r["latest_fin_period_submitted_ind"]),
            txt(r["ar_cycle_reference"]), d10(r["fin_period_start_date"]), d10(r["fin_period_end_date"])) + \
        tuple(fn(r.get(k, "")) for k, fn in PARTB_MAP)


# table -> (extract, columns, row function)
TABLES = {
    "charity": ("charity", None, row_charity),
    "return_history": ("charity_annual_return_history",
                       ["organisation_number", "reg_number", "fin_start", "fin_end", "cycle", "due", "ar_received",
                        "accounts_received", "income", "expenditure", "qualified", "suppressed", "suppression_type"],
                       lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), d10(r["fin_period_start_date"]),
                                  d10(r["fin_period_end_date"]), txt(r["ar_cycle_reference"]), d10(r["reporting_due_date"]),
                                  d10(r["date_annual_return_received"]), d10(r["date_accounts_received"]), num(r["total_gross_income"]),
                                  num(r["total_gross_expenditure"]), boo(r["accounts_qualified"]), boo(r["suppression_ind"]),
                                  txt(r["suppression_type"]))),
    "parta": ("charity_annual_return_parta", None, row_parta),
    "partb": ("charity_annual_return_partb", None, row_partb),
    "trustee": ("charity_trustee",
                ["organisation_number", "reg_number", "linked_number", "trustee_id", "name", "name_norm", "is_chair", "kind", "appointed"],
                lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                           intv(r["trustee_id"]), txt(r["trustee_name"]),
                           norm_person(r["trustee_name"]) if (r["individual_or_organisation"] or "P").strip() != "O" else None,
                           boo(r["trustee_is_chair"]), txt(r["individual_or_organisation"]), d10(r["trustee_date_of_appointment"]))),
    "classification": ("charity_classification",
                       ["organisation_number", "reg_number", "linked_number", "code", "kind", "description"],
                       lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                                  txt(r["classification_code"]), txt(r["classification_type"]), txt(r["classification_description"]))),
    "area": ("charity_area_of_operation",
             ["organisation_number", "reg_number", "linked_number", "area_type", "area", "parent_type", "parent_area", "welsh"],
             lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                        txt(r["geographic_area_type"]), txt(r["geographic_area_description"]), txt(r["parent_geographic_area_type"]),
                        txt(r["parent_geographic_area_description"]), boo(r["welsh_ind"]))),
    "other_name": ("charity_other_names",
                   ["organisation_number", "reg_number", "linked_number", "name_id", "name_type", "name", "name_core"],
                   lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                              intv(r["charity_name_id"]), txt(r["charity_name_type"]), txt(r["charity_name"]), core_name(r["charity_name"]))),
    "governing": ("charity_governing_document",
                  ["organisation_number", "reg_number", "linked_number", "document", "objects", "area_of_benefit"],
                  lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                             txt(r["governing_document_description"]), txt(r["charitable_objects"]), txt(r["area_of_benefit"]))),
    "policy": ("charity_policy", ["organisation_number", "reg_number", "linked_number", "policy"],
               lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                          txt(r["policy_name"]))),
    "event": ("charity_event_history",
              ["organisation_number", "reg_number", "linked_number", "name", "event_order", "event_type", "event_date", "reason",
               "assoc_organisation_number", "assoc_reg_number", "assoc_name"],
              lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                         txt(r["charity_name"]), intv(r["charity_event_order"]), txt(r["event_type"]), d10(r["date_of_event"]),
                         txt(r["reason"]), intv(r["assoc_organisation_number"]), intv(r["assoc_registered_charity_number"]),
                         txt(r["assoc_charity_name"]))),
    "regulator": ("charity_other_regulators", ["organisation_number", "reg_number", "regulator_order", "regulator", "url"],
                  lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["regulator_order"]),
                             txt(r["regulator_name"]), txt(r["regulator_web_url"]))),
    "report": ("charity_published_report",
               ["organisation_number", "reg_number", "linked_number", "report", "location", "published"],
               lambda r: (intv(r["organisation_number"]), intv(r["registered_charity_number"]), intv(r["linked_charity_number"]),
                          txt(r["report_name"]), txt(r["report_location"]), d10(r["date_published"]))),
}
LOAD_ORDER = ["charity", "return_history", "parta", "partb", "trustee", "classification", "area", "other_name", "governing",
              "policy", "event", "regulator", "report"]


def ensure_schema(conn) -> None:
    conn.execute(DDL)
    conn.commit()


# --- download -------------------------------------------------------------------------------------------------------

def download(force: bool = False) -> int:
    """One conditional GET per extract. Returns the number of files that changed."""
    RAW.mkdir(parents=True, exist_ok=True)
    changed = 0
    with db.connect() as conn:
        ensure_schema(conn)
        for i, name in enumerate(FILES):
            key = "file:" + name
            row = conn.execute("SELECT etag, last_modified FROM uk.meta WHERE key = %s", (key,)).fetchone()
            dest = RAW / f"publicextract.{name}.zip"
            req = urllib.request.Request(BASE.format(name), headers={"User-Agent": UA})
            if row and dest.exists() and not force:
                if row[0]:
                    req.add_header("If-None-Match", row[0])
                if row[1]:
                    req.add_header("If-Modified-Since", row[1])
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    tmp = dest.with_suffix(".part")
                    with open(tmp, "wb") as out:
                        while chunk := resp.read(1 << 20):
                            out.write(chunk)
                    zipfile.ZipFile(tmp).testzip()
                    tmp.replace(dest)
                    etag, lm = resp.headers.get("ETag"), resp.headers.get("Last-Modified")
                conn.execute("""INSERT INTO uk.meta (key, etag, last_modified, checked, note) VALUES (%s, %s, %s, now(), 'downloaded; not loaded yet')
                                ON CONFLICT (key) DO UPDATE SET etag = EXCLUDED.etag, last_modified = EXCLUDED.last_modified,
                                    checked = now(), note = 'downloaded; not loaded yet'""", (key, etag, lm))
                changed += 1
                _log(f"download: {name}: new file ({dest.stat().st_size / 1e6:.1f} MB, Last-Modified {lm})")
            except urllib.error.HTTPError as ex:
                if ex.code == 304:
                    conn.execute("UPDATE uk.meta SET checked = now() WHERE key = %s", (key,))
                    _log(f"download: {name}: unchanged")
                else:
                    _log(f"download: {name}: HTTP {ex.code}")
            conn.commit()
            if i < len(FILES) - 1:
                time.sleep(PAUSE)
    _log(f"download: {changed} of {len(FILES)} files changed")
    return changed


# --- load -----------------------------------------------------------------------------------------------------------

def columns_of(conn, table: str) -> list[str]:
    return [r[0] for r in conn.execute("""SELECT column_name FROM information_schema.columns WHERE table_schema = 'uk'
                                          AND table_name = %s ORDER BY ordinal_position""", (table,)).fetchall()]


def load(only: list[str] | None = None, force: bool = False) -> None:
    with db.connect() as conn:
        ensure_schema(conn)
        for table in LOAD_ORDER:
            if only and table not in only:
                continue
            extract, cols, fn = TABLES[table]
            zpath = RAW / f"publicextract.{extract}.zip"
            if not zpath.exists():
                _log(f"load: {table}: no file {zpath.name}, skipped")
                continue
            meta = conn.execute("SELECT etag, note FROM uk.meta WHERE key = %s", ("file:" + extract,)).fetchone()
            done = conn.execute("SELECT etag FROM uk.meta WHERE key = %s", ("table:" + table,)).fetchone()
            if not force and meta and done and done[0] == meta[0]:
                _log(f"load: {table}: up to date")
                continue
            cols = cols or columns_of(conn, table)
            t0, n = time.time(), 0
            ph = ", ".join(cols)
            seen: set = set()
            with conn.cursor() as cur:
                cur.execute(f"TRUNCATE uk.{table}")
                with cur.copy(f"COPY uk.{table} ({ph}) FROM STDIN") as cp:
                    for r in read_rows(zpath, extract):
                        row = fn(r)
                        if table in ("charity", "governing"):
                            if row[0] in seen or row[0] is None:
                                continue
                            seen.add(row[0])
                        cp.write_row(row)
                        n += 1
                        if n % 500000 == 0:
                            _log(f"load: {table}: {n:,} rows ...")
            conn.execute("""INSERT INTO uk.meta (key, etag, rows, loaded, checked, note) VALUES (%s, %s, %s, now(), now(), 'loaded')
                            ON CONFLICT (key) DO UPDATE SET etag = EXCLUDED.etag, rows = EXCLUDED.rows, loaded = now(), note = 'loaded'""",
                         ("table:" + table, meta[0] if meta else None, n))
            conn.commit()
            conn.execute(f"ANALYZE uk.{table}")
            conn.commit()
            _log(f"load: {table}: {n:,} rows in {time.time() - t0:.0f}s")


# --- summarize ------------------------------------------------------------------------------------------------------

SUMMARY_DDL = """
DROP TABLE IF EXISTS uk.charity_main_new;
CREATE TABLE uk.charity_main_new AS
SELECT c.reg_number, c.organisation_number, c.name, c.name_core, c.charity_type, c.status, c.registered, c.removed, c.reporting_status,
       c.fin_start, c.fin_end, c.income, c.expenditure, c.postcode, c.postcode_area, c.region, c.phone, c.email, c.web, c.web_domain,
       c.company_number, c.is_cio, c.activities, c.address_line,
       coalesce(t.n, 0) AS trustees, coalesce(t.individuals, 0) AS trustee_people,
       coalesce(l.n, 0) AS linked_charities,
       g.income AS income_prev, g.fin_end AS prev_end,
       p.volunteers, b.employees
FROM (SELECT c.*, uk.postcode_area(c.postcode) AS postcode_area, uk.region_of(uk.postcode_area(c.postcode)) AS region,
             uk.web_domain(c.web) AS web_domain,
             concat_ws(', ', c.address1, c.address2, c.address3, c.address4, c.address5) AS address_line
      FROM uk.charity c WHERE c.linked_number = 0) c
LEFT JOIN (SELECT reg_number, count(*) n, count(*) FILTER (WHERE kind = 'P') individuals FROM uk.trustee WHERE linked_number = 0 GROUP BY 1) t
       ON t.reg_number = c.reg_number
LEFT JOIN (SELECT reg_number, count(*) n FROM uk.charity WHERE linked_number > 0 GROUP BY 1) l ON l.reg_number = c.reg_number
LEFT JOIN LATERAL (SELECT h.income, h.fin_end FROM uk.return_history h WHERE h.organisation_number = c.organisation_number
                   AND h.fin_end < c.fin_end AND h.income IS NOT NULL ORDER BY h.fin_end DESC LIMIT 1) g ON c.fin_end IS NOT NULL
LEFT JOIN LATERAL (SELECT a.volunteers FROM uk.parta a WHERE a.organisation_number = c.organisation_number AND a.latest
                   ORDER BY a.fin_end DESC LIMIT 1) p ON true
LEFT JOIN LATERAL (SELECT x.employees FROM uk.partb x WHERE x.organisation_number = c.organisation_number AND x.latest
                   ORDER BY x.fin_end DESC LIMIT 1) b ON true;
"""

FUNCS = r"""
CREATE OR REPLACE FUNCTION uk.postcode_area(pc text) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT upper((regexp_match(pc, '^\s*([A-Za-z]{1,2})\d'))[1]) $$;
CREATE OR REPLACE FUNCTION uk.web_domain(w text) RETURNS text LANGUAGE sql IMMUTABLE AS
$$ SELECT nullif(regexp_replace(regexp_replace(regexp_replace(lower(trim(coalesce(w, ''))), '^[a-z]+://', ''), '^www\d*\.', ''), '[/?#:].*$', ''), '')
   WHERE w ~ '\.' $$;
"""


def summarize() -> None:
    t0 = time.time()
    with db.connect() as conn:
        ensure_schema(conn)
        conn.execute(FUNCS)
        conn.execute("""CREATE TABLE IF NOT EXISTS uk.region_map (area text PRIMARY KEY, region text NOT NULL)""")
        conn.execute("TRUNCATE uk.region_map")
        with conn.cursor() as cur:
            with cur.copy("COPY uk.region_map (area, region) FROM STDIN") as cp:
                for a, r in sorted(AREA_REGION.items()):
                    cp.write_row((a, r))
        conn.execute("""CREATE OR REPLACE FUNCTION uk.region_of(area text) RETURNS text LANGUAGE sql STABLE AS
                        $$ SELECT region FROM uk.region_map WHERE uk.region_map.area = $1 $$""")
        conn.commit()
        conn.execute("SET work_mem = '256MB'")
        conn.execute(SUMMARY_DDL)
        conn.execute("ALTER TABLE uk.charity_main_new ADD PRIMARY KEY (reg_number)")
        for ddl in ("(name_core)", "(income DESC NULLS LAST) WHERE income IS NOT NULL", "(web_domain) WHERE web_domain IS NOT NULL",
                    "(company_number) WHERE company_number IS NOT NULL", "(region)", "(postcode_area)",
                    "USING gin (name gin_trgm_ops)", "(status)"):
            conn.execute(f"CREATE INDEX ON uk.charity_main_new {ddl}")
        conn.commit()
        conn.execute("ANALYZE uk.charity_main_new")
        conn.execute("SET lock_timeout = '60s'")
        if conn.execute("SELECT to_regclass('uk.charity_main') IS NOT NULL").fetchone()[0]:
            # the board views depend on uk.charity_main, so the table stays and its rows are swapped in one transaction
            conn.execute("TRUNCATE uk.charity_main")
            conn.execute("INSERT INTO uk.charity_main SELECT * FROM uk.charity_main_new")
            conn.execute("DROP TABLE uk.charity_main_new")
        else:
            conn.execute("ALTER TABLE uk.charity_main_new RENAME TO charity_main")
            for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'uk' AND tablename = 'charity_main'").fetchall():
                if "_new" in idx:
                    conn.execute(f'ALTER INDEX uk."{idx}" RENAME TO "{idx.replace("charity_main_new", "charity_main")}"')
        conn.commit()
        conn.execute("ANALYZE uk.charity_main")
        conn.commit()
        n = conn.execute("SELECT count(*) FROM uk.charity_main").fetchone()[0]
        conn.execute("""INSERT INTO uk.meta (key, rows, loaded, checked, note) VALUES ('summary', %s, now(), now(), 'charity_main')
                        ON CONFLICT (key) DO UPDATE SET rows = EXCLUDED.rows, loaded = now(), checked = now()""", (n,))
        conn.commit()
    _log(f"summarize: uk.charity_main {n:,} rows in {time.time() - t0:.0f}s")


EXIT_CHANGED = 10      # `nightly` exit status when the Commission republished (scripts/nightly.sh then refreshes the boards)


def nightly(force: bool = False) -> int:
    """The nightly refresh: one conditional download per extract file (nothing is fetched when Last-Modified/ETag are unchanged);
    only when something changed: reload those tables, rebuild the summary, recompute the UK to US matches, and refresh the xlinks
    rows (once they have been published: `python -m loader.uk_xref publish` after the pages are on prod). Returns EXIT_CHANGED
    when the data changed, 0 when it did not."""
    changed = download(force=force)
    if not changed and not force:
        _log("nightly: the register has not changed since the last load")
        return 0
    load(force=force)
    summarize()
    from loader import uk_xref
    uk_xref.match()
    with db.connect() as conn:
        published = conn.execute("SELECT 1 FROM uk.meta WHERE key = 'xlinks'").fetchone()
    if published:
        uk_xref.publish()
    return EXIT_CHANGED


def status() -> None:
    with db.connect() as conn:
        if conn.execute("SELECT to_regclass('uk.meta') IS NULL").fetchone()[0]:
            print("uk charities: nothing loaded")
            return
        for k, rows, loaded, lm in conn.execute("SELECT key, rows, loaded, last_modified FROM uk.meta ORDER BY key").fetchall():
            print(f"uk charities: {k}: rows={rows} loaded={loaded} last_modified={lm}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("steps", nargs="*", default=["download", "load", "summarize"],
                    help="download load summarize nightly status (default: download load summarize)")
    ap.add_argument("--force", action="store_true", help="download and reload even when unchanged")
    ap.add_argument("--only", help="comma-separated table names for load")
    a = ap.parse_args(argv)
    changed = None
    for s in a.steps:
        if s == "download":
            changed = download(force=a.force)
        elif s == "load":
            load(a.only.split(",") if a.only else None, force=a.force)
        elif s == "summarize":
            summarize()
        elif s == "nightly":
            return nightly(force=a.force)
        elif s == "status":
            status()
        else:
            ap.error(f"unknown step {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
