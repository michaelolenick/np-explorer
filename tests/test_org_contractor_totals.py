"""Organization page: a contractor with no reported amount must not break the year's total (it did: int + None)."""

import re
from decimal import Decimal
from pathlib import Path

from app import main

SRC = (Path(__file__).resolve().parent.parent / "templates" / "org.html").read_text()
LINE = next(l for l in SRC.splitlines() if "contractor{{" in l and "<summary>" in l)


def _render(cs):
    return main.templates.env.from_string(LINE).render(year=2023, cs=cs)


def test_blank_amounts_are_skipped_not_zero():
    out = _render([{"compensation": Decimal("150000")}, {"compensation": None}])
    assert "$150K" in out or "150,000" in out or "$150" in out
    assert "some amounts not reported" in out


def test_all_blank_says_not_reported():
    assert "Not reported" in _render([{"compensation": None}])


def test_all_reported_has_no_note():
    out = _render([{"compensation": 100}, {"compensation": Decimal("50")}])
    assert "not reported" not in out.lower()
