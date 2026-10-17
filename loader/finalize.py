"""Post-load bookkeeping: superseded returns and organizations' latest_* columns."""

from __future__ import annotations

from loader import db


def run(status) -> None:
    status.phase = "finalize"
    with db.connect() as conn:
        # When an organization files more than one return for the same period and
        # form (an amendment or a resubmission), the latest object_id wins; earlier
        # ones stay visible but are excluded from per-year totals.
        conn.execute("""
            UPDATE filings f SET superseded = (f.object_id <> k.keep)
            FROM (SELECT ein, tax_period_end, form_type, max(object_id) AS keep
                  FROM filings GROUP BY ein, tax_period_end, form_type) k
            WHERE f.ein = k.ein AND f.tax_period_end IS NOT DISTINCT FROM k.tax_period_end
              AND f.form_type = k.form_type AND f.superseded <> (f.object_id <> k.keep)
        """)
        # Organizations that filed but are not (or no longer) in the BMF.
        conn.execute("""
            INSERT INTO organizations (ein, name, name_norm, dba, street, city, state, zip, website)
            SELECT DISTINCT ON (ein) ein, org_name, lower(regexp_replace(org_name, '[^A-Za-z0-9 ]+', ' ', 'g')),
                   dba, street, city, state, zip, website
            FROM filings ORDER BY ein, tax_period_end DESC NULLS LAST, object_id DESC
            ON CONFLICT (ein) DO NOTHING
        """)
        conn.execute("""
            UPDATE organizations o SET
                latest_filing_year = l.tax_year,
                latest_total_revenue = l.total_revenue,
                latest_total_expenses = l.total_expenses,
                latest_total_assets = l.total_assets_eoy,
                latest_num_employees = l.num_employees,
                latest_num_volunteers = l.num_volunteers,
                website = coalesce(l.website, o.website),
                dba = coalesce(l.dba, o.dba)
            FROM (SELECT DISTINCT ON (ein) ein, tax_year, total_revenue, total_expenses, total_assets_eoy,
                         num_employees, num_volunteers, website, dba
                  FROM filings WHERE NOT superseded
                  ORDER BY ein, tax_period_end DESC NULLS LAST, object_id DESC) l
            WHERE o.ein = l.ein AND (o.latest_filing_year IS DISTINCT FROM l.tax_year
                  OR o.latest_total_revenue IS DISTINCT FROM l.total_revenue
                  OR o.website IS DISTINCT FROM coalesce(l.website, o.website)
                  OR o.latest_total_assets IS DISTINCT FROM l.total_assets_eoy
                  OR o.dba IS DISTINCT FROM coalesce(l.dba, o.dba))
        """)
        conn.commit()
        conn.execute("ANALYZE filings")
        conn.execute("ANALYZE people")
        conn.execute("ANALYZE organizations")
        conn.commit()
