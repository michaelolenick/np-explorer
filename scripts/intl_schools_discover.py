"""Find US nonprofits tied to schools outside the United States (review step; writes no tables).

Stages (each caches its output under WORK, so reruns are cheap):
  ror         stream the ROR CSV dump (ROR_DIR/*-ror-data.csv; download once from https://zenodo.org/records/23187250)
              into ror_edu.json (active education records) and ror_us_all.json (all active US records)
  candidates  stream organizations once; match names (minus wrappers) against ROR non-US education names;
              add NTEE-B orgs reporting foreign grants (Part IX line 3) and orgs with a foreign address
  evidence    per-candidate indexed lookups: latest filings, mission, website, officers, grants, Part IX
  xml         fetch each candidate's latest return XML (GivingTuesday mirror of IRS e-file data) and read
              filer country, Schedule F regions/amounts, Schedule R foreign related orgs, program text
  report      decide EXACT / FUZZY per (school, org) pair; write docs/international-schools.md and
              data/international-schools.csv

Usage: python scripts/intl_schools_discover.py [stage ...]      (default: all stages in order)
Env: DATABASE_URL, optional INTL_WORK (cache dir, default ~/unipay-data/intl) and ROR_DIR (~/unipay-data/ror).
Memory: streams everything; peak RSS is about 300 MB.
"""
from __future__ import annotations

import csv
import gzip
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

WORK = Path(os.environ.get("INTL_WORK", Path.home() / "unipay-data" / "intl"))
ROR_DIR = Path(os.environ.get("ROR_DIR", Path.home() / "unipay-data" / "ror"))
ROR_EDU = WORK / "ror_edu.json"          # active education records, all countries (ror_filter)
ROR_US_ALL = WORK / "ror_us_all.json"    # names of every active US record, any type (name-collision check)
REPO = Path(__file__).resolve().parent.parent
UA = "furp.org research (nonprofit data; +https://furp.org)"
GT_XML = "https://gt990datalake-rawdata.s3.amazonaws.com/EfileData/XmlFiles/{oid}_public.xml"

US_STATES = set("""AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM
NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR VI GU AS MP AA AE AP FM MH PW""".split())

# IRS e-file country codes (FIPS 10-4 style) -> ISO 3166 alpha-2, for the countries that matter here.
IRS_CC = {
    "UK": "GB", "IS": "IL", "CA": "CA", "AS": "AU", "CH": "CN", "SN": "SG", "SZ": "CH", "GM": "DE", "FR": "FR",
    "SP": "ES", "IT": "IT", "JA": "JP", "KS": "KR", "EI": "IE", "NL": "NL", "MX": "MX", "BR": "BR", "IN": "IN",
    "NZ": "NZ", "SF": "ZA", "BE": "BE", "AU": "AT", "SW": "SE", "NO": "NO", "DA": "DK", "FI": "FI", "PO": "PT",
    "GR": "GR", "TU": "TR", "EG": "EG", "LE": "LB", "JO": "JO", "HK": "HK", "TW": "TW", "RP": "PH", "TH": "TH",
    "VM": "VN", "ID": "ID", "MY": "MY", "PK": "PK", "BG": "BD", "CE": "LK", "NP": "NP", "KE": "KE", "UG": "UG",
    "TZ": "TZ", "NI": "NG", "GH": "GH", "ET": "ET", "RW": "RW", "AR": "AR", "CI": "CL", "CO": "CO", "PE": "PE",
    "EC": "EC", "VE": "VE", "CS": "CR", "GT": "GT", "HO": "HN", "NU": "NI", "PM": "PA", "DR": "DO", "HA": "HT",
    "JM": "JM", "PL": "PL", "EZ": "CZ", "HU": "HU", "RO": "RO", "UP": "UA", "RS": "RU", "AM": "AM", "GG": "GE",
    "LH": "LT", "LG": "LV", "EN": "EE", "LU": "LU", "IC": "IS", "MT": "MT", "CY": "CY", "SA": "SA", "AE": "AE",
    "QA": "QA", "KU": "KW", "BA": "BH", "MU": "OM", "IZ": "IQ", "IR": "IR", "AF": "AF", "LO": "SK", "SI": "SI",
    "HR": "HR", "BK": "BA", "RI": "RS", "MK": "MK", "AL": "AL", "BO": "BY", "MD": "MD", "KZ": "KZ", "UZ": "UZ",
    "MG": "MN", "CB": "KH", "BM": "MM", "LA": "LA", "WE": "PS", "GZ": "PS", "SY": "SY", "YM": "YE", "SU": "SD",
    "MO": "MA", "TS": "TN", "AG": "DZ", "LY": "LY", "SG": "SN", "ML": "ML", "CM": "CM", "ZA": "ZM", "ZI": "ZW",
    "MI": "MW", "MZ": "MZ", "AO": "AO", "CG": "CD", "BC": "BW", "WA": "NA", "SL": "SL", "LI": "LR", "BB": "BB",
    "TD": "TT", "BF": "BS", "BD": "BM", "CJ": "KY", "VI": "VG", "RQ": "PR", "GQ": "GU", "MC": "MO", "VT": "VA",
}
# Schedule F region names -> ROR continent names.
REGION_CONTINENT = [
    ("EUROPE", "Europe"), ("RUSSIA", "Europe"), ("MIDDLE EAST", "Asia"), ("SOUTH ASIA", "Asia"),
    ("EAST ASIA", "Asia"), ("CENTRAL AMERICA", "North America"), ("NORTH AMERICA", "North America"),
    ("SOUTH AMERICA", "South America"), ("SUB-SAHARAN", "Africa"), ("AFRICA", "Africa"), ("PACIFIC", "Oceania"),
]

GENERIC = set("""UNIVERSITY UNIVERSITE UNIVERSIDAD UNIVERSITA UNIVERSITAT UNIVERSIDADE COLLEGE COLLEGES SCHOOL SCHOOLS
INSTITUTE INSTITUT INSTITUTO OF THE AND FOR IN AT DE DES DU LA LE DI DEL DA DO TECHNOLOGY TECHNICAL TECHNOLOGICAL
MEDICINE MEDICAL BUSINESS MANAGEMENT ARTS ART SCIENCE SCIENCES NURSING LAW STATE NATIONAL INTERNATIONAL AMERICAN
CHRISTIAN CATHOLIC ST SAINT ACADEMY ACADEMIE EDUCATION EDUCATIONAL STUDIES CENTER CENTRE CITY COMMUNITY HIGH GRADUATE
POLYTECHNIC FOUNDATION OPEN FREE NEW ROYAL GLOBAL ADVENTIST BAPTIST METHODIST LUTHERAN UNITED WORLD PUBLIC PRIVATE
THEOLOGICAL SEMINARY BIBLE MUSIC DESIGN ENGINEERING AGRICULTURE AGRICULTURAL HEALTH TEACHERS TRAINING ISLAMIC
JEWISH EVANGELICAL PONTIFICAL CENTRAL NORTH SOUTH EAST WEST NORTHERN SOUTHERN EASTERN WESTERN FACULTY
DEPARTMENT RESEARCH HOSPITAL CHILDREN HOLY TRINITY CHRIST JESUS MARY MARYS JOHN JOHNS JOSEPH JOSEPHS PAUL PAULS
PETER PETERS FRANCIS XAVIER IGNATIUS LADY OUR SACRED HEART CONCORDIA WESLEYAN UNION PACIFIC ATLANTIC AMERICA
INC CORP CO LLC LTD ASSOCIATION SOCIETY LEADERSHIP SPORTS SPORT POLICE DANCE YOUTH HERITAGE LEARNING SUMMIT CHAMBER
COMMERCE INNOVATION SENIOR JUNIOR GRAMMAR DEAF BLIND NAVAL MILITARY MARITIME AVIATION PERFORMING REHABILITATION
PETROLEUM WORSHIP FAITH LIFE HOPE GRACE VICTORY CHURCH MINISTRY MINISTRIES SYSTEM UNIV TECH LANGUAGE LANGUAGES
COMPUTER FILM DRAMA THEATRE THEATER FINE LIBERAL HUMANITIES SOCIAL POLITICAL ECONOMICS FINANCE ACCOUNTING HOTEL
TOURISM HOSPITALITY CULINARY BEAUTY COSMETOLOGY MODELING FASHION WOMENS WOMEN MENS MEN GIRLS BOYS ADULT CAREER
VOCATIONAL PROFESSIONAL APPLIED ADVANCED STUDY PEACE MISSION MISSIONARY GOSPEL APOSTOLIC PENTECOSTAL FAMILY
ALABAMA ALASKA ARIZONA ARKANSAS CALIFORNIA COLORADO CONNECTICUT DELAWARE FLORIDA GEORGIA HAWAII IDAHO ILLINOIS
INDIANA IOWA KANSAS KENTUCKY LOUISIANA MAINE MARYLAND MASSACHUSETTS MICHIGAN MINNESOTA MISSISSIPPI MISSOURI MONTANA
NEBRASKA NEVADA HAMPSHIRE JERSEY MEXICO YORK CAROLINA DAKOTA OHIO OKLAHOMA OREGON PENNSYLVANIA RHODE ISLAND
TENNESSEE TEXAS UTAH VERMONT VIRGINIA WASHINGTON WISCONSIN WYOMING COLUMBIA PUERTO RICO
PHYSICS CHEMISTRY MATHEMATICS BIOLOGY ECONOMY CORPORATION CORPORACION UNIVERSITARIA UNIVERSITARIO FUNDACION
ESCUELA ECOLE HOCHSCHULE SCUOLA FACULDADE FACULTAD SUPERIOR SUPERIEURE NACIONAL NATIONALE AUTONOMA PRIVATE""".split())
US_TERRITORIES = {"US", "PR", "VI", "GU", "AS", "MP", "UM"}
# IRS/US wrappers that mark a US arm of something foreign (used to keep uncorroborated containment matches).
FOREIGN_WRAP = re.compile(r"\b(AMERICANS FOR|AMERICAN FRIENDS|NORTH AMERICAN FRIENDS|US FRIENDS|FRIENDS OF|NORTH AMERICA|IN AMERICA|"
                          r"USA|U S A|US|AMERICAS|AMERICAN (SOCIETY|COMMITTEE|ASSOCIATES|FOUNDATION|COUNCIL|SUPPORTERS|"
                          r"ALUMNI|DEVELOPMENT))\b")

