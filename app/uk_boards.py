"""Leaderboards of UK charities (app/uk_charities.py, loader/uk_charities.py; owner, 2026-11-14).

uk_boards() returns Board objects for app/boards.py to append to BOARDS; GROUP goes in boards.GROUPS. The views read
uk.charity_main (one row per registered number with its latest figures), uk.trustee, uk.parta, uk.us_match and uk.us_grant,
built by loader.uk_charities summarize and loader.uk_xref match. Rebuilt from scripts/nightly.sh after the extract refresh.
The register has no pay for individuals, so there is no pay board; "staff paid over 60,000 pounds" is the nearest thing it reports.
"""

from __future__ import annotations

GROUP_NAME = "uk"
GROUP = {"title": "UK charities", "subtitle": "Across the Pond",
         "definition": "Charities on the Charity Commission register for England and Wales: the largest by income, the ones "
                       "with the most trustees, the fastest growing, those with a US counterpart in FURP's records, the "
                       "biggest recipients of US foundation grants, and income by region."}
SOURCE = ("Charity Commission for England and Wales, register of charities data extract (Open Government Licence v3.0): "
          "registered charities only, latest financial year each charity has reported. Figures are in pounds sterling "
          "unless marked as dollars. Contains public sector information licensed under the Open Government Licence v3.0.")
REGISTER = "'https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/' || c.reg_number"


def _base(value: str, where: str, extra: str = "", joins: str = "") -> str:
    """One row per registered charity; `value` is the ranked number."""
    from app.boards import norm_sql
    name = "c.name"
    return f"""
        SELECT 'uk_charity'::text AS subject_kind, c.reg_number::text AS subject_key, {name} AS subject_name,
               {norm_sql(name)} AS subject_norm, '/uk/charity/' || c.reg_number AS subject_url, NULL::text AS match,
               NULL::text AS ein, NULL::text AS org_name, NULL::text AS state, 'UK'::text AS form_type,
               extract(year FROM c.fin_end)::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               ({value})::numeric AS value, NULL::text AS org_url, {REGISTER} AS source_url,
               c.region, c.charity_type, c.income, c.expenditure, c.trustees, c.employees, c.volunteers, c.income_prev,
               to_char(c.fin_end, 'YYYY-MM-DD') AS year_to {extra}
        FROM uk.charity_main c {joins}
        WHERE c.status = 'Registered' AND {where}"""


def _largest() -> str:
    from app.boards import _ranked_by_org
    return _ranked_by_org(_base("c.income", "c.income IS NOT NULL AND c.income > 0"), "value DESC, subject_key")


def _most_trustees() -> str:
    from app.boards import _ranked_by_org
    return _ranked_by_org(_base("c.trustees", "c.trustees >= 1"), "value DESC, income DESC NULLS LAST, subject_key")


def _fastest_growing() -> str:
    from app.boards import _ranked_by_org
    return _ranked_by_org(_base("100 * (c.income - c.income_prev) / c.income_prev",
                                "c.income_prev >= 1000000 AND c.income >= 1000000 AND c.fin_end >= current_date - interval '3 years'"),
                          "value DESC, income DESC, subject_key")


def _staff_over_60k() -> str:
    from app.boards import _ranked_by_org
    return _ranked_by_org(_base("a.staff_over_60k_n", "a.staff_over_60k_n > 0",
                                extra=", a.staff_over_60k_n AS staff_over_60k, CASE WHEN a.trustee_benefit THEN 'Yes' WHEN NOT a.trustee_benefit THEN 'No' END AS trustee_benefit",
                                joins="JOIN LATERAL (SELECT p.staff_over_60k_n, p.trustee_benefit FROM uk.parta p WHERE p.organisation_number = c.organisation_number "
                                      "AND p.latest ORDER BY p.fin_end DESC LIMIT 1) a ON true"), "value DESC, income DESC NULLS LAST, subject_key")


def _us_counterparts() -> str:
    from app.boards import _ranked_by_org
    return _ranked_by_org(_base("c.income", "c.income IS NOT NULL",
                                extra=", m.us_name AS us_counterpart, m.us_key, m.us_state, m.method, m.confidence, o.latest_total_revenue AS us_revenue",
                                joins="JOIN LATERAL (SELECT x.us_name, x.us_key, x.us_state, x.method, x.confidence FROM uk.us_match x "
                                      "WHERE x.uk_reg = c.reg_number AND x.us_kind = 'org' AND x.relation = 'same' AND x.confidence IN ('high', 'medium') "
                                      "ORDER BY CASE x.confidence WHEN 'high' THEN 0 ELSE 1 END, x.method LIMIT 1) m ON true "
                                      "LEFT JOIN organizations o ON o.ein = m.us_key"), "value DESC, subject_key")


