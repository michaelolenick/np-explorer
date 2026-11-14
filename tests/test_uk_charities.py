"""UK charities (loader/uk_charities.py, loader/uk_xref.py, app/uk_charities.py, app/uk_boards.py; owner, 2026-11-14)."""

import io
import zipfile

from loader import uk_charities as uk


def test_parsing_helpers():
    assert uk.d10("2026-11-14 00:00:00.0000000") == "2026-11-14" and uk.d10("") is None and uk.d10("n/a") is None
    assert uk.num("1484700000") == "1484700000" and uk.num("") is None and uk.num("abc") is None
    assert uk.intv("12.0") == "12" and uk.intv("") is None
    assert uk.boo("True") == "t" and uk.boo("False") == "f" and uk.boo("") is None
    assert uk.txt("  a\x00b ") == "ab" and uk.txt("   ") is None


def test_postcode_area_and_region():
    assert uk.postcode_area("OX4 2JY") == "OX" and uk.postcode_area("SW1A 1AA") == "SW" and uk.postcode_area("M1 1AE") == "M"
    assert uk.postcode_area("") is None and uk.postcode_area("nonsense") is None
    assert uk.region_of("OX") == "South East" and uk.region_of("SW") == "London" and uk.region_of("CF") == "Wales"
    assert uk.region_of("ZZ") is None


def test_trustee_name_normalisation_matches_us_names():
    assert uk.norm_person("Dr Hilary COTTAM") == "hilary cottam"
    assert uk.norm_person("LADY TRISH MALLOCH-BROWN") == "trish malloch brown"
    assert uk.norm_person("Mr. John O'Neill") == "john oneill"
    assert uk.norm_person("Rt Rev Paul Hendricks") == "paul hendricks"


def _zip(rows: str) -> io.BytesIO:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("publicextract.charity_trustee.txt", rows)
    b.seek(0)
    return b


def test_read_rows_joins_broken_lines(tmp_path):
    header = "a\tb\tc"
    text = f"﻿{header}\r\n1\tone\ttwo\r\n2\tbroken\r\nline\tthree\r\n3\tx\ty\tstray\r\n"
    p = tmp_path / "t.zip"
    p.write_bytes(_zip(text).getvalue())
    rows = list(uk.read_rows(p, "charity_trustee"))
    assert [r["a"] for r in rows] == ["1", "2", "3"]
    assert rows[1]["b"] == "broken line" and rows[1]["c"] == "three"
    assert rows[2]["c"] == "y stray"


def test_charity_row_and_tables_line_up():
    r = {k: "" for k in ["organisation_number", "registered_charity_number", "linked_charity_number", "charity_name", "charity_type",
                         "charity_registration_status", "date_of_registration", "date_of_removal", "charity_reporting_status",
                         "latest_acc_fin_period_start_date", "latest_acc_fin_period_end_date", "latest_income", "latest_expenditure",
                         "charity_contact_address1", "charity_contact_address2", "charity_contact_address3", "charity_contact_address4",
                         "charity_contact_address5", "charity_contact_postcode", "charity_contact_phone", "charity_contact_email",
                         "charity_contact_web", "charity_company_registration_number", "charity_insolvent", "charity_in_administration",
                         "charity_previously_excepted", "charity_is_cdf_or_cif", "charity_is_cio", "cio_is_dissolved",
                         "date_cio_dissolution_notice", "charity_activities", "charity_gift_aid", "charity_has_land"]}
    r.update(organisation_number="1", registered_charity_number="202918", linked_charity_number="0", charity_name="OXFAM",
             charity_registration_status="Registered", latest_income="339366903", charity_contact_postcode="OX4 2JY")
    row = uk.row_charity(r)
    assert len(row) == len(_cols("uk.charity")) and row[2] == "0" and row[4] == "oxfam" and row[12] == "339366903"


def _cols(table):
    ddl = uk.DDL[uk.DDL.index(f"CREATE TABLE IF NOT EXISTS {table} ("):]
    ddl = ddl[:ddl.index(");")]
    return [c.strip().split(" ")[0] for c in ddl.split("(", 1)[1].replace("\n", " ").split(",") if c.strip()]


def test_partb_row_width_matches_ddl():
    cols = _cols("uk.partb")
    r = {k: "" for k in ["organisation_number", "registered_charity_number", "latest_fin_period_submitted_ind", "ar_cycle_reference",
                         "fin_period_start_date", "fin_period_end_date"] + [k for k, _ in uk.PARTB_MAP]}
    assert len(uk.row_partb(r)) == len(cols)
    ra = {k: "" for k in ["organisation_number", "registered_charity_number", "latest_fin_period_submitted_ind", "ar_cycle_reference",
                          "fin_period_start_date", "fin_period_end_date", "total_gross_income", "total_gross_expenditure",
                          "charity_raises_funds_from_public", "charity_professional_fundraiser", "charity_commercial_participator",
                          "grant_making_is_main_activity", "charity_receives_govt_funding_contracts", "count_govt_contracts",
                          "charity_receives_govt_funding_grants", "count_govt_grants", "income_from_government_contracts",
                          "income_from_government_grants", "charity_has_trading_subsidiary", "does_trustee_receive_any_benefit",
                          "trustee_payments_acting_as_trustee", "trustee_receives_payments_services", "employees_salary_over_60k",
                          "count_volunteers", "count_salary_band_60001_70000", "count_salary_band_over_500000"]}
    ra["count_salary_band_60001_70000"], ra["count_salary_band_over_500000"] = "3", "1"
    row = uk.row_parta(ra)
    assert len(row) == len(_cols("uk.parta")) and row[-2] == "4"


