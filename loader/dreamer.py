"""Nonprofit Dreamer's table (owner, 2026-10-30): research.dream_orgs, one row per nonprofit founded 2012-2018, with
its first five years after founding side by side, so /dreamer reads one row per organization.

Two kinds of organizations:
  open    still on the IRS Business Master File. From research.npay_years and research.npay_orgs
          (research/new_nonprofit_pay.sql; definitions there): founded = the IRS ruling year.
  closed  no longer on the BMF (revoked, terminated, merged). The IRS publishes no ruling year or NTEE code for them,
          so founded is estimated as the first tax year FURP holds any return for (990, 990-EZ or 990-N), kept only
          when that is 2012 or later: 990-N postcards are e-filed back to 2007, so an older small organization would
          show earlier returns. ntee_major is NULL.
Year k = tax year - founded. Cohorts stop at 2018 so every organization has had five full tax years to file (returns
run through 2025). Only organizations that filed something are kept.

  r1..r5      total revenue on the year-k 990 / 990-EZ; NULL when there was none (a 990-N, or nothing)
  o1..o5      officer compensation on that return (0 when nobody was paid)
  two50       some year 1-5 return shows $100K+ of salaries (two $50K salaries) or two people paid $50K+
  last_filed  the latest tax year with any return, 990-N included

Rerun:  PYTHONPATH=. .venv/bin/python -m loader.dreamer
"""

from __future__ import annotations

import logging

from loader import db

log = logging.getLogger("np.dreamer")

FIRST, LAST = 2012, 2018

YEARS = ",\n           ".join(
    f"max(y.total_revenue) FILTER (WHERE y.k = {k}) AS r{k}, max(y.officer_comp) FILTER (WHERE y.k = {k}) AS o{k}"
    for k in range(1, 6))
COLS = "r1, r2, r3, r4, r5, o1, o2, o3, o4, o5"

SQL = f"""
DROP TABLE IF EXISTS research.dream_orgs_new;
CREATE TABLE research.dream_orgs_new AS
WITH y AS (
    SELECT y.ein,
           {YEARS},
           bool_or(coalesce(y.salaries, 0) >= 100000 OR y.n50 >= 2) AS two50
    FROM research.npay_years y
    WHERE y.k BETWEEN 1 AND 5 AND y.founded BETWEEN {FIRST} AND {LAST}
    GROUP BY y.ein
), n AS (
    SELECT e.ein, max(e.tax_year) AS last_n
    FROM irs_epostcard e JOIN research.npay_orgs o USING (ein)
    WHERE o.founded BETWEEN {FIRST} AND {LAST}
    GROUP BY e.ein
)
SELECT o.ein, o.founded, false AS closed, upper(left(g.ntee, 1)) AS ntee_major, g.state, z.zip5, o.returns,
       o.peak_revenue, nullif(greatest(coalesce(o.last_return, 0), coalesce(n.last_n, 0)), 0) AS last_filed,
       {COLS}, coalesce(y.two50, false) AS two50
FROM research.npay_orgs o
JOIN organizations g USING (ein)
LEFT JOIN org_geo z USING (ein)
LEFT JOIN y USING (ein)
LEFT JOIN n USING (ein)
WHERE o.founded BETWEEN {FIRST} AND {LAST} AND (o.returns > 0 OR n.last_n IS NOT NULL);

CREATE TEMP TABLE dc AS
SELECT ein, min(ty) AS founded, max(ty) AS last_filed
FROM (SELECT f.ein, f.tax_year AS ty FROM filings f JOIN organizations o USING (ein)
      WHERE NOT o.in_bmf AND f.form_type IN ('990', '990EZ') AND f.tax_year IS NOT NULL
      UNION ALL
      SELECT e.ein, e.tax_year FROM irs_epostcard e JOIN organizations o USING (ein) WHERE NOT o.in_bmf) a
GROUP BY ein
HAVING min(ty) BETWEEN {FIRST} AND {LAST};
ALTER TABLE dc ADD PRIMARY KEY (ein);

CREATE TEMP TABLE dcy AS
WITH f AS (
    SELECT DISTINCT ON (f.ein, f.tax_year)
           f.id, f.ein, dc.founded, f.tax_year, f.form_type, f.total_revenue, f.officer_comp_total
    FROM dc JOIN filings f ON f.ein = dc.ein
    WHERE f.form_type IN ('990', '990EZ') AND f.tax_year IS NOT NULL
    ORDER BY f.ein, f.tax_year, coalesce(f.superseded, false), f.filed_date DESC NULLS LAST, f.object_id DESC
), p AS (
    SELECT p.filing_id,
           sum(p.comp_org) FILTER (WHERE p.source IN ('990-VIIA', '990EZ-IV')) AS listed_comp,
           count(*) FILTER (WHERE p.comp_org >= 50000) AS n50
    FROM people p
    WHERE p.filing_id IN (SELECT id FROM f)
      AND p.source IN ('990-VIIA', '990EZ-IV', '990EZ-HCE') AND NOT coalesce(p.is_duplicate, false)
    GROUP BY 1
), e AS (
    SELECT e.filing_id,
           CASE WHEN jsonb_array_length(e.lines) > 0 THEN
               (SELECT coalesce(sum((l->>3)::bigint), 0) FROM jsonb_array_elements(e.lines) l
                WHERE l->>0 IN ('pay_officers', 'pay_disqualified', 'pay_other', 'pay')) END AS salaries
    FROM expense_breakdown e
    WHERE e.filing_id IN (SELECT id FROM f)
)
SELECT f.ein, f.tax_year - f.founded AS k, f.total_revenue,
       CASE WHEN f.form_type = '990' THEN coalesce(f.officer_comp_total, p.listed_comp, 0)
            ELSE coalesce(p.listed_comp, 0) END AS officer_comp,
       e.salaries, coalesce(p.n50, 0) AS n50
FROM f LEFT JOIN p ON p.filing_id = f.id LEFT JOIN e ON e.filing_id = f.id;

INSERT INTO research.dream_orgs_new
SELECT dc.ein, dc.founded, true, NULL, g.state, z.zip5, coalesce(r.returns, 0), r.peak, dc.last_filed,
       {COLS}, coalesce(y.two50, false)
FROM dc
JOIN organizations g USING (ein)
LEFT JOIN org_geo z USING (ein)
LEFT JOIN (SELECT ein, count(*) AS returns, max(total_revenue) AS peak FROM dcy GROUP BY ein) r USING (ein)
LEFT JOIN (SELECT y.ein, {YEARS},
                  bool_or(coalesce(y.salaries, 0) >= 100000 OR y.n50 >= 2) AS two50
           FROM dcy y WHERE y.k BETWEEN 1 AND 5 GROUP BY y.ein) y USING (ein);

ALTER TABLE research.dream_orgs_new ADD PRIMARY KEY (ein);
CREATE INDEX ON research.dream_orgs_new (ntee_major);
CREATE INDEX ON research.dream_orgs_new (state);
ANALYZE research.dream_orgs_new;
DROP TABLE IF EXISTS research.dream_orgs;
ALTER TABLE research.dream_orgs_new RENAME TO dream_orgs;
"""


def build() -> int:
    with db.connect() as conn:
        conn.execute("SET LOCAL statement_timeout = '30min'")
        for stmt in [s for s in SQL.split(";\n") if s.strip()]:
            conn.execute(stmt)
        conn.execute("ALTER INDEX IF EXISTS research.dream_orgs_new_pkey RENAME TO dream_orgs_pkey")
        n = conn.execute("SELECT count(*) FROM research.dream_orgs").fetchone()[0]
    log.info("dream_orgs: %s organizations", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(build())