def _us_grants() -> str:
    from app.boards import _ranked_by_org
    return _ranked_by_org(_base("g.total", "g.total > 0",
                                extra=", g.grantors, g.grants, g.first_year, g.last_year, g.top_grantor",
                                joins="JOIN (SELECT uk_reg, sum(total) AS total, count(*) AS grantors, sum(grants) AS grants, min(first_year) AS first_year, "
                                      "max(last_year) AS last_year, (array_agg(grantor_ein ORDER BY total DESC))[1] AS top_ein, "
                                      "(SELECT o.name FROM organizations o WHERE o.ein = (array_agg(grantor_ein ORDER BY total DESC))[1]) AS top_grantor "
                                      "FROM uk.us_grant GROUP BY uk_reg) g ON g.uk_reg = c.reg_number"), "value DESC, subject_key")


def _income_by_region() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'uk_region'::text AS subject_kind, r.region AS subject_key, r.region AS subject_name, {norm_sql('r.region')} AS subject_norm,
               '/uk/search?q=a&region=' || replace(r.region, ' ', '%20') AS subject_url, NULL::text AS match, NULL::text AS ein,
               NULL::text AS org_name, NULL::text AS state, 'UK'::text AS form_type, r.year AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, r.income::numeric AS value, NULL::text AS org_url,
               'https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download' AS source_url,
               r.charities, r.avg_income, r.biggest, r.biggest_income, r.share
        FROM (SELECT c.region, count(*) AS charities, sum(c.income) AS income, avg(c.income) AS avg_income,
                     max(extract(year FROM c.fin_end))::int AS year,
                     (array_agg(c.name ORDER BY c.income DESC NULLS LAST))[1] AS biggest, max(c.income) AS biggest_income,
                     100 * sum(c.income) / sum(sum(c.income)) OVER () AS share
              FROM uk.charity_main c WHERE c.status = 'Registered' AND c.region IS NOT NULL AND c.income IS NOT NULL
                AND c.region NOT LIKE 'Scotland%' GROUP BY c.region) r"""
    return _ranked_by_org(inner, "value DESC, subject_key")


def uk_boards() -> list:
    from app.boards import Board, Column
    from app.uk_charities import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="census", year_label="Year to", source_label="the Charity Commission register",
              search=True, org_label="Organization")
    common = [Column("region", "Region"), Column("charity_type", "Type"), Column("trustees", "Trustees", "num"),
              Column("employees", "Employees", "num?"), Column("year_to", "Year to")]
    return [
        Board("uk-largest-income", "The largest UK charities by income", "Big Charity, Big Island",
              "Registered charities in England and Wales ranked by the income they reported for their latest financial year.",
              "Value = total gross income on the charity's latest annual return (part A), in pounds. Registered charities only; "
              "removed charities and charities with no return are left out. " + SOURCE,
              _largest(), Column("value", "Income (£)", "gbp"),
              [Column("expenditure", "Spending (£)", "gbp?"), Column("income_prev", "Income the year before (£)", "gbp?")] + common,
              ["Large charities that are groups (a university, a hospital trust) report the parent charity's income; linked "
               "subsidiary charities are on the parent's page."], unit="charity", **kw),
        Board("uk-most-trustees", "UK charities with the most trustees", "Too Many Cooks",
              "Registered charities ranked by the number of current trustees the register lists.",
              "Value = the number of current trustees on the main charity's register entry (individuals and organizations). "
              "Ties are broken by income. " + SOURCE,
              _most_trustees(), Column("value", "Trustees", "num"),
              [Column("income", "Income (£)", "gbp?"), Column("charity_type", "Type"), Column("region", "Region"),
               Column("year_to", "Year to")],
              ["Housing associations, almshouses and village hall trusts often list dozens of trustees."], unit="charity", **kw),
        Board("uk-fastest-growing", "The fastest-growing large UK charities", "Rocket Fuel",
              "Charities that reported at least £1 million in income in each of their last two years, ranked by the percentage "
              "growth in income.",
              "Value = (latest income minus the previous year's income) divided by the previous year's income, as a percentage. "
              "Both years must be at least £1,000,000 and the latest year must end within the last three years. Mergers and "
              "one-off legacies move this far more than growth in activity. " + SOURCE,
              _fastest_growing(), Column("value", "Income growth", "pct"),
              [Column("income", "Income (£)", "gbp"), Column("income_prev", "Income the year before (£)", "gbp")] + common,
              ["A jump can be a merger, a transfer of assets from another charity, or a legacy: see the charity's history."],
              unit="charity", **kw),
        Board("uk-staff-over-60k", "UK charities paying the most staff over £60,000", "Six Figures, Near Enough",
              "Charities ranked by how many staff the trustees report as earning £60,000 or more in the latest year.",
              "Value = the sum of the staff counts in every salary band from £60,001 up in the charity's latest part A return. The "
              "register publishes bands only, not names or exact pay. " + SOURCE,
              _staff_over_60k(), Column("value", "Staff paid over £60,000", "num"),
              [Column("income", "Income (£)", "gbp?"), Column("trustee_benefit", "Trustees received benefits"),
               Column("employees", "Employees", "num?"), Column("region", "Region"), Column("year_to", "Year to")],
              ["The register has no per-person pay for UK charities; this is the closest figure it carries."], unit="charity", **kw),
        Board("uk-with-us-counterpart", "UK charities with a US counterpart", "Special Relationship",
              "UK charities that match a US nonprofit in FURP's records by website, an “American Friends of” name, or the same "
              "name with a country word, ranked by the UK charity's income.",
              "Value = the UK charity's latest income in pounds. Counterparts are high or medium confidence matches from uk.us_match "
              "(loader/uk_xref.py): the same website; an American Friends of X name; the same name plus USA, America or UK; or the same "
              "name with a US signal in the charity's activities or areas. Same-name-only matches are left out. " + SOURCE,
              _us_counterparts(), Column("value", "UK income (£)", "gbp"),
              [Column("us_counterpart", "US counterpart"), Column("us_state", "US state"), Column("us_revenue", "US revenue ($)", "money?"),
               Column("method", "Matched by"), Column("confidence", "Confidence")] + common,
              ["Every match says how it was made on the charity's page; a shared name is not proof of the same organization."],
              unit="charity", **kw),
        Board("uk-us-grants", "UK charities receiving the most from US foundations", "Dollars Across the Water",
              "UK charities ranked by the total of grants US foundations reported to them on Form 990 grant schedules.",
              "Value = the dollars in grants to recipients the US filing places in the UK (state UK, England, Great Britain and the "
              "like) whose name equals a registered charity's, summed over every year and grantor FURP has. Dollars, not pounds. " + SOURCE,
              _us_grants(), Column("value", "US grants ($)", "money"),
              [Column("grantors", "US grantors", "num"), Column("grants", "Grants", "num"), Column("top_grantor", "Largest grantor"),
               Column("first_year", "From", "year"), Column("last_year", "To", "year"), Column("income", "UK income (£)", "gbp?")] + common[:2],
              ["Only grants whose recipient the filing places in the UK are counted; grants to a charity listed without a country are not."],
              unit="charity", **kw),
        Board("uk-income-by-region", "UK charity income by region", "Where the Money Is",
              "Regions of England and Wales ranked by the total income of the registered charities whose postcode is there.",
              "Value = the sum of latest income of registered charities in the region, the region taken from the postcode area "
              "(approximate: a few areas straddle regions; charities with no postcode are left out). " + SOURCE,
              _income_by_region(), Column("value", "Income (£)", "gbp"),
              [Column("charities", "Charities", "num"), Column("avg_income", "Average income (£)", "gbp"),
               Column("share", "Share of all", "pct"), Column("biggest", "Biggest charity"), Column("biggest_income", "Its income (£)", "gbp")],
              ["London's total includes national charities with a London head office."], unit="region", **{**kw, "org_label": "Region"}),
    ]


ALTERNATIVES = {
    "uk-largest-income": ["Big Charity, Big Island", "Pound Heavy", "The Biggest Charities in England and Wales"],
    "uk-most-trustees": ["Too Many Cooks", "Full Board", "Trustee Crowds"],
    "uk-fastest-growing": ["Rocket Fuel", "Charity Boom", "Growth Spurt"],
    "uk-staff-over-60k": ["Six Figures, Near Enough", "Over Sixty", "Staff on 60K"],
    "uk-with-us-counterpart": ["Special Relationship", "Across the Pond", "Transatlantic Charities"],
    "uk-us-grants": ["Dollars Across the Water", "American Money, British Causes", "Stateside Support"],
    "uk-income-by-region": ["Where the Money Is", "Regional Purse", "Charity by Postcode"],
}
