"""Schools links to the student loan report (a live summary); student loan pages highlight Schools in the menu."""

import datetime as dt

from starlette.testclient import TestClient

from app import main, student_loans


def test_schools_links_to_student_loans(monkeypatch):
    monkeypatch.setattr(student_loans, "summary", lambda: {"trusts": 80, "families": 3, "live_balance": 12.34e9,
                                                           "data_through": dt.date(2026, 8, 1)})
    html = TestClient(main.app).get("/schools").text      # no `with`: keeps the shared pool open
    assert '<a href="/student-loans">Student loan securitization reports</a>' in html
    assert "80 SEC-registered student loan trusts from 3 issuer families" in html
    assert "$12.3 billion still owed" in html and "monthly data through August 2026" in html


def test_schools_says_nothing_before_data(monkeypatch):
    monkeypatch.setattr(student_loans, "summary", lambda: None)
    assert 'href="/student-loans"' not in TestClient(main.app).get("/schools").text


def test_student_loan_pages_sit_under_schools():
    html = TestClient(main.app).get("/student-loans").text
    assert '<a href="/schools" class="active" aria-current="page">Schools</a>' in html
    nav = html[html.index('class="site-nav"'):html.index("</nav>", html.index('class="site-nav"'))]
    assert "student-loans" not in nav                     # not a separate menu item


def test_summary_handles_database_numerics(monkeypatch):
    # Postgres sums come back as Decimal; the template divides by 1e9, so summary() must hand it a float.
    from decimal import Decimal
    monkeypatch.setattr(student_loans, "overview", lambda: {"trusts": [{}, {}], "issuers": [],
        "families": [{"live_balance": Decimal("4000000000.50")}, {"live_balance": None}]})
    monkeypatch.setattr(student_loans, "last_update", lambda: {"data_through": None})
    s = student_loans.summary()
    assert s["trusts"] == 2 and isinstance(s["live_balance"], float) and s["live_balance"] > 4e9
