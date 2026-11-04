"""Form 5500, Open Payments, state and city payroll and the cross-links (owner, 2026-11-04): parsers, menu, pages."""

import datetime as dt

from loader import form5500, gov_payroll, openpayments, xlinks  # noqa: F401  (xlinks imports must work)


def test_form5500_parse():
    r = {"ACK_ID": "20250103142145NAL0001", "FORM_PLAN_YEAR_BEGIN_DATE": "2024-01-01", "DATE_RECEIVED": "2025-01-03",
         "PLAN_NAME": "ACME 401(K) PLAN", "SPONS_DFE_PN": "001", "SPONSOR_DFE_NAME": "ACME WIDGETS INC", "SPONS_DFE_DBA_NAME": "ACME",
         "SPONS_DFE_MAIL_US_STATE": "tx", "SPONS_DFE_MAIL_US_CITY": "AUSTIN", "SPONS_DFE_EIN": "12-3456789", "ADMIN_NAME": "ACME WIDGETS INC",
         "ADMIN_EIN": "123456789", "ADMIN_US_STATE": "TX", "SPONS_SIGNED_NAME": "JANE Q PUBLIC", "ADMIN_SIGNED_NAME": "",
         "ADMIN_MANUAL_SIGNED_NAME": "JOHN DOE", "PREPARER_NAME": "", "PREPARER_FIRM_NAME": "BIG FOUR LLP", "PREPARER_US_STATE": "NY",
         "LAST_RPT_SPONS_NAME": "ACME WIDGETS INC", "LAST_RPT_SPONS_EIN": "123456789"}
    filing, names = form5500.parse("5500", r, 2024, dt.datetime(2026, 11, 4, tzinfo=dt.UTC))
    assert filing[:4] == ("20250103142145NAL0001", "5500", 2024, 2024) and filing[4] == dt.date(2025, 1, 3)
    assert filing[7:12] == ("ACME WIDGETS INC", "ACME", "123456789", "TX", "AUSTIN")
    kinds = {n[1]: n for n in names}
    assert kinds["sponsor_signer"][2:5] == ("JANE Q PUBLIC", "jane q public", "TX")
    assert kinds["admin_signer"][2] == "JOHN DOE" and kinds["preparer_firm"][4] == "NY" and kinds["sponsor_dba"][2] == "ACME"
    assert "last_sponsor" not in kinds                      # same sponsor as reported: not a separate name
    assert form5500._ein("000000000") is None and form5500._state("Texas") is None


def test_openpayments_helpers():
    assert openpayments._num("1,234.5") == 1234.5 and openpayments._num("") is None
    assert openpayments._date("10/23/2024") == dt.date(2024, 10, 23) and openpayments._date("2024-10-23") is None
    c = openpayments.Cols(["Record_ID", "Covered_Recipient_Type", "Teaching_Hospital_ID", "Covered_Recipient_Profile_ID",
                           "Covered_Recipient_First_Name", "Covered_Recipient_Middle_Name", "Covered_Recipient_Last_Name",
                           "Covered_Recipient_Name_Suffix", "Recipient_City", "Recipient_State", "Recipient_Country",
                           "Covered_Recipient_Specialty_1", "Covered_Recipient_NPI"])
    key, raw = openpayments._recipient(c, ["1", "Covered Recipient Physician", "", "232750", "CHRISTOPHER", "", "STALLTER", "",
                                           "AURORA", "IL", "United States", "Allopathic & Osteopathic Physicians|Family Medicine", "1134115629"])
    assert key == "p232750" and raw[0] == "Physician" and raw[7] == "CHRISTOPHER STALLTER" and raw[9] == "IL"
    key, raw = openpayments._recipient(c, ["2", "Covered Recipient Teaching Hospital", "14811", "", "", "", "", "", "COLUMBIA", "MO", "United States", "", ""])
    assert key == "h14811" and raw[0] == "Teaching hospital"


def test_gov_payroll_parsers():
    nyc = gov_payroll.p_nyc({"fiscal_year": "2025", "agency_name": "ADMIN FOR CHILDREN'S SVCS", "last_name": "BLANCO", "first_name": "ELMER",
                             "mid_init": "S", "title_description": "PROGRAM EVALUATOR", "base_salary": "95897.00", "pay_basis": "per Annum",
                             "regular_gross_paid": "89097.13", "total_ot_paid": "0.00", "total_other_pay": "699.41"})
    assert nyc["name"] == "BLANCO, ELMER S" and nyc["total"] == 89796.54 and nyc["base"] == 95897.0 and nyc["year"] == 2025
    assert gov_payroll.p_nyc({"agency_name": "COMMUNITY COLLEGE (BRONX)"}) is None          # the CUNY source has them
    chi = gov_payroll.p_chicago({"name": "AARON, KARINA", "job_titles": "POLICE OFFICER", "department": "CHICAGO POLICE DEPARTMENT",
                                 "full_or_part_time": "F", "salary_or_hourly": "HOURLY", "typical_hours": "40", "hourly_rate": "25"})
    assert chi["base"] == 52000.0 and chi["components"]["annualized_from_hourly"] == 25.0
    nj = gov_payroll.p_nj({"record_type": "DETAIL"})
    assert nj is None
    assert {s.key for s in gov_payroll.SOURCES} >= {"gov_nyc", "gov_nj", "gov_ma", "gov_fl", "gov_pa", "gov_il"}
    assert all(k.startswith("gov_") for k in gov_payroll.SOURCE_INFO)


def test_xlinks_urls_and_menu():
    from app import xlinks as xl
    assert xl.SOURCES["f5500_sponsor"][2]("123456789") == "/form5500/sponsor/123456789"
    assert xl.TARGETS["biz"][1]("NY:123", "x") == "/business/NY/123" and xl.TARGETS["person"][1]("5", "x") == "/person/5"
    assert "state=NY" in xl.SOURCES["payroll_person"][2]("NY:AGENCY:john q public")
    base = open("templates/base.html").read()
    for href in ("/pay", "/form5500", "/openpayments", "/fara"):
        assert f'<a href="{href}">' in base, href
    assert "Employers and pay" in base and "Health care" in base


def test_pages():
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    for path, h1 in [("/form5500", "Form 5500 plan sponsors"), ("/openpayments", "Open Payments"), ("/pay", "State and city payroll")]:
        r = c.get(path)
        if r.status_code == 404:        # not loaded on this database
            continue
        assert r.status_code == 200 and f"<h1>{h1}" in r.text, path
    assert c.get("/form5500/sponsor/abc").status_code == 404
    assert c.get("/openpayments/recipient/zzz").status_code == 404
    assert c.get("/pay/nope").status_code == 404
    assert c.get("/pay/search?q=smith&state=NY").status_code == 200
    more = c.get("/more").text
    assert '<a href="/pay">' in more and '<a href="/openpayments">' in more and '<a href="/form5500">' in more
