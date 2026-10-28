"""The order of the record sections on person and organization pages, top to bottom, and of the data the "Explain"
summary gets for those pages (owner, 2026-10-28). Change the order here: templates/person.html and templates/org.html
loop over SECTION_ORDER (one template per section in templates/_sections/), and app/explain.py follows it too.
Sections with no records stay hidden, as before.
"""

from __future__ import annotations

import re

from app import db

SECTION_ORDER = [
    "form_d",     # SEC Form D private offerings: funds and SPVs, with the totals line
    "adv",        # Form ADV registered advisers (and securities registration)
    "insider",    # Form 4 insider trades and buybacks
    "990",        # nonprofit filings: officers, pay, grants, finances
    "politics",   # FEC donations, political committees and lobbying
    "federal",    # federal spending and contracts
    "business",   # state business registrations
    "ip",         # patents and trademarks
    "other",      # public salaries, food recalls and everything else
]

# Names and titles that say "fund, VC or investor". With no Form D on file, such a page gets a one-line note at the
# top. A plain "Fund" is left out: most nonprofits called a fund (scholarship funds, relief funds) are not investors.
FUND_RE = re.compile(r"\b(?:venture\s+capital|ventures?|vc|venture\s+partners?|investors?(?!\s+relations)|"
                     r"private\s+equity|hedge\s+funds?|investment\s+(?:fund|partners?|manager)s?|"
                     r"fund\s+(?:[ivx]+|\d+)\b|fund,?\s+(?:l\.?\s?p\.?|llc)|capital\s+partners|"
                     r"general\s+partner|managing\s+partner|managing\s+member)\b", re.I)


def fund_like(*texts) -> bool:
    """True when any of the names or titles (strings, or lists of them) describes a fund, VC or investor."""
    for t in texts:
        if isinstance(t, (list, tuple)):
            if fund_like(*t):
                return True
        elif t and FUND_RE.search(str(t)):
            return True
    return False


def formd_totals(rows) -> dict:
    """The totals line over Form D rows: filings, offerings (each original Form D with its amendments, followed back
    through previous_accession), how many are SPVs, and amount sold. Amendments repeat the running total, so each
    offering counts once, at its latest reported amount sold (sec_formd_offerings.latest_sold)."""
    accs = sorted({r["accession"] for r in rows or [] if r.get("accession")})
    out = {"filings": len(rows or []), "offerings": 0, "spvs": 0, "sold": None}
    if not accs:
        return out
    try:
        with db.conn() as conn:
            conn.execute("SET LOCAL statement_timeout = '3s'")
            t = conn.execute("""
                WITH RECURSIVE up AS (
                    SELECT accession, previous_accession, 0 AS depth FROM sec_formd WHERE accession = ANY(%s)
                    UNION ALL
                    SELECT d.accession, d.previous_accession, up.depth + 1 FROM up JOIN sec_formd d
                      ON d.accession = up.previous_accession WHERE up.depth < 50)
                SELECT count(*) AS offerings, count(*) FILTER (WHERE o.is_spv) AS spvs, sum(o.latest_sold) AS sold
                FROM sec_formd_offerings o
                WHERE o.root_accession IN (SELECT accession FROM up WHERE previous_accession IS NULL)""",
                             (accs,)).fetchone()
    except Exception:  # noqa: BLE001 - the totals line is optional; the table below still shows every filing
        return out
    out.update(offerings=t["offerings"] or 0, spvs=t["spvs"] or 0, sold=t["sold"])
    return out