WRAP_PREFIX = [
    "CHANCELLOR MASTERS AND SCHOLARS OF THE", "CHANCELLOR MASTERS AND SCHOLARS OF",
    "NORTH AMERICAN FRIENDS OF THE", "NORTH AMERICAN FRIENDS OF", "AMERICAN FRIENDS OF THE", "AMERICAN FRIENDS OF",
    "AMERICAN FRIENDS FOR THE", "AMERICAN FRIENDS FOR", "US FRIENDS OF THE", "US FRIENDS OF", "FRIENDS OF THE",
    "FRIENDS OF", "AMERICAN FOUNDATION FOR THE", "AMERICAN FOUNDATION FOR", "AMERICAN FOUNDATION OF THE",
    "AMERICAN FOUNDATION OF", "AMERICAS FOUNDATION FOR THE", "AMERICAS FOUNDATION FOR", "AMERICAN SOCIETY FOR THE",
    "AMERICAN SOCIETY FOR", "AMERICAN SOCIETY OF THE", "AMERICAN SOCIETY OF", "AMERICAN COMMITTEE FOR THE",
    "AMERICAN COMMITTEE FOR", "AMERICAN COUNCIL FOR THE", "AMERICAN COUNCIL FOR", "AMERICAN ASSOCIATES OF THE",
    "AMERICAN ASSOCIATES OF", "AMERICAN ASSOCIATES", "AMERICAN SUPPORTERS OF THE", "AMERICAN SUPPORTERS OF",
    "AMERICAN ALUMNI OF THE", "AMERICAN ALUMNI OF", "US FOUNDATION FOR THE", "US FOUNDATION FOR",
    "FOUNDATION FOR THE", "FOUNDATION FOR", "ALUMNI AND FRIENDS OF THE", "ALUMNI AND FRIENDS OF", "ALUMNI OF THE",
    "ALUMNI OF", "AMERICANS FOR THE", "AMERICANS FOR", "AMERICAN SUPPORT FOR THE", "AMERICAN SUPPORT FOR",
    "AMERICAN DEVELOPMENT FOUNDATION FOR THE", "AMERICAN DEVELOPMENT FOUNDATION FOR", "ASSOCIATES OF THE",
    "ASSOCIATES OF", "NORTH AMERICAN OFFICE OF THE", "NORTH AMERICAN OFFICE", "GOVERNING COUNCIL OF THE",
    "BOARD OF GOVERNORS OF THE", "BOARD OF TRUSTEES OF THE", "THE GOVERNORS OF THE", "GOVERNORS OF THE",
    "COUNCIL OF THE", "PRESIDENT AND FELLOWS OF", "NATIONAL UNIVERSITY CORPORATION", "THE",
]
WRAP_SUFFIX = [
    "INCORPORATED", "INC", "CORPORATION", "CORP", "LIMITED", "LTD", "CO", "NFP", "THE",
    "FOUNDATION IN AMERICA", "NORTH AMERICAN FOUNDATION", "AMERICAN FOUNDATION", "US FOUNDATION", "USA FOUNDATION",
    "FOUNDATION USA", "FOUNDATION US", "FOUNDATION OF AMERICA", "DEVELOPMENT FOUNDATION", "EDUCATIONAL FOUNDATION",
    "HERITAGE FOUNDATION", "HERITAGE FUND", "ENDOWMENT FUND", "ENDOWMENT", "FOUNDATION", "FUND", "TRUST",
    "IN NORTH AMERICA", "NORTH AMERICA", "IN AMERICA", "OF AMERICA", "IN THE UNITED STATES", "IN THE USA",
    "IN THE US", "IN USA", "IN US", "USA", "U S A", "US", "U S", "AMERICAS", "AMERICA", "AMERICAN FRIENDS",
    "AMERICAN ALUMNI ASSOCIATION", "ALUMNI ASSOCIATION", "ALUMNI", "FRIENDS", "N A", "NA",
    "DEVELOPMENT OFFICE", "DEVELOPMENT", "EDUCATION FOUNDATION", "EDUCATIONAL TRUST", "TRUST FUND",
]
_PREFIX_RE = [re.compile(r"^" + p + r"\s+") for p in WRAP_PREFIX]
_SUFFIX_RE = [re.compile(r"\s+" + s + r"$") for s in WRAP_SUFFIX]
WRAPPER_HINT = re.compile(r"\b(AMERICA|AMERICAN|AMERICAS|USA|US|U S A|FRIENDS|FOUNDATION|FUND|TRUST|ALUMNI|"
                          r"ENDOWMENT|NORTH AMERICA|SUPPORTERS|ASSOCIATES|SOCIETY|COMMITTEE|SCHOLARS)\b")
SCHOOL_WORD = re.compile(r"\b(UNIVERSITY|UNIVERSITE|UNIVERSIDAD|UNIVERSITA|UNIVERSITAT|UNIVERSIDADE|UNIV|COLLEGE|"
                         r"SCHOOL|INSTITUTE|INSTITUT|INSTITUTO|POLYTECHNIC|TECHNION|INSEAD|IIT|IIM|ACADEMY|ACADEMIC|SEMINARY|"
                         r"CONSERVATORY|CONSERVATOIRE|ECOLE|ESCUELA|HOCHSCHULE|SCUOLA|POLITECNICO|FACULTY)\b")
NAME_PATTERN = re.compile(r"\b(NORTH AMERICA|IN AMERICA|AMERICAN FRIENDS OF|FRIENDS OF|USA|U S A|US FOUNDATION|"
                          r"AMERICAS FOUNDATION|AMERICAN FOUNDATION FOR|AMERICAN SOCIETY FOR|AMERICAN ASSOCIATES|"
                          r"FOUNDATION)\b|\(US\)")
