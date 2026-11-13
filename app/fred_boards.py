"""Leaderboards that cross FRED's county economy with FURP's records (app/fred.py, loader/fred.py; owner, 2026-11-13).

fred_boards() returns Board objects for app/boards.py to append to BOARDS; GROUP goes in boards.GROUPS. The views read
fred.area_latest (the latest value per county and kind), fred.county_trend (five-year real change in per capita personal
income against nonprofit revenue per resident) and fred.observations, joined to census_area, census_area_furp and
census_area_people (loader/census.py). Rebuilt by loader.fred summarize (after each load; weekly from the nightly).
"""

from __future__ import annotations

GROUP_NAME = "fred"
GROUP = {"title": "The local economy against the records", "subtitle": "Main Street",
         "definition": "Counties measured by the economy around them (FRED, Federal Reserve Bank of St. Louis: "
                       "unemployment rate, per capita personal income, population, house prices) against the nonprofits "
                       "and the pay in FURP's records: places where income fell while nonprofit revenue per resident rose, "
                       "high-unemployment counties with the biggest nonprofits, executive pay as a multiple of the county's "
                       "per capita personal income."}
SOURCE = ("Economic figures: FRED, Federal Reserve Bank of St. Louis (BLS county unemployment rates, BEA per capita "
          "personal income, Census population estimates), each linked to its FRED series. Nonprofit figures: the IRS "
          "Form 990 returns of organizations placed in the county by ZIP code (the county holding most of the ZIP's "
          "land). Source: FRED, Federal Reserve Bank of St. Louis.")
MIN_COUNTY_POP = 10_000
BIG_NONPROFIT = 50_000_000


def _income_down_nonprofits_up() -> str:
    from app.boards import _ranked_by_org, norm_sql
    name = "a.short_name || ', ' || a.stusab"
    inner = f"""
        SELECT 'county'::text AS subject_kind, a.gisjoin AS subject_key, {name} AS subject_name,
               {norm_sql(name)} AS subject_norm, '/census/' || lower(a.stusab) || '/' || a.slug AS subject_url,
               NULL::text AS match, NULL::text AS ein, NULL::text AS org_name, a.stusab AS state, 'FRED'::text AS form_type,
               t.year_b AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               (100 * ((t.rev_b / t.pop_b) / (t.rev_a_real / t.pop_a) - 1))::numeric AS value, NULL::text AS org_url,
               'https://fred.stlouisfed.org/series/PCPI' || a.geoid AS source_url,
               (100 * (t.pcpi_b / t.pcpi_a_real - 1))::numeric AS income_change, t.pcpi_b, t.pcpi_a_real,
               (t.rev_b / t.pop_b)::numeric AS rev_per_resident, (t.rev_a_real / t.pop_a)::numeric AS rev_per_resident_before,
               t.pop_b AS population, t.filings_b AS filings, t.year_a, t.year_b
        FROM fred.county_trend t JOIN census_area a ON a.gisjoin = t.gisjoin AND a.level = 'county'
        WHERE t.pop_a > 0 AND t.pop_b >= {MIN_COUNTY_POP} AND t.rev_a_real > 0 AND t.pcpi_a_real > 0 AND t.filings_b >= 10
          AND t.pcpi_b < t.pcpi_a_real AND (t.rev_b / t.pop_b) > (t.rev_a_real / t.pop_a)"""
    return _ranked_by_org(inner, "value DESC, population DESC, subject_key")


def _unemployment_big_nonprofits() -> str:
    from app.boards import _ranked_by_org, norm_sql
    name = "a.short_name || ', ' || a.stusab"
    inner = f"""
        SELECT 'county'::text AS subject_kind, a.gisjoin AS subject_key, {name} AS subject_name,
               {norm_sql(name)} AS subject_norm, '/census/' || lower(a.stusab) || '/' || a.slug AS subject_url,
               NULL::text AS match, NULL::text AS ein, NULL::text AS org_name, a.stusab AS state, 'FRED'::text AS form_type,
               extract(year FROM l.date)::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               l.value::numeric AS value, NULL::text AS org_url, 'https://fred.stlouisfed.org/series/' || l.series_id AS source_url,
               to_char(l.date, 'Mon YYYY') AS month, l.value_1y AS rate_year_ago, f.top_name AS biggest,
               f.top_value AS biggest_revenue, f.total AS nonprofit_revenue, f.n AS nonprofits, a.population,
               a.median_hh_income, a.poverty_rate
        FROM fred.area_latest l JOIN census_area a ON a.gisjoin = l.gisjoin AND a.level = 'county'
        JOIN census_area_furp f ON f.gisjoin = a.gisjoin AND f.kind = 'org'
        WHERE l.kind = 'unemployment_rate' AND l.geo_level = 'county' AND a.population >= {MIN_COUNTY_POP}
          AND f.top_value >= {BIG_NONPROFIT}"""
    return _ranked_by_org(inner, "value DESC, biggest_revenue DESC, subject_key")


