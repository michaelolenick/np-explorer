"""Natural-language "top paid": ranks within the list, one row per person, plain-English
categories, higher-ed definition, related entities, years. The ranking SQL runs over
hand-made rows in a throwaway schema (needs DATABASE_URL); labels run anywhere."""

import os
import uuid
from contextlib import contextmanager

import pytest

from app import ask, boards

TABLES = ["filings", "people", "person_clusters", "person_cluster_members", "organizations"]
UNIV, MGMT, COLLEGE, HOSP, OTHERU = "200000001", "200000002", "200000003", "200000004", "200000005"
ORGS = [  # ein, name, ntee, state
    (UNIV, "STATE UNIVERSITY", "B430", "NY"),
    (MGMT, "STATE UNIVERSITY MANAGEMENT COMPANY", "B430", "NY"),   # an investment arm: related entity
    (COLLEGE, "SMALLVILLE COLLEGE", None, "KS"),                    # no NTEE code: found by name
    (HOSP, "STATE UNIVERSITY HEALTH SYSTEM", "E220", "NY"),          # health care, not higher ed
    (OTHERU, "OTHER UNIVERSITY", "B430", "OH"),
]
CLUSTERS = [  # id, name, first, last
    (1, "Ann Dean", "ann", "dean"), (2, "Bob Coach", "bob", "coach"), (3, "Cy Fund", "cy", "fund"),
    (4, "Dee Small", "dee", "small"), (5, "Ed Doc", "ed", "doc"), (6, "Ed Doc", "ed", "doc"),
    (7, "Flo Ohio", "flo", "ohio"),
]
PAY = [  # (filing id, ein, year), person id, cluster, pay
    ((1, UNIV, 2021), 101, 1, 900_000), ((2, UNIV, 2022), 102, 1, 1_200_000), ((2, UNIV, 2022), 103, 2, 1_000_000),
    ((3, MGMT, 2022), 104, 3, 5_000_000), ((4, COLLEGE, 2022), 105, 4, 400_000),
    ((5, HOSP, 2022), 106, 5, 3_000_000), ((2, UNIV, 2022), 107, 6, 3_000_000),   # Ed Doc: same pay, two records
    ((6, OTHERU, 2020), 108, 7, 2_000_000),
]


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from psycopg.rows import dict_row
    from app.config import DATABASE_URL
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True, row_factory=dict_row)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"top_paid_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    c.execute(f"CREATE SCHEMA {schema}")
    try:
        c.execute(f"SET search_path = {schema}, public")
        for t in TABLES:
            c.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING DEFAULTS)")
        for ein, name, ntee, state in ORGS:
            c.execute("INSERT INTO organizations (ein, name, name_norm, ntee, state) VALUES (%s,%s,%s,%s,%s)",
                      (ein, name, name.lower(), ntee, state))
        for (fid, ein, year), *_ in PAY:
            c.execute("""INSERT INTO filings (id, ein, object_id, form_type, tax_year, org_name, state, total_revenue,
                         total_assets_eoy, superseded, amended)
                         SELECT %s, %s, %s, '990', %s, name, state, 20000000, 1, false, false FROM organizations
                         WHERE ein = %s ON CONFLICT DO NOTHING""", (fid, ein, 900 + fid, year, ein))
        for cid, disp, first, last in CLUSTERS:
            c.execute("""INSERT INTO person_clusters (id, display_name, name_norm, first_name, last_name, is_institution)
                         VALUES (%s,%s,%s,%s,%s,false)""", (cid, disp, disp.lower(), first, last))
        for (fid, ein, year), pid, cid, pay in PAY:
            c.execute("""INSERT INTO people (id, filing_id, ein, tax_year, source, name_raw, name_norm, title, comp_org)
                         SELECT %s, %s, %s, %s, '990-VIIA', upper(display_name), name_norm, 'PRESIDENT', %s
                         FROM person_clusters WHERE id = %s""", (pid, fid, ein, year, pay, cid))
            c.execute("INSERT INTO person_cluster_members (person_id, cluster_id) VALUES (%s, %s)", (pid, cid))
        c.execute(f"CREATE TABLE board_top_paid AS {boards.BY_SLUG['top-paid'].sql}")
        yield c
    finally:
        c.execute(f"DROP SCHEMA {schema} CASCADE")
        c.close()


