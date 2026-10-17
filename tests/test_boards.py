"""Leaderboard queries against known fixtures.

Each board's SQL runs over a handful of hand-made rows in a throwaway schema
(same table definitions as the live database), so the expected rows are known.
Needs DATABASE_URL; skipped without a database. Formatting tests run anywhere.
"""

import os
import uuid

import pytest

from app import boards as B

R, A = B.BOARD_MIN_REVENUE, B.BOARD_MIN_ASSETS
TABLES = ["filings", "people", "person_clusters", "person_cluster_members", "organizations", "contractors",
          "related_orgs"]

# EINs
ALPHA, BETA, SMALL, TWIN, PHANTOM, F, G, H = (f"10000000{i}" for i in range(1, 9))

ORGS = [  # ein, name, state, latest revenue, latest assets, ruling year
    (ALPHA, "ALPHA HOSPITAL", "NY", 20_000_000, 320_000_000, 1950),
    (BETA, "BETA FOUNDATION", "CA", 500_000, 80_000_000, 1990),
    (SMALL, "SMALL CLINIC", "TX", 2_000_000, 1_000_000, 2001),
    (TWIN, "Alpha Hospital", "NJ", 300_000, 400_000, 2015),
    (PHANTOM, "PHANTOM FUND", "DE", 12_000_000, 5_000_000, 2010),
    (F, "FOX TRUST", "MA", 15_000_000, 1_000_000, 2000),
    (G, "GULL TRUST", "MA", 15_000_000, 1_000_000, 2000),
    (H, "HERON TRUST", "MA", 15_000_000, 1_000_000, 2000),
]

FILINGS = [  # id, ein, form, year, revenue, expenses, assets, net assets, contributions, fundraising, employees
    (1, ALPHA, "990", 2021, 1_000_000, 900_000, 60_000_000, 55_000_000, 600_000, 300_000, 0),
    (2, ALPHA, "990", 2022, 20_000_000, 15_000_000, 320_000_000, 300_000_000, 2_000_000, 100_000, 50),
    (3, BETA, "990PF", 2022, 500_000, 4_000_000, 80_000_000, 79_000_000, None, None, None),
    (4, SMALL, "990", 2022, 2_000_000, 1_900_000, 1_000_000, 500_000, 900_000, 800_000, 0),
    (5, TWIN, "990EZ", 2022, 300_000, 290_000, 400_000, 350_000, 100_000, None, None),
    (6, PHANTOM, "990", 2022, 12_000_000, 11_000_000, 5_000_000, 4_000_000, 0, 0, 1),
    (7, F, "990", 2022, 15_000_000, 14_000_000, 1_000_000, 900_000, 0, 0, 20),
    (8, G, "990", 2022, 15_000_000, 14_000_000, 1_000_000, 900_000, 0, 0, 20),
    (9, H, "990", 2022, 15_000_000, 14_000_000, 1_000_000, 900_000, 0, 0, 20),
]

CLUSTERS = [  # id, display name, name_norm, institution, evidence
    (11, "Jane Doe", "jane doe", False, None),
    (12, "John Roe", "john roe", False, '[{"r": "variant", "ein": "100000002", "names": ["john roe", "john q roe"]}]'),
    (13, "Bank Of America", "bank of america", True, None),
    (14, "Rich Outsider", "rich outsider", False, None),
    (15, "Ann Zed", "ann zed", False, None),
    (16, "Bob Zed", "bob zed", False, None),
    (17, "Sam Serial", "sam serial", False, None),
    (18, "Sanford Group Return", "sanford group return", False, None),   # a placeholder, not a person
]

PEOPLE = [  # id, filing, cluster, name_norm, comp_org, street
    (101, 2, 11, "jane doe", 900_000, None),
    (102, 1, 11, "jane doe", 60_000, None),
    (103, 3, 12, "john roe", 400_000, None),
    (104, 3, 13, "bank of america", 500_000, None),
    (105, 4, 14, "rich outsider", 5_000_000, None),
    (106, 2, 15, "ann zed", 0, "1 ELM ST"),
    (107, 2, 16, "bob zed", 0, "1 ELM ST"),
    (108, 2, 18, "sanford group return", 1_000_000, None),
] + [(110 + i, fid, 17, "sam serial", 0, None) for i, fid in enumerate([2, 3, 6, 7, 8, 9])]

