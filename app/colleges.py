"""Colleges and universities: institution pages, public payroll, and their links to 990 data.

Tables are built by loader/colleges.py (load.py colleges). Pay is shown as each publisher reports
it (payroll_sources.pay_basis says how); a blank is "Not reported", never $0. Links between payroll
people and person pages, and between institutions and nonprofits, carry an EXACT or FUZZY tag and
their evidence.
"""

from __future__ import annotations

import re

from app import db
from app.cache import ttl_lru

TOP_SHOWN = 50
PEOPLE_PAGE = 100
RELATION_LABELS = {"endowment": "Endowment, fund or pension entity", "self": "The institution itself", "foundation": "Foundation", "alumni": "Alumni association",
                   "athletic": "Athletic or booster organization", "research": "Research foundation",
                   "hospital": "Hospital or medical organization"}
RANKS = {1: "Professor", 2: "Associate professor", 3: "Assistant professor", 4: "Instructor", 5: "Lecturer",
         6: "No academic rank", 7: "All ranks"}
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
          "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
          "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
          "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
          "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
          "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
          "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
          "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
          "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}


def available() -> bool:
    try:
        with db.conn() as conn:
            return bool(conn.execute("SELECT 1 FROM colleges LIMIT 1").fetchone())
    except Exception:  # noqa: BLE001 - tables not built yet
        return False


# --- coverage --------------------------------------------------------------------------------

@ttl_lru()
def coverage() -> dict:
    """Which states and years of public payroll are loaded, by source; and which states are not."""
    with db.conn() as conn:
        sources = conn.execute("""SELECT source_key, state, title, publisher, pay_basis, url, first_year, last_year,
                                         n_rows, n_institutions, names_truncated
                                  FROM payroll_sources ORDER BY state, first_year""").fetchall()
    by_state: dict = {}
    for s in sources:
        by_state.setdefault(s["state"], []).append(s)
    loaded = sorted(by_state)
    return {"sources": sources, "by_state": by_state, "loaded": loaded,
            "not_loaded": [st for st in sorted(STATES) if st not in by_state],
            "n_rows": sum(s["n_rows"] or 0 for s in sources),
            "years": (min((s["first_year"] for s in sources if s["first_year"]), default=None),
                      max((s["last_year"] for s in sources if s["last_year"]), default=None))}


def state_coverage(state: str | None) -> list[dict]:
    return coverage()["by_state"].get(state or "", [])


# --- search ----------------------------------------------------------------------------------

def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (q or "").lower().replace("&", " and "))).strip()


# Well-known short names IPEDS doesn't list as aliases. Ambiguous ones (OSU, UW, USC) are left out on purpose.
NICKNAMES = {"uconn": "university of connecticut", "umass": "university of massachusetts amherst",
             "umass amherst": "university of massachusetts amherst", "uga": "university of georgia",
             "georgia tech": "georgia institute of technology", "unm": "university of new mexico",
             "asu": "arizona state university", "ku": "university of kansas", "k state": "kansas state university",
             "unl": "university of nebraska lincoln", "uic": "university of illinois chicago",
             "uiuc": "university of illinois urbana champaign", "ttu": "texas tech university",
             "tamu": "texas a and m university college station", "texas a and m": "texas a and m university college station",
             "ut austin": "the university of texas at austin", "unt": "university of north texas",
             "utep": "the university of texas at el paso", "utsa": "the university of texas at san antonio",
             "uh": "university of houston", "ou": "university of oklahoma", "kennesaw": "kennesaw state university"}


def search(q: str, limit: int = 10, state: str | None = None) -> list[dict]:
    """Institutions by name (and alias), best first."""
    n = _norm(q)
    n = NICKNAMES.get(n, n)
    q = n if n != _norm(q) else q
    if len(n) < 2 or not available():
        return []
    with db.conn() as conn:
        return conn.execute("""
            SELECT c.unitid, c.name, c.city, c.state, c.control, c.level, c.enrollment,
                   s.payroll_total, s.fiscal_year AS payroll_year, (s.unitid IS NOT NULL AND s.n_orgs > 0) AS has_orgs,
                   greatest(similarity(c.name_norm, %(n)s), word_similarity(%(n)s, c.name_norm)) AS score
            FROM colleges c LEFT JOIN school_rows s ON s.unitid = c.unitid AND s.latest
            WHERE (c.name_norm %% %(n)s OR c.name_norm LIKE %(like)s OR c.name_tsv @@ plainto_tsquery('simple', %(q)s))
              AND (%(st)s::text IS NULL OR c.state = %(st)s)
            ORDER BY (c.name_norm = %(n)s OR c.core_norm = %(n)s) DESC, score DESC, c.enrollment DESC NULLS LAST
            LIMIT %(lim)s""", {"n": n, "like": "%" + n + "%", "q": q, "st": state, "lim": limit}).fetchall()


