"""International schools: the reviewed CSV -> colleges, college_orgs and Schedule F rows (loader/intl_schools.py).

The load runs over hand-made rows in a throwaway schema (same table definitions as the live database).
INSEAD North America (EIN 31-1734079) is the worked example. Needs DATABASE_URL for the database tests.
"""

import csv
import os
import uuid

import pytest

from app import boards as B
from loader import intl_schools as I

INSEAD, OXFORD_SELF, OXFORD_FUNDS, HEC_FRIENDS, SOKA, ALUMNI = (
    "311734079", "986001062", "980680056", "208152139", "953909672", "300000001")
ROWS = [  # ror_id, school, country, website, ein, org, match, evidence
    ("https://ror.org/00ghzk478", "INSEAD", "France", "https://www.insead.edu", INSEAD, "INSEAD NORTH AMERICA INC",
     "EXACT", "name_exact: 'Insead' | Schedule R related org 'Institut Europeen Dadministration Des' in FR"),
    ("https://ror.org/052gg0110", "University of Oxford", "United Kingdom", "https://www.ox.ac.uk", OXFORD_SELF,
     "UNIVERSITY OF OXFORD", "EXACT", "name_exact: 'University Of Oxford' | the school itself files a US return"),
    ("https://ror.org/052gg0110", "University of Oxford", "United Kingdom", "https://www.ox.ac.uk", OXFORD_FUNDS,
     "THE OXFORD FUNDS", "EXACT", "name_exact: 'Oxford'"),
    ("https://ror.org/052gg0110", "University of Oxford", "United Kingdom", "https://www.ox.ac.uk", ALUMNI,
     "OXFORD UNIVERSITY ALUMNI CLUB OF NEW YORK", "EXACT", "name_exact: 'University Of Oxford'"),
    ("https://ror.org/03dpb7k12", "HEC Paris", "France", "https://www.hec.edu", HEC_FRIENDS, "FRIENDS OF HEC INC",
     "FUZZY", "name_token: 'HEC' (shared with HEC Montreal)"),          # FUZZY only: never linked, no school row
    ("https://ror.org/04q9tew83", "Soka University", "Japan", "https://www.soka.ac.jp", SOKA,
     "SOKA UNIVERSITY OF AMERICA", "EXACT", "name_exact: 'Soka University'"),   # a US school (IPEDS): dropped
]
GRANTS = [(INSEAD, 2023, "1", "Part II: grants to organizations", "Europe (including Iceland and Greenland)", 2_500_000,
           "Educational")]


def test_relation_rules():
    assert I.relation("UNIVERSITY OF OXFORD", "986001062", "") == "self"            # an IRS 98- (foreign) EIN
    assert I.relation("X", "131599108", "... the school itself files a US return") == "self"
    assert I.relation("THE OXFORD FUNDS", "980680056"[:0] + "123456789", "") == "endowment"
    assert I.relation("CARLETON UNIVERSITY RETIREMENT PLAN", "123456789", "") == "endowment"
    assert I.relation("OXFORD UNIVERSITY ALUMNI CLUB OF NEW YORK", "123456789", "") == "alumni"
    assert I.relation("INSEAD NORTH AMERICA INC", INSEAD, "") == "foundation"


