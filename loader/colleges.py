"""Colleges and universities: IPEDS institutions, public university payroll, and links to 990 data.

Built by load.py colleges [--only ipeds,orgs,labels,payroll,summary,links,coaches]. Reads the IPEDS
directory files in data/ipeds/ and the payroll staging schema (unipay, loaded by scripts/unipay/).
Each table is built beside the live one and copied in, in one transaction (the university
leaderboard views depend on them, so they are never dropped).

  colleges                 IPEDS HD (directory) + DRVEF (fall enrollment), one row per UNITID.
  college_orgs             an institution's related nonprofits: itself (the EIN IPEDS lists: EXACT),
                           its foundation, alumni, athletic and booster, research and hospital
                           organizations. EXACT: the name is the institution's name plus only the
                           relation's own words, in the same state. FUZZY: the institution's name with
                           other words too, or the same name at its address. The evidence says which.
  payroll_labels           each published employer label -> one IPEDS institution (EXACT: same name
                           once abbreviations are spelled out; FUZZY: nearly the same name in the same
                           state), or none for system offices and boards.
  payroll_rows             the published rows, copied from unipay.public_payroll_records.
  payroll_person_years     one row per person, employer and year: rows of the same name summed only
                           where the publisher splits one person's pay into several lines.
  college_payroll_years    per institution and year: headcount, total, median and top pay.
  college_faculty_salaries IPEDS average salaries by rank.
  payroll_person_links     payroll person -> person page, EXACT or FUZZY (rules in link_people()).
  coach_titles             coach titles classified by app/coach_class.py.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections import defaultdict

from app import coach_class
from app.config import ROOT
from loader import db

IPEDS_DIR = ROOT / "data" / "ipeds"
HD_FILE, ENROLL_FILE = "HD2024.zip", "DRVEF2023.zip"
ENROLL_YEAR = 2023

STEPS = ["ipeds", "orgs", "intl", "labels", "payroll", "summary", "links", "coaches", "schools"]

# Payroll publications: how each reports pay, in plain words. "publisher" is who published the list.
SOURCE_INFO = {
    "ct": ("State of Connecticut payroll", "State of Connecticut (Open Data CT)",
           "Gross pay in the fiscal year (salary, overtime and other pay)"),
    "ma": ("Massachusetts CTHRU statewide payroll", "Massachusetts Office of the Comptroller (CTHRU)",
           "Total pay in the calendar year"),
    "nyc": ("NYC Citywide Payroll (CUNY community colleges)", "NYC Office of Payroll Administration",
            "Regular, overtime and other pay in the city fiscal year"),
    "ga": ("Open Georgia salaries", "Georgia Department of Audits and Accounts (Open Georgia)",
           "Salary paid in the fiscal year"),
    "tx": ("Texas College Salaries", "Compiled by the Texas College Salaries volunteer project from Texas Public "
           "Information Act records", "Base salary as of the records date"),
    "il_iccb": ("Illinois community college salaries and benefits", "Illinois Community College Board",
                "Base salary plus extra duty and enhancements"),
    "oh_osu": ("The Ohio State University earnings", "The Ohio State University", "Gross earnings in the calendar year"),
    "oh_ou": ("Ohio University annual salary report", "Ohio University", "Medicare (W-2) wages in the calendar year"),
    "mn": ("Minnesota state employee salary data", "Minnesota Management and Budget",
           "Earnings in the fiscal year (all state positions)"),
    "wa": ("Washington state salaries", "State of Washington (data.wa.gov)", "Salary in the calendar year"),
    "ne": ("University of Nebraska budgeted salaries", "University of Nebraska", "Budgeted annual salary as of July 1"),
    "me": ("University of Maine System employee compensation", "University of Maine System", "Compensation as published"),
    "nm": ("University of New Mexico salary book", "University of New Mexico (Sunshine portal)",
           "Primary position salary as of the snapshot"),
    "dc": ("DC government employee salaries (UDC)", "Government of the District of Columbia",
           "Compensation rate as of the snapshot"),
    "az_asu": ("Arizona State University salaries", "Compiled by The State Press from Arizona State University records",
               "Base salary"),
    "az_ua": ("University of Arizona salaries", "Compiled by a newsroom from University of Arizona records",
              "Salary at the employee's appointment (FTE)"),
    "ks": ("Kansas state payroll", "Compiled by the Kansas Policy Institute (KansasOpenGov) from state records",
           "Total pay in the calendar year"),
    "nj": ("New Jersey pension membership", "New Jersey Division of Pensions and Benefits",
           "Salary reported to the pension system (members only; no titles)"),
    "ok": ("Oklahoma state payroll", "Oklahoma Office of Management and Enterprise Services",
           "Payments in the fiscal year (monthly lines summed)"),
    "il_graybook": ("University of Illinois Gray Book", "University of Illinois Board of Trustees",
                    "Proposed salary for the fiscal year (budget)"),
    "sc": ("South Carolina state salaries", "South Carolina Department of Administration",
           "Total compensation as published (salaries under $50,000 not listed)"),
}
SOURCE_INFO.update({
    "md": ("University of Maryland salaries", "Compiled by The Diamondback from University of Maryland records",
           "Salary as published (includes settlement payments to departed staff)"),
    "vt_uvm": ("University of Vermont salaries", "University of Vermont (base budget book)", "Base salary as published"),
    "mi_um": ("University of Michigan salary record", "University of Michigan", "Full-time-equivalent salary as published"),
    "il_stl": ("Illinois university salaries (St. Louis Post-Dispatch)",
               "Compiled by the St. Louis Post-Dispatch from public records", "Salary as published"),
    "il_isu": ("Illinois State University salary book", "Illinois State University", "Salary as published"),
    "nm_nmhu": ("New Mexico Highlands University salaries", "New Mexico Highlands University", "Salary as published"),
    "mo_um": ("University of Missouri System salaries", "University of Missouri System", "Salary as published"),
    "mo_stl": ("Missouri university salaries (St. Louis Post-Dispatch)",
               "Compiled by the St. Louis Post-Dispatch from public records", "Salary as published"),
    "me_hist": ("University of Maine System employee compensation (earlier years)", "University of Maine System",
                "Compensation as published"),
    "dc_hist": ("DC government employee salaries (UDC, earlier years)", "Government of the District of Columbia",
                "Compensation rate as of each snapshot"),
    "ne_cc": ("Nebraska community college salaries", "Nebraska community colleges (newsroom pages)", "Salary as published"),
    "tn_etsu": ("East Tennessee State University salaries", "East Tennessee State University", "Salary as published"),
    "mo_msu": ("Missouri State University budget", "Missouri State University", "Budgeted salary"),
    "ar_adhe": ("Arkansas higher education administrator salaries", "Arkansas Division of Higher Education",
                "Salary as published (administrators paid $100,000 or more)"),
    "tn_apsu": ("Austin Peay State University salaries", "Austin Peay State University", "Salary as published"),
    "pa_pitt": ("University of Pittsburgh highest salaries", "University of Pittsburgh (top 200 only)", "Salary as published"),
    "pa_temple": ("Temple University highest salaries", "Temple University (top 200 only)", "Salary as published"),
})
SOURCE_INFO.update({
    "in_gateway": ("Indiana Gateway employee compensation (public colleges and universities)",
                   "Indiana Gateway for Government Units (Department of Local Government Finance and State Board of "
                   "Accounts); used under its non-commercial terms", "Total compensation in the calendar year (Form 100R)"),
    "il_ibhe": ("Illinois Board of Higher Education salary search (public universities)",
                "Illinois Board of Higher Education", "Salary as reported (administrators and faculty only)"),
})
TRUNCATED_NAMES = {"tx", "ok"}       # first name + last initial, or last name + initials: never linked to people
SUM_LINES = {"ok"}                   # the publisher splits one person's year into several lines: sum them
WITHHELD = r"^\s*(undisclosed|withheld|redacted|confidential|name withheld|not disclosed)\M"


# --- names -----------------------------------------------------------------------------------

ABBREV = [(r"\buniv\b", "university"), (r"\bokla\b", "oklahoma"), (r"\bok\b", "oklahoma"), (r"\bst\b", "state"),
          (r"\bcoll?\b", "college"), (r"\bcolleg\b", "college"), (r"\bcolege\b", "college"), (r"\bcomm\b", "community"),
          (r"\btech\b", "technical"), (r"\bco\b", "county"), (r"\bcount\b", "county"), (r"\bnj\b", "new jersey"),
          (r"\bsc\b", "south carolina"), (r"\bmt\b", "mount"), (r"\bvall\b", "valley"), (r"\bflo\b", "florence"),
          (r"\bs w\b", "southwestern"), (r"\bs e\b", "southeastern"), (r"\bn e\b", "northeastern"),
          (r"\binst\b", "institute"), (r"\bctr\b", "center"), (r"\bmed\b", "medical"), (r"\bsci\b", "science"),
          (r"\bumass\b", "university of massachusetts"), (r"\buconn\b", "university of connecticut"),
          (r"\buthealth\b", "university of texas health"), (r"\butsa\b", "university of texas at san antonio")]
CORP = r"\b(inc|incorporated|corp|corporation|co|ltd|llc|the)\b"   # not "a": Texas A and M


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("&", " and ").replace("'", "")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def expand(s: str | None) -> str:
    n = norm((s or "").strip().strip('"'))
    for pat, rep in ABBREV:
        n = re.sub(pat, rep, n)
    return re.sub(r"\s+", " ", n).strip()


def core(name: str) -> str:
    """Name without a leading "the" and a campus suffix ("-Main Campus", "Campus Immersion")."""
    n = norm(re.sub(r"(?i)([- ]+main campus| campus immersion| digital immersion)$", "", name or ""))
    return re.sub(r"^the ", "", n)


def bare(n: str) -> str:
    """A normalized organization name without corporate words (inc, corp, the ...)."""
    return re.sub(r"\s+", " ", re.sub(CORP, " ", n)).strip()


# --- refill helper -----------------------------------------------------------------------------

def _refill(conn, name: str, cols: list[str]) -> int:
    """Copy name__new into name in one transaction (TRUNCATE + INSERT keeps dependent views valid)."""
    c = ", ".join(cols)
    conn.execute("SET lock_timeout = '60s'")
    conn.execute(f"TRUNCATE {name}")
    conn.execute(f"INSERT INTO {name} ({c}) SELECT {c} FROM {name}__new")
    conn.execute(f"DROP TABLE {name}__new")
    conn.execute("SET lock_timeout = 0")
    n = conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
    conn.commit()
    conn.execute(f"ANALYZE {name}")
    return n


def _new(conn, name: str) -> None:
    schema = conn.execute("SELECT current_schema()").fetchone()[0]
    conn.execute(f'DROP TABLE IF EXISTS "{schema}".{name}__new')
    conn.execute(f"CREATE TABLE {name}__new (LIKE {name} INCLUDING DEFAULTS)")


# --- IPEDS -------------------------------------------------------------------------------------

CONTROL = {"1": "Public", "2": "Private nonprofit", "3": "Private for-profit"}
LEVEL = {"1": "Four or more years", "2": "At least 2 but less than 4 years", "3": "Less than 2 years"}
COLLEGE_COLS = ["unitid", "name", "name_norm", "core_norm", "alias", "street", "city", "state", "zip", "ein",
                "website", "sector", "control", "level", "system_name", "hbcu", "medical", "landgrant",
                "enrollment", "enrollment_year", "closed", "opeid"]


def _csv_rows(zip_name: str):
    with zipfile.ZipFile(IPEDS_DIR / zip_name) as z:
        member = next(n for n in z.namelist() if n.lower().endswith(".csv") and "_rv" not in n.lower())
        with z.open(member) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"))


def _ein(v: str | None) -> str | None:
    d = re.sub(r"\D", "", v or "")
    return d if len(d) == 9 and d not in ("000000000", "999999999") else None


def load_ipeds(conn, status) -> int:
    enroll = {r["UNITID"]: r.get("ENRTOT") for r in _csv_rows(ENROLL_FILE)}
    rows = []
    for r in _csv_rows(HD_FILE):
        name = r["INSTNM"].strip()
        e = enroll.get(r["UNITID"])
        rows.append((int(r["UNITID"]), name, norm(name), core(name), (r.get("IALIAS") or "").strip() or None,
                     r.get("ADDR") or None, r.get("CITY") or None, r.get("STABBR") or None, r.get("ZIP") or None,
                     _ein(r.get("EIN")), (r.get("WEBADDR") or "").strip() or None,
                     int(r["SECTOR"]) if (r.get("SECTOR") or "").lstrip("-").isdigit() else None,
                     CONTROL.get(r.get("CONTROL")), LEVEL.get(r.get("ICLEVEL")),
                     (r.get("F1SYSNAM") or "").strip() if (r.get("F1SYSNAM") or "").strip() not in ("", "-2") else None,
                     r.get("HBCU") == "1", r.get("MEDICAL") == "1", r.get("LANDGRNT") == "1",
                     int(e) if e and e.isdigit() else None, ENROLL_YEAR if e and e.isdigit() else None,
                     (r.get("CLOSEDAT") or "-2").strip() not in ("-2", ""),
                     re.sub(r"\D", "", r.get("OPEID") or "").zfill(8) if re.sub(r"\D", "", r.get("OPEID") or "").strip("0") else None))
    _new(conn, "colleges")
    with conn.cursor() as cur:
        db.copy_rows(cur, "colleges__new", COLLEGE_COLS, rows)
    conn.execute("UPDATE colleges__new SET name_tsv = to_tsvector('simple', name || ' ' || coalesce(alias, ''))")
    n = _refill(conn, "colleges", COLLEGE_COLS + ["name_tsv"])
    status.emit(f"colleges: {n:,} IPEDS institutions")
    return n


# --- related nonprofits --------------------------------------------------------------------------

# Relation words, in priority order: an "athletic foundation" is athletic.
RELATIONS = [
    ("athletic", r"\b(athletic|athletics|athletes?|boosters?|sports|varsity|letterm[ae]n|letterwinners?|"
                 r"touchdown club|quarterback club|tip ?off club|hoop club|scholarship club|gridiron)\b"),
    ("alumni", r"\b(alumni|alumnae|alumnus|alum|graduates association)\b"),
    ("hospital", r"\b(hospitals?|medical center|health system|health care|healthcare|health center|physicians|"
                 r"practice plan|clinics?|medical practice|faculty practice)\b"),
    ("research", r"\b(research|technology transfer|innovation|innovations|patents?|ventures)\b"),
    ("foundation", r"\b(foundation|endowment|fund|trust)\b"),
]
_RELATIONS = [(k, re.compile(p)) for k, p in RELATIONS]
# Words an EXACT name may have beyond the institution's name and the relation's words.
FILLER = {"of", "at", "for", "and", "the", "association", "society", "club", "council", "board", "group", "national",
          "foundation", "fund", "endowment", "trust", "inc", "corporation", "corp", "incorporated", "institute",
          "organization", "support", "supporting"}
# Organizations named after an institution that are not its nonprofits.
STOP = re.compile(r"\b(chapter|fraternity|sorority|students?|league|christian|islamic|muslim|catholic|newman|hillel|"
                  r"jewish|ministry|ministries|church|chapel|credit union|cooperative|co op|press|bookstore|"
                  r"faculty association|professors|aaup|federation|union|employees|retirees|parents|daycare|"
                  r"child care|preschool|nursery|apartments|band boosters|rugby|lacrosse club|crew club|"
                  r"pta|pto|wives|women s club|womens club|garden|orchestra|choirs?|chorus|theatre|theater|wesley|baptist|"
                  r"methodist|presbyterian|lutheran|episcopal|canterbury|chabad|intervarsity|campus crusade|panhellenic|"
                  r"alpha|beta|gamma|delta|epsilon|zeta|theta|iota|kappa|lambda|omicron|sigma|upsilon|phi|chi|psi|omega)\b")


NAME_PREFILTER = (r"(universit|college|institut|school|academ|seminar|polytechnic|citadel|tech|state|foundation|"
                  r"endowment|fund|trust|alumn|athlet|booster|sports|varsity|letterm|research|innovation|patent|"
                  r"venture|hospital|medical|health|physician|clinic|practice)")


def _relation(rest: str) -> str | None:
    return next((k for k, rx in _RELATIONS if rx.search(rest)), None)


# Short names foundations and associations use instead of the IPEDS name. A match on one is FUZZY unless the
# organization files from the institution's city or ZIP code.
SHORT_NAMES = {
    "Texas A&M University-College Station": ["texas a and m"],
    "Pennsylvania State University-Main Campus": ["penn state", "pennsylvania state university"],
    "University of Mississippi": ["ole miss"],
    "Virginia Polytechnic Institute and State University": ["virginia tech"],
    "Georgia Institute of Technology-Main Campus": ["georgia tech", "georgia institute of technology"],
    "Louisiana State University and Agricultural & Mechanical College": ["louisiana state university", "lsu"],
    "University of Connecticut": ["uconn"],
    "University of Massachusetts-Amherst": ["umass amherst", "umass"],
    "University of Nebraska-Lincoln": ["university of nebraska"],
    "University of Washington-Seattle Campus": ["university of washington"],
    "Rutgers University-New Brunswick": ["rutgers university", "rutgers"],
}


def _keys(colleges: list[dict]) -> dict[tuple[str, str], int]:
    """(state, name key) -> unitid. Each institution's core name, plus the part before a dash
    ("University of Michigan" for "University of Michigan-Ann Arbor") for the largest campus only."""
    keys: dict[tuple[str, str], int] = {}
    size: dict[tuple[str, str], int] = {}
    for c in sorted(colleges, key=lambda c: -(c["enrollment"] or 0)):
        if c["closed"] or not c["state"]:
            continue
        cands = [c["core_norm"]]
        if "-" in c["name"]:
            cands.append(core(c["name"].split("-")[0]))
        for k in cands:
            if len(k.split()) < 2 or k in ("community college", "technical college", "state university"):
                continue
            key = (c["state"], k)
            if key not in keys:                    # largest enrollment first wins a shared key
                keys[key] = c["unitid"]
                size[key] = c["enrollment"] or 0
        for k in SHORT_NAMES.get(c["name"], []):
            SHORT_KEYS.add((c["state"], k))
            keys.setdefault((c["state"], k), c["unitid"])
    return keys


SHORT_KEYS: set = set()


def link_orgs(conn, status) -> int:
    colleges = [dict(zip(("unitid", "name", "core_norm", "state", "city", "zip", "street", "ein", "enrollment",
                          "closed"), r)) for r in conn.execute(
        "SELECT unitid, name, core_norm, state, city, zip, street, ein, enrollment, closed FROM colleges")]
    by_id = {c["unitid"]: c for c in colleges}
    out: dict[tuple[int, str], tuple] = {}
    # 1. The institution itself: the EIN IPEDS lists.
    for c in colleges:
        if c["ein"]:
            r = conn.execute("SELECT name FROM organizations WHERE ein = %s", (c["ein"],)).fetchone()
            if r:
                out[(c["unitid"], c["ein"])] = ("self", "EXACT", {"rule": "ipeds_ein", "ipeds_ein": c["ein"],
                                                                  "org_name": r[0]})
    # 2. Organizations whose name contains the institution's name, in the same state.
    keys = _keys(colleges)
    by_state = defaultdict(list)
    for (st, k), uid in keys.items():
        by_state[st].append((k, uid))
    n_checked = 0
    for st, ks in by_state.items():
        # Only names that could hold an institution's name and a relation word (the rest can't match).
        orgs = conn.execute("""SELECT ein, name, name_norm, city, zip, street FROM organizations
                               WHERE state = %s AND name_norm ~ %s""", (st, NAME_PREFILTER)).fetchall()
        for ein, oname, onorm, ocity, ozip, ostreet in orgs:
            on = bare(norm(oname))
            if not on:
                continue
            best = None
            for k, uid in ks:
                if (" " + k + " ") in (" " + on + " ") and (not best or len(k) > len(best[0])):
                    best = (k, uid)
            if not best:
                continue
            n_checked += 1
            k, uid = best
            c = by_id[uid]
            if (uid, ein) in out:
                continue
            if STOP.search(on):
                continue
            rest = (" " + on + " ").replace(" " + k + " ", " ").strip()
            same_city = bool(ocity and c["city"] and norm(ocity) == norm(c["city"]))
            same_zip = bool(ozip and c["zip"] and ozip[:5] == c["zip"][:5])
            ev = {"rule": "name", "institution_name": c["name"], "org_name": oname, "state": st,
                  "same_city": same_city, "same_zip": same_zip}
            if not rest:
                # The institution's own name: the same organization only if IPEDS lists this EIN (above),
                # else a same-name filer at the institution's address (FUZZY).
                if same_city or same_zip:
                    out[(uid, ein)] = ("self", "FUZZY", {**ev, "rule": "same_name_same_place"})
                continue
            rel = _relation(rest)
            if not rel:
                continue
            extra = [w for w in rest.split() if w not in FILLER and not _relation(w)]
            # Multi-word relation phrases ("medical center") leave single words behind: drop those too.
            for k2, rx in _RELATIONS:
                for m in rx.finditer(rest):
                    for w in m.group(0).split():
                        if w in extra:
                            extra.remove(w)
            match = "EXACT" if not extra else "FUZZY"
            if (st, k) in SHORT_KEYS:
                ev["short_name"] = k
                if not (same_city or same_zip):
                    match = "FUZZY"
            out[(uid, ein)] = (rel, match, {**ev, "relation_words": rest, "other_words": extra})
    # One institution, several organizations with the same EXACT name (local chapters filing separately):
    # only those at the institution's city or ZIP stay EXACT; the rest are FUZZY, with the reason.
    groups = defaultdict(list)
    for (u, e), (rel, m, ev) in out.items():
        if m == "EXACT" and ev.get("rule") == "name":
            groups[(u, rel, bare(norm(ev["org_name"])))].append((u, e))
    for keys_ in groups.values():
        if len(keys_) > 1:
            for k in keys_:
                rel, m, ev = out[k]
                if not (ev["same_city"] or ev["same_zip"]):
                    out[k] = (rel, "FUZZY", {**ev, "rule": "same_name_elsewhere",
                                             "note": f"{len(keys_)} organizations share this name; this one files "
                                                     f"from another place"})
    # IPEDS sometimes lists one EIN for several campuses (Emory and its Oxford College): the EIN stays EXACT for
    # the largest campus only, so its 990 is counted once; the others keep it as FUZZY, with the reason.
    size = {c["unitid"]: c["enrollment"] or 0 for c in colleges}
    by_ein = defaultdict(list)
    for (u, e), (rel, m, ev) in out.items():
        if rel == "self" and m == "EXACT":
            by_ein[e].append(u)
    for e, us in by_ein.items():
        if len(us) > 1:
            keep = max(us, key=lambda u: (size.get(u, 0), -u))
            for u in us:
                if u != keep:
                    rel, m, ev = out[(u, e)]
                    out[(u, e)] = (rel, "FUZZY", {**ev, "rule": "shared_ipeds_ein", "shared_with": by_id[keep]["name"],
                                                  "n_sharing": len(us)})
    # A same-name filer at the institution's address adds nothing once IPEDS names the EIN.
    has_self = {u for (u, e), (rel, m, ev) in out.items() if rel == "self" and m == "EXACT"}
    out = {k: v for k, v in out.items() if not (v[0] == "self" and v[1] == "FUZZY" and k[0] in has_self)}
    _new(conn, "college_orgs")
    with conn.cursor() as cur:
        db.copy_rows(cur, "college_orgs__new", ["unitid", "ein", "relation", "match", "evidence"],
                     [(u, e, rel, m, json.dumps(ev)) for (u, e), (rel, m, ev) in out.items()])
    n = _refill(conn, "college_orgs", ["unitid", "ein", "relation", "match", "evidence"])
    status.emit(f"college orgs: {n:,} institution-nonprofit links ({n_checked:,} name hits checked)")
    return n


# --- payroll labels ------------------------------------------------------------------------------

SYSTEM_LABEL = re.compile(r"\b(system|systems|board of|regents|district office|system office|state board|"
                          r"central administration|ccc district|unop|universities|colleges and universities|"
                          r"state universities|community colleges|eastern community colleges|"
                          r"university center at ponca city)\b")
# Labels the name rules can't place, checked by hand: (state, label as published) -> (IPEDS name or None,
# match, why). Renamed institutions are EXACT; merged-away ones go to the institution they joined (FUZZY).
RENAMED, MERGED = "EXACT", "FUZZY"
LABEL_OVERRIDES = {
    ("AZ", "Arizona State University"): ("Arizona State University Campus Immersion", RENAMED, "IPEDS lists the Tempe campus as Campus Immersion"),
    ("OH", "The Ohio State University"): ("Ohio State University-Main Campus", RENAMED, "main campus"),
    ("OH", "Ohio University"): ("Ohio University-Main Campus", RENAMED, "main campus"),
    ("MA", "UMass Chan Medical School"): ("University of Massachusetts Chan Medical School", RENAMED, "same institution"),
    ("MA", "University of Massachusetts Amherst"): ("University of Massachusetts-Amherst", RENAMED, "same institution"),
    ("MA", "Mass Bay Community College"): ("Massachusetts Bay Community College", RENAMED, "same institution"),
    ("MA", "Bridgewater State College"): ("Bridgewater State University", RENAMED, "renamed a university in 2010"),
    ("MA", "Salem State College"): ("Salem State University", RENAMED, "renamed a university in 2010"),
    ("MA", "Westfield State College"): ("Westfield State University", RENAMED, "renamed a university in 2010"),
    ("MA", "Worcester State College"): ("Worcester State University", RENAMED, "renamed a university in 2010"),
    ("MA", "Fitchburg State College"): ("Fitchburg State University", RENAMED, "renamed a university in 2010"),
    ("MA", "Framingham State College"): ("Framingham State University", RENAMED, "renamed a university in 2010"),
    ("CT", "UConn Health"): ("University of Connecticut", MERGED, "UConn Health reports to IPEDS as part of UConn"),
    ("TX", "Texas A&M"): ("Texas A&M University-College Station", RENAMED, "the College Station campus"),
    ("TX", "Texas Tech"): ("Texas Tech University", RENAMED, "same institution"),
    ("TX", "UT MD Anderson"): ("The University of Texas MD Anderson Cancer Center", RENAMED, "same institution"),
    ("TX", "UTHealth Houston"): ("The University of Texas Health Science Center at Houston", RENAMED, "same institution"),
    ("TX", "UTHealth San Antonio"): ("The University of Texas Health Science Center at San Antonio", RENAMED, "same institution"),
    ("TX", "Texas A&M Prairie View"): ("Prairie View A & M University", RENAMED, "same institution"),
    ("TX", "Texas A&M Galveston"): ("Texas A&M University-College Station", MERGED, "the Galveston campus reports under College Station"),
    ("TX", "Texas A&M Health Science Center"): ("Texas A&M University-College Station", MERGED, "merged into Texas A&M in 2013"),
    ("TX", "Texas A&M Victoria"): ("University of Houston-Victoria", MERGED, "joined the Texas A&M System in 2025; IPEDS still lists the earlier name"),
    ("TX", "Lone Star Community College"): ("Lone Star College System", RENAMED, "same institution"),
    ("TX", "Houston City College"): ("Houston Community College", RENAMED, "renamed in 2025"),
    ("SC", "The Citadel"): ("Citadel Military College of South Carolina", RENAMED, "same institution"),
    ("SC", "University of Charleston"): ("College of Charleston", RENAMED, "same institution"),
    ("SC", "Spartanburg Technical College"): ("Spartanburg Community College", RENAMED, "renamed"),
    ("WA", "University of Washington"): ("University of Washington-Seattle Campus", RENAMED, "the Seattle campus (the state lists all campuses together)"),
    ("WA", "Pierce Community College"): ("Pierce College District", RENAMED, "same institution"),
    ("WA", "Lake Washington Technical College"): ("Lake Washington Institute of Technology", RENAMED, "renamed"),
    ("WA", "Seattle Community College"): (None, None, "a district of three colleges"),
    ("NJ", "Rowan College Gloucester Count"): ("Rowan College of South Jersey-Gloucester Campus", RENAMED, "same institution"),
    ("NJ", "Union County College"): ("UCNJ Union College of Union County, New Jersey", RENAMED, "renamed"),
    ("NJ", "Rutgers University"): ("Rutgers University-New Brunswick", MERGED, "the state lists all Rutgers campuses together"),
    ("IL", "Black Hawk"): ("Black Hawk College", RENAMED, "same institution"),
    ("IL", "University of Illinois Urbana-Champaign"): ("University of Illinois Urbana-Champaign", RENAMED, "same institution"),
    ("NY", "Kingsboro Community College"): ("CUNY Kingsborough Community College", RENAMED, "same institution"),
    ("NY", "Queensboro Community College"): ("CUNY Queensborough Community College", RENAMED, "same institution"),
    ("GA", "Georgia Regents University"): ("Augusta University", RENAMED, "renamed Augusta University in 2015"),
    ("GA", "Armstrong State University"): ("Georgia Southern University", MERGED, "merged into Georgia Southern in 2018"),
    ("GA", "Darton State College"): ("Albany State University", MERGED, "merged into Albany State in 2017"),
    ("GA", "Bainbridge College"): ("Abraham Baldwin Agricultural College", MERGED, "merged into ABAC in 2017"),
    ("GA", "Bainbridge State College"): ("Abraham Baldwin Agricultural College", MERGED, "merged into ABAC in 2017"),
    ("GA", "Moultrie Technical College"): ("Southern Regional Technical College", MERGED, "merged into Southern Regional in 2015"),
    ("GA", "Southwest Georgia Technical College"): ("Southern Regional Technical College", MERGED, "merged into Southern Regional in 2015"),
    ("GA", "Middle Georgia State College"): ("Middle Georgia State University", RENAMED, "renamed a university in 2015"),
    ("GA", "Gordon College"): ("Gordon State College", RENAMED, "renamed in 2012"),
    ("GA", "Georgia Perimeter College"): ("Georgia State University-Perimeter College", MERGED, "merged into Georgia State in 2016"),
    ("ME", "University of Maine at Machias"): ("University of Maine", MERGED, "merged into the University of Maine in 2017"),
    ("ME", "University of Maine School of Law"): (None, None, "IPEDS has no separate institution for the law school"),
}
LABEL_OVERRIDES.update({
    ("IL", "Mc Henry County College"): ("McHenry County College", RENAMED, "same institution"),
    ("SC", "Tech Coll of Low Country"): ("Technical College of the Lowcountry", RENAMED, "same institution"),
    ("SC", "Orangeburg Calhoun Tec College"): ("Orangeburg Calhoun Technical College", RENAMED, "same institution"),
})
LABEL_OVERRIDES.update({
    ("MN", "Minneapolis College"): ("Minneapolis Community and Technical College", RENAMED, "renamed Minneapolis College in 2020"),
    ("CT", "Northwestern Connecticut Community College"): (
        "Connecticut State Community College", MERGED, "merged into Connecticut State Community College in 2023"),
    ("MO", "MU Health Care"): (None, None, "a health system, not an IPEDS institution"),
    ("AR", "University of Arkansas, Fayetteville"): ("University of Arkansas", RENAMED, "the Fayetteville campus"),
    ("IL", "Southern Illinois University School of Medicine"): (None, None, "IPEDS has no separate institution for the medical school"),
    ("MO", "University of Missouri Health Care"): (None, None, "a health system, not an IPEDS institution"),
})
for _mn in ("Hibbing Community College", "Mesabi Range College", "Itasca Community College", "Vermilion Community College",
            "Rainy River Community College"):
    LABEL_OVERRIDES[("MN", _mn)] = ("Minnesota North College", MERGED, "merged into Minnesota North College in 2022")
for _cc in ("Gateway", "Naugatuck Valley", "Manchester", "Norwalk", "Tunxis", "Three Rivers", "Housatonic", "Capital",
            "Middlesex", "Asnuntuck", "Northwestern", "Quinebaug Valley"):
    LABEL_OVERRIDES[("CT", f"{_cc} Community College")] = (
        "Connecticut State Community College", MERGED, "merged into Connecticut State Community College in 2023")
# Words that don't tell institutions apart: a near-identical label must share every other word.
GENERIC = {"college", "colleges", "community", "university", "technical", "of", "the", "at", "and", "county",
           "institute", "school", "campus", "district", "system", "cuny", "city", "colleges"}


def _distinct_words_match(label: str, candidate: str) -> bool:
    cw = candidate.split()
    for w in label.split():
        if w in GENERIC:
            continue
        if not any(c == w or (len(w) >= 5 and (c.startswith(w) or w.startswith(c))) for c in cw):
            return False
    return True


def map_labels(conn, status) -> int:
    labels = conn.execute("SELECT state, institution, n_rows FROM unipay.payroll_institutions").fetchall()
    colleges = conn.execute("SELECT unitid, name, name_norm, core_norm, alias, state, enrollment FROM colleges "
                            "WHERE NOT closed").fetchall()
    by_name: dict = {}
    for uid, name, nn, cn, alias, st, enr in sorted(colleges, key=lambda c: -(c[6] or 0)):
        keys = {expand(name), expand(cn), re.sub(r"^cuny ", "", expand(name))}
        if "-" in name:
            head, tail = name.split("-", 1)
            keys |= {expand(head), expand(tail) if len(expand(tail).split()) >= 2 else None}
        for a in re.split(r"[|,;]", alias or ""):
            keys.add(expand(a))
        for k in keys:
            if k and k not in ("main campus",):
                by_name.setdefault((st, re.sub(r"^the ", "", k)), uid)
    names = {(c[5], c[1]): c[0] for c in colleges}
    out = []
    for st, label, n_rows in labels:
        e = re.sub(r"^the ", "", expand(label))
        uid, match, how = None, None, None
        if (st, label) in LABEL_OVERRIDES:
            target, match, why = LABEL_OVERRIDES[(st, label)]
            uid = names.get((st, target)) if target else None
            how = f"checked by hand: {target}, {why}" if target else f"checked by hand: {why}"
            match = match if uid else None
        elif SYSTEM_LABEL.search(e) or label.strip() in ("-9", ""):
            how = "a system office, board or several institutions: no single IPEDS institution"
        elif (st, e) in by_name:
            uid, match, how = by_name[(st, e)], "EXACT", "same name once abbreviations are spelled out"
        else:
            r = conn.execute("""SELECT unitid, name, name_norm, similarity(name_norm, %(e)s) AS s FROM colleges
                                WHERE state = %(st)s AND NOT closed ORDER BY s DESC LIMIT 2""",
                             {"e": e, "st": st}).fetchall()
            if r and r[0][3] >= 0.6 and (len(r) == 1 or r[0][3] - r[1][3] >= 0.05) \
                    and _distinct_words_match(e, expand(r[0][1])):
                uid, match, how = r[0][0], "FUZZY", f"nearly the same name: {r[0][1]} (similarity {r[0][3]:.2f})"
            else:
                how = "no confident match" + (f" (closest {r[0][1]}, {r[0][3]:.2f})" if r else "")
        out.append((st, label, uid, match, how, n_rows))
    _new(conn, "payroll_labels")
    with conn.cursor() as cur:
        db.copy_rows(cur, "payroll_labels__new", ["state", "label", "unitid", "match", "how", "n_rows"], out)
    n = _refill(conn, "payroll_labels", ["state", "label", "unitid", "match", "how", "n_rows"])
    mapped = sum(r[5] or 0 for r in out if r[2])
    status.emit(f"payroll labels: {n:,} labels, {sum(1 for r in out if r[2]):,} mapped "
                f"({mapped:,} of {sum(r[5] or 0 for r in out):,} rows)")
    return n


# --- payroll rows ----------------------------------------------------------------------------------

PAYROLL_COLS = ["id", "source_key", "state", "label", "unitid", "person_name", "name_norm", "withheld", "title",
                "department", "base_pay", "other_pay", "total_pay", "fiscal_year", "source_url", "pay_note", "year_note"]
PPY_COLS = ["id", "source_key", "state", "label", "unitid", "person_name", "name_norm", "withheld", "title",
            "department", "base_pay", "other_pay", "total_pay", "n_lines", "fiscal_year", "source_url", "pay_note",
            "year_note"]
# Flags the staging loader sets in pay_components (scripts/unipay/): a $0 the source published where pay is
# evidently missing (shown as Not reported; the staged row keeps the $0), and years the source didn't print.
ZERO = "coalesce((r.pay_components->>'source_published_zero')::boolean, false)"
PAY_NOTE = f"CASE WHEN {ZERO} THEN 'The source published $0' END"
YEAR_NOTE = ("CASE WHEN coalesce((r.pay_components->>'year_not_published')::boolean, false) THEN 'Year not published' "
             "WHEN r.pay_components ? 'year_derived' THEN 'Year derived from the PDF''s creation date' END")


def copy_payroll(conn, status) -> int:
    conn.execute("SET statement_timeout = 0")
    conn.execute("SET work_mem = '512MB'")
    # Sources.
    src = conn.execute("""SELECT s.source_key, min(s.state), min(s.url), min(r.fiscal_year), max(r.fiscal_year),
                                 count(*), count(DISTINCT r.institution)
                          FROM unipay.public_payroll_sources s
                          JOIN unipay.public_payroll_records r ON r.source_id = s.id
                          GROUP BY s.source_key""").fetchall()
    rows = []
    for key, st, url, y0, y1, n, ni in src:
        title, publisher, basis = SOURCE_INFO.get(key, (None, None, None))
        if not title:
            cat = conn.execute("""SELECT coalesce(u.institution, u.system), u.url FROM unipay.public_payroll_sources s
                                  JOIN unipay.university_pay_sources u ON u.id = s.catalog_source_id
                                  WHERE s.source_key = %s LIMIT 1""", (key,)).fetchone()
            title = (cat[0] if cat and cat[0] else key) + " payroll"
            publisher, basis = None, "Pay as published"
        rows.append((key, st, title, publisher, basis, url, y0, y1, n, ni, key in TRUNCATED_NAMES))
    _new(conn, "payroll_sources")
    with conn.cursor() as cur:
        db.copy_rows(cur, "payroll_sources__new", ["source_key", "state", "title", "publisher", "pay_basis", "url",
                                                   "first_year", "last_year", "n_rows", "n_institutions",
                                                   "names_truncated"], rows)
    _refill(conn, "payroll_sources", ["source_key", "state", "title", "publisher", "pay_basis", "url", "first_year",
                                      "last_year", "n_rows", "n_institutions", "names_truncated"])
    # Rows.
    _new(conn, "payroll_rows")
    conn.execute(f"""
        INSERT INTO payroll_rows__new ({', '.join(PAYROLL_COLS)})
        SELECT r.id, s.source_key, r.state, r.institution, l.unitid, r.person_name, nullif(r.name_norm, ''),
               r.person_name IS NULL OR r.person_name ~* %(withheld)s, nullif(trim(r.title), ''),
               nullif(trim(r.department), ''),
               CASE WHEN {ZERO} THEN NULL ELSE r.base_pay END, CASE WHEN {ZERO} THEN NULL ELSE r.other_pay END,
               CASE WHEN {ZERO} THEN NULL ELSE r.total_pay END,
               CASE WHEN coalesce((r.pay_components->>'year_not_published')::boolean, false) THEN NULL
                    ELSE r.fiscal_year END, r.source_url, {PAY_NOTE}, {YEAR_NOTE}
        FROM unipay.public_payroll_records r
        JOIN unipay.public_payroll_sources s ON s.id = r.source_id
        LEFT JOIN payroll_labels l ON l.state = r.state AND l.label = r.institution""", {"withheld": WITHHELD})
    n = _refill(conn, "payroll_rows", PAYROLL_COLS)
    # One row per person, employer and year. Most publishers already list one line per person and year
    # (a second line is a second job and is kept apart); SUM_LINES publishers split a year into lines.
    _new(conn, "payroll_person_years")
    conn.execute(f"""
        INSERT INTO payroll_person_years__new ({', '.join(PPY_COLS)})
        SELECT min(id), source_key, state, label, min(unitid), min(person_name), name_norm, false,
               (array_agg(title ORDER BY total_pay DESC NULLS LAST))[1],
               (array_agg(department ORDER BY total_pay DESC NULLS LAST))[1],
               sum(base_pay), sum(other_pay), sum(total_pay), count(*), fiscal_year, min(source_url),
               max(pay_note), max(year_note)
        FROM payroll_rows WHERE source_key = ANY(%(sum)s) AND NOT withheld AND name_norm IS NOT NULL
        GROUP BY source_key, state, label, name_norm, fiscal_year
        UNION ALL
        SELECT id, source_key, state, label, unitid, person_name, name_norm, withheld, title, department,
               base_pay, other_pay, total_pay, 1, fiscal_year, source_url, pay_note, year_note
        FROM payroll_rows WHERE NOT (source_key = ANY(%(sum)s) AND NOT withheld AND name_norm IS NOT NULL)""",
                 {"sum": list(SUM_LINES)})
    m = _refill(conn, "payroll_person_years", PPY_COLS)
    status.emit(f"payroll: {n:,} published rows, {m:,} person-years, {len(rows)} sources")
    return n


# --- summaries ---------------------------------------------------------------------------------------

def summarize(conn, status) -> int:
    conn.execute("SET statement_timeout = 0")
    _new(conn, "college_payroll_years")
    conn.execute("""
        INSERT INTO college_payroll_years__new
        SELECT unitid, fiscal_year, count(*) AS headcount, sum(n_lines) AS n_rows, count(total_pay) AS n_pay,
               sum(total_pay), percentile_cont(0.5) WITHIN GROUP (ORDER BY total_pay), max(total_pay),
               array_agg(DISTINCT source_key ORDER BY source_key)
        FROM payroll_person_years WHERE unitid IS NOT NULL AND fiscal_year IS NOT NULL
        GROUP BY unitid, fiscal_year""")
    n = _refill(conn, "college_payroll_years", ["unitid", "fiscal_year", "headcount", "n_rows", "n_pay", "total_pay",
                                                "median_pay", "max_pay", "source_keys"])
    _new(conn, "college_faculty_salaries")
    conn.execute("""
        INSERT INTO college_faculty_salaries__new
        SELECT DISTINCT ON (unitid, academic_year, arank) unitid, academic_year, arank, rank_label, staff_count,
               avg_salary_9mo_equated, avg_salary_9mo_equated_men, avg_salary_9mo_equated_women
        FROM unipay.ipeds_faculty_salary_averages WHERE unitid IS NOT NULL
        ORDER BY unitid, academic_year, arank""")
    m = _refill(conn, "college_faculty_salaries", ["unitid", "academic_year", "arank", "rank_label", "staff_count",
                                                   "avg_salary", "avg_men", "avg_women"])
    status.emit(f"college summaries: {n:,} institution-years of payroll, {m:,} IPEDS salary averages")
    return n


# --- people -----------------------------------------------------------------------------------------

COMMON_CLUSTERS = 3       # a name on this many person pages is common: never linked


def _tokens(n: str) -> list[str]:
    return [t for t in (n or "").split() if t not in ("jr", "sr", "ii", "iii", "iv", "md", "phd", "dr")]


def link_people(conn, status) -> int:
    """Payroll person (state, employer label, name) -> person page.

    EXACT: the same normalized full name as a person-page record at the institution itself or one of its
    affiliated nonprofits (college_orgs, either tag). FUZZY: the same first and last name with a middle name
    or initial on only one side, at the same institution or affiliate. Never linked: names that are common
    (on COMMON_CLUSTERS or more person pages), names with initials only, sources that truncate names,
    withheld names, two payroll people with the same name at one employer, or more than one matching page.
    """
    conn.execute("SET statement_timeout = 0")
    conn.execute("SET work_mem = '512MB'")
    # Candidate person records at affiliated organizations.
    cand = conn.execute("""
        SELECT co.unitid, p.name_norm, m.cluster_id, p.ein, max(p.tax_year), min(p.tax_year),
               (array_agg(p.title ORDER BY p.tax_year DESC))[1], co.relation, co.match, min(o.name)
        FROM college_orgs co
        JOIN people p ON p.ein = co.ein
        JOIN person_cluster_members m ON m.person_id = p.id
        LEFT JOIN organizations o ON o.ein = p.ein
        WHERE NOT p.is_duplicate AND p.name_norm IS NOT NULL
        GROUP BY co.unitid, p.name_norm, m.cluster_id, p.ein, co.relation, co.match""").fetchall()
    by_full = defaultdict(list)       # (unitid, full name) -> candidates
    by_fl = defaultdict(list)         # (unitid, first, last) -> candidates
    for uid, nn, cid, ein, y1, y0, title, rel, omatch, oname in cand:
        t = _tokens(nn)
        if len(t) < 2:
            continue
        c = {"cluster_id": cid, "name_norm": nn, "ein": ein, "org": oname, "relation": rel, "org_match": omatch,
             "years_990": f"{y0}-{y1}" if y0 != y1 else str(y1), "title_990": title}
        by_full[(uid, nn)].append(c)
        by_fl[(uid, t[0], t[-1])].append(c)
    commons = {r[0] for r in conn.execute(
        "SELECT name_norm FROM person_clusters WHERE NOT coalesce(is_institution, false) "
        "GROUP BY name_norm HAVING count(*) >= %s", (COMMON_CLUSTERS,))}
    pp = conn.execute(f"""
        SELECT state, label, unitid, name_norm, min(person_name), count(DISTINCT id), min(fiscal_year), max(fiscal_year)
        FROM payroll_person_years
        WHERE unitid IS NOT NULL AND NOT withheld AND name_norm IS NOT NULL
          AND NOT (source_key = ANY(%s))
        GROUP BY state, label, unitid, name_norm""", (list(TRUNCATED_NAMES),)).fetchall()
    # Two payroll people with one name at one employer (different titles in the same year) can't be told apart.
    dup = {(r[0], r[1], r[2]) for r in conn.execute("""
        SELECT state, label, name_norm FROM payroll_person_years
        WHERE NOT withheld AND name_norm IS NOT NULL GROUP BY state, label, name_norm, fiscal_year
        HAVING count(*) > 1 AND count(DISTINCT title) > 1""")}
    out, skipped = [], defaultdict(int)
    for st, label, uid, nn, pname, n, y0, y1 in pp:
        t = _tokens(nn)
        if len(t) < 2 or len(t[0]) < 2 or len(t[-1]) < 2:
            skipped["initials"] += 1
            continue
        if nn in commons:
            skipped["common"] += 1
            continue
        if (st, label, nn) in dup:
            skipped["same name twice at the employer"] += 1
            continue
        exact = by_full.get((uid, nn), [])
        clusters = {c["cluster_id"] for c in exact}
        match = "EXACT"
        if not clusters:
            fuzzy = [c for c in by_fl.get((uid, t[0], t[-1]), [])
                     if c["name_norm"] != nn and _middle_compatible(t, _tokens(c["name_norm"]))
                     and c["name_norm"] not in commons]
            clusters = {c["cluster_id"] for c in fuzzy}
            exact, match = fuzzy, "FUZZY"
        if not clusters:
            continue
        if len(clusters) > 1:
            skipped["more than one person page"] += 1
            continue
        c = sorted(exact, key=lambda c: (c["org_match"] != "EXACT", c["relation"] != "self"))[0]
        ev = {"payroll_name": pname, "payroll_years": f"{y0}-{y1}" if y0 != y1 else str(y0), "label": label,
              "990_name": c["name_norm"], "ein": c["ein"], "org": c["org"], "relation": c["relation"],
              "org_link": c["org_match"], "990_years": c["years_990"], "990_title": c["title_990"],
              "rule": "same full name" if match == "EXACT" else "same first and last name; middle name differs"}
        out.append((st, label, nn, uid, next(iter(clusters)), match, json.dumps(ev)))
    _new(conn, "payroll_person_links")
    with conn.cursor() as cur:
        db.copy_rows(cur, "payroll_person_links__new",
                     ["state", "label", "name_norm", "unitid", "cluster_id", "match", "evidence"], out)
    n = _refill(conn, "payroll_person_links", ["state", "label", "name_norm", "unitid", "cluster_id", "match", "evidence"])
    status.emit(f"payroll person links: {n:,} ({sum(1 for r in out if r[5] == 'EXACT'):,} EXACT); not linked: "
                + ", ".join(f"{k} {v:,}" for k, v in skipped.items()))
    return n


def _middle_compatible(a: list[str], b: list[str]) -> bool:
    """Same first and last name; the middle parts differ only by one side having one (or an initial of it)."""
    ma, mb = a[1:-1], b[1:-1]
    if not ma or not mb:
        return True
    return ma[0][0] == mb[0][0] and (len(ma[0]) == 1 or len(mb[0]) == 1)


# --- coaches ----------------------------------------------------------------------------------------

def classify_coaches(conn, status) -> int:
    rows = []
    for title, dept in conn.execute("""SELECT DISTINCT title, coalesce(department, '') FROM payroll_person_years
                                       WHERE title ~* 'coach'""").fetchall():
        ok, sport, role, reason = coach_class.classify(title, dept)
        rows.append(("payroll", title, dept, ok, sport, role, reason))
    for (title,) in conn.execute("SELECT DISTINCT title FROM people WHERE title ~* 'coach'").fetchall():
        ok, sport, role, reason = coach_class.classify(title)
        rows.append(("990", title, "", ok, sport, role, reason))
    _new(conn, "coach_titles")
    with conn.cursor() as cur:
        db.copy_rows(cur, "coach_titles__new", ["src", "title", "department", "is_coach", "sport", "role", "reason"], rows)
    n = _refill(conn, "coach_titles", ["src", "title", "department", "is_coach", "sport", "role", "reason"])
    status.emit(f"coach titles: {n:,} distinct titles, {sum(1 for r in rows if r[3]):,} sports coaches")
    return n


# --- the Schools list -------------------------------------------------------------------------------

SCHOOL_SQL = """
INSERT INTO school_rows__new
WITH yrs AS (SELECT * FROM college_payroll_years),
span AS (SELECT unitid, max(fiscal_year) AS last_year,
                min(fiscal_year)::text || CASE WHEN min(fiscal_year) <> max(fiscal_year) THEN '-' || max(fiscal_year) ELSE '' END AS years
         FROM yrs GROUP BY unitid),