def resolve(name: str, state: str | None = None) -> tuple[dict | None, list[dict]]:
    """One institution for a name, or the candidates when it isn't clear. Never guesses between close names:
    'University of Texas' lists the UT campuses; 'Ohio State' finds Ohio State's main campus."""
    rows = search(name, 12, state)
    if not rows:
        return None, []
    n = _norm(name)
    exact = [r for r in rows if _norm(r["name"]) == n or _norm(re.sub(r"(?i)-main campus$", "", r["name"])) == n]
    if len(exact) == 1:
        return exact[0], []
    top = rows[0]
    second = rows[1] if len(rows) > 1 else None
    # A clear winner: well ahead on name, or the only one with payroll among near-ties.
    if not second or top["score"] - second["score"] >= 0.15:
        return top, []
    close = [r for r in rows if top["score"] - r["score"] < 0.15]
    # Near-ties among one school's campuses ("Ohio State"): the one campus with payroll, if it is also the largest.
    with_pay = [r for r in close if r["payroll_total"]]
    if len(with_pay) == 1 and (with_pay[0]["enrollment"] or 0) >= max(r["enrollment"] or 0 for r in close):
        return with_pay[0], []
    return None, close


# --- institution page --------------------------------------------------------------------------

def institution(unitid: int) -> dict | None:
    with db.conn() as conn:
        c = conn.execute("SELECT * FROM colleges WHERE unitid = %s", (unitid,)).fetchone()
        if not c:
            return None
        school = conn.execute("SELECT * FROM school_rows WHERE unitid = %s AND latest", (unitid,)).fetchone()
        years = conn.execute("""SELECT * FROM college_payroll_years WHERE unitid = %s ORDER BY fiscal_year DESC""",
                             (unitid,)).fetchall()
        # The sources come from the precomputed yearly summary (scanning payroll rows here would be slow).
        keys = sorted({k for y in years for k in (y["source_keys"] or [])})
        labels = conn.execute("""SELECT l.label, l.match, l.how, l.n_rows, s.source_key, s.title, s.publisher,
                                        s.pay_basis, s.url, s.first_year, s.last_year, s.names_truncated
                                 FROM payroll_labels l JOIN payroll_sources s ON s.state = l.state
                                 WHERE l.unitid = %s AND s.source_key = ANY(%s)
                                 ORDER BY l.n_rows DESC""", (unitid, keys)).fetchall() if keys else []
        faculty = conn.execute("""SELECT * FROM college_faculty_salaries WHERE unitid = %s
                                  ORDER BY academic_year DESC, arank""", (unitid,)).fetchall()
        orgs = conn.execute("""
            SELECT co.ein, co.relation, co.match, co.evidence, o.name, o.city, o.state, o.ntee,
                   o.latest_filing_year, o.latest_total_revenue, o.latest_total_expenses, o.latest_total_assets,
                   lf.net_assets_eoy, lf.id AS filing_id,
                   (SELECT count(*) FROM org_funders f WHERE f.recipient_ein = co.ein) AS n_funders
            FROM college_orgs co JOIN organizations o ON o.ein = co.ein
            LEFT JOIN LATERAL (SELECT f.id, f.net_assets_eoy FROM filings f WHERE f.ein = co.ein AND NOT f.superseded
                               ORDER BY f.tax_year DESC, f.amended DESC, f.id DESC LIMIT 1) lf ON true
            WHERE co.unitid = %s
            ORDER BY co.match, array_position(ARRAY['self','foundation','athletic','alumni','research','hospital'],
                                              co.relation), o.latest_total_revenue DESC NULLS LAST""",
                            (unitid,)).fetchall()
        eins = [o["ein"] for o in orgs if o["match"] == "EXACT"]
        funders = conn.execute("""
            SELECT f.grantor_ein, max(f.grantor_name) AS grantor_name, max(f.grantor_kind) AS grantor_kind,
                   sum(f.total) AS total, count(DISTINCT f.recipient_ein) AS n_recipients, max(f.last_year) AS last_year
            FROM org_funders f WHERE f.recipient_ein = ANY(%s) AND NOT (f.grantor_ein = ANY(%s))
            GROUP BY f.grantor_ein ORDER BY total DESC NULLS LAST LIMIT 25""", (eins, eins)).fetchall() if eins else []
        events = conn.execute("""
            SELECT DISTINCT ON (e.ein) e.ein, o.name, e.tax_year, e.filing_id, e.special_event_gross AS gross,
                   e.special_event_expenses AS direct, e.special_event_net AS net
            FROM expense_breakdown e JOIN filings f ON f.id = e.filing_id AND NOT f.superseded
            JOIN organizations o ON o.ein = e.ein
            WHERE e.ein = ANY(%s) AND (e.special_event_gross IS NOT NULL OR e.special_event_expenses IS NOT NULL)
            ORDER BY e.ein, e.tax_year DESC, f.amended DESC, f.id DESC""", (eins,)).fetchall() if eins else []
        coaches = _board_rows(conn, "board_coaches", "unitid = %s", (unitid,), 15)
        cdr = cdr_rows(conn, c.get("opeid"))
        # People paid by the linked nonprofits (latest return of each EXACT link), highest pay first.
        people = conn.execute("""
            SELECT DISTINCT ON (pc.id) pc.id AS cluster_id, pc.display_name, p.title, p.tax_year, o.name AS org,
                   p.ein, coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total
            FROM org_profile op JOIN people p ON p.filing_id = op.latest_filing_id AND NOT p.is_duplicate
            JOIN person_cluster_members m ON m.person_id = p.id JOIN person_clusters pc ON pc.id = m.cluster_id
            JOIN organizations o ON o.ein = p.ein
            WHERE op.ein = ANY(%s)
            ORDER BY pc.id, total DESC""", (eins,)).fetchall() if eins else []
        people = sorted(people, key=lambda r: -(r["total"] or 0))[:25]
        abroad = conn.execute("""SELECT g.*, o.name AS org FROM intl_grants_abroad g JOIN organizations o ON o.ein = g.ein
                                 WHERE g.ein = ANY(%s) ORDER BY g.amount DESC NULLS LAST""",
                              ([o["ein"] for o in orgs],)).fetchall() if c.get("international") else []
        intl = conn.execute("SELECT * FROM intl_schools WHERE unitid = %s", (unitid,)).fetchone() \
            if c.get("international") else None
    return {"college": c, "school": school, "years": years, "labels": labels, "faculty": faculty,
            "faculty_latest": _latest_year(faculty), "orgs": orgs, "funders": funders, "events": events,
            "coaches": coaches, "coverage": state_coverage(c["state"]), "people": people, "abroad": abroad,
            "cdr": cdr,
            "intl": intl,
            "relation_labels": RELATION_LABELS, "ranks": RANKS}


