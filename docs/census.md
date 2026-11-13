# The census on FURP

The census tables are IPUMS NHGIS extracts (ACS 2020-2024 five-year estimates and the 2020 Demographic and Housing
Characteristics), loaded into schema `nhgis` by `loader/nhgis.py` and summarised by `loader/census.py` into:

- `census_area`: one row per state, county, place and tract with the headline measures (`MEASURES` in
  loader/census.py: population, median household income, poverty rate, education, housing, race and ethnicity,
  foreign-born share, age shares, unemployment, labor force, mean commute).
- `census_links`: every FURP record kind with an address (org, contractor, college, formd, lda_client, fec_committee,
  f5500, op_recipient, recallfirm, ip_firm, ipo, fed, biz) to its state, county, place and tract GISJOIN, placed by
  ZIP code (`census_zip_county`, `census_zip_tract`) and city name (`geo_places`), never by street address.
- `census_area_furp` and `census_area_people`: per-area roll-ups for the pages under `/census`.

Pages: `/census`, `/census/<st>`, `/census/<st>/<county>`, `/census/<st>/place/<place>`, `/census/tract/<geoid>`,
`/census/tables`, `/census/area` (find by ZIP or city), `/census/of/<kind>/<key>` (the census page of one record;
the "area" links on leaderboard rows). Entity pages show "The area" (`templates/_census_area_section.html`). The API
has `/api/v1/area` and profiles carry `census_area`; the MCP server has `get_area`. Citation: `app.census.CITATION`.

## Census context in search results (2026-11-13)

Owner: "make sure the census data is integrated into the results of everything else ... make sure to show
demographic data. If somebody asks about education show ed levels or housing ... make sure the models know about
the census tables".

**The panel.** Every result list shows "The places behind these results" (`templates/_census_places.html`): the
rows are placed (by their `census_links` row when they carry an EIN, a school id, a record URL or a firm id; else by
ZIP, city and state), grouped by county (plus the city when most rows are in one), and the top eight areas are shown
with the measures that fit the question, each area linking to its `/census` page (and the county map colored by the
first measure), each figure to its table at data.census.gov, with one or two FURP-style comparisons (the top pay
against the county's median household income; the listed organizations' revenue per resident; the lead county's
figure against the state's) and the state's own figures as a reference row. `app/census.py`:

- `topic(question)`: the measures for the question's subject (`TOPIC_MEASURES`): housing (units, owner and renter
  shares, home value, rent, income), education (bachelor's share, income, poverty, under 18), immigration
  (foreign-born, Hispanic, Asian shares), seniors (65 and over, median age), children (under 18, households, family
  income), health (poverty, 65 and over, foreign-born, income), jobs (unemployment, labor force, commute), race (the
  race shares), poverty and food (poverty, income, per-capita income); otherwise population, median household
  income, poverty rate and bachelor's share.
- `places_for_rows(question, rows, kind)`, `places_for_result(question, result)` (an `/ask` result of any kind:
  rows, or the one organization or school it is about), `places_for_search(q, ctx)` (the classic results page).
  A few batched queries, cached five minutes per question (`_places`), nothing when `census.ready()` is false.
- `places_facts(places)`: the panel as compact data for the short answer; `places_out(places)`: the `areas` block of
  `/api/v1/search` and the MCP `search` tool.

**The written answer** (`app/answer.py`): DATA gets `census` (the areas, their figures as the page shows them, the
comparisons, the state for comparison) and the model is told to use a figure when it bears on the question, quoting
it as given; the answer cache key carries `#census` so answers written before this are written again.

**Deep queries** (`app/deep.py`): the planning prompt describes `census_area`, `census_links` and
`census_zip_county` with worked joins; the plan may set `census_measure`, and cohorts (topic, pay by year, funders)
get "Where they are: counties" with population, median household income and poverty rate, plus the organizations
ranked by their county's measure when one was asked for.

**The planner** (`app/ask.py`): the `census_area` tool (place, state, measure, children, lowest_first) and a SYSTEM
note that measure-of-a-place questions are census questions, never unknowns. Before the model, `census.question()`
reads them by rule: "median rent in Austin, TX", "bachelor's degree share in Travis County", "Travis County poverty
rate", "poverty rate of Mississippi counties" and "poorest counties in Mississippi" (a state's counties, or a
county's cities or tracts, ranked by the measure), answered from `census_area` with the matching fact group first
and a map link (`templates/_census_result.html`).

Tests: `tests/test_census_context.py`.