@pytest.fixture
def run(conn, monkeypatch):
    @contextmanager
    def use(*a, **k):
        yield conn
    monkeypatch.setattr(ask.db, "conn", use)

    def go(**args):
        intent = ask.validate("top_paid", {"scope": "ntee" if args.get("ntee") else "all", "limit": 10, **args})
        return ask.top_paid_rows(intent), intent
    return go


def names(rows):
    return [r["subject_name"] for r in rows]


def test_ranks_restart_at_one_within_a_filtered_list(run):
    rows, _ = run(ntee="higher_ed")
    assert [r["list_rank"] for r in rows] == list(range(1, len(rows) + 1))
    assert all(r["rank"] >= r["list_rank"] for r in rows)        # the board's global rank is not what's shown


def test_one_row_per_person_with_years_count(run):
    rows, _ = run(ntee="higher_ed")
    ann = [r for r in rows if r["subject_name"] == "Ann Dean"]
    assert len(ann) == 1 and ann[0]["tax_year"] == 2022 and ann[0]["value"] == 1_200_000 and ann[0]["n_years"] == 2


def test_every_year_toggle(run):
    rows, _ = run(ntee="higher_ed", per_person=False)
    assert names(rows).count("Ann Dean") == 2


def test_higher_ed_uses_ntee_codes_and_names(run):
    rows, _ = run(ntee="higher_ed")
    assert set(names(rows)) == {"Ann Dean", "Bob Coach", "Dee Small", "Ed Doc", "Flo Ohio"}
    # Dee Small: Smallville College has no NTEE code, found by name. The hospital's Ed Doc row is not higher ed,
    # but the other Ed Doc record (same name, same pay, State University) is.


def test_related_entities_off_by_default_and_on_when_asked(run):
    assert "Cy Fund" not in names(run(ntee="higher_ed")[0])
    assert "Cy Fund" in names(run(ntee="higher_ed", include_related=True)[0])


def test_same_pay_reported_twice_is_shown_once(run):
    rows, _ = run()
    ed = [r for r in rows if r["subject_name"] == "Ed Doc"]
    assert len(ed) == 1 and ed[0]["also"]


def test_year_and_state_filters(run):
    rows, _ = run(ntee="higher_ed", year=2020)
    assert names(rows) == ["Flo Ohio"]
    rows, _ = run(state="OH")
    assert names(rows) == ["Flo Ohio"] and rows[0]["list_rank"] == 1


def test_labels_are_plain_english():
    assert ask.category_label("higher_ed") == "Higher education"
    assert ask.category_label("B") == "Education (NTEE B)"
    assert ask.category_label("E") == "Health care (NTEE E)"
    assert ask.category_label("B430") == "Higher education (NTEE B43)"
    assert ask.category_label("E220") == "Health care (NTEE E22)"
    assert ask.validate("top_paid", {"scope": "ntee", "ntee": "higher education"})["ntee"] == "higher_ed"
    assert ask.validate("top_paid", {"scope": "ntee", "ntee": "B43"})["ntee"] == "B"


def test_searching_line_says_all_years_and_category():
    it = ask.validate("top_paid", {"scope": "ntee", "ntee": "higher_ed", "limit": 10})
    assert ask.describe(it) == "the 10 highest-paid people in higher education, all years"
    it = ask.validate("top_paid", {"scope": "ntee", "ntee": "B", "limit": 10, "year": 2022, "per_person": False})
    assert ask.describe(it) == "the 10 highest-paid people in education (NTEE B) in 2022, every year listed"


def test_edit_links_keep_the_search_and_flip_one_option():
    it = ask.validate("top_paid", {"scope": "ntee", "ntee": "higher_ed", "limit": 10})
    url = ask.edit_url(it, per_person=False)
    assert "intent=top_paid" in url and "ntee=higher_ed" in url and "per_person=0" in url and "limit=10" in url
    assert "include_related=1" in ask.edit_url(it, include_related=True)
    assert ask.top_paid_notes(it) == [ask.HIGHER_ED_NOTE, ask.RELATED_NOTE]
