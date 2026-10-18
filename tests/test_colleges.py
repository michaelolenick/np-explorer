"""Colleges, public payroll, coaches and the Schools list.

Pure rules (coach titles, name matching) run without a database. The link and board SQL runs over
hand-made rows in a throwaway schema (same table definitions as the live database), as in
test_event_boards.py; those tests need DATABASE_URL.
"""

import json
import os
import uuid

import pytest

from app import boards as B
from app import coach_class as C
from app import uni_boards as U
from loader import colleges as L


# --- coach titles (no database) ---------------------------------------------------------------

@pytest.mark.parametrize("title, dept, coach, sport, role", [
    ("Head Coach-Major Sports", "CC12637 Athletics | Football", True, "Football", "head"),
    ("Assistant Coach-Major Sports", "CC12633 Athletics | Basketball Men", True, "Men's basketball", "assistant"),
    ("Asst Coach -Women's Basketball", "UNIVERSITY OF MASSACHUSETTS SYSTEM (UMS)", True, "Women's basketball", "assistant"),
    ("HEAD BASKETBALL COACH", "", True, "Basketball (men's or women's not stated)", "head"),
    ("Assoc Head Coach", "SDA Administration", True, "Unclear", "assistant"),
    ("SUCoachPT", "", True, "Unclear", "other"),
    ("CCAstCoachMa", "", True, "Unclear", "assistant"),
    ("CoachesDrivers", "MASSASOIT COMMUNITY COLLEGE (MAS)", False, None, None),
    ("Success Coach", "EdPlus Success Coaching Center", False, None, None),
    ("Academic Coach", "Learning Commons", False, None, None),
    ("Health Coach 3", "CC10325 OSU Health Plan | Health Coaching", False, None, None),
    ("INSTRUCTIONAL COACH", "", False, None, None),
    ("Track  Field Asst Coach", "", True, "Track and field / cross country", "assistant"),
    ("Asst Coach-Track&Fld/X-Country", "", True, "Track and field / cross country", "assistant"),
    ("Strength and Conditioning Coach 2", "", True, "Strength and conditioning", "other"),
    ("Head Women's Ice Hockey Coach", "", True, "Ice hockey", "head"),
    ("Assistant Coach - Field Hockey", "", True, "Field hockey", "assistant"),
    ("Offensive Coordinator/Quarterbacks Coach", "", True, "Football", "assistant"),
    ("Co-Head Coach", "", True, "Unclear", "head"),
    ("Assistant Coach", "CC12672 Athletics | Rowing Women", True, "Rowing", "assistant"),
    ("Head Swim Coach", "", True, "Swimming and diving", "head"),
    ("Head Coach, Beach Volleyball", "", True, "Beach volleyball", "head"),
    ("Softball Head Coach", "BRIDGEWATER STATE UNIVERSITY (BSC)", True, "Softball", "head"),
    ("Wrestling Asst Coach", "", True, "Wrestling", "assistant"),
    ("Head Coach", "Athletics", True, "Unclear", "head"),
    ("DIRECTOR OF COACHING", "", True, "Unclear", "other"),
    ("Pitching Coach", "", True, "Unclear", "other"),            # baseball or softball: not guessed
    ("Vocal Coach", "", False, None, None),
    ("Director of Athletics", "Athletics", False, None, None),
])
def test_coach_titles(title, dept, coach, sport, role):
    ok, s, r, reason = C.classify(title, dept)
    assert (ok, s, r) == (coach, sport, role), reason


# --- name rules (no database) ----------------------------------------------------------------------

def test_label_and_name_rules():
    assert L.expand("S. E. Okla. St. Univ.") == "southeastern oklahoma state university"
    assert L.core("The Ohio State University-Main Campus") == "ohio state university"
    assert L._distinct_words_match("kingsboro community college", "cuny kingsborough community college")
    assert not L._distinct_words_match("darton state college", "dalton state college")      # a different school
    assert not L._distinct_words_match("arizona state university", "university of arizona")
    assert L._relation("athletic foundation") == "athletic" and L._relation("alumni association") == "alumni"
    assert L.STOP.search("wesley foundation of the university of georgia")
    assert L._middle_compatible(["walter", "carter"], ["walter", "b", "carter"])
    assert not L._middle_compatible(["walter", "a", "carter"], ["walter", "b", "carter"])


# --- database fixtures ---------------------------------------------------------------------------

UNI, PRIV, SMALL = 9001, 9002, 9003
FOUND, ALUMNI, ALUMNI_FAR, LAWALUM, MINISTRY, ATHL, PRIV_EIN, OTHER = (f"55000000{i}" for i in range(1, 9))


