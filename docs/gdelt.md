# GDELT news and events (2026-11-14)

FURP shows, for organizations and people, the news articles that name them. Source: the GDELT Project
(https://www.gdeltproject.org/), Global Knowledge Graph 2.0 (GKG), 15-minute files from 2015-02-18.

**Terms** (https://www.gdeltproject.org/about.html#termsofuse): free for unlimited and unrestricted use, including commercial;
any use or redistribution must include a citation to the GDELT Project and a link to its website. Every "In the news" block,
/news-index and /data#gdelt carry "News article metadata and links: The GDELT Project (https://www.gdeltproject.org/)".
We store metadata and links only (URL, domain, title, date, language, tone, a few themes, name offsets), never article text.
One download per file, User-Agent `furp.org data loader (info@furp.org)`.

## Size (estimated before loading, 2026-11-14)
GKG 2.0 zips: 2.9 TB in all (2015 273 GB, 2016 403 GB, 2017 348 GB, 2018 311 GB, 2019 259 GB, 2020 216 GB, 2021 187 GB,
2022 165 GB, 2023 214 GB, 2024 204 GB, 2025 173 GB, 2026 to date 138 GB); about 1,4 million files, 450 million article records.
The zips are streamed in memory and never kept (raw files cheaper to re-download than to store). Filtered per-day files
(`/bulk/gdelt/parsed`, about 6 MB a day) are kept: they are the raw hits and allow re-resolving without downloading.
Database growth is about 25 MB per day loaded (schema `gdelt`), about 100 GB for 2015-2026; cap 300 GB.

## Pipeline
1. `loader/gdelt_parse.py` (no database; any server): per day, 96 files in memory, keep articles that name a known name,
   write `<day>.a.tsv.gz`, `<day>.m.tsv.gz`, `<day>.done`. Dictionaries (`python -m loader.gdelt dict`): 5.4 M organization name
   cores, 7.2 M person names unique to one person cluster, 2.1 M shared person names (kept only when the article also names a
   known organization); a 2^30-bit prefilter plus exact hash lookup.
2. `python -m loader.gdelt maps` builds `gdelt.org_map` (name core to record) and `gdelt.common_last`; `famous` builds
   `gdelt.famous` (very frequent names) from a sample of parsed days.
3. `python -m loader.gdelt load [--from D --to D --max-days N]`: one transaction per parsed day (`gdelt.loaded_days`, restartable
   by day), a progress line per day, COPY into temp tables, resolve, insert `gdelt.articles`, `gdelt.links`, `gdelt.entity_month`.
   Heavy loads wait for the quiet hours (loader/offpeak.py; all weekend is quiet; NP_NOW=1 skips).
4. `summarize` rebuilds `gdelt.entity_news` (per record: articles, first/last month, this month) and `gdelt.stats` (totals shown
   on the pages; they update themselves). `daily` = parse yesterday, load, summarize (scripts/nightly.sh; the dictionaries are
   rebuilt on Sundays).

## Matching rules (precision first)
* Organization: the GDELT organization's core (loader.recalls.core: lower case, no legal suffix) equals the core of exactly one
  record of a kind (up to 5 for kinds with several ids per company: fed, lda_client, contractor...). Kinds linked: nonprofits (org,
  EIN), sec, college, ipo_company, lda_client, fed, contractor, formd, adv. Single-word nonprofit names that an SEC filer, adviser or
  IPO registrant also carries go to the company. Very frequent names (`gdelt.famous`) keep only sec, college, ipo_company, adv,
  lda_client and nonprofits with $10M or more of revenue.
* Person: (a) the full name belongs to exactly one person cluster in FURP, the surname is shared by fewer than 300 clusters, and
  the name is neither famous (`gdelt.famous`) nor "hot" that day (6 or more articles); or (b) any other case, only when an
  organization of that person's Form 990 filings (people.ein to gdelt.org_map) is named in the same article, and exactly one cluster fits.
  Every link carries `how` in words; pages say a shared name is not proof of the same person.

## Pages and API
"In the news" (latest 10 articles, linked out, attribution) on organization, person, SEC company and college pages
(templates/_news_block.html); /news-index (organizations, nonprofits and people most in the news this month; Research menu);
`/api/v1/xlinks?kind=&key=` and MCP `get_links` return a `news` entry. Pages read the latest articles from the links primary key
(entity, date) and counts from `gdelt.entity_news`; nothing scans the big tables.

## Not done / notes
GDELT 1.0 GKG (2013-04 to 2015-02) is daily, with sources and entities not tied to single articles, so it is not loaded. GDELT
Events/Mentions are not loaded (see status). Business-registry (`biz`) pages do not carry news (names are not unique across
42 M registrations).
