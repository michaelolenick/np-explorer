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


def test_monthly_report_links(monkeypatch):
    """Monthly adviser reports: the date comes from the name (mmddyy), odd suffixes included; reports before 2025
    (the bulk filing-data years) are left out."""
    import datetime as dt
    from loader import adv as L
    d = "/files/investment/data/other/information-about-registered-investment-advisers-exempt-reporting-advisers/"
    html = "".join(f'<a href="{d}{n}">x</a>' for n in ("ia100226.zip", "ia020226-exemptzip.zip", "ia010225_0.xlsx",
                                                        "ia120224.xlsx", "ia-no-data-110125.pdf"))
    monkeypatch.setattr(L, "_get", lambda url: html.encode())
    got = L.monthly_files()
    assert [(r, n) for r, n, _ in got] == [(dt.date(2025, 1, 2), "ia010225_0.xlsx"),
                                           (dt.date(2026, 2, 2), "ia020226-exemptzip.zip"),
                                           (dt.date(2026, 10, 2), "ia100226.zip")]
    assert got[-1][2] == "https://www.sec.gov" + d + "ia100226.zip"


def test_monthly_report_rows_and_zip_codes(tmp_path):
    import zipfile
    from loader import adv as L
    p = tmp_path / "ia100226.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("ia09012026.csv", "Organization CRD#,Latest ADV Filing Date,5F(2)(c)\n38,06/26/2026,"
                                     "\"   630,665,806.00\"\n")
    rows = list(L._report_rows(p))
    assert rows[0]["Organization CRD#"] == "38" and L._date(rows[0]["Latest ADV Filing Date"]).year == 2026
    assert L._num(rows[0]["5F(2)(c)"]) == 630665806
    assert L._postal("2110", "United States") == "02110"
    assert L._postal("SW1A 1AA", "United Kingdom") == "SW1A 1AA"
