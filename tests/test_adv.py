from app import adv


def test_chart_years_and_form_d_dots():
    years = [{"year": 2020, "gav": 10_000_000, "owners": 50}, {"year": 2022, "gav": 5_000_000, "owners": 40}]
    c = adv.chart(years, {2021: 8_000_000})
    assert [b["year"] for b in c["value"]] == [2020, 2022]          # no bar for the year with no ADV report
    assert [l["year"] for l in c["labels"]] == [2020, 2021, 2022]
    assert c["dots"][0]["year"] == 2021
    tallest = min(b["y"] for b in c["value"])
    assert tallest == c["value"][0]["y"]                             # the peak year has the tallest bar


def test_chart_empty():
    assert adv.chart([], {}) is None


def test_person_name_order():
    from loader.adv import _person
    assert _person("SMITH, JOHN, A") == _person("John A Smith")


def test_iapd_link():
    assert adv.iapd("291058") == "https://adviserinfo.sec.gov/firm/summary/291058"


def test_no_circle_for_zero_form_d_sales():
    c = adv.chart([{"year": 2022, "gav": 1e8, "owners": 30}], {2020: 0.0})
    assert c["dots"] == [] and c["no_sales"]


def test_exemptions_in_plain_english():
    from app.corporate import exemptions_plain
    assert exemptions_plain("06b, 3C, 3C.1, 3C.7") == ("Private offering, no general advertising (Rule 506(b)); "
                                                       "Investment company exemption (3(c)); Fund under 100 investors (3(c)(1)); "
                                                       "Qualified purchasers only (3(c)(7))")
    assert exemptions_plain("06c") == "Private offering, advertising allowed, accredited only (Rule 506(c))"