def _pay_vs_county_income() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'person'::text AS subject_kind, p.cluster_id::text AS subject_key, p.name AS subject_name,
               {norm_sql('p.name')} AS subject_norm, '/person/' || p.cluster_id AS subject_url, NULL::text AS match,
               p.ein, p.org_name, a.stusab AS state, '990'::text AS form_type, p.tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, (p.total / i.value)::numeric AS value, '/org/' || p.ein AS org_url,
               'https://fred.stlouisfed.org/series/' || s.id AS source_url,
               p.title, p.total AS pay, fred.real_dollars(p.total, p.tax_year) AS pay_real, i.value AS pcpi,
               extract(year FROM i.date)::int AS pcpi_year, a.short_name || ', ' || a.stusab AS county,
               '/census/' || lower(a.stusab) || '/' || a.slug AS county_url, a.poverty_rate
        FROM census_area_people p JOIN census_area a ON a.gisjoin = p.county_gj AND a.level = 'county'
        JOIN fred.series s ON s.gisjoin = a.gisjoin AND s.kind = 'per_capita_income'
        JOIN LATERAL (SELECT o.value, o.date FROM fred.observations o
                      WHERE o.series_id = s.id AND o.value IS NOT NULL AND o.date <= make_date(p.tax_year, 12, 31)
                      ORDER BY o.date DESC LIMIT 1) i ON true
        WHERE p.rank_county <= 100 AND p.total >= 200000 AND i.value > 0"""
    return _ranked_by_org(inner, "value DESC, pay DESC, subject_key")


def fred_boards() -> list:
    from app.boards import Board, Column
    from app.fred import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="census", year_label="Year",
              source_label="FRED (Federal Reserve Bank of St. Louis) and FURP's records", search=True, org_label="County")
    return [
        Board("fred-income-down-nonprofits-up", "Counties where income fell while nonprofit revenue per resident rose",
              "Charity Up, Paychecks Down",
              "Counties (population 10,000 or more) where real per capita personal income fell over five years while the "
              "real revenue of the nonprofits based there, per resident, rose; ranked by the rise.",
              "Value = the five-year change in nonprofit revenue per resident, after inflation (both years in the later "
              "year's dollars by the CPI-U annual average, fred.real_dollars); shown only where real per capita personal "
              "income (BEA, via FRED) fell over the same five years. Revenue is the sum of the Form 990 returns of the "
              "county's nonprofits for each tax year (at least 10 returns in the later year); population is the Census "
              "estimate via FRED. " + SOURCE,
              _income_down_nonprofits_up(), Column("value", "Nonprofit revenue per resident, real change", "pct"),
              [Column("income_change", "Per capita income, real change", "pct"), Column("pcpi_b", "Per capita personal income", "money"),
               Column("rev_per_resident", "Nonprofit revenue per resident", "money"),
               Column("rev_per_resident_before", "Five years earlier (same dollars)", "money"),
               Column("population", "Population", "num"), Column("filings", "Returns", "num"), Column("year_a", "From", "year"),
               Column("year_b", "To", "year")],
              ["A hospital merger or a university's growth moves a county's nonprofit revenue far more than its residents' "
               "incomes; the point is the places where the two lines crossed."], unit="county", **kw),
        Board("fred-unemployment-big-nonprofits", "High-unemployment counties with the biggest nonprofits", "Jobless Next Door",
              "Counties (population 10,000 or more) with a nonprofit reporting $50 million or more in revenue, ranked by "
              "their latest monthly unemployment rate.",
              "Value = the county's latest unemployment rate (BLS Local Area Unemployment Statistics, monthly, not seasonally "
              "adjusted, via FRED); the biggest nonprofit is the one with the largest latest-return revenue placed in the "
              "county. " + SOURCE,
              _unemployment_big_nonprofits(), Column("value", "Unemployment rate", "pct"),
              [Column("month", "Month"), Column("rate_year_ago", "A year earlier", "pct"), Column("biggest", "Biggest nonprofit"),
               Column("biggest_revenue", "Its revenue", "money"), Column("nonprofit_revenue", "All nonprofit revenue", "money"),
               Column("nonprofits", "Nonprofits", "num"), Column("population", "Population", "num"),
               Column("poverty_rate", "Poverty rate", "pct")],
              ["Monthly county rates are not seasonally adjusted: farm and resort counties swing with the season."],
              unit="county", **kw),
        Board("fred-pay-vs-county-income", "Nonprofit pay against the county's per capita personal income", "Hometown Multiples",
              "People paid $200,000 or more on a nonprofit's latest return, ranked by their pay as a multiple of the per capita "
              "personal income of the county the nonprofit is based in, for the same year.",
              "Value = the person's reported pay (salary, related-organization pay and other compensation) divided by the "
              "county's per capita personal income (BEA, via FRED) for the return's tax year (the latest earlier year when "
              "that year is not out yet). Pay is also shown in today's dollars (CPI-U annual averages, fred.real_dollars). "
              "The 100 highest paid in each county are considered. " + SOURCE,
              _pay_vs_county_income(), Column("value", "Times the county's per capita income", "multiple"),
              [Column("pay", "Pay", "money"), Column("pay_real", "Pay in today's dollars", "money"), Column("title", "Title"),
               Column("county", "County"), Column("pcpi", "County per capita personal income", "money"),
               Column("pcpi_year", "Income year", "year"), Column("poverty_rate", "County poverty rate", "pct")],
              ["Per capita personal income counts every resident, children included, so the multiples run higher than "
               "against the median household income."], unit="person", **{**kw, "org_label": "Organization"}),
    ]


ALTERNATIVES = {
    "fred-income-down-nonprofits-up": ["Charity Up, Paychecks Down", "Crossing Lines", "Richer Charities, Poorer Towns"],
    "fred-unemployment-big-nonprofits": ["Jobless Next Door", "Big Charity, No Work", "Idle Hands, Full Coffers"],
    "fred-pay-vs-county-income": ["Hometown Multiples", "Pay vs. the County", "Local Paycheck Multiple"],
}
