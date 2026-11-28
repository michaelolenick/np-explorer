from pathlib import Path


def test_org_page_has_the_donor_line_once():
    t = Path(__file__).resolve().parent.parent.joinpath("templates", "org.html").read_text()
    assert t.count("Reduce your risk when donating") == 1