CDR_LABEL = "Federal cohort default rate (Department of Education)"


def cdr_rows(conn, opeid: str | None) -> list[dict]:
    """The Department of Education's official cohort default rates for the school (its 8-digit OPE ID's first six
    digits, so branch campuses show their main school's rate), newest cohort first. [] when there are none."""
    if not opeid:
        return []
    try:
        return conn.execute("""SELECT opeid, fiscal_year, school_name, borrowers, defaulters, rate, source_url
                               FROM cohort_default_rates WHERE opeid = %s ORDER BY fiscal_year DESC""",
                            (opeid[:6],)).fetchall()
    except Exception:  # noqa: BLE001 - table not loaded
        conn.rollback()
        return []


def _latest_year(faculty: list[dict]) -> list[dict]:
    if not faculty:
        return []
    y = faculty[0]["academic_year"]
    return [f for f in faculty if f["academic_year"] == y]


def _board_rows(conn, view: str, where: str, params: tuple, limit: int) -> list[dict]:
    try:
        return conn.execute(f"SELECT * FROM {view} WHERE {where} ORDER BY value DESC NULLS LAST LIMIT {limit}",
                            params).fetchall()
    except Exception:  # noqa: BLE001 - board not built yet
        conn.rollback()
        return []


def payroll_people(unitid: int, year: int | None, page: int = 1, q: str | None = None,
                   per_page: int = PEOPLE_PAGE) -> dict:
    """One institution's payroll for a year, highest pay first, with person-page links where made."""
    with db.conn() as conn:
        if year is None:
            r = conn.execute("SELECT max(fiscal_year) AS y FROM college_payroll_years WHERE unitid = %s",
                             (unitid,)).fetchone()
            year = r["y"] if r else None
        if year is None:
            return {"rows": [], "total": 0, "year": None}
        params = {"u": unitid, "y": year, "lim": per_page, "off": (page - 1) * per_page,
                  "q": f"%{_norm(q)}%" if q else None}
        filt = "AND (p.name_norm LIKE %(q)s OR lower(p.title) LIKE %(q)s)" if q else ""
        rows = conn.execute(f"""
            SELECT p.*, l.cluster_id, l.match, l.evidence, s.pay_basis, s.title AS source_title
            FROM payroll_person_years p
            LEFT JOIN payroll_person_links l ON l.state = p.state AND l.label = p.label AND l.name_norm = p.name_norm
            JOIN payroll_sources s ON s.source_key = p.source_key
            WHERE p.unitid = %(u)s AND p.fiscal_year = %(y)s {filt}
            ORDER BY p.total_pay DESC NULLS LAST, p.id LIMIT %(lim)s OFFSET %(off)s""", params).fetchall()
        total = conn.execute(f"""SELECT count(*) AS n FROM payroll_person_years p
                                 WHERE p.unitid = %(u)s AND p.fiscal_year = %(y)s {filt}""", params).fetchone()["n"]
    return {"rows": rows, "total": total, "year": year}


