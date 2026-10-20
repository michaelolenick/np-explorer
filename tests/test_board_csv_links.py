"""Board CSVs: rows without a page of their own (payroll-only people) still export."""

from app import boards
from app import main


def test_row_without_subject_page_exports():
    b = boards.BY_SLUG["uni-top-paid"]
    row = {"rank": 1, "subject_name": "Name withheld", "subject_url": None, "subject_kind": "payroll", "value": 200000,
           "tax_year": 2024, "filing_id": None}
    out = main._row_out(b, row, "fiscal years 2010 to 2025")
    assert out["subject_url"] is None and out["filing_url"] is None and out["value"] == 200000
    linked = main._row_out(b, {**row, "subject_url": "/person/5"}, "w")
    assert linked["subject_url"].endswith("/person/5")