CONTRACTORS = [  # id, filing, name_norm, paid
    (201, 2, "acme law llp", 150_000),
    (202, 3, "acme law llp", 60_000),
    (203, 6, "acme law llp", 120_000),
    (204, 2, "tiny vendor", 90_000),       # under the 990 threshold
    (205, 4, "big outsider", 1_000_000),   # organization out of scope
]


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"boards_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    try:
        conn.execute(f"SET search_path = {schema}, public")
        conn.execute(f"SET pg_trgm.similarity_threshold = {B.LOOKALIKE_SIMILARITY}")
        for t in TABLES:
            conn.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)")
        for ein, name, state, rev, assets, ruling in ORGS:
            conn.execute("""INSERT INTO organizations (ein, name, name_norm, state, latest_total_revenue,
                            latest_total_assets, ruling_year, latest_filing_year) VALUES (%s,%s,%s,%s,%s,%s,%s,2022)""",
                         (ein, name, name.lower(), state, rev, assets, ruling))
        for fid, ein, form, year, rev, exp, assets, net, contrib, fr, emp in FILINGS:
            conn.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, state, total_revenue,
                            total_expenses, total_assets_eoy, net_assets_eoy, contributions, fundraising_expenses,
                            num_employees, superseded, amended)
                            VALUES (%s,%s,%s,%s,%s,(SELECT name FROM organizations WHERE ein=%s),
                                    (SELECT state FROM organizations WHERE ein=%s),%s,%s,%s,%s,%s,%s,%s,false,false)""",
                         (fid, ein, 900000 + fid, form, year, ein, ein, rev, exp, assets, net, contrib, fr, emp))
        for cid, disp, nn, inst, ev in CLUSTERS:
            conn.execute("""INSERT INTO person_clusters (id, display_name, name_norm, is_institution, evidence,
                            last_name) VALUES (%s,%s,%s,%s,%s,%s)""", (cid, disp, nn, inst, ev, nn.split()[-1]))
        for pid, fid, cid, nn, comp, street in PEOPLE:
            conn.execute("""INSERT INTO people (id, filing_id, ein, tax_year, source, name_raw, name_norm, title,
                            comp_org, street)
                            SELECT %s, id, ein, tax_year, '990-VIIA', upper(%s), %s, 'DIRECTOR', %s, %s
                            FROM filings WHERE id = %s""", (pid, nn, nn, comp, street, fid))
            conn.execute("INSERT INTO person_cluster_members (person_id, cluster_id) VALUES (%s, %s)", (pid, cid))
        for kid, fid, nn, paid in CONTRACTORS:
            conn.execute("""INSERT INTO contractors (id, filing_id, ein, tax_year, source, name_raw, name_norm,
                            compensation, service_description)
                            SELECT %s, id, ein, tax_year, 'x', upper(%s), %s, %s, 'LEGAL' FROM filings WHERE id=%s""",
                         (kid, nn, nn, paid, fid))
        conn.execute("INSERT INTO related_orgs (filing_id, ein, related_ein, related_name) VALUES (8, %s, %s, 'FOX')",
                     (G, F))
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def run(db, slug):
    board = B.BY_SLUG[slug]
    cur = db.cursor(row_factory=__import__("psycopg").rows.dict_row)
    return cur.execute(f"SELECT * FROM ({board.sql}) q ORDER BY pos").fetchall()


def keys(rows, col="subject_key"):
    return [r[col] for r in rows]


def test_top_paid(db):
    rows = run(db, "top-paid")
    # Rich Outsider's org is out of scope; the bank is an institution; Jane's 2021 pay is under the floor;
    # the group-return row isn't a person.
    assert keys(rows) == ["11", "12"]
    assert rows[0]["value"] == 900_000 and rows[0]["tax_year"] == 2022 and rows[0]["match"] == "EXACT"
    assert rows[1]["match"] == "FUZZY"
    assert rows[0]["subject_url"] == "/person/11" and rows[0]["filing_id"] == 2


def test_top_vendors(db):
    rows = run(db, "top-vendors")
    assert [r["value"] for r in rows] == [150_000, 120_000, 60_000]
    assert {r["form_type"] for r in rows} == {"990", "990PF"}


def test_dragon_hoard(db):
    rows = run(db, "dragon-hoard")
    by_filing = {r["filing_id"]: float(r["value"]) for r in rows}
    assert by_filing[1] == pytest.approx(61.11)       # 55M / 900K
    assert by_filing[3] == pytest.approx(19.75)       # 79M / 4M
    assert 4 not in by_filing                         # out of scope
    assert rows[0]["filing_id"] == 1


def test_expensive_dollar(db):
    rows = run(db, "expensive-dollar")
    assert [(r["filing_id"], float(r["value"])) for r in rows] == [(1, 0.5), (2, 0.05)]


def test_small_org_big_check(db):
    rows = run(db, "small-org-big-check")
    # Beta: $500K revenue, $80M assets. The bank's bigger number doesn't count.
    assert [(r["subject_key"], r["value"]) for r in rows] == [("12", 400_000)]


def test_biggest_swings(db):
    rows = run(db, "biggest-swings")
    got = {(r["measure"], r["subject_key"]): float(r["value"]) for r in rows}
    assert got[("Revenue", ALPHA)] == 20.0
    assert got[("Officer pay", "11")] == 15.0
    assert all(r["prior_year"] == 2021 for r in rows)


def test_phantom_staff(db):
    rows = run(db, "phantom-staff")
    assert keys(rows) == [PHANTOM]


def test_lookalikes(db):
    rows = run(db, "lookalikes")
    assert len(rows) == 1
    pair = {rows[0]["subject_key"], rows[0]["twin_ein"]}
    assert pair == {ALPHA, TWIN} and float(rows[0]["value"]) == 1.0


def test_shared_vendors(db):
    rows = run(db, "shared-vendors")
    assert [(r["subject_key"], r["value"], r["total_paid"]) for r in rows] == [("acme law llp", 3, 330_000)]


def test_revolving_door(db):
    rows = run(db, "revolving-door")
    # Six organizations, but Gull is related to Fox (Schedule R): five.
    assert [(r["subject_key"], r["value"]) for r in rows] == [("17", 5)]


def test_family_plan(db):
    rows = run(db, "family-plan")
    assert [(r["filing_id"], r["surname"], r["value"]) for r in rows] == [(2, "zed", 2)]


# --- no database needed -------------------------------------------------------

def test_every_board_documented():
    for b in B.BOARDS:
        assert b.title and b.subtitle and b.definition and b.formula, b.slug
        assert b.sql.lstrip().startswith("SELECT row_number()"), b.slug


def test_person_level_hidden_by_default():
    assert not B.BOARDS_PERSON_LEVEL
    assert {b.slug for b in B.visible()} >= {"top-paid", "top-vendors", "dragon-hoard"}
    assert B.get("revolving-door") is None and B.get("family-plan") is None


def test_format_and_finding():
    assert B.fmt(1234567, "money") == "$1,234,567"
    assert B.fmt(12.345, "years") == "12.3 yrs"
    assert B.fmt(0.4567, "cost") == "$0.46"
    assert B.fmt(15, "multiple") == "15.0x"
    assert B.window({"year_min": 2011, "year_max": 2025}) == "tax years 2011 to 2025, e-filed returns only"
    row = {"subject_name": "Jane Doe", "value": 900000, "tax_year": 2022}
    assert B.finding(B.BY_SLUG["top-paid"], row) == "Top row: Jane Doe, $900,000, tax year 2022"


def test_norm():
    assert B.norm("  O'Brien & Sons, LLP ") == "o brien sons llp"
