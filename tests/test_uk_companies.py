"""UK companies (loader/uk_companies.py, loader/uk_companies_xref.py, app/uk_companies.py, app/uk_company_boards.py; owner, 2026-11-14)."""

import io
import zipfile

from fastapi.testclient import TestClient

from app import uk_companies as app_ukco
from loader import uk_companies as uk


def test_parsing_helpers():
    assert uk.d_uk("11/09/2012") == "2012-09-11" and uk.d_uk("") is None and uk.d_uk("31/02/2020") is None
    assert uk.d_iso("2026-03-01T00:00:00Z") == "2026-03-01" and uk.d_iso("9999-12-31T00:00:00Z") is None and uk.d_iso(None) is None
    assert uk.intv(" 3 ") == 3 and uk.intv("") is None
    assert uk.txt(" a\x00b ") == "ab" and uk.txt("  ") is None


def test_postcode_region():
    assert uk.postcode_area("HG1 1ND") == "HG" and uk.postcode_area("EC1V 2NX") == "EC" and uk.postcode_area("") is None
    assert uk.AREA_REGION["HG"] == "Yorkshire and The Humber" and uk.AREA_REGION["EH"] == "Scotland" and uk.AREA_REGION["BT"] == "Northern Ireland"


def test_name_core_drops_uk_forms():
    assert uk.core_uk("ROLLS-ROYCE HOLDINGS PLC") == "rolls royce holdings"
    assert uk.core_uk("Acme Widgets Ltd.") == "acme widgets"
    assert uk.core_uk("!ABRIDGE TAX LTD") == "abridge tax"
    assert uk.norm_person("Michael", "Charles", "Saunders") == "michael charles saunders"


def _csv_zip() -> io.BytesIO:
    head = ("CompanyName, CompanyNumber,RegAddress.CareOf,RegAddress.POBox,RegAddress.AddressLine1, RegAddress.AddressLine2,RegAddress.PostTown,"
            "RegAddress.County,RegAddress.Country,RegAddress.PostCode,CompanyCategory,CompanyStatus,CountryOfOrigin,DissolutionDate,IncorporationDate,"
            "Accounts.AccountRefDay,Accounts.AccountRefMonth,Accounts.NextDueDate,Accounts.LastMadeUpDate,Accounts.AccountCategory,Returns.NextDueDate,"
            "Returns.LastMadeUpDate,Mortgages.NumMortCharges,Mortgages.NumMortOutstanding,Mortgages.NumMortPartSatisfied,Mortgages.NumMortSatisfied,"
            "SICCode.SicText_1,SICCode.SicText_2,SICCode.SicText_3,SICCode.SicText_4,LimitedPartnerships.NumGenPartners,LimitedPartnerships.NumLimPartners,"
            "URI,PreviousName_1.CONDATE, PreviousName_1.CompanyName,ConfStmtNextDueDate, ConfStmtLastMadeUpDate\n")
    row = ('"A, B LTD","08209948","","","9 PRINCES SQUARE","","HARROGATE","","ENGLAND","HG1 1ND","Private Limited Company","Active","United Kingdom","",'
           '"11/09/2012","30","9","30/06/2027","30/09/2025","DORMANT","","","0","0","0","0","99999 - Dormant Company","62020 - IT consultancy","","","0","0",'
           '"http://x","27/03/2026","OLD NAME LTD","25/09/2027","11/09/2026"\n')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("BasicCompanyDataAsOneFile-2026-11-01.csv", head + row)
    b.seek(0)
    return b


def test_basic_row_parsed(tmp_path):
    p = tmp_path / "basic.zip"
    p.write_bytes(_csv_zip().read())
    rows = list(uk._rows_basic(p))
    assert len(rows) == 1
    company, prev = rows[0]
    assert len(company) == len(uk.COMPANY_COLS)
    d = dict(zip(uk.COMPANY_COLS, company))
    assert d["company_number"] == "08209948" and d["name"] == "A, B LTD" and d["name_core"] == "a b"
    assert d["incorporated"] == "2012-09-11" and d["region"] == "Yorkshire and The Humber" and d["sic"] == ["99999", "62020"]
    assert d["sic_text"][1] == "IT consultancy" and d["previous_names"] == 1
    assert prev == [(1, "2026-03-27", "OLD NAME LTD")]