class Status:
    phase = ""

    def emit(self, m):
        pass


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"intl_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    d = tmp_path_factory.mktemp("intl")
    links, grants = d / "links.csv", d / "grants.csv"
    with open(links, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ror_id", "school_name", "country", "website", "ein", "org_name", "match", "evidence", "latest_revenue"])
        w.writerows([r + ("1000",) for r in ROWS])
    with open(grants, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ein", "tax_year", "object_id", "part", "region", "amount", "description"])
        w.writerows(GRANTS)
    try:
        conn.execute(f"SET search_path = {schema}, public")
        for t in ("colleges", "college_orgs", "organizations", "intl_schools", "intl_grants_abroad"):
            conn.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING ALL)")
        for ein, name in [(INSEAD, "INSEAD NORTH AMERICA INC"), (OXFORD_SELF, "UNIVERSITY OF OXFORD"),
                          (OXFORD_FUNDS, "THE OXFORD FUNDS"), (HEC_FRIENDS, "FRIENDS OF HEC INC"),
                          (SOKA, "SOKA UNIVERSITY OF AMERICA"), (ALUMNI, "OXFORD UNIVERSITY ALUMNI CLUB OF NEW YORK")]:
            conn.execute("INSERT INTO organizations (ein, name, name_norm) VALUES (%s, %s, %s)", (ein, name, name.lower()))
        conn.execute("""INSERT INTO colleges (unitid, name, name_norm, core_norm, state, control, ein)
                        VALUES (121150, 'Soka University of America', 'soka university of america',
                                'soka university of america', 'CA', 'Private nonprofit', %s)""", (SOKA,))
        conn.execute("""INSERT INTO college_orgs (unitid, ein, relation, match, evidence)
                        VALUES (121150, %s, 'self', 'EXACT', '{"rule": "ipeds_ein"}')""", (SOKA,))
        I.build(conn, Status(), links, grants)
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def test_insead_north_america_worked_example(db):
    row = db.execute("""SELECT c.unitid, c.name, c.country, c.international, c.control, co.relation, co.match
                        FROM college_orgs co JOIN colleges c USING (unitid) WHERE co.ein = %s""", (INSEAD,)).fetchone()
    assert row[0] >= I.FIRST_ID and row[1:] == ("INSEAD", "France", True, "International", "foundation", "EXACT")
    g = db.execute("SELECT region, amount FROM intl_grants_abroad WHERE ein = %s", (INSEAD,)).fetchall()
    assert g == [("Europe (including Iceland and Greenland)", 2_500_000)]


def test_own_return_endowment_and_alumni(db):
    rel = dict(db.execute("SELECT ein, relation FROM college_orgs WHERE ein = ANY(%s)",
                          ([OXFORD_SELF, OXFORD_FUNDS, ALUMNI],)).fetchall())
    assert rel == {OXFORD_SELF: "self", OXFORD_FUNDS: "endowment", ALUMNI: "alumni"}
    assert db.execute("SELECT files_own_return FROM intl_schools WHERE name = 'University of Oxford'").fetchone()[0]


def test_fuzzy_not_linked_and_school_without_us_affiliate(db):
    assert db.execute("SELECT count(*) FROM college_orgs WHERE ein = %s", (HEC_FRIENDS,)).fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM colleges WHERE name = 'HEC Paris'").fetchone()[0] == 0   # no EXACT link


def test_us_school_named_after_a_foreign_one_is_dropped(db):
    assert db.execute("SELECT count(*) FROM colleges WHERE name = 'Soka University'").fetchone()[0] == 0
    assert db.execute("SELECT relation FROM college_orgs WHERE ein = %s", (SOKA,)).fetchall() == [("self",)]


def test_ids_are_stable_across_rebuilds(db, tmp_path):
    before = dict(db.execute("SELECT ror_id, unitid FROM intl_schools").fetchall())
    links = tmp_path / "l.csv"
    with open(links, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ror_id", "school_name", "country", "website", "ein", "org_name", "match", "evidence", "latest_revenue"])
        w.writerows([r + ("1",) for r in reversed(ROWS)])
    I.build(db, Status(), links, tmp_path / "none.csv")
    assert dict(db.execute("SELECT ror_id, unitid FROM intl_schools").fetchall()) == before


def test_country_filter(monkeypatch):
    b = B.BY_SLUG["schools"]
    monkeypatch.setattr(B, "filter_options", lambda board: {"country": [("France", 2), ("Canada", 30)],
                                                           "control": [], "sector": []})
    params = {}
    where = B._where(b, {"country": "France", "international": "1"}, params)
    assert '"country" = %(f_country)s' in where and params["f_country"] == "France" and "international" in where
    params = {}
    assert "f_country" not in B._where(b, {"country": "Narnia"}, params) + str(params)   # not an offered value
