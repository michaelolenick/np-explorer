"""Parser tests against real IRS filings: each form type in both schema eras.

Fixtures (tests/fixtures/*.xml.gz) are unmodified public e-file returns:
  2009v1.3  990, 990-EZ         2011v1.2  990-PF       (pre-2013 element names)
  2013v4.0  990-PF   2014v6.0  990   2015v2.1  990-EZ  (2013+ element names)
  2024v5.2  990, 990-EZ, 990-PF                        (current; not yet in KNOWN_VERSIONS when first seen)
  2021v4.0  990 with Schedules D (donor-advised funds), I (grants) and L (loans)
  2025v4.1  990 of a volunteer-run charity (no pay; spending mostly on events)
"""

import gzip
from datetime import date
from pathlib import Path

import pytest

from loader import mapping
from loader.parser import parse

FIX = Path(__file__).parent / "fixtures"


def load(oid):
    return parse(gzip.open(FIX / f"{oid}.xml.gz").read(), oid)


def person(r, name):
    return next(p for p in r["people"] if p["name_raw"] == name)


def test_era_detection():
    assert mapping.era_for("2009v1.3") == ("v2009", True)
    assert mapping.era_for("2012v2.3") == ("v2009", True)
    assert mapping.era_for("2013v4.0") == ("v2013", True)
    assert mapping.era_for("2031v1.0") == ("v2013", False)   # unknown future version: parsed, flagged
    assert mapping.era_for("garbage") == ("unknown", False)


def test_990_v2009():
    r = load("201100129349300655")
    f = r["filing"]
    assert (f["form_type"], f["return_version"], f["ein"], f["tax_year"]) == ("990", "2009v1.3", "382406558", 2009)
    assert f["total_revenue"] == 14795929
    assert f["total_assets_eoy"] == 13179418
    assert f["net_assets_eoy"] == 9808782
    assert f["num_employees"] == 182
    assert r["warnings"] == []
    p = person(r, "ARCHIE LEFLORE")
    assert p["title"] == "SECRETARY" and p["avg_hours"] == 2.0
    assert p["is_director"] and not p["is_officer"]
    assert (p["comp_org"], p["comp_related"], p["other_comp"]) == (0, 0, 0)
    assert person(r, "REV BERRY GOODLETT")["name_norm"] == "berry goodlett"
    assert len(r["people"]) == 18
    assert len(r["contractors"]) == 4
    assert len(r["schedule_j"]) == 1


def test_990_v2013():
    r = load("201600119349300520")
    f = r["filing"]
    assert (f["form_type"], f["return_version"], f["ein"], f["tax_year"]) == ("990", "2014v6.0", "590711167", 2014)
    assert f["total_revenue"] == 37612695
    assert f["total_assets_eoy"] == 31453321
    assert f["net_assets_eoy"] == 23230840
    assert f["num_employees"] == 826
    p = person(r, "RICHARD KINZER")
    assert p["title"] == "BOARD PRESIDENT"
    assert p["is_director"] and p["is_officer"]
    c = next(c for c in r["contractors"] if c["name_raw"] == "COVENTRY HEALTH CARE")
    assert (c["city"], c["state"], c["zip"]) == ("BETHESDA", "MD", "20817")
    assert c["service_description"] == "HEALTH INSURANCE"
    sj = next(s for s in r["schedule_j"] if s["name_raw"] == "DRSTEVEN RONIK")
    assert sj["base_org"] == 281553 and sj["deferred_org"] == 11417 and sj["nontaxable_org"] == 29513
    assert sj["base_related"] == 0
    assert {x["related_ein"] for x in r["related"]} == {"201295515", "592533533"}


def test_990_current_version():
    r = load("202502739349301000")
    f = r["filing"]
    assert (f["return_version"], f["ein"], f["tax_year"]) == ("2024v5.2", "136783346", 2024)
    assert f["total_revenue"] == 42822567 and f["total_assets_eoy"] == 45576999
    assert f["num_employees"] == 0
    p = person(r, "MARK COLLINS")
    assert p["title"] == "UNION TRUSTEE" and p["is_director"]


