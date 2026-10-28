"""The section order on person and org pages (app/sections.py): every key has its templates, the pages loop over the
list, the Form D totals line, and the "fund, VC or investor" check behind the no-Form-D note."""

from pathlib import Path

from app import sections

T = Path(__file__).resolve().parent.parent / "templates"


def test_form_d_comes_first_and_every_section_has_a_template():
    assert sections.SECTION_ORDER[:4] == ["form_d", "adv", "insider", "990"]
    assert len(set(sections.SECTION_ORDER)) == len(sections.SECTION_ORDER)
    for key in sections.SECTION_ORDER:
        assert (T / "_sections" / f"person_{key}.html").exists(), key
        if key != "insider":                       # organizations file no Form 4
            assert (T / "_sections" / f"org_{key}.html").exists(), key
    for page in ("person.html", "org.html"):
        assert "sections.SECTION_ORDER" in (T / page).read_text()


def test_formd_totals_with_no_rows():
    assert sections.formd_totals([]) == {"filings": 0, "offerings": 0, "spvs": 0, "sold": None}


def test_fund_like():
    for yes in ("Managing Partner", "Acme Ventures LLC", "Example Fund II, L.P.", "Angel investor", "Venture Partner"):
        assert sections.fund_like(yes), yes
    for no in ("Executive Director", "Scholarship Fund of Ohio", "Director of Investor Relations", "Treasurer", None):
        assert not sections.fund_like(no), no
    assert sections.fund_like(["Trustee", "General Partner"])
