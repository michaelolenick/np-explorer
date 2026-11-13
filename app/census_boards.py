"""Leaderboards that cross the census with FURP's records (app/census.py, loader/census.py; owner, 2026-11-12).

census_boards() returns Board objects for app/boards.py to append to BOARDS; GROUP goes in boards.GROUPS. The views
read census_area (the measures per county and place), census_area_furp (records per area) and census_area_people
(the highest-paid people per area), all built by loader/census.py after the nightly census load. Year is the ACS
estimate's end year (2024). Shown only where CENSUS_PUBLIC=1.
"""

from __future__ import annotations

GROUP_NAME = "census"
GROUP = {"title": "Places: the census against the records", "subtitle": "Zip Code Lottery",
         "definition": "Counties and cities measured against the people and money in FURP's records: nonprofit "
                       "revenue per resident, nonprofits per 10,000 people, executive pay as a multiple of the local "
                       "median household income, big nonprofits in high-poverty counties, federal money per resident. "
                       "Census figures from IPUMS NHGIS (ACS 2020-2024)."}
SOURCE = ("Census figures are American Community Survey 2020-2024 five-year estimates by county or place, via IPUMS "
          "NHGIS (Schroeder et al., IPUMS NHGIS Version 21.0, 2026, http://doi.org/10.18128/D050.V21.0). FURP records "
          "are placed in a county by ZIP code (the county holding most of the ZIP's land) and in a place by city name. "
          "Nonprofit revenue is each organization's latest return.")
MIN_COUNTY_POP = 10_000
MIN_PLACE_POP = 25_000
ACS_YEAR = 2024


def _areas(level: str, kind: str, value: str, where: str, min_pop: int) -> str:
    """One row per area of one level with the records of one kind in it."""
    from app.boards import _ranked_by_org, norm_sql
    name = ("a.short_name || ', ' || a.stusab" if level == "county"
            else "regexp_replace(a.short_name, '\\s+(city|town|village|borough|CDP|municipality)$', '') || ', ' || a.stusab")
    url = ("'/census/' || lower(a.stusab) || '/' || a.slug" if level == "county"
           else "'/census/' || lower(a.stusab) || '/place/' || a.slug")
    inner = f"""
        SELECT '{level}'::text AS subject_kind, a.gisjoin AS subject_key, {name} AS subject_name,
               {norm_sql(name)} AS subject_norm, {url} AS subject_url, NULL::text AS match,
               NULL::text AS ein, NULL::text AS org_name, a.stusab AS state, 'ACS'::text AS form_type,
               {ACS_YEAR} AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value,
               NULL::text AS org_url,
               'https://data.census.gov/table/ACSDT5Y{ACS_YEAR}.B19013?g=' || (CASE WHEN a.level = 'county' THEN '0500000US' ELSE '1600000US' END) || a.geoid AS source_url,
               a.population, a.median_hh_income, a.poverty_rate, a.median_age, f.n AS records, f.total,
               f.top_name AS biggest
        FROM census_area a JOIN census_area_furp f ON f.gisjoin = a.gisjoin AND f.kind = '{kind}'
        WHERE a.level = '{level}' AND a.population >= {min_pop} AND {where}"""
    return _ranked_by_org(inner, "value DESC, population DESC, subject_key")


