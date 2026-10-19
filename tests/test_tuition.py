"""Average tuition (NCES Digest Table 330.10): parsing, the summary and the section on the student loan pages."""

import pytest
from starlette.testclient import TestClient

from app import main, tuition
from loader import tuition as loader


def _rows():
    hdr = [["Table 330.10. Average undergraduate tuition..."],
           ["Academic year and control of institution", "Current dollars"] + [None] * 11 + ["Constant 2023-24 dollars\\1\\"],
           [None] * 25, [None] * 25, [str(i) for i in range(1, 26)]]

    def yr(label, cur, const):
        r = [label] + ["1,000", "1,100", "800", cur, "1", "2"] + ["0"] * 6 + ["9,000", "9,100", "8,000", const, "3", "4"] + [""] * 6
        return r
    return hdr + [["All institutions"] + [""] * 24, yr("1976-77 ", "$500", "$2,000"), yr("2023-24", "8,000", "8,000"),
                  ["\nPublic institutions"] + [""] * 24, yr("1985-86\\5\\ ", "400", "1,500"),
                  ["  \n    Nonprofit"] + [""] * 24, yr("    2003-04 ", "18,000", "30,000")]


def test_parse_rows():
    rows, base = loader.parse_rows(_rows())
    assert base == "2023-24"
    got = {(r["control"], r["level"], r["year_start"]): r for r in rows}
    assert len(rows) == 12                                # 4 year rows x 3 levels
    a = got[("all", "all", 1976)]
    assert a["academic_year"] == "1976-77" and a["tuition_fees_current"] == 500 and a["tuition_fees_constant"] == 2000
    assert got[("public", "all", 1985)]["academic_year"] == "1985-86"          # footnote marker removed
    assert ("private_nonprofit", "4-year", 2003) in got
    assert loader._num("---") is None and loader._num("") is None and loader._num("$1,248") == 1248.0


def test_parse_rejects_a_table_without_constant_dollars():
    with pytest.raises(ValueError):
        loader.parse_rows([["Table"], ["Academic year", "Current dollars"]])


def test_section_on_student_loan_pages(monkeypatch):
    fake = {"line": "8,150 632,10", "w": 640, "h": 160, "marks": [{"x": 300.0, "label": "1976", "text": "t"}],
            "first": "1963-64", "last": "2023-24", "low": 5000.0, "high": 9000.0, "base": "2023-24", "edition": 2024,
            "source_url": "https://nces.ed.gov/programs/digest/d24/tables/xls/tabn330.10.xlsx",
            "controls": tuition.CONTROLS, "events": tuition.EVENTS, "now_current": 8125.0,
            "table": [{"start": 1976, "label": "1976-77", "cells": [{"then": 2000.0, "now": 8000.0, "pct": 300.0,
                                                                     "then_current": 500.0}, None, None]}]}
    monkeypatch.setitem(main.templates.env.globals, "tuition_summary", lambda: fake)
    client = TestClient(main.app)          # no `with`: keeps the shared pool open
    for path in ("/schools/student-loans", "/student-loans"):
        html = client.get(path).text
        assert "Tuition since student loans stopped going away in bankruptcy" in html, path
        assert "+300%" in html and "$2,000 to $8,000" in html and "Education Amendments of 1976" in html
        assert "dt24_330.10.asp" in html


def test_section_hidden_without_data(monkeypatch):
    monkeypatch.setitem(main.templates.env.globals, "tuition_summary", lambda: None)
    assert "Tuition since student loans" not in TestClient(main.app).get("/schools/student-loans").text


def test_four_digit_year_end():
    assert loader._YEAR.match("1999-2000 ").group(0) == "1999-2000"
    assert loader._YEAR.match("1976-77 ").group(0) == "1976-77"
