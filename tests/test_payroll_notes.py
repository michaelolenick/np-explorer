"""Payroll notes: a published $0 shown as Not reported (staged row keeps $0), derived years, years not published."""

import pytest
from jinja2 import Environment, FileSystemLoader

from app.config import ROOT
from app.fmt import money_nr
from loader import colleges as L


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        c = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    yield c
    c.close()


def _row(conn, components: dict, pay=0, year=2025):
    import json
    return conn.execute(f"""
        SELECT CASE WHEN {L.ZERO} THEN NULL ELSE r.total_pay END AS shown_pay,
               CASE WHEN coalesce((r.pay_components->>'year_not_published')::boolean, false) THEN NULL
                    ELSE r.fiscal_year END AS shown_year,
               {L.PAY_NOTE} AS pay_note, {L.YEAR_NOTE} AS year_note, r.total_pay AS staged_pay
        FROM (SELECT %s::numeric AS total_pay, %s::int AS fiscal_year, %s::jsonb AS pay_components) r""",
        (pay, year, json.dumps(components))).fetchone()


def test_published_zero_is_not_reported_but_staged_zero_kept(conn):
    shown, year, pay_note, year_note, staged = _row(conn, {"source_published_zero": True}, pay=0)
    assert shown is None and staged == 0 and pay_note == "The source published $0" and year == 2025
    assert money_nr(shown) == "Not reported"
    shown, _, pay_note, _, _ = _row(conn, {}, pay=0)                 # a real $0 without the flag stays $0
    assert shown == 0 and pay_note is None and money_nr(shown) == "$0"


def test_derived_and_unpublished_years(conn):
    _, year, _, note, _ = _row(conn, {"year_derived": "pdf_creation_date"}, pay=50000, year=2027)
    assert year == 2027 and note == "Year derived from the PDF's creation date"
    _, year, _, note, _ = _row(conn, {"year_not_published": True}, pay=50000, year=2024)
    assert year is None and note == "Year not published"           # never guessed


def test_templates_show_the_notes():
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    env.filters["money_nr"] = money_nr
    env.globals["evidence_text"] = lambda ev: ""
    html = env.get_template("_person_payroll.html").render(payroll=[{
        "fiscal_year": None, "year_note": "Year not published", "unitid": 1, "institution": "X College", "label": "X",
        "title": "Instructor", "department": None, "total_pay": None, "pay_note": "The source published $0",
        "source_url": "https://example.org", "source_home": None, "source_title": "X list", "publisher": "X",
        "pay_basis": "Salary as published", "match": "EXACT", "evidence": {}}])
    assert "Year not published" in html and "Not reported" in html and "The source published $0" in html
    tpl = (ROOT / "templates" / "institution_payroll.html").read_text()
    assert "year=none" in tpl and "left out of the yearly totals" in tpl and "year derived" in tpl
