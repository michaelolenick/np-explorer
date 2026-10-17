"""Post-load bookkeeping: superseded returns, organizations' latest_* columns, DAF sponsors."""

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
        mark_daf_sponsors(conn)
        mark_duplicate_people(conn)
        conn.execute("DELETE FROM filing_year_counts")
        conn.execute("""INSERT INTO filing_year_counts
                        SELECT tax_year, count(*) FROM filings WHERE tax_year IS NOT NULL GROUP BY tax_year""")
        conn.commit()
        conn.execute("ANALYZE filings")
        conn.execute("ANALYZE people")
        conn.execute("ANALYZE organizations")
        conn.commit()


DAF_SPONSOR_SQL = """
    UPDATE organizations o SET daf_sponsor = (x.ein IS NOT NULL), daf_last_year = x.last_year
    FROM organizations o2
    LEFT JOIN (SELECT d.ein, max(d.tax_year) AS last_year
               FROM daf_stats d JOIN filings f ON f.id = d.filing_id AND NOT f.superseded
               WHERE d.maintains_dafs OR d.daf_count > 0 OR d.daf_value_eoy > 0
               GROUP BY d.ein) x ON x.ein = o2.ein
    WHERE o.ein = o2.ein
      AND (o.daf_sponsor IS DISTINCT FROM (x.ein IS NOT NULL) OR o.daf_last_year IS DISTINCT FROM x.last_year)
"""


def mark_daf_sponsors(conn) -> int:
    """Organizations whose returns say they maintain donor-advised funds (or report any)."""
    return conn.execute(DAF_SPONSOR_SQL).rowcount


def mark_duplicate_people(conn, since_filing_id: int | None = None) -> int:
    """Flag repeats of the same name with identical pay on one return (the first row stays).
    Only filings after the last one checked, unless since_filing_id is given (0 = everything)."""
    if since_filing_id is None:
        row = conn.execute("SELECT rows FROM loader_progress WHERE file = 'people-duplicates'").fetchone()
        since_filing_id = int(row[0]) if row and row[0] else 0
    top = conn.execute("SELECT max(id) FROM filings").fetchone()[0] or 0
    n = conn.execute("""
        UPDATE people p SET is_duplicate = true
        FROM (SELECT id, row_number() OVER (PARTITION BY filing_id, name_norm, comp_org, comp_related, other_comp
                                            ORDER BY id) AS rn
              FROM people WHERE filing_id > %s) x
        WHERE p.id = x.id AND x.rn > 1 AND NOT p.is_duplicate""", (since_filing_id,)).rowcount
    db.progress(conn, "people-duplicates", "done", kind="finalize", rows=top)
    return n
