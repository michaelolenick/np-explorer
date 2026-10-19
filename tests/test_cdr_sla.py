"""Federal cohort default rates on school pages, the weekly student loan refresh, its notices, and the front page."""

import contextlib
import os
import uuid

import pytest
from jinja2 import Environment, FileSystemLoader

from app import boards as B
from app import colleges
from app.config import ROOT


def test_pct_and_not_reported():
    assert B.fmt(0.8, "pct?") == "0.8%" and B.fmt(None, "pct?") == "Not reported" and B.fmt(0, "pct?") == "0.0%"
    b = B.BY_SLUG["schools"]
    assert "cdr_rate" in B.sortable(b)
    assert any(c.label == colleges.CDR_LABEL for c in b.columns)


def _env():
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    return env


def test_coverage_notice_says_what_is_missing():
    from datetime import date, datetime
    env = _env()
    env.globals["sl_last_update"] = lambda: {"last_ok": datetime(2026, 10, 17, 3, 40), "data_through": date(2026, 8, 1),
                                             "failed": {"started_at": datetime(2026, 10, 24, 3, 0), "message": "x"}}
    html = env.get_template("_sl_coverage.html").render()
    for words in ("Only some trusts report continuously", "Rule 144A", "municipal issuers", "EMMA",
                  "no loan-level data and no school-level data", "Last updated 2026-10-17", "August 2026",
                  "did not finish", "Federal cohort default rates"):
        assert words in html, words


def test_front_page_text():
    html = (ROOT / "templates" / "index.html").read_text()
    # Owner's copy, 2026-10-19
    assert "<strong>The records are public. The picture isn't.</strong>" in html
    assert "Every salary, grant and gala sits in a filing somewhere. Connecting them takes hours, so nobody does." in html
    assert ("We did. Type a name, a school, a charity or a plain question. We'll show who they are, who pays them "
            "and who's paying for it, every number linked to its filing.") in html
    assert ("Public records are everywhere. We connect the people, the pay and the money behind nonprofits and "
            "schools, with every number linked to its filing.") in html
    assert "We saw a problem." not in html and "We're fixing the problem" not in html


@pytest.fixture(scope="module")
def db():
    psycopg = pytest.importorskip("psycopg")
    from app.config import DATABASE_URL
    try:
        conn = psycopg.connect(DATABASE_URL, connect_timeout=5, autocommit=True)
    except Exception:  # noqa: BLE001
        pytest.skip("no database")
    schema = f"cdr_test_{os.getpid()}_{uuid.uuid4().hex[:6]}"
    conn.execute(f"CREATE SCHEMA {schema}")
    try:
        conn.execute(f"SET search_path = {schema}, public")
        for t in ("cohort_default_rates", "student_loan_runs", "student_loan_trust_months"):
            conn.execute(f"CREATE TABLE {t} (LIKE public.{t} INCLUDING ALL)")
        for y, rate in ((2021, 2.5), (2022, 0.4), (2023, None)):
            conn.execute("""INSERT INTO cohort_default_rates (opeid, fiscal_year, school_name, borrowers, defaulters, rate)
                            VALUES ('001234', %s, 'Test U', 1000, 25, %s)""", (y, rate))
        yield conn, schema
    finally:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
        conn.close()


def test_cdr_rows_by_opeid(db):
    conn, _ = db
    from psycopg.rows import dict_row
    cur = conn.cursor(row_factory=dict_row)

    class C:                      # cdr_rows takes a connection with execute()
        def execute(self, *a):
            return cur.execute(*a)

        def rollback(self):
            pass
    rows = colleges.cdr_rows(C(), "00123400")
    assert [r["fiscal_year"] for r in rows] == [2023, 2022, 2021]           # newest cohort first
    assert rows[0]["rate"] is None and float(rows[1]["rate"]) == 0.4         # a blank stays blank
    assert [r["fiscal_year"] for r in colleges.cdr_rows(C(), "00123401")] == [2023, 2022, 2021]   # a branch campus
    assert colleges.cdr_rows(C(), None) == [] and colleges.cdr_rows(C(), "99999900") == []


def test_refresh_failure_keeps_previous_data(db, monkeypatch):
    conn, schema = db
    import psycopg
    from app.config import DATABASE_URL
    from loader import db as ldb
    from loader import student_loans as SL

    def connect(autocommit=False):
        c = psycopg.connect(DATABASE_URL, autocommit=autocommit)
        c.execute(f"SET search_path = {schema}, public")
        if not autocommit:
            c.commit()
        return c
    monkeypatch.setattr(ldb, "connect", connect)
    conn.execute("""INSERT INTO student_loan_trust_months (cik, period, pool_balance, retrieved_at)
                    VALUES (1, '2026-07-01', 100, now())""")
    assert SL.refresh(lambda *a, **k: None, months_fn=lambda s: 1, stats_fn=lambda s: None, boards_fn=lambda s: None)

    def boom(status):
        raise RuntimeError("SEC unreachable")
    assert not SL.refresh(lambda *a, **k: None, months_fn=boom, stats_fn=lambda s: None, boards_fn=lambda s: None)
    runs = conn.execute("SELECT ok, message FROM student_loan_runs ORDER BY id").fetchall()
    assert runs[0][0] is True and runs[1] == (False, "RuntimeError: SEC unreachable")
    assert conn.execute("SELECT count(*) FROM student_loan_trust_months").fetchone()[0] == 1     # data kept

    from app import student_loans as appsl
    from psycopg.rows import dict_row

    @contextlib.contextmanager
    def fake():
        c = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        c.execute(f"SET search_path = {schema}, public")
        try:
            yield c
        finally:
            c.close()
    monkeypatch.setattr("app.db.conn", fake)
    u = appsl.last_update()
    assert u["last_ok"] is not None and u["failed"]["message"] == "RuntimeError: SEC unreachable"
    assert u["data_through"].isoformat() == "2026-07-01"