SUBS = [("INDIAN INSTITUTE OF TECHNOLOGY", "IIT"), ("INDIAN INSTITUTE OF MANAGEMENT", "IIM"),
        ("SAINT", "ST"), ("UNIVERSITY", "UNIV")]


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).upper()
    s = s.replace("&", " AND ").replace("'", "").replace("’", "").replace("`", "")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def strip_wrappers(n: str) -> tuple[list[str], bool]:
    """All cores reachable by peeling wrapper prefixes/suffixes; whether any wrapper was removed."""
    seen, out, todo, wrapped = {n}, [n], [n], False
    while todo:
        cur = todo.pop()
        for rx in _PREFIX_RE + _SUFFIX_RE:
            nxt = rx.sub("", cur).strip()
            if nxt and nxt != cur and nxt not in seen:
                seen.add(nxt)
                out.append(nxt)
                todo.append(nxt)
                wrapped = True
    return out, wrapped


def distinctive(v: str) -> bool:
    toks = v.split()
    return any(t not in GENERIC and not t.isdigit() and len(t) > 1 for t in toks)


def ror_variants(rec: dict) -> tuple[set[str], set[str], set[str]]:
    """(full-name variants, acronyms, city-short variants) for one ROR record."""
    city = norm(rec.get("city"))
    country = norm(rec.get("country"))
    full, acr, short = set(), set(), set()
    for n in rec["names"]:
        v = norm(n["v"])
        if not v:
            continue
        if "acronym" in n["t"]:
            two = re.match(r"^([A-Z]{3,}) [A-Z]+$", v)
            for vv in {v} | {re.sub(rf"\s+{loc}$", "", v) for loc in (city, country) if loc} | (
                    {two.group(1)} if two else set()):
                if len(vv.replace(" ", "")) >= 3 and vv.replace(" ", "") not in GENERIC:
                    acr.add(vv.replace(" ", ""))     # also "HEC PARIS" -> HEC
            continue
        base = {v, re.sub(r"^THE ", "", v), norm(re.sub(r"\(.*?\)", "", n["v"]))}
        more = set()
        for b in base:
            for loc in filter(None, {city, country}):
                for pat in (rf"\s+(OF|IN|AT|DE|DU|DI|DA|DO|BEI)\s+{loc}$", rf"\s+{loc}$", rf"^{loc}\s+"):
                    m = re.sub(pat, "", b).strip()
                    if m != b and len(m.split()) >= 2:
                        more.add(m)
                    elif m != b and m and re.search(rf"\b{m}\b", n["v"]) and len(m) >= 3:
                        acr.add(m)      # "HEC Paris" -> HEC (upper case in the ROR name: an acronym)
            m = re.match(r"^(.+) (DE|DU|OF) [A-Z]+$", b)
            if m and len(m.group(1).split()) >= 3 and distinctive(m.group(1)):
                more.add(m.group(1))    # "Ecole des Hautes Etudes Commerciales de Paris" (campus city differs)
            m = re.match(r"^(.+ (UNIVERSITY|COLLEGE|INSTITUTE|SCHOOL))( OF THE| OF) [A-Z]+$", b)
            if m and len(m.group(1).split()) >= 3 and distinctive(m.group(1)):
                more.add(m.group(1))    # "Ben-Gurion University of the Negev" -> BEN GURION UNIVERSITY
            m = re.match(r"^UNIVERSITY OF (.+)$", b)
            if m:
                more.add(m.group(1) + " UNIVERSITY")
                if m.group(1) == city and m.group(1) not in GENERIC:
                    short.add(m.group(1))
            m = re.match(r"^(.+) UNIVERSITY$", b)
            if m:
                more.add("UNIVERSITY OF " + m.group(1))
        base |= more
        for b in list(base):
            for a, z in SUBS:
                if re.search(rf"\b{a}\b", b):
                    base.add(re.sub(rf"\b{a}\b", z, b))
        full |= {b for b in base if b}
    return full, acr, short


TOKEN_IDX: dict[str, set] = {}
FULL_IDX: dict[str, set] = {}


def load_ror():
    recs = json.load(open(ROR_EDU))
    by_id = {r["id"]: r for r in recs}
    # Foreign branch campuses of US schools (Georgetown Qatar, Texas A&M Qatar, ...) are not foreign schools here.
    recs = [r for r in recs if r["cc"] == "US" or not any(
        x["type"].lower() == "parent" and by_id.get(x["id"], {}).get("cc") == "US" for x in r["rel"])]
    full_idx, acr_idx, short_idx = defaultdict(set), defaultdict(set), defaultdict(set)
    us_full, us_acr = set(), set()
    if ROR_US_ALL.exists():
        for r in json.load(open(ROR_US_ALL)):
            full, acr, _ = ror_variants(r)
            us_full |= full
            us_acr |= acr
    # ...and branch campuses whose name starts with a US school's name ("Bard College Berlin",
    # "Rochester Institute of Technology - Dubai", "Suffolk University Madrid").
    us_prefix = {norm(n["v"]) for r in recs if r["cc"] == "US" for n in r["names"] if "acronym" not in n["t"]}
    us_prefix = {u for u in us_prefix if len(u.split()) >= 2 and distinctive(u)}

    def us_branch(r):
        d = norm(r.get("display"))
        toks = d.split()
        return any(" ".join(toks[:k]) in us_prefix for k in range(2, len(toks)))
    recs = [r for r in recs if r["cc"] == "US" or not us_branch(r)]
    for r in recs:      # US territories count as US here
        if r["cc"] in US_TERRITORIES:
            r["cc"] = "US"
    for r in recs:
        full, acr, short = ror_variants(r)
        r["_full"], r["_acr"] = sorted(full), sorted(acr)
        r["_orig"] = {norm(n["v"]) for n in r["names"] if "acronym" not in n["t"]} | \
                     {re.sub(r"^THE ", "", norm(n["v"])) for n in r["names"] if "acronym" not in n["t"]}
        if r["cc"] == "US":
            us_full |= full
            us_acr |= acr
            continue
        for v in full:
            full_idx[v].add(r["id"])
        for a in acr:
            acr_idx[a].add(r["id"])
        for s in short:
            short_idx[s].add(r["id"])
    by_id = {r["id"]: r for r in recs}
    # Tokens that occur in the names of exactly one non-US school family (school + its ROR children) and in no
    # US name: "TSINGHUA", "WEIZMANN". Used for the weakest name signal (always FUZZY).
    us_tokens = {t for v in us_full for t in v.split()}
    fam_of = {}
    for r in recs:
        par = next((x["id"] for x in r["rel"] if x["type"].lower() == "parent" and x["id"] in by_id), None)
        fam_of[r["id"]] = par or r["id"]
    tok_fams = defaultdict(set)
    for r in recs:
        if r["cc"] == "US":
            continue
        for n in r["names"]:
            if "acronym" in n["t"]:
                continue
            for t in norm(n["v"]).split():
                if len(t) >= 6 and t not in GENERIC and t not in us_tokens and not t.isdigit():
                    tok_fams[t].add(fam_of[r["id"]])
    FULL_IDX.clear()
    FULL_IDX.update(full_idx)
    TOKEN_IDX.clear()
    TOKEN_IDX.update({t: f for t, f in tok_fams.items() if len(f) == 1})
    return by_id, full_idx, acr_idx, short_idx, us_full, us_acr