def test_xref_name_rules_are_sql_safe():
    from loader import uk_xref
    assert uk_xref.SUFFIX_US.split("|")[0] == "usa" and "uk" in uk_xref.SUFFIX_UK.split("|")
    assert "facebook.com" in uk_xref.DOMAIN_BLOCK and "wordpress.com" in uk_xref.DOMAIN_BLOCK


def test_attribution_text_is_the_licence_wording():
    from app import uk_charities as pages
    assert pages.ATTRIBUTION == ("Contains public sector information licensed under the Open Government Licence v3.0. "
                                 "Source: Charity Commission for England and Wales.")
    assert uk.ATTRIBUTION == pages.ATTRIBUTION


def test_formatting_and_nl_route():
    from app import uk_charities as pages
    assert pages.gbp(1234567) == "£1,234,567" and pages.gbp(None) == "Not reported" and pages.gbp(-5) == "-£5"
    assert pages.short_gbp(1_484_700_000) == "£1.5bn" and pages.short_gbp(250_000) == "£250k"
    assert pages.title_case("THE BRITISH COUNCIL") == "The British Council" and pages.title_case("Kiln Theatre") == "Kiln Theatre"
    assert pages.title_case("OXFAM (UK) LTD").startswith("Oxfam (UK)")
    assert pages.nl_route("UK charities named oxfam") == "/uk/search?q=oxfam"
    assert pages.nl_route("charity commission") == "/uk"
    assert pages.nl_route("highest paid hospital executives in Ohio") is None


def test_menu_has_uk_charities_under_research_and_nothing_else_changed():
    base = open("templates/base.html").read()
    research = base[base.index('nav-drop-head">Research'):base.index('nav-drop-head">By email')]
    assert '<a href="/uk">UK charities</a>' in research
    for kept in ("/deep", "/nearby", "/how-to-spot-a-fake", "/dreamer", "/categories"):
        assert f'href="{kept}"' in research
    assert '("/more", "Research"), ("/boards", "Leaderboards"), ("/about", "About"), ("/support", "Support FURP")' in base


def test_boards_are_registered():
    from app import boards
    slugs = [b.slug for b in boards.BOARDS if b.group == "uk"]
    for s in ("uk-largest-income", "uk-most-trustees", "uk-fastest-growing", "uk-with-us-counterpart", "uk-income-by-region"):
        assert s in slugs, s
    assert "uk" in boards.GROUPS
    assert boards.fmt(1234, "gbp") == "£1,234" and "gbp" in boards.NUMERIC


def test_xlinks_kinds():
    from app import xlinks
    assert xlinks.SOURCES["uk_charity"][2]("202918") == "/uk/charity/202918"
    assert xlinks.SOURCES["uk_trustee"][2]("12") == "/uk/trustee/12"
    assert "uk_charity" in xlinks.TARGETS


def test_pages():
    from app import uk_charities as pages
    if not pages.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    hub = c.get("/uk")
    if hub.status_code == 404:          # tables not loaded on this database
        return
    assert "<h1>UK charities</h1>" in hub.text and "Open Government Licence v3.0" in hub.text
    assert '<body class="wide contained">' in hub.text
    s = c.get("/uk/search?q=oxfam")
    assert s.status_code == 200 and "/uk/charity/202918" in s.text
    ch = c.get("/uk/charity/202918")
    assert ch.status_code == 200 and "<h1>Oxfam</h1>" in ch.text
    assert "Contains public sector information licensed under the Open Government Licence v3.0" in ch.text
    assert '<body class="wide contained">' in ch.text and ">UK charities<" in ch.text        # the same width and the same menu
    assert c.get("/uk/charity/abc").status_code == 404 and c.get("/uk/charity/99999999").status_code == 404
    assert c.get("/uk/trustee/abc").status_code == 404
    srch = c.get("/search?q=oxfam&type=name")
    assert srch.status_code == 200 and "UK charities (England and Wales)" in srch.text
    red = c.get("/search?q=UK+charities+named+oxfam", follow_redirects=False)
    assert red.status_code == 302 and red.headers["location"].startswith("/uk/search")
    assert 'href="/uk"' in c.get("/more").text
    data = c.get("/data").text
    assert 'id="uk-charities"' in data and "Open Government Licence v3.0" in data


def test_org_and_person_blocks_render_without_matches():
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    r = c.get("/org/943242767")
    assert r.status_code == 200