srcs AS (SELECT p.unitid, string_agg(DISTINCT s.title, '; ') AS titles
         FROM (SELECT DISTINCT unitid, source_key FROM payroll_person_years WHERE unitid IS NOT NULL) p
         JOIN payroll_sources s USING (source_key) GROUP BY p.unitid),
top AS (SELECT DISTINCT ON (p.unitid, p.fiscal_year) p.unitid, p.fiscal_year,
               CASE WHEN p.withheld THEN 'Name withheld' ELSE p.person_name END AS person, p.title, p.total_pay,
               CASE WHEN l.cluster_id IS NOT NULL THEN '/person/' || l.cluster_id END AS url
        FROM payroll_person_years p
        LEFT JOIN payroll_person_links l ON l.state = p.state AND l.label = p.label AND l.name_norm = p.name_norm
        WHERE p.unitid IS NOT NULL AND p.total_pay IS NOT NULL
        ORDER BY p.unitid, p.fiscal_year, p.total_pay DESC, p.id),
fac AS (SELECT DISTINCT ON (unitid) unitid, academic_year FROM college_faculty_salaries ORDER BY unitid, academic_year DESC),
facr AS (SELECT f.unitid, f.academic_year,
                max(s.avg_salary) FILTER (WHERE s.arank = 1) AS prof, max(s.avg_salary) FILTER (WHERE s.arank = 2) AS assoc,
                max(s.avg_salary) FILTER (WHERE s.arank = 3) AS asst
         FROM fac f JOIN college_faculty_salaries s USING (unitid, academic_year) GROUP BY 1, 2),
