"""Public pension investors in private funds (loader/pensions.py): the line on Form D and fund pages, e.g.
"CalPERS committed $100 million (vintage 2019), net IRR 14.8%", from each pension's latest report."""

from __future__ import annotations

import logging

from app import db

log = logging.getLogger("np.pensions")
CONF_LABEL = {"high": "name and vintage match", "medium": "name match", "low": "close name and vintage match"}


def _rows(where: str, params) -> list[dict]:
    try:
        with db.conn() as conn:
            if not conn.execute("SELECT to_regclass('pension_fund_matches') IS NOT NULL AS ok").fetchone()["ok"]:
                return []
            return conn.execute(f"""
                SELECT DISTINCT ON (c.pension, c.fund_name) c.*, m.confidence
                FROM pension_fund_matches m
                JOIN pension_commitments c ON c.pension = m.pension AND c.fund_name = m.fund_name
                WHERE {where} ORDER BY c.pension, c.fund_name, c.as_of DESC""", params).fetchall()
    except Exception:  # noqa: BLE001 - an extra line; never fail the page
        log.exception("pension investors")
        return []


def for_formd(cik: str | None) -> list[dict]:
    if not cik:
        return []
    return _rows("m.kind = 'formd' AND m.key IN (SELECT root_accession FROM sec_formd_offerings WHERE cik = %s)", (cik,))


def for_fund(fund_id: str) -> list[dict]:
    return _rows("m.kind = 'adv' AND m.key = %s", (fund_id,))


def history(pension: str, fund_name: str) -> list[dict]:
    with db.conn() as conn:
        return conn.execute("""SELECT as_of, committed, cash_in, cash_out, total_value, net_irr, multiple
                               FROM pension_commitments WHERE pension = %s AND fund_name = %s ORDER BY as_of""",
                            (pension, fund_name)).fetchall()