def test_990ez_v2009():
    r = load("201100129349200280")
    f = r["filing"]
    assert (f["form_type"], f["ein"], f["tax_year"], f["total_revenue"]) == ("990EZ", "840774207", 2009, 36802)
    p = person(r, "MIKE GALLI")
    assert p["title"] == "PRESIDENT" and p["avg_hours"] == 1.0 and p["comp_org"] == 0
    assert p["is_officer"]            # 990-EZ has no checkboxes; inferred from the title


def test_990ez_v2013():
    r = load("202502749349200235")
    f = r["filing"]
    assert (f["form_type"], f["ein"], f["tax_year"], f["total_revenue"]) == ("990EZ", "237051966", 2024, 125287)
    p = person(r, "SCOTT CAMERON MD")
    assert p["name_norm"] == "scott cameron" and p["avg_hours"] == 4.0
    c = next(c for c in r["contractors"] if c["name_raw"] == "CAMERLENGO AND ASSOC")
    assert (c["city"], c["state"], c["service_description"], c["compensation"]) == ("WAKEFIELD", "MA", "ACCOUNTING", 1610)
    assert load("201600089349200000")["filing"]["return_version"] == "2015v2.1"


def test_990pf_v2009():
    r = load("201300079349100105")
    f = r["filing"]
    assert (f["form_type"], f["return_version"], f["ein"], f["tax_year"]) == ("990PF", "2011v1.2", "203199483", 2011)
    assert f["total_revenue"] == 76535
    p = person(r, "MARJORIE W DRACKETT")
    assert p["title"] == "PRESIDENT" and p["comp_org"] == 0
    assert (p["street"], p["city"], p["state"], p["zip"]) == ("100 GLENVIEW PLACE 1102", "NAPLES", "FL", "34108")


def test_990pf_v2013():
    r = load("202502699349100415")
    f = r["filing"]
    assert (f["form_type"], f["ein"], f["tax_year"], f["total_revenue"]) == ("990PF", "980453795", 2024, 110732224)
    p = person(r, "Adrienne Kelly")
    assert p["comp_org"] == 203567 and p["avg_hours"] == 37.5 and p["city"] == "MONTREAL"
    assert any(c["name_raw"] == "BURGUNDY ASSET MANAGEMENT" and c["city"] == "TORONTO" for c in r["contractors"])
    assert all(x["related_ein"] != "999999999" for x in r["related"])   # placeholder EINs dropped
    assert load("201500099349100350")["filing"]["return_version"] == "2013v4.0"


@pytest.mark.parametrize("oid", [p.name[:18] for p in FIX.glob("*.xml.gz")])
def test_every_fixture_parses_cleanly(oid):
    r = load(oid)
    f = r["filing"]
    assert f["form_type"] in mapping.FORMS
    assert len(f["ein"]) == 9 and f["tax_year"] and isinstance(f["tax_period_end"], date)
    assert f["total_revenue"] is not None
    assert r["people"], "every fixture lists at least one person"
    assert all(p["name_norm"] for p in r["people"])


def test_non_990_forms_are_skipped():
    xml = b'<Return xmlns="http://www.irs.gov/efile" returnVersion="2023v6.0"><ReturnHeader><ReturnTypeCd>990T</ReturnTypeCd></ReturnHeader></Return>'
    assert parse(xml, "1") is None


def test_rows_with_unusable_names_are_dropped():
    # A real 2022 filing had a Schedule J row named just "'" (normalizes to nothing).
    xml = (b'<Return xmlns="http://www.irs.gov/efile" returnVersion="2021v4.2"><ReturnHeader>'
           b'<ReturnTypeCd>990</ReturnTypeCd><Filer><EIN>821820277</EIN></Filer><TaxYr>2020</TaxYr></ReturnHeader>'
           b'<ReturnData><IRS990><ContractorCompensationGrp><ContractorName><BusinessName>'
           b'<BusinessNameLine1Txt>--</BusinessNameLine1Txt></BusinessName></ContractorName></ContractorCompensationGrp>'
           b'</IRS990><IRS990ScheduleJ><RltdOrgOfficerTrstKeyEmplGrp><PersonNm>\'</PersonNm>'
           b'<BaseCompensationFilingOrgAmt>0</BaseCompensationFilingOrgAmt></RltdOrgOfficerTrstKeyEmplGrp>'
           b'</IRS990ScheduleJ></ReturnData></Return>')
    r = parse(xml, "1")
    assert r["schedule_j"] == [] and r["contractors"] == [] and r["people"] == []