orgs AS (SELECT co.unitid, co.ein, co.relation,
                -- International schools: alumni clubs and endowment or pension entities are listed, not totaled.
                CASE WHEN c.international AND co.relation IN ('alumni', 'endowment') THEN 'LISTED' ELSE co.match END AS match,
                o.name, o.latest_total_revenue, o.latest_total_expenses, o.latest_filing_year, op.latest_filing_id
         FROM college_orgs co JOIN colleges c ON c.unitid = co.unitid
         JOIN organizations o ON o.ein = co.ein LEFT JOIN org_profile op ON op.ein = co.ein),
lf AS (SELECT o.unitid, o.ein, f.net_assets_eoy FROM orgs o JOIN filings f ON f.id = o.latest_filing_id
       WHERE o.match = 'EXACT'),
orgsum AS (SELECT o.unitid, count(*) FILTER (WHERE o.match = 'EXACT') AS n_exact,
                  count(*) FILTER (WHERE o.match = 'FUZZY') AS n_fuzzy,
                  sum(o.latest_total_revenue) FILTER (WHERE o.match = 'EXACT') AS revenue,
                  sum(o.latest_total_expenses) FILTER (WHERE o.match = 'EXACT') AS expenses,
                  max(o.latest_filing_year) FILTER (WHERE o.match = 'EXACT') AS year,
                  max(o.ein) FILTER (WHERE o.relation = 'self' AND o.match = 'EXACT') AS self_ein,
                  max(o.latest_total_expenses) FILTER (WHERE o.relation = 'self' AND o.match = 'EXACT') AS self_expenses
           FROM orgs o GROUP BY o.unitid),