def _pay_vs_income() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'person'::text AS subject_kind, p.cluster_id::text AS subject_key, p.name AS subject_name,
               {norm_sql('p.name')} AS subject_norm, '/person/' || p.cluster_id AS subject_url, NULL::text AS match,
               p.ein, p.org_name, a.stusab AS state, '990'::text AS form_type, p.tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, (p.total / a.median_hh_income)::numeric AS value, '/org/' || p.ein AS org_url,
               'https://data.census.gov/table/ACSDT5Y{ACS_YEAR}.B19013?g=0500000US' || a.geoid AS source_url,
               p.title, p.total AS pay, a.median_hh_income, a.poverty_rate, a.short_name || ', ' || a.stusab AS county,
               '/census/' || lower(a.stusab) || '/' || a.slug AS county_url
        FROM census_area_people p JOIN census_area a ON a.gisjoin = p.county_gj
        WHERE a.level = 'county' AND a.median_hh_income > 0 AND p.rank_county <= 100 AND p.total >= 200000"""
    return _ranked_by_org(inner, "value DESC, pay DESC, subject_key")


def census_boards() -> list:
    from app.boards import Board, Column
    from app.census import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="census", year_label="ACS year",
              source_label="IPUMS NHGIS (ACS 2020-2024) and FURP's records", search=True, org_label="County")
    area_cols = [Column("population", "Population", "num"), Column("records", "Nonprofits", "num"),
                 Column("total", "Nonprofit revenue", "money"), Column("median_hh_income", "Median household income", "money"),
                 Column("poverty_rate", "Poverty rate", "pct"), Column("biggest", "Biggest nonprofit")]
    return [
        Board("census-revenue-per-resident", "Counties with the most nonprofit revenue per resident", "Charity Capitals",
              "Counties (population 10,000 or more) ranked by the latest-year revenue of the nonprofits based there, "
              "per resident.",
              f"Value = the sum of the latest reported revenue of every nonprofit placed in the county, divided by the "
              f"county's population. {SOURCE}",
              _areas("county", "org", "f.total / a.population", "f.total > 0", MIN_COUNTY_POP),
              Column("value", "Revenue per resident", "money"), area_cols,
              ["A county with one big hospital system or university can show tens of thousands of dollars per resident."],
              unit="county", **kw),
        Board("census-nonprofits-per-10k", "Counties with the most nonprofits per 10,000 residents", "Nonprofit Density",
              "Counties (population 10,000 or more) ranked by the number of nonprofits based there for every 10,000 "
              "residents.",
              f"Value = nonprofits placed in the county (every organization in the IRS master file with an address there) "
              f"per 10,000 residents. {SOURCE}",
              _areas("county", "org", "10000.0 * f.n / a.population", "f.n > 0", MIN_COUNTY_POP),
              Column("value", "Per 10,000 residents", "ratio"), area_cols, [], unit="county", **kw),
        Board("census-pay-vs-income", "Nonprofit pay against the local median household income", "Local Multiples",
              "People paid $200,000 or more on a nonprofit's latest return, ranked by their pay as a multiple of the "
              "median household income of the county the nonprofit is based in.",
              f"Value = the person's reported pay (latest year; salary, related-organization pay and other compensation) "
              f"divided by the median household income of the organization's county. The 100 highest paid in each "
              f"county are considered. {SOURCE}",
              _pay_vs_income(), Column("value", "Times the median household income", "multiple"),
              [Column("pay", "Pay", "money"), Column("title", "Title"), Column("county", "County"),
               Column("median_hh_income", "County median household income", "money"), Column("poverty_rate", "County poverty rate", "pct")],
              ["Pay is what the return reports; a hospital executive in a poor rural county tops a bigger salary in a rich suburb."],
              unit="person", **{**kw, "org_label": "Organization"}),
        Board("census-poor-counties-rich-nonprofits", "High-poverty counties with the biggest nonprofits", "Rich Charity, Poor County",
              "Counties where at least a fifth of residents live in poverty, ranked by the latest-year revenue of the "
              "nonprofits based there per resident.",
              f"Value = nonprofit revenue per resident, in counties (population 10,000 or more) with a poverty rate of "
              f"20% or more. {SOURCE}",
              _areas("county", "org", "f.total / a.population", "f.total > 0 AND a.poverty_rate >= 20", MIN_COUNTY_POP),
              Column("value", "Revenue per resident", "money"), area_cols, [], unit="county", **kw),
        Board("census-places-revenue-per-resident", "Cities with the most nonprofit revenue per resident", "Charity Cities",
              "Cities and towns (population 25,000 or more) ranked by the latest-year revenue of the nonprofits based "
              "there, per resident.",
              f"Value = the sum of the latest reported revenue of every nonprofit placed in the city (by its city name), "
              f"divided by the city's population. {SOURCE}",
              _areas("place", "org", "f.total / a.population", "f.total > 0", MIN_PLACE_POP),
              Column("value", "Revenue per resident", "money"), area_cols, [], unit="city", **{**kw, "org_label": "City"}),
        Board("census-federal-per-resident", "Counties with the most federal money per resident", "Federal Lifelines",
              "Counties (population 10,000 or more) ranked by federal grants and contracts to recipients based there, "
              "per resident, over the fiscal years loaded.",
              f"Value = USAspending obligations (all fiscal years loaded) to recipients placed in the county, divided by "
              f"the county's population; filled once the federal recipients are linked (a quiet-hours job). {SOURCE}",
              _areas("county", "fed", "f.total / a.population", "f.total > 0", MIN_COUNTY_POP),
              Column("value", "Federal awards per resident", "money"),
              [Column("population", "Population", "num"), Column("records", "Recipients", "num"),
               Column("total", "Federal awards", "money"), Column("median_hh_income", "Median household income", "money"),
               Column("poverty_rate", "Poverty rate", "pct"), Column("biggest", "Biggest recipient")],
              ["Formula grants to a state agency land in the state capital's county."], unit="county", **kw),
    ]


ALTERNATIVES = {
    "census-revenue-per-resident": ["Charity Capitals", "Nonprofit Per Capita", "Where the Money Sits"],
    "census-nonprofits-per-10k": ["Nonprofit Density", "Charity Per Capita", "Crowded Causes"],
    "census-pay-vs-income": ["Local Multiples", "Pay vs. the Neighbors", "Hometown Multiple"],
    "census-poor-counties-rich-nonprofits": ["Rich Charity, Poor County", "Wealth Next to Want", "The Gap Next Door"],
    "census-places-revenue-per-resident": ["Charity Cities", "Nonprofit Towns", "Per Capita Giving"],
    "census-federal-per-resident": ["Federal Lifelines", "Washington's Share", "Per Capita Pork"],
}
