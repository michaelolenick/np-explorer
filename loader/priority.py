"""Priority pages (owner, 2026-10-30): the organizations, funders and people submitted to search engines first.

Rebuilt nightly before the sitemap (loader/sitemap.py writes them to priority-*.xml.gz, which /sitemap.xml lists
ahead of everything else) and listed on the /top hub (app/top.py), so each is three clicks from the home page:
home, /top (footer), a page of the list, the entity.

  org     the largest organizations by latest revenue (ORGS), then the most visited ones not already listed
          (people, not crawlers, over the last TRAFFIC_DAYS days; at most TRAFFIC)
  funder  organizations that granted the most, all years (org_funders)
  person  the highest-paid people, from the Highest-paid people leaderboard (board_top_paid)

Usage: python -m loader.priority
"""

from __future__ import annotations

import logging

from loader import db

log = logging.getLogger("np.priority")
ORGS, TRAFFIC, TRAFFIC_DAYS, FUNDERS, PEOPLE = 10000, 2000, 90, 5000, 5000

SQL = [
    ("org", """
     INSERT INTO priority_pages (kind, rank, ident, name, figure, detail, why)
     SELECT 'org', row_number() OVER (ORDER BY latest_total_revenue DESC, ein), ein, name, latest_total_revenue,
            concat_ws(', ', initcap(city), state), 'revenue'
     FROM (SELECT ein, name, city, state, latest_total_revenue FROM organizations
           WHERE latest_filing_year IS NOT NULL AND latest_total_revenue IS NOT NULL
           ORDER BY latest_total_revenue DESC, ein LIMIT %(orgs)s) o"""),
    ("org", """
     INSERT INTO priority_pages (kind, rank, ident, name, figure, detail, why)
     SELECT 'org', %(orgs)s + row_number() OVER (ORDER BY v.views DESC, v.ein), v.ein, o.name, v.views,
            concat_ws(', ', initcap(o.city), o.state), 'traffic'
     FROM (SELECT substring(path FROM '([0-9]{9})$') AS ein, count(*) AS views FROM events
           WHERE ua_class = 'human' AND name = 'page' AND route = 'org' AND path ~ '^/org/[^/]*[0-9]{9}$'
             AND ts > now() - make_interval(days => %(days)s)
           GROUP BY 1) v
     JOIN organizations o ON o.ein = v.ein AND o.latest_filing_year IS NOT NULL
     WHERE NOT EXISTS (SELECT 1 FROM priority_pages p WHERE p.kind = 'org' AND p.ident = v.ein)
     ORDER BY v.views DESC, v.ein LIMIT %(traffic)s"""),
    ("funder", """
     INSERT INTO priority_pages (kind, rank, ident, name, figure, detail, why)
     SELECT 'funder', row_number() OVER (ORDER BY f.total DESC, f.ein), f.ein, o.name, f.total,
            concat_ws(', ', initcap(o.city), o.state), 'granted'
     FROM (SELECT grantor_ein AS ein, sum(total) AS total FROM org_funders WHERE grantor_ein IS NOT NULL
           GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT %(funders)s) f
     JOIN organizations o ON o.ein = f.ein AND o.latest_filing_year IS NOT NULL"""),
    # The Highest-paid people leaderboard's rows (app/boards.py: one filing per person per year, institutions,
    # trustee titles and placeholder rows left out), so a typo in one filing's pay can't top the list.
    ("person", """
     INSERT INTO priority_pages (kind, rank, ident, name, figure, detail, why)
     SELECT 'person', row_number() OVER (ORDER BY value DESC, subject_key), subject_key, subject_name, value, title,
            'pay'
     FROM (SELECT DISTINCT ON (subject_key) subject_key, subject_name, value, title FROM board_top_paid
           ORDER BY subject_key, value DESC) b
     ORDER BY value DESC, subject_key LIMIT %(people)s"""),
]


def build() -> dict[str, int]:
    """Replace priority_pages in one transaction; the counts by kind."""
    params = {"orgs": ORGS, "traffic": TRAFFIC, "days": TRAFFIC_DAYS, "funders": FUNDERS, "people": PEOPLE}
    with db.connect() as conn:
        conn.execute("SET LOCAL statement_timeout = '10min'")
        conn.execute("DELETE FROM priority_pages")
        for _kind, sql in SQL:
            conn.execute(sql, params)
        counts = dict(conn.execute("SELECT kind, count(*) FROM priority_pages GROUP BY 1").fetchall())
    log.info("priority pages: %s", counts)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(build())