na AS (SELECT unitid, sum(net_assets_eoy) AS net_assets FROM lf GROUP BY unitid),
orgtop AS (SELECT DISTINCT ON (o.unitid) o.unitid, pc.display_name AS person, '/person/' || m.cluster_id AS url, o.name AS org,
                  coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS pay
           FROM orgs o JOIN people p ON p.filing_id = o.latest_filing_id AND NOT p.is_duplicate
           JOIN person_cluster_members m ON m.person_id = p.id JOIN person_clusters pc ON pc.id = m.cluster_id
           WHERE o.match = 'EXACT'
           ORDER BY o.unitid, coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) DESC, p.id),
fund AS (SELECT o.unitid, f.grantor_ein, sum(f.total) AS total
         FROM orgs o JOIN org_funders f ON f.recipient_ein = o.ein
         WHERE o.match = 'EXACT'
           AND NOT EXISTS (SELECT 1 FROM orgs o2 WHERE o2.unitid = o.unitid AND o2.ein = f.grantor_ein)
         GROUP BY o.unitid, f.grantor_ein),
fundsum AS (SELECT unitid, sum(total) AS total, count(*) AS n FROM fund GROUP BY unitid),
fundtop AS (SELECT DISTINCT ON (f.unitid) f.unitid, f.grantor_ein, f.total, o.name
            FROM fund f LEFT JOIN organizations o ON o.ein = f.grantor_ein ORDER BY f.unitid, f.total DESC),