class Status:
    phase = ""

    def emit(self, m):
        pass


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"colleges_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    try:
        conn.execute(f"SET search_path = {schema}, public")
        for t in ("colleges", "college_orgs", "organizations", "filings", "people", "person_clusters",
                  "person_cluster_members", "payroll_person_years", "payroll_sources", "payroll_person_links",
                  "coach_titles", "school_rows"):
            conn.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)")
        for uid, name, city, ein, control, enr in [
                (UNI, "Testland State University", "Testville", None, "Public", 30000),
                (PRIV, "Testland Private College", "Testville", PRIV_EIN, "Private nonprofit", 3000),
                (SMALL, "Tiny Test Community College", "Elsewhere", None, "Public", 800)]:
            conn.execute("""INSERT INTO colleges (unitid, name, name_norm, core_norm, city, state, zip, ein, control, enrollment)
                            VALUES (%s, %s, %s, %s, %s, 'ZZ', '99999', %s, %s, %s)""",
                         (uid, name, L.norm(name), L.core(name), city, ein, control, enr))
        for ein, name, city in [(FOUND, "TESTLAND STATE UNIVERSITY FOUNDATION INC", "TESTVILLE"),
                                (ALUMNI, "TESTLAND STATE UNIVERSITY ALUMNI ASSOCIATION", "TESTVILLE"),
                                (ALUMNI_FAR, "TESTLAND STATE UNIVERSITY ALUMNI ASSOCIATION", "FARAWAY"),
                                (LAWALUM, "TESTLAND STATE UNIVERSITY LAW SCHOOL ALUMNI ASSOCIATION", "TESTVILLE"),
                                (MINISTRY, "WESLEY FOUNDATION AT TESTLAND STATE UNIVERSITY", "TESTVILLE"),
                                (ATHL, "TESTLAND STATE UNIVERSITY ATHLETIC ASSOCIATION", "TESTVILLE"),
                                (PRIV_EIN, "TESTLAND PRIVATE COLLEGE", "TESTVILLE"),
                                (OTHER, "SPRINGFIELD YOUTH SOCCER CLUB", "SPRINGFIELD")]:
            conn.execute("""INSERT INTO organizations (ein, name, name_norm, city, state, zip, latest_total_revenue,
                            latest_total_expenses) VALUES (%s, %s, %s, %s, 'ZZ', %s, 1000000, 900000)""",
                         (ein, name, L.norm(name), city, "99999" if city == "TESTVILLE" else "11111"))
        L.link_orgs(conn, Status())
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def links(db):
    return {r[0]: (r[1], r[2], r[3]) for r in db.execute("SELECT ein, unitid, relation, match FROM college_orgs")}


def test_institution_nonprofit_links_exact_vs_fuzzy(db):
    got = links(db)
    assert got[FOUND] == (UNI, "foundation", "EXACT")
    assert got[ATHL] == (UNI, "athletic", "EXACT")
    assert got[ALUMNI] == (UNI, "alumni", "EXACT")             # same name, the institution's city
    assert got[ALUMNI_FAR] == (UNI, "alumni", "FUZZY")         # same name, filed from somewhere else
    assert got[LAWALUM] == (UNI, "alumni", "FUZZY")            # other words: law school
    assert got[PRIV_EIN] == (PRIV, "self", "EXACT")            # the EIN IPEDS lists
    assert MINISTRY not in got and OTHER not in got            # a campus ministry; unrelated
    ev = json.loads(db.execute("SELECT evidence::text FROM college_orgs WHERE ein = %s", (LAWALUM,)).fetchone()[0])
    assert ev["other_words"] == ["law", "school"]


