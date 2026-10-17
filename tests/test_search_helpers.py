"""Search helpers that need no database."""

from app.main import _EIN, _ORG_SUFFIX
from app.queries import sound_query


def test_sound_query_skips_numbers():
    # An EIN or number has no sound code; an empty term made an invalid tsquery (a 500).
    assert sound_query(["86", "1821217"]) == ""
    assert sound_query(["redm", "1821217"]) == "r350"


def test_ein_pattern():
    assert _EIN.match("86-1821217") and _EIN.match(" 861821217 ")
    assert not _EIN.match("8618212") and not _EIN.match("redm")


def test_org_suffix():
    assert _ORG_SUFFIX.sub("", "redm inc") == "redm"
    assert _ORG_SUFFIX.sub("", "ford foundation") == "ford"


def test_expense_view_and_pay_summary():
    from app.queries import _expense_view, _pay_summary
    e = _expense_view({"form_type": "990", "total_expenses": 1000, "event_lines_total": 600, "special_event_expenses": 50,
                       "conferences_total": None, "lines": [["total", "Total", None, 1000, None, None, None, False],
                                                            ["other", "Other", "GALA", 600, None, None, 600, True],
                                                            ["office", "Office", None, 400, 400, None, None, False]]})
    assert [ln["desc"] for ln in e["detail"]] == ["GALA", None] and e["events"] == 650
    assert e["detail"][0]["share"] == 0.6
    people = [{"tax_year": 2025, "total": 0, "superseded": False}, {"tax_year": 2025, "total": 0, "superseded": False},
              {"tax_year": 2024, "total": 5000, "superseded": False}, {"tax_year": 2024, "total": 9, "superseded": True}]
    filings = [{"tax_year": 2025, "num_employees": 0, "num_volunteers": 200, "superseded": False}]
    s = _pay_summary(people, filings)
    assert s[2025] == {"listed": 2, "paid": 0, "total": 0, "employees": 0, "volunteers": 200}
    assert s[2024] == {"listed": 1, "paid": 1, "total": 5000}
