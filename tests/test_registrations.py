from app import registrations
from loader import registrations as lr


def test_search_links_go_to_the_official_sites():
    links = registrations.search_links("Jake Crowley")
    assert links["brokercheck"].startswith("https://brokercheck.finra.org/") and "Jake%20Crowley" in links["brokercheck"]
    assert links["iapd"].startswith("https://adviserinfo.sec.gov/")


def test_broker_dealer_list_reads_utf16_and_ascii():
    text = "0000001904\tABRAHAM SECURITIES CORPORATION\t00829452\t3724 47TH STREET CT\t\tGIG HARBOR\tWA\t98335\t"
    assert lr._bd_text(text.encode("utf-16")) == text
    assert lr._bd_text(text.encode("latin-1")) == text


def test_manager_roles_are_flagged():
    assert registrations.ROLE_RX.search("Managing Member of the General Partner")
    assert registrations.ROLE_RX.search("Promoter")
    assert not registrations.ROLE_RX.search("Director")
    assert registrations.NOT_ROLE_RX.search("Attorney of the General Partner")