ev AS (SELECT DISTINCT ON (o.unitid, e.ein) o.unitid, e.ein, e.special_event_expenses AS direct, e.special_event_net AS net
       FROM orgs o JOIN expense_breakdown e ON e.ein = o.ein JOIN filings f ON f.id = e.filing_id AND NOT f.superseded
       WHERE o.match = 'EXACT' ORDER BY o.unitid, e.ein, e.tax_year DESC, f.amended DESC, f.id DESC),
evsum AS (SELECT unitid, sum(direct) AS direct, sum(net) AS net FROM ev GROUP BY unitid),
cdr AS (SELECT DISTINCT ON (opeid) opeid, fiscal_year, rate, borrowers, defaulters
        FROM cohort_default_rates ORDER BY opeid, fiscal_year DESC),
coach AS (SELECT DISTINCT ON (b.unitid) b.unitid, b.subject_name, b.value, b.sport, b.subject_url, b.tax_year
          FROM board_coaches b WHERE b.unitid IS NOT NULL ORDER BY b.unitid, b.tax_year DESC, b.value DESC),
rowsy AS (SELECT c.unitid, y.fiscal_year FROM colleges c LEFT JOIN yrs y ON y.unitid = c.unitid WHERE NOT c.closed)
SELECT c.unitid, r.fiscal_year, (r.fiscal_year IS NULL OR r.fiscal_year = sp.last_year),
       c.name, c.name_norm, c.state, c.city, c.control, c.level, c.enrollment, c.international,
       coalesce(c.country, 'United States'),
       y.total_pay, y.headcount, sp.years, srcs.titles,
       t.person, t.title, t.total_pay, t.url,
       facr.prof, facr.assoc, facr.asst, facr.academic_year,
       coalesce(os.n_exact, 0), coalesce(os.n_fuzzy, 0), coalesce(os.n_exact, 0) > 0,
       os.revenue, os.expenses, na.net_assets, os.year,
       ot.person, ot.pay, ot.url, ot.org,
       os.self_ein, os.self_expenses,
       fs.total, fs.n, ft.name, ft.grantor_ein, ft.total,
       es.direct, es.net,
       ch.subject_name, ch.value, ch.sport, ch.subject_url, ch.tax_year,
       coalesce(y.total_pay, os.self_expenses, CASE WHEN c.international THEN os.expenses END),
       CASE WHEN y.total_pay IS NOT NULL THEN 'Public payroll' WHEN os.self_expenses IS NOT NULL
            THEN 'Own 990 total expenses' WHEN c.international AND os.expenses IS NOT NULL
            THEN 'US affiliates'' 990 expenses' END,
       cdr.rate, cdr.fiscal_year, cdr.borrowers, cdr.defaulters