def _person(db, cid, name_norm, display, ein, year, title, comp_org, comp_related=0, other=0, fid=None):
    fid = fid or cid * 10 + year % 10
    db.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, state, superseded, amended)
                  VALUES (%s, %s, %s, '990', %s, 'x', 'ZZ', false, false) ON CONFLICT DO NOTHING""",
               (fid, ein, 700000 + fid, year))
    pid = db.execute("SELECT coalesce(max(id), 0) + 1 FROM people").fetchone()[0]
    db.execute("""INSERT INTO people (id, filing_id, ein, tax_year, name_raw, name_norm, title, comp_org, comp_related,
                  other_comp, is_duplicate) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)""",
               (pid, fid, ein, year, display, name_norm, title, comp_org, comp_related, other))
    db.execute("INSERT INTO person_cluster_members (person_id, cluster_id) VALUES (%s, %s)", (pid, cid))
    db.execute("""INSERT INTO person_clusters (id, display_name, name_norm, evidence) VALUES (%s, %s, %s, '[]')
                  ON CONFLICT DO NOTHING""", (cid, display, name_norm))


def _payroll(db, pid, name, name_norm, title, dept, pay, year, source="zz", label="Testland State University"):
    db.execute("""INSERT INTO payroll_person_years (id, source_key, state, label, unitid, person_name, name_norm,
                  withheld, title, department, total_pay, n_lines, fiscal_year, source_url)
                  VALUES (%s, %s, 'ZZ', %s, %s, %s, %s, false, %s, %s, %s, 1, %s, 'https://example.org/list')""",
               (pid, source, label, UNI, name, name_norm, title, dept, pay, year))


@pytest.fixture(scope="module")
def people(db):
    db.execute("""INSERT INTO payroll_sources (source_key, state, title, pay_basis) VALUES
                  ('zz', 'ZZ', 'Testland payroll', 'Gross pay'), ('tx', 'ZZ', 'Initials payroll', 'Base salary')""")
    # Coach A: EXACT (same full name, on the athletic association's 990 the same year).
    _person(db, 1, "pat q coachman", "Pat Q Coachman", ATHL, 2023, "HEAD FOOTBALL COACH", 2_000_000, 500_000, 100_000)
    _person(db, 1, "pat q coachman", "Pat Q Coachman", FOUND, 2023, "DIRECTOR", 0, 2_400_000, 0, fid=999)  # same money
    _payroll(db, 1, "Coachman, Pat Q", "pat q coachman", "Head Coach", "Athletics | Football", 1_000_000, 2023)
    _payroll(db, 2, "Coachman, Pat Q", "pat q coachman", "Head Coach", "Athletics | Football", 900_000, 2022)
    # Coach B: FUZZY (middle initial only on the 990).
    _person(db, 2, "lee r hooper", "Lee R Hooper", ATHL, 2023, "HEAD BASKETBALL COACH", 300_000)
    _payroll(db, 3, "Hooper, Lee", "lee hooper", "Head Coach", "Athletics | Basketball Women", 700_000, 2023)
    # Common name: on three person pages.
    for cid in (3, 4, 5):
        _person(db, cid, "john smith", "John Smith", FOUND if cid == 3 else OTHER, 2023, "DIRECTOR", 0)
    _payroll(db, 4, "Smith, John", "john smith", "Professor", "History", 120_000, 2023)
    # Initials-only source: never linked.
    _person(db, 6, "jo k", "Jo K", FOUND, 2023, "TRUSTEE", 0)
    _payroll(db, 5, "K, Jo", "jo k", "Lecturer", "", 50_000, 2023, source="tx")
    # A 990-only coach at an unrelated club.
    _person(db, 7, "sam kicker", "Sam Kicker", OTHER, 2023, "DIRECTOR OF COACHING", 80_000)
    for src, title, dept in [("payroll", "Head Coach", "Athletics | Football"),
                             ("payroll", "Head Coach", "Athletics | Basketball Women"),
                             ("990", "HEAD FOOTBALL COACH", ""), ("990", "HEAD BASKETBALL COACH", ""),
                             ("990", "DIRECTOR OF COACHING", "")]:
        ok, sport, role, reason = C.classify(title, dept)
        db.execute("INSERT INTO coach_titles VALUES (%s, %s, %s, %s, %s, %s, %s)", (src, title, dept, ok, sport, role, reason))
    L.link_people(db, Status())
    return db


def test_person_links(people):
    got = {r[0]: (r[1], r[2]) for r in people.execute("SELECT name_norm, cluster_id, match FROM payroll_person_links")}
    assert got["pat q coachman"] == (1, "EXACT")
    assert got["lee hooper"] == (2, "FUZZY")
    assert "john smith" not in got           # common name: never linked
    assert "jo k" not in got                 # initials only


def coach_rows(db):
    cur = db.cursor(row_factory=__import__("psycopg").rows.dict_row)
    return cur.execute(f"SELECT * FROM ({U.coaches()}) q ORDER BY pos").fetchall()


def test_coaches_exact_combines_fuzzy_does_not(people):
    rows = coach_rows(people)
    pat = [r for r in rows if r["subject_key"] == "1"]
    combined = [r for r in pat if r["tax_year"] == 2023]
    assert len(combined) == 1                                   # one row for the person and year
    c = combined[0]
    assert (c["from_payroll"], c["from_nonprofit"], c["related_not_added"], c["combined"]) == (
        1_000_000, 2_100_000, 500_000, 3_100_000)               # 990 own pay = comp_org + other; related not added
    assert c["source_type"] == "Public payroll; University or foundation 990" and c["match"] == "EXACT"
    assert [r["tax_year"] for r in pat if r["combined"] is None] == [2022]     # another year: never combined
    lee = [r for r in rows if r["subject_name"] in ("Hooper, Lee", "Lee R Hooper")]
    assert len(lee) == 2 and all(r["combined"] is None for r in lee)          # FUZZY: two separate rows
    assert {r["source_type"] for r in lee} == {"Public payroll", "University or foundation 990"}
    assert any(r["match"] == "FUZZY" and r["link_evidence"] for r in lee)
    sam = next(r for r in rows if r["subject_name"] == "Sam Kicker")
    assert sam["source_type"] == "Other nonprofit 990" and sam["sport"] == "Unclear"


def test_same_payment_on_two_990s_counted_once(people):
    pat_990 = [r for r in coach_rows(people) if r["subject_key"] == "1" and r["tax_year"] == 2023]
    # The foundation's 990 reports the same $2.4M as related-organization pay: it is neither added nor a second row.
    assert len(pat_990) == 1 and pat_990[0]["value"] == 3_100_000


def test_coaches_default_view_latest_year_highest_first(people):
    rows = coach_rows(people)
    default = sorted((r for r in rows if r["org_pos"]), key=lambda r: r["org_pos"])
    assert [r["subject_key"] for r in default if r["subject_key"] == "1"] == ["1"]   # one row per person
    assert next(r for r in default if r["subject_key"] == "1")["tax_year"] == 2023   # the latest year
    vals = [r["value"] for r in default]
    assert vals == sorted(vals, reverse=True)
    assert B.fmt(None, "money?") == "Not reported" and B.fmt(0, "money?") == "$0"


def test_schools_default_sort_and_private_without_payroll(db):
    db.execute("DELETE FROM school_rows")
    for uid, name, year, latest, payroll, self_exp, basis in [
            (UNI, "Testland State University", 2023, True, 900_000_000, None, "Public payroll"),
            (UNI, "Testland State University", 2022, False, 850_000_000, None, "Public payroll"),
            (PRIV, "Testland Private College", None, True, None, 1_200_000_000, "Own 990 total expenses"),
            (SMALL, "Tiny Test Community College", None, True, None, None, None)]:
        db.execute("""INSERT INTO school_rows (unitid, fiscal_year, latest, name, name_norm, state, payroll_total,
                      self_expenses, sort_value, sort_basis, n_orgs, n_orgs_fuzzy, has_orgs, international)
                      VALUES (%s, %s, %s, %s, %s, 'ZZ', %s, %s, %s, %s, 0, 0, false, false)""",
                   (uid, year, latest, name, L.norm(name), payroll, self_exp, payroll or self_exp, basis))
    cur = db.cursor(row_factory=__import__("psycopg").rows.dict_row)
    rows = cur.execute(f"SELECT * FROM ({U.schools()}) q ORDER BY org_pos NULLS LAST, pos").fetchall()
    default = [r for r in rows if r["org_pos"]]
    assert [r["unitid"] for r in default] == [PRIV, UNI, SMALL]      # private school ranks by its own 990 expenses
    assert default[0]["sort_basis"] == "Own 990 total expenses" and default[1]["tax_year"] == 2023
    assert default[2]["value"] is None and B.fmt(default[2]["payroll_total"], "money?") == "Not reported"
    assert len(rows) == 4                                            # every year with ?all=1


# --- natural-language intents (no database) ------------------------------------------------------

def test_school_intents_validate():
    from app import ask
    assert ask.validate("university_pay", {"institution": "Ohio State", "title_contains": "head coach"}) == {
        "intent": "university_pay", "institution": "Ohio State", "state": None, "title_contains": "head coach",
        "name": None, "year": None, "limit": 25}
    assert ask.validate("university_pay", {})["intent"] == "unknown"
    assert ask.validate("coaches", {"sport": "Football", "head_only": True})["sport"] == "Football"
    assert ask.validate("coaches", {"sport": "Quidditch"})["sport"] is None
    assert ask.validate("school_lookup", {"institution": "UConn", "topic": "nonprofits"})["topic"] == "nonprofits"
    assert "head coach" in ask.describe(ask.validate("university_pay", {"institution": "Ohio State",
                                                                        "title_contains": "head coach"}))


def test_resolve_never_guesses(monkeypatch):
    from app import colleges
    many = [{"unitid": i, "name": f"The University of Texas at {c}", "score": 0.6, "payroll_total": 1}
            for i, c in enumerate(["Austin", "Dallas", "Arlington"])]
    monkeypatch.setattr(colleges, "search", lambda q, limit=10, state=None: many)
    inst, choices = colleges.resolve("University of Texas")
    assert inst is None and len(choices) == 3
    one = [{"unitid": 1, "name": "Ohio State University-Main Campus", "score": 0.9, "payroll_total": 1},
           {"unitid": 2, "name": "Ohio State University-Lima Campus", "score": 0.6, "payroll_total": None}]
    monkeypatch.setattr(colleges, "search", lambda q, limit=10, state=None: one)
    assert colleges.resolve("Ohio State University")[0]["unitid"] == 1