def test_fundraising_expenses():
    # Part I line 16b (Part IX column D): both eras; not on the 990-EZ or 990-PF.
    assert load("201600119349300520")["filing"]["fundraising_expenses"] == 148000
    assert load("201100129349300655")["filing"]["fundraising_expenses"] == 0
    assert load("201600089349200000")["filing"]["fundraising_expenses"] is None


def test_pf_grants_and_payout_v2009():
    r = load("201300079349100105")
    g = r["grants"][0]
    assert (g["source"], g["recipient_name"], g["city"], g["state"], g["cash_amount"]) == (
        "990PF-XV", "ARTSWAVE", "CINCINNATI", "OH", 5500)
    assert len(r["grants"]) == 11 and r["pf_payout"]["noncharitable_assets"] is not None


def test_pf_grant_to_individual_keeps_no_name():
    g = next(x for x in load("201500099349100350")["grants"] if x["recipient_is_person"])
    assert g["recipient_name"] is None and g["recipient_name_norm"] is None and g["cash_amount"] == 120000


def test_pf_payout_v2013():
    p = load("202502699349100415")["pf_payout"]
    assert (p["noncharitable_assets"], p["min_investment_return"], p["qualifying_distributions"]) == (
        1504304951, 75215248, 92320127)


def test_daf_flag_answered_no():
    d = load("202502739349301000")["daf"]
    assert d["maintains_dafs"] is False and d["daf_count"] is None
    assert load("201300079349100105")["daf"] is None     # not asked on the 990-PF


def test_schedule_i_d_l_v2013():
    # A 2021 Form 990 (2021v4.0) from a community foundation: Schedule I grants, Schedule D Part I, Schedule L.
    r = load("202233199349323138")
    assert r["daf"] == {"maintains_dafs": True, "daf_count": 32, "daf_contributions": 9056925,
                        "daf_grants": 5511554, "daf_value_eoy": 42184831, "other_count": 2,
                        "other_contributions": None, "other_grants": 25600, "other_value_eoy": 359305}
    g = r["grants"][0]
    assert (g["source"], g["recipient_name"], g["recipient_ein"], g["state"], g["cash_amount"], g["irc_section"]) == (
        "990-I", "BISHOP WARD HIGH SCHOOL", "480559094", "KS", 100000, "501C3")
    assert len(r["grants"]) == 16
    loan = r["loans"][0]
    assert (loan["original_principal"], loan["balance_due"], loan["from_org"], loan["in_default"],
            loan["board_approved"]) == (500000, 209783, True, False, True)


def test_expenses_990_events_and_zero_pay():
    # REDM Inc, tax year 2025 (2025v4.1): volunteers only; most spending is events.
    e = load("202641359349312124")["expenses"]
    assert (e["total_expenses"], e["pay_total"], e["grants_total"], e["event_lines_total"]) == (545207, 0, 10501, 479469)
    ev = next(ln for ln in e["lines"] if ln[2] == "EVENT EXPENDITURES")
    assert ev[0] == "other" and ev[3:7] == [479469, 100000, None, 379469] and ev[7] is True
    assert not next(ln for ln in e["lines"] if ln[2] == "MERCHANT BANK FEES")[7]


def test_expenses_ez_and_pf():
    ez = load("202502749349200235")["expenses"]
    assert ez["total_expenses"] == 118759 and ["fees_contractors", "Fees to independent contractors", None,
                                               116100, None, None, None, False] in ez["lines"]
    pf = load("202502699349100415")["expenses"]
    assert (pf["total_expenses"], pf["grants_total"], pf["pay_total"]) == (97892412, 86636735, 4500922)


def test_expenses_v2009():
    e = load("201100129349300655")["expenses"]
    assert e["total_expenses"] == 12407882 and e["pay_total"] == 8569294
    other = next(ln for ln in e["lines"] if ln[2] == "IN-KIND SERVICES")
    assert other[3] == 985656 and other[7] is False
