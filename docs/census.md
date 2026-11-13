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

## Nationwide rankings, comparisons, organizations by county measure (2026-11-13)

"list Counties with the highest share of foreign-born residents" came back "No results" although the data was loaded:
the planner's plan was right (census_area, foreign_born_share, children county, place United States) but
`census.answer()` looked the place up in `census_area`, which has no nation row, and `ranked()` only knew a state's
counties. Now:

- `census.nation_area()` builds the United States from the states (counts summed, rates population-weighted,
  medians blank); `lookup()` returns it for "United States", "US", "nationwide", "the country" and the like, and
  `answer()` assumes it when a ranking names no place.
- `ranked()` runs in SQL for any parent (nation, state, county) with `limit` (top N, at most 100); nationwide it
  leaves out areas under `NATION_MIN_POP` residents (10,000 for counties and places) so the tiniest do not crowd
  the top, and the page says so.
- Rule-based parsing (`census.question()`) covers rankings with or without a place ("which counties have the
  longest average commute?", "counties in Texas with the lowest poverty rate", "top 10 ..."), "compare <measure>
  in A and B" (both places side by side, the asked-for measure first), and `census.org_question()` turns "food
  banks in the poorest counties" into an `orgs_in_topic` intent with `area_measure`, which `rank_topic_by_area()`
  runs: each organization gets its county and the value, ranked. Synonyms live in `MEASURE_WORDS` (foreign-born,
  born abroad, share of foreign born, poverty rates, average commute time, ...) and `RANK_WORDS` (bare nouns such
  as immigrants, children, seniors that count only inside a ranking or a comparison, so "immigrants in Queens"
  stays an organization search).
- The planner tool `census_area` gained `limit` and `compare_with`, `orgs_in_topic` gained `area_measure` and
  `area_lowest_first`, and both descriptions and the system prompt list the measures with their synonyms.
- Zero rows: `ask.broaden()` tries one wider plan (a state's ranking becomes the country's; a filter is dropped)
  and the page says "No results for X. Showing Y instead."; when nothing can be widened the empty page offers
  census questions (`census.suggestions()`, the asked-for measure's first) and a checked idea only if it shares
  two words with the question.
- Names: 377 areas (Doña Ana, the Puerto Rico municipios) were double-encoded by the NHGIS load; repaired in
  `census_area` and `nhgis.geo`, `loader/nhgis.py` now undoes the encoding on load, and `slugify()` transliterates
  accents (dona-ana-county).
- Regression tests: `tests/test_census_queries.py` pins the owner's eight questions, their intents, the rows, the
  pages, the broader retry and the suggestions.