def test_psc_row_keeps_no_individual_address():
    ind = {"company_number": "08810260", "data": {"kind": "individual-person-with-significant-control", "name": "Mr Michael Charles Saunders",
           "name_elements": {"forename": "Michael", "middle_name": "Charles", "surname": "Saunders"}, "nationality": "British",
           "country_of_residence": "England", "date_of_birth": {"month": 8, "year": 1951}, "notified_on": "2016-04-06",
           "address": {"address_line_1": "1 Home Street", "postal_code": "HU10 7NY"}, "natures_of_control": ["ownership-of-shares-75-to-100-percent"],
           "links": {"self": "/company/08810260/persons-with-significant-control/individual/Q4obUUw"}}}
    r = dict(zip(uk.PSC_COLS, uk._psc_row(ind)))
    assert r["kind"] == "individual" and r["name_norm"] == "michael charles saunders" and r["birth_year"] == 1951 and r["psc_id"] == "Q4obUUw"
    assert r["addr_postcode"] is None and r["addr_country"] is None and r["addr_locality"] is None
    corp = {"company_number": "07434180", "data": {"kind": "corporate-entity-person-with-significant-control", "name": "Robert Hitchins Limited",
            "identification": {"registration_number": "00686734", "country_registered": "England & Wales"}, "address": {"country": "England"}}}
    c = dict(zip(uk.PSC_COLS, uk._psc_row(corp)))
    assert c["kind"] == "corporate-entity" and c["name_core"] == "robert hitchins" and c["reg_number"] == "00686734"


def test_us_state_names():
    assert uk._us_state("California") == "CA" and uk._us_state("tx") == "TX" and uk._us_state("Nowhere") is None


def test_attribution_is_the_licence_wording():
    assert app_ukco.ATTRIBUTION == ("Contains public sector information licensed under the Open Government Licence v3.0. Source: Companies House.")
    assert uk.ATTRIBUTION == app_ukco.ATTRIBUTION


def test_number_and_title_helpers():
    assert app_ukco.norm_number("1994") == "00001994" and app_ukco.norm_number("sc123456") == "SC123456" and app_ukco.norm_number("rolls royce") is None
    assert app_ukco.title_case("ROLLS-ROYCE HOLDINGS PLC") == "Rolls-Royce Holdings PLC"
    assert app_ukco.nature("voting-rights-25-to-50-percent").startswith("holds 25")


def test_nl_route():
    assert app_ukco.nl_route("UK companies named Rolls Royce") == "/uk/companies/search?q=Rolls%20Royce"
    assert app_ukco.nl_route("persons with significant control") == "/uk/companies"
    assert app_ukco.nl_route("charities in Texas") is None


def test_xlinks_kinds_and_boards_registered():
    from app import boards, xlinks
    assert "uk_company" in xlinks.SOURCES and "uk_psc" in xlinks.TARGETS
    assert xlinks.TARGETS["uk_psc"][1]("08210:abc", None) == "/uk/company/08210#psc"
    for s in ("uk-companies-new-by-sic", "uk-psc-networks", "uk-company-status-by-region"):
        assert s in boards.BY_SLUG and boards.BY_SLUG[s].group == "uk-companies"


def _client():
    from app import db
    from app.main import app
    db.pool.open(wait=False)
    return TestClient(app)


def test_menu_has_uk_companies_under_research_only():
    base = open("templates/base.html").read()
    research = base[base.index('nav-drop-head">Research'):base.index('nav-drop-head">By email')]
    assert '<a href="/uk/companies">UK companies</a>' in research and '<a href="/uk">UK charities</a>' in research
    assert base.count('href="/uk/companies"') == 1


def test_pages():
    c = _client()
    if not app_ukco.ready():
        assert c.get("/uk/companies").status_code == 404
        return
    r = c.get("/uk/companies")
    assert r.status_code == 200 and "Open Government Licence v3.0" in r.text and "wide contained" in r.text
    r = c.get("/uk/companies/search?q=rolls royce")
    assert r.status_code == 200
    assert c.get("/uk/company/notanumber").status_code == 404
    assert c.get("/uk/company/00000000").status_code == 404
    data = c.get("/data").text
    assert 'id="uk-companies"' in data and "Companies House" in data


def test_company_page_renders():
    c = _client()
    if not app_ukco.ready():
        return
    rows = app_ukco.search("rolls royce holdings", 3)
    if rows:
        r = c.get("/uk/company/" + rows[0]["company_number"])
        assert r.status_code == 200 and "People with significant control" in r.text and "Contains public sector information" in r.text