def stage_ror():
    """Stream the ROR v2 CSV (low memory) into the two compact files used by load_ror()."""
    csv.field_size_limit(10**8)
    src = sorted(ROR_DIR.glob("*-ror-data.csv"))[-1]
    lang = re.compile(r"^([a-z]{2,3}): ")

    def split(v):
        return [x.strip() for x in (v or "").split("; ") if x.strip()]

    def names(v, typ):
        out = []
        for x in split(v):
            m = lang.match(x)
            out.append({"v": x[m.end():] if m else x, "t": typ, "l": m.group(1) if m else None})
        return out

    edu, us = [], []
    with open(src, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["status"] != "active":
                continue
            nm = (names(r["names.types.ror_display"], "ror_display") + names(r["names.types.label"], "label")
                  + names(r["names.types.alias"], "alias") + names(r["names.types.acronym"], "acronym"))
            cc = r["locations.geonames_details.country_code"]
            if cc == "US":
                us.append({"id": r["id"], "cc": "US", "city": r["locations.geonames_details.name"],
                           "country": "United States", "types": r["types"], "rel": [], "names": nm})
            if "education" not in r["types"].lower():
                continue
            rel = [{"type": t, "id": i.strip()}         # "parent: https://ror.org/a, https://ror.org/b; child: ..."
                   for t, ids in (x.split(": ", 1) for x in split(r["relationships"]) if ": " in x)
                   for i in ids.split(",") if i.strip()]
            edu.append({
                "id": r["id"], "names": nm, "display": (names(r["names.types.ror_display"], "") or [{"v": ""}])[0]["v"],
                "cc": cc, "country": r["locations.geonames_details.country_name"],
                "city": r["locations.geonames_details.name"], "continent": r["locations.geonames_details.continent_name"],
                "website": r["links.type.website"] or None, "domains": split(r["domains"]), "rel": rel,
                "types": r["types"]})
    json.dump(edu, open(ROR_EDU, "w"))
    json.dump(us, open(ROR_US_ALL, "w"))
    print(f"{src.name}: {len(edu)} education records ({sum(r['cc'] != 'US' for r in edu)} non-US); {len(us)} US records")


def db():
    import psycopg
    c = psycopg.connect(os.environ["DATABASE_URL"], application_name="intl_schools_review")
    c.execute("set statement_timeout = '300s'")
    return c


# ---------------------------------------------------------------- stage 1: candidates
def stage_candidates():
    by_id, full_idx, acr_idx, short_idx, us_full, us_acr = load_ror()
    max_n = max(len(v.split()) for v in full_idx)
    cands, counts = {}, defaultdict(int)
    with db() as c, c.cursor(name="orgs") as cur:
        cur.itersize = 20000
        cur.execute("""SELECT ein, name, dba, city, state, website, ntee, latest_total_revenue
                       FROM organizations""")
        for ein, name, dba, city, state, website, ntee, rev in cur:
            counts["orgs_scanned"] += 1
            hits = []
            for raw in filter(None, {name, dba}):
                n = norm(raw)
                if not n:
                    continue
                if NAME_PATTERN.search(n) and SCHOOL_WORD.search(n):
                    counts["signal_name_pattern_school_word"] += 1
                cores, wrapped = strip_wrappers(n)
                for core in cores:
                    if core in full_idx and (wrapped or core == n) and (distinctive(core) or wrapped):
                        hits.append(("name_exact", core, sorted(full_idx[core]), core in us_full, wrapped))
                    nc = core.replace(" ", "")
                    if wrapped and (core in acr_idx or (len(core.split()) == 1 and nc in acr_idx)):
                        key = core if core in acr_idx else nc
                        hits.append(("acronym", key, sorted(acr_idx[key]), key in us_acr, wrapped))
                    if wrapped and core in short_idx:
                        hits.append(("city_short", core, sorted(short_idx[core]), core in us_full, wrapped))
                # containment: a distinctive multi-word school name inside a longer org name
                if WRAPPER_HINT.search(n) or not state or state.upper() not in US_STATES:
                    toks = n.split()
                    for i in range(len(toks)):
                        for j in range(i + 2, min(len(toks), i + max_n) + 1):
                            g = " ".join(toks[i:j])
                            if g != n and g in full_idx and distinctive(g) and SCHOOL_WORD.search(g + " "):
                                hits.append(("name_contains", g, sorted(full_idx[g]), g in us_full, True))
                if not hits and (WRAPPER_HINT.search(n) or SCHOOL_WORD.search(n)):
                    for t in set(n.split()):
                        if t in TOKEN_IDX:
                            hits.append(("name_token", t, sorted(TOKEN_IDX[t]), False, True))
            foreign_addr = not state or state.upper() not in US_STATES
            if hits or foreign_addr:
                cands[ein] = {"ein": ein, "name": name, "dba": dba, "city": city, "state": state, "website": website,
                              "ntee": ntee, "rev": rev, "hits": hits, "foreign_addr": foreign_addr}
                if hits:
                    counts["signal_name_ror_hit"] += 1
                if foreign_addr:
                    counts["signal_org_foreign_address"] += 1
                    if not state:
                        counts["org_state_null"] += 1
        # NTEE B (education) orgs whose latest Form 990 reports grants outside the US (Part IX line 3).
        with c.cursor() as cur2:
            cur2.execute("""
            WITH b AS (SELECT ein, latest_filing_year FROM organizations WHERE ntee LIKE 'B%')
            SELECT b.ein, x.fg FROM b CROSS JOIN LATERAL (
                SELECT max((l->>3)::bigint) fg FROM filings f JOIN expense_breakdown eb ON eb.filing_id = f.id,
                       jsonb_array_elements(eb.lines) l
                WHERE f.ein = b.ein AND f.tax_year = b.latest_filing_year AND NOT coalesce(f.superseded, false)
                  AND l->>0 = 'grants_foreign') x
            WHERE x.fg > 0""")
            fg_rows = cur2.fetchall()
            counts["signal_ntee_b_foreign_grants"] = len(fg_rows)
            missing = [e for e, _ in fg_rows if e not in cands]
            if missing:
                cur2.execute("""SELECT ein, name, dba, city, state, website, ntee, latest_total_revenue
                                FROM organizations WHERE ein = ANY(%s)""", (missing,))
                for ein, name, dba, city, state, website, ntee, rev in cur2.fetchall():
                    cands[ein] = {"ein": ein, "name": name, "dba": dba, "city": city, "state": state,
                                  "website": website, "ntee": ntee, "rev": rev, "hits": [], "foreign_addr": False}
            for e, fg in fg_rows:
                cands[e]["part9_foreign_grants"] = fg
    counts["candidates_total"] = len(cands)
    json.dump({"counts": counts, "cands": cands}, open(WORK / "candidates.json", "w"))
    print(dict(counts))


# ---------------------------------------------------------------- stage 2: evidence from the database
def stage_evidence():
    data = json.load(open(WORK / "candidates.json"))
    cands = data["cands"]
    eins = list(cands)
    with db() as c, c.cursor() as cur:
        for i in range(0, len(eins), 500):
            chunk = eins[i:i + 500]
            cur.execute("""
                SELECT DISTINCT ON (ein) ein, id, object_id, form_type, tax_year, org_name, city, state, website,
                       mission, total_revenue
                FROM filings WHERE ein = ANY(%s) AND NOT coalesce(superseded, false)
                ORDER BY ein, tax_year DESC, (form_type = '990') DESC, id DESC""", (chunk,))
            for ein, fid, oid, form, ty, oname, city, state, web, mission, rev in cur.fetchall():
                cands[ein]["filing"] = {"id": fid, "object_id": oid, "form": form, "tax_year": ty, "city": city,
                                        "state": state, "website": web, "mission": mission, "revenue": rev}
            cur.execute("""SELECT ein, string_agg(DISTINCT left(mission, 600), ' | ')
                           FROM filings WHERE ein = ANY(%s) AND mission IS NOT NULL AND tax_year >= 2018
                           GROUP BY ein""", (chunk,))
            for ein, ms in cur.fetchall():
                cands[ein]["missions"] = ms
            fids = [cands[e]["filing"]["id"] for e in chunk if "filing" in cands[e]]
            cur.execute("""SELECT ein, name_raw, title, city, state FROM people
                           WHERE filing_id = ANY(%s) AND state IS NOT NULL""", (fids,))
            for ein, nm, title, city, state in cur.fetchall():
                if state.upper() not in US_STATES:
                    cands[ein].setdefault("foreign_officers", []).append([nm, title, city, state])
            cur.execute("""SELECT ein, tax_year, source, recipient_name, city, state, cash_amount FROM grants
                           WHERE ein = ANY(%s) AND tax_year >= 2018 AND recipient_name IS NOT NULL
                             AND NOT coalesce(recipient_is_person, false)""", (chunk,))
            for ein, ty, src, rn, city, state, amt in cur.fetchall():
                g = cands[ein].setdefault("grants", [])
                if len(g) < 400:
                    g.append([ty, src, rn, city, state, amt])
            print("evidence", i + len(chunk), "/", len(eins), flush=True)
    json.dump(data, open(WORK / "evidence.json", "w"))


# ---------------------------------------------------------------- stage 3: return XML
def _strip(tag):
    return tag.rsplit("}", 1)[-1]


def _f(el, *paths):
    """First matching subelement (Element truthiness is its child count, so `find() or find()` is wrong)."""
    for p in paths:
        x = el.find(p)
        if x is not None:
            return x
    return None


def parse_xml(path: Path) -> dict:
    out = {"filer_country": None, "sched_f_regions": [], "sched_r_foreign": [], "program_text": [], "website": None,
           "sched_f_part2": []}
    root = ET.parse(gzip.open(path)).getroot()
    hdr = root.find(".//{*}ReturnHeader/{*}Filer")
    if hdr is not None:
        cc = _f(hdr, ".//{*}ForeignAddress/{*}CountryCd", ".//{*}ForeignAddress/{*}Country")
        if cc is not None:
            out["filer_country"] = (cc.text or "").strip()
    rd = root.find("{*}ReturnData")
    if rd is None:
        return out
    for el in rd.iter():
        t = _strip(el.tag)
        if t in ("WebsiteAddressTxt", "WebSite") and el.text and not out["website"]:
            out["website"] = el.text.strip()
        elif t in ("ActivityOrMissionDesc", "MissionDesc", "Desc", "DescriptionProgramSrvcAccomTxt",
                   "PrimaryExemptPurposeTxt", "ExplanationTxt", "TypeOfActivitiesConductedTxt",
                   "PurposeOfGrantTxt") and el.text:
            if len(out["program_text"]) < 60:
                out["program_text"].append(el.text.strip()[:800])
    sf = rd.find("{*}IRS990ScheduleF")
    if sf is not None:
        for grp in sf.iter():
            g = _strip(grp.tag)
            if g in ("AccountActivitiesOutsideUSGrp", "ActivitiesPerRegion"):
                reg = _f(grp, "{*}RegionTxt", "{*}Region")
                exp = _f(grp, "{*}RegionTotalExpendituresAmt", "{*}TotalExpenditures")
                act = _f(grp, "{*}TypeOfActivitiesConductedTxt", "{*}TypeOfActivitiesConducted")
                out["sched_f_regions"].append([(reg.text or "").strip() if reg is not None else None,
                                               int(exp.text) if exp is not None and (exp.text or "").strip().lstrip("-").isdigit() else None,
                                               (act.text or "").strip()[:200] if act is not None else None])
            elif g in ("GrantsToOrgOutsideUSGrp", "GrantsToOrgOutsideUS"):
                reg = _f(grp, "{*}RegionTxt", "{*}Region")
                amt = _f(grp, "{*}CashGrantAmt", "{*}AmountOfCashGrant")
                pur = _f(grp, "{*}PurposeOfGrantTxt", "{*}PurposeOfGrant")
                out["sched_f_part2"].append([(reg.text or "").strip() if reg is not None else None,
                                             int(amt.text) if amt is not None and (amt.text or "").strip().isdigit() else None,
                                             (pur.text or "").strip()[:200] if pur is not None else None])
    sr = rd.find("{*}IRS990ScheduleR")
    if sr is not None:
        for grp in sr:
            g = _strip(grp.tag)
            if not g.startswith("Id"):
                continue
            dom = _f(grp, "{*}LegalDomicileForeignCountryCd", "{*}LegalDomicileForeignCountry")
            fc = _f(grp, "{*}ForeignAddress/{*}CountryCd", "{*}AddressForeign/{*}Country")
            if dom is None and fc is None:
                continue
            nm = " ".join((e.text or "").strip() for e in grp.iter() if _strip(e.tag).startswith("BusinessNameLine"))
            city = _f(grp, "{*}ForeignAddress/{*}CityNm", "{*}AddressForeign/{*}City")
            out["sched_r_foreign"].append([nm, ((dom if dom is not None else fc).text or "").strip(),
                                           (city.text or "").strip() if city is not None else None])
    return out


def good_hit(h) -> bool:
    method, key = h[0], h[1]
    if method in ("name_exact", "name_contains"):
        return distinctive(key)
    return True


def foreign_signal(c: dict) -> bool:
    return bool(c["foreign_addr"] or c.get("part9_foreign_grants") or c.get("foreign_officers"))


def needs_xml(c: dict) -> bool:
    """Read the return XML only where it can change the outcome."""
    if foreign_signal(c):
        return True
    wrap = bool(FOREIGN_WRAP.search(norm(c["name"])))
    return any(good_hit(h) and (h[0] in ("name_exact", "name_contains") or wrap) for h in c["hits"])


def stage_xml():
    data = json.load(open(WORK / "evidence.json"))
    xdir = WORK / "xml"
    xdir.mkdir(exist_ok=True)
    todo = [c for c in data["cands"].values() if c.get("filing") and c["filing"]["object_id"] and needs_xml(c)]
    print("xml to read:", len(todo), flush=True)
    for k, c in enumerate(todo):
        oid = str(c["filing"]["object_id"])
        p = xdir / f"{oid}.xml.gz"
        if not p.exists():
            try:
                req = urllib.request.Request(GT_XML.format(oid=oid), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                with gzip.open(p, "wb") as f:
                    f.write(body)
            except Exception as e:  # noqa: BLE001
                c["xml_error"] = f"{type(e).__name__}: {e}"[:200]
                continue
            time.sleep(0.15)
        try:
            c["xml"] = parse_xml(p)
        except Exception as e:  # noqa: BLE001
            c["xml_error"] = f"parse {type(e).__name__}: {e}"[:200]
        if k % 200 == 0:
            print("xml", k, "/", len(todo), flush=True)
    json.dump(data, open(WORK / "evidence_xml.json", "w"))


# ---------------------------------------------------------------- stage 4: decide and report
def host(u: str | None) -> str:
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^[a-z]+://", "", u)
    u = u.split("/")[0].split(":")[0]
    return re.sub(r"^www\d?\.", "", u)


def contains_phrase(text_n: str, phrase: str) -> bool:
    return bool(phrase) and re.search(rf"(^| ){re.escape(phrase)}( |$)", text_n) is not None


def evidence_for(c: dict, rec: dict) -> list[str]:
    """Corroborating signals tying org c to ROR school rec."""
    ev = []
    own = set(strip_wrappers(norm(c["name"]))[0]) | set(strip_wrappers(norm(c.get("dba")))[0])
    texts = [c.get("missions") or "", (c.get("filing") or {}).get("mission") or ""]
    texts += (c.get("xml") or {}).get("program_text", [])
    tn = norm(" ".join(texts))
    names = [v for v in rec["_full"] if len(v.split()) >= 2 and distinctive(v)]
    hit = next((v for v in sorted(names, key=len, reverse=True) if contains_phrase(tn, v)), None)
    by_acronym = False
    if not hit:
        hit = next((a for a in rec["_acr"] if len(a) >= 4 and a not in GENERIC and contains_phrase(tn, a)), None)
        by_acronym = hit is not None
    if hit and len(FULL_IDX.get(hit, ())) > 1:
        hit = None      # the phrase names several schools ("Ecole des Hautes Etudes Commerciales"): not evidence
    if hit:
        # An org's mission naturally repeats its own name, so the text must also place the school abroad:
        # the school's country or city named somewhere other than inside the matched phrase.
        rest = re.sub(rf"(^| ){re.escape(hit)}( |$)", " ", tn)
        country_n, city_n = norm(rec["country"]), norm(rec["city"])
        if hit not in own and not by_acronym and SCHOOL_WORD.search(hit):
            ev.append(f"mission/program text names '{hit.title()}'")
        elif country_n and (contains_phrase(rest, country_n) or contains_phrase(hit, country_n)):
            ev.append(f"mission/program text names '{hit.title()}' and {rec['country']}")
        elif city_n and not contains_phrase(hit, city_n) and contains_phrase(rest, city_n):
            ev.append(f"mission/program text names '{hit.title()}' and {rec['city']}")
        elif rec["cc"] == "IN" and re.match(r"^(IIT|IIM|INDIAN) ", hit):
            ev.append(f"mission/program text names '{hit.title()}'")
    doms = {host(rec.get("website"))} | {d.lower() for d in rec.get("domains", [])}
    doms.discard("")
    for w in {host(c.get("website")), host((c.get("filing") or {}).get("website")),
              host((c.get("xml") or {}).get("website"))}:
        if w and any(w == d or w.endswith("." + d) for d in doms):
            ev.append(f"website {w} matches ROR domain")
            break
    cc = rec["cc"]
    country_n, city_n = norm(rec["country"]), norm(rec["city"])
    fc = (c.get("xml") or {}).get("filer_country")
    if fc and IRS_CC.get(fc, fc) == cc:
        ev.append(f"filer address in {rec['country']} (IRS code {fc})")
    elif c["foreign_addr"]:
        loc = norm(" ".join(filter(None, [c.get("city"), c.get("state"), (c.get("filing") or {}).get("city"),
                                          (c.get("filing") or {}).get("state")])))
        if contains_phrase(loc, country_n) or (city_n and contains_phrase(loc, city_n)):
            ev.append(f"foreign filer address ({loc.title()})")
    offs = [o for o in c.get("foreign_officers", [])
            if contains_phrase(norm(f"{o[2]} {o[3]}"), country_n) or (city_n and contains_phrase(norm(f"{o[2]} {o[3]}"), city_n))]
    if offs:
        ev.append(f"{len(offs)} officer(s) at addresses in {rec['country']}")
    for nm, code, city in (c.get("xml") or {}).get("sched_r_foreign", []):
        nn = norm(nm)
        if IRS_CC.get(code, code) != cc:
            continue
        if any(contains_phrase(nn, v) for v in names) or any(contains_phrase(nn, a) for a in rec["_acr"] if len(a) >= 3):
            ev.append(f"Schedule R related org '{nm.title()}' in {rec['country']}")
            break
        if city_n and norm(city) == city_n:
            ev.append(f"related org on Schedule R in {rec['city']}, {rec['country']} ('{nm.title()}')")
            break
    gtot, gn = 0, 0
    for ty, src, rn, gcity, gstate, amt in c.get("grants", []):
        rnn = norm(rn)
        abroad_g = (gstate or "").upper() not in US_STATES or any(
            x and contains_phrase(rnn, x) for x in (norm(rec["country"]), norm(rec["city"])))
        if abroad_g and (any(contains_phrase(rnn, v) for v in names) or (rec["_acr"] and rnn in rec["_acr"])):
            gtot += amt or 0
            gn += 1
    if gn:
        ev.append(f"{gn} grant(s) to the school on Sch I/990-PF since 2018 (${gtot:,})")
    regs = (c.get("xml") or {}).get("sched_f_regions", []) + (c.get("xml") or {}).get("sched_f_part2", [])
    cont = rec.get("continent")
    for reg, amt, _ in regs:
        r = (reg or "").upper()
        cn = next((v for k, v in REGION_CONTINENT if k in r), None)
        if cn and cn == cont:
            if cc == "CA" and "NORTH AMERICA" not in r and "CENTRAL AMERICA" in r:
                continue
            ev.append(f"Schedule F spending in region '{reg}'")
            break
    return ev


def is_strong(e: str) -> bool:
    """Country- or school-specific evidence (not mission text, not a Schedule F world region)."""
    return not e.startswith(("mission/", "Schedule F spending"))


def sched_f_total(c: dict) -> int | None:
    x = c.get("xml") or {}
    tot = sum(a or 0 for _, a, _ in x.get("sched_f_part2", []))
    if not tot:
        tot = sum(a or 0 for _, a, _ in x.get("sched_f_regions", []))
    return tot or c.get("part9_foreign_grants") or None


def stage_report():
    by_id, full_idx, acr_idx, short_idx, us_full, us_acr = load_ror()
    data = json.load(open(WORK / "evidence_xml.json"))
    counts, cands = data["counts"], data["cands"]
    pairs = {}      # (ror_id, ein) -> row
    rank = {"name_exact": 0, "acronym": 1, "city_short": 2, "schedule_r_name": 2, "name_contains": 3, "name_token": 4}
    # Orgs with no name hit (foreign-address / Part IX-only candidates): try Schedule R related-org names.
    for c in cands.values():
        if c["hits"]:
            continue
        for nm, code, city in (c.get("xml") or {}).get("sched_r_foreign", []):
            nn = norm(nm)
            ids = full_idx.get(nn)
            if not ids:
                cores, _ = strip_wrappers(nn)
                ids = next((full_idx[x] for x in cores if x in full_idx and distinctive(x)), None)
            if ids:
                c["hits"].append(("schedule_r_name", nn, sorted(ids), nn in us_full, False))
    dropped = defaultdict(int)
    for ein, c in cands.items():
        if not c["hits"]:
            continue
        strong_wrap = bool(FOREIGN_WRAP.search(norm(c["name"])))
        x = c.get("xml") or {}
        abroad = bool(c["foreign_addr"] or x.get("filer_country") or ein.startswith("98"))
        # unique-token hits only for orgs that look like a US arm of something foreign, or sit abroad
        best = sorted((h for h in c["hits"] if good_hit(h) and (h[0] != "name_token" or strong_wrap or abroad)),
                      key=lambda h: rank.get(h[0], 9))
        for method, key, ids, us_amb, wrapped in best:
            recs = [by_id[i] for i in ids if i in by_id][:25]
            # collapse parent/child duplicates: keep candidates whose parent is not also a candidate
            idset = {r["id"] for r in recs}
            top = [r for r in recs if not any(x["type"] == "parent" and x["id"] in idset for x in r["rel"])] or recs
            if not top:
                continue
            if method == "name_contains" and not us_amb:
                toks = norm(c["name"]).split()
                grams = {" ".join(toks[i:j]) for i in range(len(toks)) for j in range(i + 1, len(toks) + 1)}
                us_amb = any(g in us_full and key in g and g != key for g in grams)   # "Old Dominion University"
            if us_amb and not abroad:
                dropped["us_school_name"] += 1   # the US school itself (or a US namesake), not a foreign school
                continue
            scored = [(r, evidence_for(c, r)) for r in top]
            strong = [(r, ev) for r, ev in scored if any(is_strong(e) for e in ev)]
            medium = [(r, ev) for r, ev in scored if any(e.startswith("mission/") for e in ev)]
            # a Schedule F world region alone says too little to keep a link
            any_ev = [(r, ev) for r, ev in scored if any(not e.startswith("Schedule F") for e in ev)]
            names_school = [(r, ev) for r, ev in scored if any(
                e.startswith(("mission/", "Schedule R", "website")) or "grant(s) to the school" in e for e in ev)]
            if method == "city_short":
                qual = [(r, ev) for r, ev in names_school if (r, ev) in strong or (r, ev) in medium]
            elif us_amb or (method == "name_exact" and not SCHOOL_WORD.search(key + " ")):
                qual = strong
            else:
                qual = strong or medium
            if len(qual) > 1 and strong:
                qual = strong
            if len(qual) == 1 and method in ("name_exact", "schedule_r_name", "acronym", "city_short") and (
                    len(top) == 1 or key in qual[0][0]["_orig"] or method == "schedule_r_name"):
                # (with several ROR candidates, evidence may pick one only if the name is that school's own name,
                # not a derived variant: "Victoria University" is not the University of Victoria)
                tag, chosen = "EXACT", qual
            elif method == "name_token":
                if not names_school:
                    dropped[method] += 1
                    continue
                tag, chosen = "FUZZY", names_school
            elif any_ev and not (us_amb and not strong):
                tag, chosen = "FUZZY", (qual or any_ev)
            elif not any_ev and method == "name_exact" and not us_amb and len(top) <= 3 and len(key.split()) >= 2 \
                    and (abroad or key != re.sub(r"( (INC|INCORPORATED|CORP|CORPORATION|LTD|THE))+$", "",
                                                 re.sub(r"^THE ", "", norm(c["name"])))):
                # (a US-based org carrying exactly a foreign school's name, with nothing else, is a namesake)
                tag, chosen = "FUZZY", scored
            elif not any_ev and method == "name_contains" and strong_wrap and not us_amb and len(top) <= 3:
                tag, chosen = "FUZZY", scored
            else:
                dropped["us_name_collision" if us_amb else method] += 1
                continue
            for r, ev in chosen[:3]:
                k = (r["id"], ein)
                if k in pairs and pairs[k]["tag"] == "EXACT":
                    continue
                note = []
                if us_amb:
                    note.append("name also matches a US school")
                if len(chosen) > 1:
                    note.append(f"ambiguous: {len(chosen)} ROR candidates")
                if tag == "FUZZY" and ev and not any(is_strong(e) or e.startswith("mission/") for e in ev):
                    note.append("region-level evidence only")
                if abroad and not wrapped and method in ("name_exact", "acronym"):
                    note.append("the school itself files a US return")
                elif ein.startswith("98"):
                    note.append("EIN 98- prefix: foreign organization")
                if re.search(r"\bALUMNI\b|\bCLUB\b|\bCHAPTER\b", norm(c["name"])):
                    note.append("alumni club/chapter")
                pairs[k] = {
                    "ror_id": r["id"], "school_name": r["display"], "country": r["country"], "cc": r["cc"],
                    "website": r.get("website") or "", "ein": ein, "org_name": c["name"],
                    "match": f"{method}: '{key.title()}'", "tag": tag,
                    "evidence": "; ".join(ev + note) or "name similarity only",
                    "latest_revenue": c.get("rev"), "sched_f": sched_f_total(c),
                }
            if tag == "EXACT":
                break
    for k, v in dropped.items():
        counts[f"dropped_uncorroborated_{k}"] = v
    rows = sorted(pairs.values(), key=lambda p: (p["country"] or "", p["school_name"], -(p["latest_revenue"] or 0)))
    write_outputs(rows, counts, cands)


def money(v):
    return "" if v is None else f"${v:,.0f}"


def md_cell(s):
    return str(s or "").replace("|", "/").replace("\n", " ")


def write_outputs(rows, counts, cands):
    ver = (ROR_DIR / "VERSION.txt").read_text().strip().splitlines() if (ROR_DIR / "VERSION.txt").exists() else []
    (REPO / "data").mkdir(exist_ok=True)
    with open(REPO / "data" / "international-schools.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ror_id", "school_name", "country", "website", "ein", "org_name", "match", "evidence",
                    "latest_revenue"])
        for p in rows:
            w.writerow([p["ror_id"], p["school_name"], p["country"], p["website"], p["ein"], p["org_name"],
                        p["tag"], f"{p['match']} | {p['evidence']}", p["latest_revenue"] if p["latest_revenue"] is not None else ""])
    schools = defaultdict(list)
    for p in rows:
        schools[p["ror_id"]].append(p)
    exact_s = {k for k, v in schools.items() if any(p["tag"] == "EXACT" for p in v)}
    n_exact = sum(1 for p in rows if p["tag"] == "EXACT")
    L = []
    L.append("# US nonprofits tied to schools outside the United States\n")
    L.append("Review draft. Nothing here is linked into the site yet. Generated by "
             "`scripts/intl_schools_discover.py`; machine-readable copy in `data/international-schools.csv`.\n")
    L.append("## Summary\n")
    L.append(f"- Foreign schools found: **{len(schools)}** ({len(exact_s)} with at least one EXACT affiliate, "
             f"{len(schools) - len(exact_s)} FUZZY only)")
    L.append(f"- School-to-US-org links: **{len(rows)}** ({n_exact} EXACT, {len(rows) - n_exact} FUZZY)")
    L.append(f"- Registry: {' / '.join(ver)}; filtered to active ROR records of type `education` "
             f"outside the US.\n")
    L.append("## Method\n")
    L.append("""1. **Registry.** The Research Organization Registry (ROR) data dump was downloaded once from Zenodo and
   filtered to active `education` records. Each school's names, labels, aliases and acronyms were normalised
   (accents removed, upper case, punctuation dropped, `&` to `AND`) and expanded with mechanical variants: leading
   *The* dropped, a trailing *of/in/at {city or country}* dropped (e.g. *Hebrew University of Jerusalem* ->
   *Hebrew University*), *University of X* <-> *X University*, *Indian Institute of Technology* -> *IIT*,
   *Saint* -> *St*, a trailing *de/du/of {place}* dropped when three or more words remain, campus suffixes dropped
   from acronyms (*HEC Paris* -> *HEC*). Names of every active US ROR record (any type: universities, museums,
   companies) were indexed separately to detect collisions with US institutions. Excluded: foreign campuses of US
   universities (ROR parent in the US, or a display name that starts with a US school's name, e.g. *Bard College
   Berlin*) and US territories (Puerto Rico, US Virgin Islands, Guam), which count as US.
2. **Name signal.** Every row of `organizations` (name and DBA) was normalised and peeled of wrapper words
   (*American Friends of*, *Friends of*, *Americas Foundation for*, *American Society for*, *Chancellor Masters and
   Scholars of*, *Foundation*, *Fund*, *Trust*, *Inc*, *North America*, *in America*, *USA*, *(US)*, *Heritage Fund*,
   *Alumni Association*, ...). A core equal to a ROR variant is a `name_exact` hit; equal to a ROR acronym an
   `acronym` hit; equal to the city in *University of {city}* (only after a wrapper was peeled, e.g. *Cambridge in
   America*) a `city_short` hit; a distinctive multi-word school name inside a longer org name a `name_contains`
   hit; a word found in exactly one non-US school's names and in no US name (*Tsinghua*, *Bucerius*) a
   `name_token` hit (the weakest; kept only when the org also has a US-arm wrapper or a foreign address and other
   evidence names the school).
3. **Other discovery signals.** NTEE `B*` (education) organisations whose latest Form 990 reports *grants and
   assistance outside the US* (Part IX line 3, the Schedule F total) and organisations whose address on file is
   outside the US were added to the candidate pool. For orgs with no name hit, foreign related organisations listed
   on Schedule R were matched to ROR names.
4. **Corroboration.** For every candidate the latest return's XML (IRS e-file data, via the GivingTuesday
   990 data lake mirror) was read for: filer foreign address country, Schedule F regions and amounts,
   Schedule R related organisations with a foreign legal domicile, program/mission text and website. The database
   supplied mission text (all filings since 2018), officers' addresses, website, and Schedule I / 990-PF grant
   recipients. Signals counted as corroboration: mission/program text naming the school (when the phrase is the
   org's own name it must also name the school's country or city elsewhere, since every charity's mission repeats
   its own name; a phrase shared by several ROR schools does not count); website domain equal to
   the ROR domain; filer or officers located in the school's country/city; a Schedule R related org in the school's
   country whose name or city matches; grants to the school; Schedule F spending in the school's world region.
5. **Tags.** Evidence is *strong* when it is specific to the school or its country (address, officers, Schedule R
   related org, website domain, grants to the school), *medium* for mission/program text naming the school, *weak*
   for Schedule F spending in the school's world region. **EXACT** = the wrapper-stripped name equals a ROR
   name/alias/acronym-expanded name of exactly one non-US school (after collapsing ROR parent/child duplicates)
   **and** strong or medium corroboration (strong only, when the name also belongs to a US school or the hit came
   from an acronym or a bare city name). **FUZZY** = everything else that survives: containment matches, several
   ROR candidates, region-only evidence, or an exact name with no corroboration. When several ROR schools share
   the name, evidence may single one out for EXACT only if the name is that school's own ROR name (not a derived
   variant). Dropped: hits whose name is also a US institution's name when the org is US-based; uncorroborated
   acronym, city-name and single-token hits; uncorroborated containment matches without a US-arm wrapper
   (*American Friends*, *North America*, *USA*, *in America*, ...); a US-based org carrying exactly a foreign
   school's name with no other signal (a namesake).

Limits: the loader does not store Schedule F line items in the database, and Schedule F Part II names only a
region, not the recipient, so "grants to the school's country" is approximated by region. Foreign filer addresses
keep only province/city in `organizations`; the country comes from the XML. Officers' addresses are rarely
reported on Part VII, so that signal is thin.
""")
    L.append("## Signal counts\n")
    labels = {
        "orgs_scanned": "Organisations scanned (name + DBA)",
        "signal_name_pattern_school_word": "Names with a wrapper pattern (North America, in America, Friends of, USA, "
                                           "(US), Foundation, ...) and a school word",
        "signal_name_ror_hit": "Organisations whose name hits a non-US ROR school (any method, including the noisy "
                               "single-token signal)",
        "signal_ntee_b_foreign_grants": "NTEE B organisations reporting grants outside the US on Part IX line 3 "
                                        "(latest 990)",
        "signal_org_foreign_address": "Organisations with an address on file outside the 50 states/DC/territories",
        "org_state_null": "  of which the state field is empty (typical of foreign filers)",
        "candidates_total": "Candidate pool (union of the above)",
        "dropped_uncorroborated_us_school_name": "Name hits dropped: the name is also a US institution's name (any ROR "
                                                 "type) and the org is US-based",
        "dropped_uncorroborated_us_name_collision": "Name hits dropped: also a US name, no country-specific "
                                                    "corroboration",
        "dropped_uncorroborated_name_contains": "Containment hits dropped: no corroboration and no US-arm wrapper",
        "dropped_uncorroborated_acronym": "Acronym hits dropped: no country-specific corroboration",
        "dropped_uncorroborated_city_short": "City-name hits dropped: no country-specific corroboration",
        "dropped_uncorroborated_name_exact": "Exact-name hits dropped: no corroboration and either more than 3 ROR "
                                             "candidates, a one-word name, or a US-based namesake",
        "dropped_uncorroborated_name_token": "Single-token hits dropped: no evidence naming the school",
    }
    for k, lab in labels.items():
        if k in counts:
            L.append(f"- {lab}: {counts[k]:,}")
    extra = defaultdict(int)
    for c in cands.values():
        x = c.get("xml") or {}
        if x.get("filer_country"):
            extra["filer_foreign_country_xml"] += 1
        if x.get("sched_r_foreign"):
            extra["sched_r_foreign_related"] += 1
        if x.get("sched_f_regions") or x.get("sched_f_part2"):
            extra["sched_f_present"] += 1
        if c.get("foreign_officers"):
            extra["foreign_officers"] += 1
        if c.get("xml_error"):
            extra["xml_errors"] += 1
    L.append(f"- Candidates whose return XML shows a foreign filer address: {extra['filer_foreign_country_xml']:,}")
    L.append(f"- Candidates with Schedule F detail (regions/grants abroad): {extra['sched_f_present']:,}")
    L.append(f"- Candidates listing a foreign related org on Schedule R: {extra['sched_r_foreign_related']:,}")
    L.append(f"- Candidates with officers at non-US addresses: {extra['foreign_officers']:,}")
    L.append(f"- Return XML not retrievable: {extra['xml_errors']:,}\n")
    L.append("## Known examples\n")
    for ein in ["311734079", "131568923", "526071299", "770428724"]:
        hit = [p for p in rows if p["ein"] == ein]
        nm = (cands.get(ein) or {}).get("name", ein)
        L.append(f"- {nm} ({ein}): " + ("; ".join(f"{p['tag']} -> {p['school_name']} ({p['country']})" for p in hit)
                                       if hit else "not matched"))
    L.append("")
    n_self = sum(1 for p in rows if "the school itself files" in p["evidence"])
    n_alum = sum(1 for p in rows if "alumni club" in p["evidence"])
    L.append("## Needs the owner's decision\n")
    L.append(f"""- **Foreign schools filing their own US return ({n_self} links).** Many Canadian, UK, Australian and Israeli
  universities file Form 990 themselves (often with a 98- EIN and a foreign address): Oxford, Cambridge, Toronto,
  UBC, Alberta, Queensland, Tel Aviv, Weizmann, ... They are the school, not a US affiliate. They dominate the
  revenue ranking. Decide whether they get the same link type as the "American Friends of ..." charities or a
  separate "files a US return" flag.
- **US-chartered universities that operate abroad** (American University of Beirut, American University in Cairo,
  Lebanese American University, American University of Paris/Rome/Bulgaria/Armenia, John Cabot, Central European
  University). These are US nonprofits whose campus is abroad, so the "US affiliate" is the school itself.
- **Separate US institutions named after a foreign one** (Soka University of America, Tokyo International
  University of America): related by name and mission, but they are schools in their own right.
- **Endowment and pension vehicles** (The Oxford Funds, Oxford Funds Endowment Master, Carleton University
  Retirement Plan): tied to the school but not a fundraising affiliate.
- **Alumni associations and clubs ({n_alum} links, tagged "alumni club/chapter")**: real ties, usually tiny.
- **Ambiguous registry names**: where ROR has the same name in several countries (Assumption University, University
  of Reading and its Malaysia campus, Victoria University) the link stays FUZZY with every candidate listed.
- **Not found in our 990 data under any recognisable name**: Americas Foundation for the University of Oxford
  (Oxford's US arms here are Americans for Oxford and Oxford University Development North America), London
  Business School (only an alumni club, dropped), IMD, ESADE, IE, Trinity College Dublin, National University of
  Singapore, Australian National University, HEC Paris (Friends of HEC Inc names only the school's French name,
  which ROR shares with HEC Montreal, so it was not linked).
- US territories (Puerto Rico, US Virgin Islands, Guam) are treated as US and excluded.
""")
    L.append("## 50 biggest by revenue\n")
    L.append("By the US affiliate's latest total revenue (`organizations.latest_total_revenue`). "
             "An org linked to several schools appears once per school.\n")
    L.append("| # | School | Country | US affiliate | EIN | Revenue | Tag |")
    L.append("|---|---|---|---|---|---|---|")
    top = sorted(rows, key=lambda p: -(p["latest_revenue"] or 0))[:50]
    for i, p in enumerate(top, 1):
        L.append(f"| {i} | {md_cell(p['school_name'])} | {p['country']} | {md_cell(p['org_name'])} | {p['ein']} | "
                 f"{money(p['latest_revenue'])} | {p['tag']} |")
    L.append("")
    L.append("## Schools\n")
    L.append("One table per school, grouped by country. *Sch F abroad* = Schedule F grants/expenditures abroad "
             "on the latest return (Part IX line 3 when Schedule F detail is missing).\n")
    by_country = defaultdict(list)
    for rid, ps in schools.items():
        by_country[ps[0]["country"]].append(rid)
    for country in sorted(by_country, key=lambda x: x or ""):
        L.append(f"### {country}\n")
        for rid in sorted(by_country[country], key=lambda r: schools[r][0]["school_name"]):
            ps = schools[rid]
            p0 = ps[0]
            L.append(f"#### {md_cell(p0['school_name'])}\n")
            L.append(f"ROR [{rid.rsplit('/', 1)[-1]}]({rid}) · {country} · {p0['website'] or 'no website in ROR'}\n")
            L.append("| US affiliate | EIN | Match | Tag | Evidence | Latest revenue | Sch F abroad |")
            L.append("|---|---|---|---|---|---|---|")
            for p in sorted(ps, key=lambda p: -(p["latest_revenue"] or 0)):
                L.append(f"| {md_cell(p['org_name'])} | {p['ein']} | {md_cell(p['match'])} | {p['tag']} | "
                         f"{md_cell(p['evidence'])} | {money(p['latest_revenue'])} | {money(p['sched_f'])} |")
            L.append("")
    (REPO / "docs").mkdir(exist_ok=True)
    (REPO / "docs" / "international-schools.md").write_text("\n".join(L) + "\n")
    print(f"schools={len(schools)} exact_schools={len(exact_s)} links={len(rows)} exact_links={n_exact}")
    print(json.dumps(counts))
    print(json.dumps(extra))


STAGES = {"ror": stage_ror, "candidates": stage_candidates, "evidence": stage_evidence, "xml": stage_xml, "report": stage_report}

if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)
    for s in sys.argv[1:] or list(STAGES):
        t = time.time()
        STAGES[s]()
        print(f"[{s}] {time.time() - t:.0f}s", flush=True)