FROM rowsy r JOIN colleges c ON c.unitid = r.unitid
LEFT JOIN yrs y ON y.unitid = r.unitid AND y.fiscal_year = r.fiscal_year
LEFT JOIN span sp ON sp.unitid = r.unitid
LEFT JOIN srcs ON srcs.unitid = r.unitid
LEFT JOIN top t ON t.unitid = r.unitid AND t.fiscal_year = r.fiscal_year
LEFT JOIN facr ON facr.unitid = r.unitid
LEFT JOIN orgsum os ON os.unitid = r.unitid
LEFT JOIN na ON na.unitid = r.unitid
LEFT JOIN orgtop ot ON ot.unitid = r.unitid
LEFT JOIN fundsum fs ON fs.unitid = r.unitid
LEFT JOIN fundtop ft ON ft.unitid = r.unitid
LEFT JOIN evsum es ON es.unitid = r.unitid
LEFT JOIN coach ch ON ch.unitid = r.unitid
LEFT JOIN cdr ON cdr.opeid = left(c.opeid, 6)
"""
SCHOOL_COLS = None   # same columns as the table, in order


def build_schools(conn, status) -> int:
    """The Schools list. Needs board_coaches (refreshed here first) and org_funders/org_profile (load.py funders)."""
    from app import boards as B
    from loader import boards as LB
    conn.execute("SET statement_timeout = 0")
    conn.execute("SET work_mem = '512MB'")
    if B.BY_SLUG.get("coaches"):
        LB._prepare(conn)
        LB.refresh_board(conn, B.BY_SLUG["coaches"], status)
        conn.commit()
    _new(conn, "school_rows")
    conn.execute(SCHOOL_SQL)
    cols = [r[0] for r in conn.execute("""SELECT column_name FROM information_schema.columns
                                          WHERE table_name = 'school_rows' AND table_schema = current_schema()
                                          ORDER BY ordinal_position""")]
    n = _refill(conn, "school_rows", cols)
    status.emit(f"schools: {n:,} rows")
    return n


def _intl(conn, status) -> int:
    from loader import intl_schools
    return intl_schools.build(conn, status)


def build(status, only: list[str] | None = None) -> None:
    steps = {"ipeds": load_ipeds, "orgs": link_orgs, "labels": map_labels, "payroll": copy_payroll,
             "summary": summarize, "links": link_people, "coaches": classify_coaches, "schools": build_schools,
             "intl": _intl}
    if only and ({"ipeds", "orgs"} & set(only)) and "intl" not in only:
        only = [*only, "intl"]      # those steps rebuild colleges / college_orgs; international rows go back in after
    with db.connect() as conn:
        for name in STEPS:
            if only and name not in only:
                continue
            status.phase = f"colleges: {name}"
            steps[name](conn, status)
            conn.commit()
