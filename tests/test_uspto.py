"""USPTO patents and trademarks: the loaders' parsing (loader/uspto.py, loader/patents.py, loader/trademarks.py)
and the pages (app/patents.py, app/trademarks.py)."""

import datetime as dt

from loader import patents as P
from loader import trademarks as T
from loader import uspto as U


def test_dates_in_each_format():
    assert U.date_any("2018-06-19") == dt.date(2018, 6, 19)          # PatentsView
    assert U.date_any("22apr1991") == dt.date(1991, 4, 22)           # patent assignments
    assert U.date_any("19550103") == dt.date(1955, 1, 3)             # trademark assignments
    assert U.date_any("1074-08-14") is None                          # PatentsView typo years
    assert U.date_any("") is None and U.date_any("31feb2001") is None


def test_state_codes():
    assert U.state_code("TEXAS") == "TX" and U.state_code("ny") == "NY"
    assert U.state_code("Ontario") is None and U.state_code(None) is None


def test_twenty_year_cutoff():
    today = dt.date.today()
    assert U.CUTOFF.year == today.year - 20 and U.CUTOFF.month == today.month


def test_patent_numbers():
    assert P.patent_number("US 10,000,000 B2") == "10000000"
    assert P.patent_number("D0654321") == "D654321"
    assert P.patent_number("RE049123") == "RE49123"
    assert P.patent_number("PP34567P3") == "PP34567"
    assert P.patent_number("7654321") == "7654321"
    assert P.patent_number("hello") is None and P.patent_number("") is None


def test_google_patents_url_uses_the_kind():
    assert P.google_url("10000000", "B2") == "https://patents.google.com/patent/US10000000B2"


def test_assignee_names():
    org = {"disambig_assignee_organization": "DIVERGENT TECHNOLOGIES, INC.", "disambig_assignee_individual_name_first": "",
           "disambig_assignee_individual_name_last": ""}
    assert P.assignee_name(org) == ("DIVERGENT TECHNOLOGIES, INC.", False)
    person = {"disambig_assignee_organization": "", "disambig_assignee_individual_name_first": "Jane",
              "disambig_assignee_individual_name_last": "Doe"}
    assert P.assignee_name(person) == ("Jane Doe", True)


def test_name_forms_for_links():
    assert P.full_norm("Acme Widgets, Inc.") == "acme widgets inc"
    assert P.college_core("The Regents of the University of California") == "university of california"
    assert P.college_core("Board of Trustees of the Leland Stanford Junior University") == \
        "leland stanford junior university"
    assert P.college_core("Massachusetts Institute of Technology") == "massachusetts institute of technology"


def test_trademark_status_from_dates_and_codes():
    assert T.is_dead("602", dt.date(2010, 1, 1), None)
    assert T.is_dead("710", None, dt.date(2012, 1, 1))
    assert T.is_dead("900", None, None) and T.is_dead("606", None, None)
    assert not T.is_dead("700", None, None) and not T.is_dead("800", None, None) and not T.is_dead("630", None, None)
    assert T.status_label({"status_code": "800", "registration_date": dt.date(2001, 1, 1),
                           "renewal_date": dt.date(2011, 1, 1)}) == "Registered and renewed"
    assert T.status_label({"status_code": "700", "registration_date": dt.date(2020, 1, 1)}) == "Registered"
    assert T.status_label({"status_code": "630"}) == "Pending application"
    assert T.status_label({"status_code": "602", "abandon_date": dt.date(2019, 5, 1)}) == "Abandoned"
    assert T.status_label({"status_code": "710", "cancel_date": dt.date(2019, 5, 1)}) == "Registration cancelled"


def test_trademark_owner_types_and_keys():
    assert T.owner_type_label("10") == "Original applicant"
    assert T.owner_type_label("31") == "New owner after registration"
    assert T.owner_type_label("") == "Owner"
    assert T.owner_key("acme", "tx") == T.owner_key("acme", "TX") != T.owner_key("acme", "NY")
    assert len(T.owner_key("acme", None)) == 12
    assert T.mark_norm("Coca-Cola!") == "coca cola" and T.mark_norm("") is None


def test_tsdr_link():
    assert T.tsdr_url("90015123") == ("https://tsdr.uspto.gov/#caseNumber=90015123&caseType=SERIAL_NO"
                                      "&searchType=statusSearch")


def test_bad_numbers_are_404():
    from starlette.testclient import TestClient
    from app import main
    client = TestClient(main.app)
    assert client.get("/patent/not-a-number").status_code == 404
    assert client.get("/trademark/123").status_code == 404
    assert client.get("/trademarks/owner/zzz").status_code == 404


def test_pages_render_with_the_site_layout():
    """A loaded patent, its first inventor and assignee, and a loaded mark render inside the site's one layout."""
    import re

    from starlette.testclient import TestClient
    from app import db, main
    try:
        db.pool.open()
    except Exception:  # noqa: BLE001 - already open
        pass
    with db.conn() as conn:
        if not conn.execute("SELECT to_regclass('pat_patents') IS NOT NULL AS ok").fetchone()["ok"]:
            return
        p = conn.execute("""SELECT a.patent_id, a.assignee_id, i.inventor_id FROM pat_assignees a
                            JOIN pat_inventors i USING (patent_id)
                            WHERE a.assignee_id IN (SELECT assignee_id FROM pat_assignee_orgs)
                              AND i.inventor_id IN (SELECT inventor_id FROM pat_inventor_people) LIMIT 1""").fetchone()
        m = conn.execute("SELECT serial_no FROM tm_marks LIMIT 1").fetchone()
    client = TestClient(main.app)
    paths = []
    if p:
        paths += [f"/patent/{p['patent_id']}", f"/inventor/{p['inventor_id']}", f"/patents/assignee/{p['assignee_id']}"]
    if m:
        paths.append(f"/trademark/{m['serial_no']}")
    for path in paths:
        r = client.get(path)
        assert r.status_code == 200, path
        assert re.search(r"<body[^>]*>", r.text).group(0) == '<body class="wide contained">', path
        assert "Not reported" in r.text or "Source" in r.text


def test_uspto_firm_pages():
    """A USPTO-only firm renders in the site layout, marked as derived from USPTO records; bad ids are 404."""
    import re

    from starlette.testclient import TestClient
    from app import db, main
    client = TestClient(main.app)
    assert client.get("/business/USPTO/not-a-firm").status_code == 404
    try:
        db.pool.open()
    except Exception:  # noqa: BLE001 - already open
        pass
    with db.conn() as conn:
        if not conn.execute("SELECT to_regclass('ip_firms') IS NOT NULL AS ok").fetchone()["ok"]:
            return
        f = conn.execute("SELECT firm_id, name FROM ip_firms WHERE match_kind IS NULL AND NOT hidden LIMIT 1").fetchone()
    if f:
        r = client.get(f"/business/USPTO/{f['firm_id']}")
        assert r.status_code == 200
        assert re.search(r"<body[^>]*>", r.text).group(0) == '<body class="wide contained">'
        assert "USPTO only" in r.text and "Possible related entities" in r.text


def test_trademark_entity_labels():
    assert T.entity_label("03") == "Corporation" and T.entity_label("16") == "Limited liability company"
    assert T.entity_label("3", "a Delaware corporation") == "a Delaware corporation"
    assert T.entity_label("") is None