# --- person pages and org pages ------------------------------------------------------------------

def person_payroll(cluster_id: int) -> list[dict]:
    """Public payroll rows linked to a person page, newest first, with the tag and evidence."""
    try:
        with db.conn() as conn:
            return conn.execute("""
                SELECT p.fiscal_year, p.title, p.department, p.base_pay, p.other_pay, p.total_pay, p.n_lines,
                       p.label, p.unitid, p.source_url, c.name AS institution, l.match, l.evidence,
                       s.title AS source_title, s.publisher, s.pay_basis, s.url AS source_home
                FROM payroll_person_links l
                JOIN payroll_person_years p ON p.state = l.state AND p.label = l.label AND p.name_norm = l.name_norm
                JOIN payroll_sources s ON s.source_key = p.source_key
                LEFT JOIN colleges c ON c.unitid = p.unitid
                WHERE l.cluster_id = %s
                ORDER BY p.fiscal_year DESC NULLS LAST, p.total_pay DESC NULLS LAST""", (cluster_id,)).fetchall()
    except Exception:  # noqa: BLE001 - tables not built yet
        return []


def org_institutions(ein: str) -> list[dict]:
    """Institutions an organization is linked to (its university, for a foundation)."""
    try:
        with db.conn() as conn:
            return conn.execute("""SELECT co.unitid, co.relation, co.match, co.evidence, c.name, c.state
                                   FROM college_orgs co JOIN colleges c ON c.unitid = co.unitid
                                   WHERE co.ein = %s ORDER BY co.match, c.name""", (ein,)).fetchall()
    except Exception:  # noqa: BLE001
        return []


def evidence_text(ev: dict | None) -> str:
    """Plain words for a link's evidence."""
    if not ev:
        return ""
    rule = ev.get("rule")
    if rule == "ipeds_ein":
        return f"IPEDS lists EIN {ev.get('ipeds_ein')} for this institution."
    if rule == "intl":
        return f"Matched to {ev.get('school')} ({ev.get('country')}) in the Research Organization Registry: {ev.get('evidence')}."
    if rule == "shared_ipeds_ein":
        return (f"IPEDS lists this EIN for {ev.get('n_sharing')} campuses; its 990 is counted with "
                f"{ev.get('shared_with')}.")
    if rule == "same_name_same_place":
        return (f"Same name as the institution, filed from its {'city' if ev.get('same_city') else 'ZIP code'}; "
                f"IPEDS lists a different EIN or none.")
    if rule in ("name", "same_name_elsewhere"):
        place = ", same city" if ev.get("same_city") else ", same ZIP code" if ev.get("same_zip") else ""
        other = ev.get("other_words") or []
        s = (f"Name is “{ev.get('institution_name')}” plus “{ev.get('relation_words')}”, same state{place}.")
        if other:
            s += " Other words in the name: " + ", ".join(other) + "."
        if ev.get("short_name"):
            s += f" “{ev['short_name'].title()}” is a short name for the institution" + (
                "; the organization files from its city or ZIP code." if ev.get("same_city") or ev.get("same_zip")
                else "; the organization files from elsewhere.")
        if ev.get("note"):
            s += " " + ev["note"] + "."
        return s
    if "payroll_name" in ev:
        return (f"Payroll name “{ev['payroll_name']}” ({ev.get('label')}, {ev.get('payroll_years')}) and 990 name "
                f"“{(ev.get('990_name') or '').title()}” ({ev.get('990_title') or 'no title'}, {ev.get('990_years')}) at "
                f"{ev.get('org')} ({RELATION_LABELS.get(ev.get('relation'), ev.get('relation'))}, "
                f"{(ev.get('org_link') or '').lower()} link to the institution): {ev.get('rule')}.")
    return ""
