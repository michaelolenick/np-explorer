from app import business
from loader import business_registry as br


def test_registry_links_fill_in_the_name_where_allowed():
    links = {l["state"]: l for l in business.registry_links("Acme Widgets")}
    assert links["MN"]["prefilled"] and "Acme%20Widgets" in links["MN"]["url"]
    assert links["DE"]["url"].startswith("https://icis.corp.delaware.gov/") and not links["DE"]["prefilled"]


def test_florida_dates_and_socrata_dates():
    assert str(br._date("03151999")) == "1999-03-15" and str(br._date("2015-03-02T00:00:00.000")) == "2015-03-02"


def test_coverage_note_wording():
    assert business.COVERAGE == ("FURP doesn" + chr(39) + "t yet include every registered business. Not finding a company "
                                 "here doesn" + chr(39) + "t mean it doesn" + chr(39) + "t exist.")
