# np-explorer

Nonprofit people search. Type a name and see every IRS Form 990 that person
appears on: every organization, title, year and dollar, linked to the filing
itself. Live at <https://strategystudio.org>.

Free, open source (MIT), no ads, no login.

## What's in it

- **People**: officers, directors, trustees, key employees and highest-paid
  employees from Form 990 Part VII Section A, Form 990-PF Part VIII and Form
  990-EZ Part IV, with Schedule J compensation breakdowns where filed.
- **Contractors**: the top independent contractors (990 Part VII Section B,
  990-PF Part VIII, 990-EZ).
- **Organizations**: name, address, website, NTEE code, mission and finances
  across years, from the filings and the IRS Business Master File.
- **The filings**: every e-filed 990, 990-EZ and 990-PF, viewable field by
  field with the IRS element names shown for citation.

E-filed returns only. Paper filers and 990-N postcard filers aren't included.

## Architecture

```
IRS downloads ──► scripts/load.py ──► Postgres ◄── app (FastAPI + Jinja2) ◄── nginx ◄── you
 zips, index CSVs     │ parse in 8 processes,        organizations, filings, people,
 BMF CSVs             │ COPY into stage_* tables,    schedule_j, contractors, related_orgs,
                      │ move per zip in 1 txn        person_clusters, loader_progress
                      ▼
               /data/raw  (zips, indexes, BMF)
               /data/xml  (each filing, gzipped, for the filing viewer)
```

- `loader/mapping.py`: the mapping table from logical fields to XML paths, per
  schema era. The IRS renamed almost every element with the 2013v3.0 schemas,
  so each field lists candidate paths for 2009v1–2012v4 and for 2013v3 onward.
  Unknown schema versions are parsed with the nearest era and logged to
  `/var/log/np-explorer/loader-errors.log`; they never stop a load.
- `loader/parser.py`: turns one XML return into filing, people, contractor,
  Schedule J and Schedule R rows, plus grants (Schedule I Part II; 990-PF
  grants paid), donor-advised fund figures (Part IV flag; Schedule D Part I),
  990-PF payout figures (Parts X-XII), Schedule L Part II loans, and every
  expense line (990 Part IX with its columns and the filer's descriptions;
  990-EZ and 990-PF Part I), with lines the filer describes as events marked.
- `loader/extras.py`: the tables for those last four (`grants`, `daf_stats`,
  `pf_payout`, `insider_loans`, `expense_breakdown`), written by every load;
  `scripts/load.py backfill-extras` reads them from the stored XML of filings
  loaded earlier (resumable, idempotent), then builds their indexes. Grants to
  individuals keep the amount but not the name. Recipients link to
  organizations by the EIN the grantor reported (990-PF grants have no EIN
  column; organization pages match those by exact name and state).
- `loader/ingest.py`: parallel parsing and the staging-table load. Every zip
  (or, for 2011–2016, every 10,000-filing chunk) loads atomically and is
  recorded in `loader_progress`, and every object id in `loaded_objects`, so
  a restart never reprocesses or duplicates anything.
- `loader/cluster.py`: groups people rows into person clusters (rules below),
  builds new tables beside the live ones and swaps them in.
- `app/`: the website and JSON API.

### Data sources

| What | Where |
|---|---|
| 990 XML, 2017 onward | IRS [Form 990 series downloads](https://www.irs.gov/charities-non-profits/form-990-series-downloads): `index_YYYY.csv` and the yearly/monthly zips at `apps.irs.gov/pub/epostcard/990/xml/` |
| 990 XML, 2011–2016 | The original IRS release on AWS, mirrored by GivingTuesday at `gt990datalake-rawdata.s3.amazonaws.com` (individual `{object_id}_public.xml` files plus an all-years index) |
| Organization details | IRS Exempt Organizations Business Master File, `irs.gov/pub/irs-soi/eo1.csv`…`eo4.csv` |

Years are IRS *release* years: the 2025 files are returns the IRS processed in
2025, mostly for tax year 2024.

## How people are linked ("clustering")

Many people share a name, so we only link records when there is evidence, and
every link records why it was made. Person pages show the reasons under "Why
these are linked".

1. **Same name, same organization**: rows with the same normalized name at
   the same EIN in different years are the same person.
2. **Name variants at one organization**: "John Smith" and "John A. Smith" at
   the same EIN are the same person, unless the middle names conflict.
3. **Same name at two organizations** is linked only with evidence:
   - the organizations list each other as related on Schedule R;
   - the organizations share a street address (unless 20+ organizations
     share it, like a registered agent), or the person's own listed address
     matches (990-PF lists officer addresses);
   - **co-board overlap**: the two organizations share at least two *other*
     people's names.
4. **Institutions are one record.** Banks, trust companies and firms listed as
   officers or trustees (Bank of America serves thousands of foundations) are
   tagged as institutions and kept out of the people results. Records with the
   same name once suffixes like "N.A." and "Trustee" are dropped are merged:
   "Bank Of America", "Bank Of America N A" and "Bank of America NA Trustee"
   are one page.
5. **Otherwise they stay separate.** A cluster never holds conflicting middle
   names, so a bare "John Smith" can't chain "John A. Smith" to "John B.
   Smith".

Names are normalized before comparison: lowercased, accents and punctuation
removed, "Last, First" flipped, honorifics (Dr., Rev.) and credentials (MD,
PhD, CPA) dropped, and suffixes (Jr., III) kept in a standard form.

A person's URL is `/person/{id}`, where the id is the smallest people-row id
in the cluster. Ids stay stable as years are added, and if a later merge
retires an id, the old URL redirects. Spot a wrong link? Use the "Not the
same person? Report it" link on the page.

## Search

The search box has a **Name / Firm** select (Name is the default). **Firm**
searches organizations and lists each one's people: latest title, years,
latest-year pay, total pay from that organization, and how many organizations
each person serves, linked to their pages. Everything cross-links: a person's
filings link to each organization and to "everyone at this firm"; an
organization's page lists everyone who has served there across all years.
New search types go in `SEARCH_TYPES` in `app/main.py`.

For name searches, results come in three labeled sections: **exact matches** (every word you typed,
as whole words, in order), **close matches** (names starting with your words in
order, or spelled almost the same) and **other matches** (similar spellings and
sounds-alike names). Institutions are listed in their own section.

`/search?q=` ranks people by pg_trgm word similarity ("mauborgn" finds Renee
Mauborgne), with whole-word and prefix token matching as fallback ("mich olen"
finds Michael Olenick; queries of short words skip the trigram step, which needs
five or more letters to be selective). An exact full-name match ranks first,
then names whose words start with the query words in order, then similarity,
then number of filings. Names that sound alike (Soundex) are added only when
little else matches. Results are grouped by person cluster, 50 per page, and
can be narrowed by state, years, title, minimum compensation and organization
name. Contractor and organization matches follow below the people.

Name indexes: tsvector GIN, Soundex tsvector GIN, `text_pattern_ops` prefix
btrees, first/last-name btrees, and (with `pg_trgm`) trigram GIN on people,
person clusters, contractors and organizations.

## Ask (plain-English search)

`/ask` (also the "Ask" choice in the search box) takes a question such as
"Who runs the Workforce Incubator Foundation?" and sends it to Anthropic's API
(`claude-haiku-5-5`, `NP_ASK_MODEL` to change) with five tools: people search,
an organization's people, organizations by name/city/state (optionally only DAF
sponsors), an organization's money (finances, spending, grants made or
received, DAFs) and a leaderboard. The model picks one tool and its
parameters; `app/ask.py` runs the site's own query for it. The model never
writes SQL, so a question can't make the database do anything the site
doesn't already do, and answers come from the filings, not the model. The page
shows how the question was read and links to the full page. Limits: 20
questions per IP per hour, 2,000 model calls per worker per day, answers
cached for a day; `ANTHROPIC_API_KEY` in `.env` turns it on.

Firm and DAF searches also take `state` and `city` (the "More options" panel
under the search box); with a place and no name they list every organization
there, largest first.

## JSON API

Same data as the pages, rate-limited to about one request a second per IP:

- `GET /api/search?q=NAME[&state=&year_from=&year_to=&title=&min_comp=&org=&page=]`
- `GET /api/search?type=firm&q=ORGANIZATION[&page=]`: organizations with their people and pay
- `GET /api/person/{id}`
- `GET /api/org/{ein}`

OpenAPI docs at `/api/docs`.

## Leaderboards

`/boards` lists ranked boards built straight from the filings; `/boards/<slug>`
shows one (filters: tax year, form, state; 50 a page), with its plain-English
definition, exact rule, caveats, coverage window and the standing line:
"Unusual is not the same as improper. Many of these patterns have ordinary explanations. Check the filing." Each board also serves `/boards/<slug>.csv`,
`/api/boards/<slug>` (JSON; `/api/boards` lists them) and a 1200x630 share card
at `/boards/<slug>.png` (used for link previews). The `/boards` search box (and
the Boards option in the main search) shows every board a person, organization
or vendor appears on, with their best rank.

Each board is a materialized view (`board_<slug>`) defined in `app/boards.py`
and built by `loader/boards.py` (`scripts/load.py boards`); it is refreshed
after every re-cluster (nightly and during `all`). A board whose SQL changed is
rebuilt beside the live one and swapped in. `board_meta` holds row counts and
the tax-year window; `board_entries` indexes who appears where, for search.

Launch scope: filings reporting at least `NP_BOARD_MIN_REVENUE` ($10,000,000)
revenue or `NP_BOARD_MIN_ASSETS` ($50,000,000) total assets that year.
Person-level boards (`revolving-door`, `family-plan`) are built but hidden until
`NP_BOARDS_PERSON_LEVEL=true`. Fundraising expenses (for the cost-per-dollar
board) were backfilled with `scripts/load.py backfill-fundraising`
(`--all` for every 990, not just the board scope).

| Slug | Board | Exact rule |
| --- | --- | --- |
| `top-paid` | Highest-paid people ("The Corner Office") | Total = reportable pay from the organization + reportable pay from related organizations + other compensation (Form 990 Part VII; 990-EZ Part IV; 990-PF Part VIII). One row per person per tax year: their largest single filing. Floor $250,000. Institutions (banks acting as trustee, entries titled institutional or corporate trustee) and group-return placeholder rows excluded. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `top-vendors` | Highest-paid vendors ("Invoice Royalty") | Compensation to one contractor on one filing (Form 990 Part VII Section B; 990-PF Part VIII). Thresholds: $100,000 on the 990, $50,000 on the 990-PF (the forms' own reporting floors). Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `dragon-hoard` | Cash reserves in years of spending ("Dragon Hoard") | Years = net assets at year end / total expenses for the year (total assets when net assets aren't reported). Organizations with expenses under $500,000 excluded. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `expensive-dollar` | Fundraising cost per dollar raised ("The Most Expensive Dollar") | Cost = total fundraising expenses (Form 990 Part I line 16b, Part IX column D) / contributions, gifts and grants (Part VIII line 1h). Form 990 only; contributions of at least $500,000. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `small-org-big-check` | Highest single salary at organizations with under $1M revenue ("Small Org, Big Check") | One row per filing: the person with the largest total pay (as on Highest-paid people) where total revenue was under $1,000,000. Institutions excluded. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year (so these are asset-rich organizations with small revenue). |
| `biggest-swings` | Biggest year-over-year jumps ("Biggest Swings") | Multiple = this year / prior year, for the same EIN in consecutive tax years. Revenue: prior year at least $50,000. Officer pay: the same normalized name at the same EIN (an EXACT match), prior year at least $50,000. Multiple of at least 10. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year (in the later year). |
| `phantom-staff` | Large revenue, one employee or none ("Phantom Staff") | Total revenue of at least $5,000,000 and total employees (Form 990 Part I line 5) of 0 or 1. Form 990 only. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `lookalikes` | Organizations with nearly identical names ("Lookalikes") | Trigram similarity of the two names (PostgreSQL pg_trgm) of at least 0.9, different EINs. One row per organization reporting $10,000,000 in revenue or $50,000,000 in assets on its latest e-filed return: its closest lookalike (the largest, when several are equally close) and how many it has. Latest filing shown. |
| `shared-vendors` | Vendors paid by many organizations ("Everybody's Contractor") | Count of distinct EINs listing the same normalized contractor name in one tax year (Form 990 Part VII Section B; 990-PF Part VIII), with the combined amount. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. The filing shown is the largest single payment. |
| `insider-loans` | Loans between organizations and insiders ("In-House Lending") | Schedule L Part II: one row per loan with a balance due at year end, as reported (direction, original principal, balance, default, board approval, written agreement). Form 990 only. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `hugging-the-floor` | Foundations paying out right at the legal minimum ("Hugging the Floor") | Payout = qualifying distributions (990-PF Part XII line 4) / net value of noncharitable-use assets (Part X line 5). The minimum investment return is 5% of that line (Part X line 6). Longest run of consecutive tax years at 5.0% to 5.2%, at least 5. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `funding-loops` | Largest grant went to an organization sharing a board member ("Funding Loops") | Largest single grant on the filing (Schedule I Part II, or 990-PF grants paid) to an organization we can identify: by the EIN the grantor reported, or, on the 990-PF (which lists no EINs), by an exact, unique name and state. A person on the grantor's filing is linked to a person on the grantee's filing for the same tax year. EXACT: the same normalized name on both. FUZZY: linked records with different spellings. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |
| `contractor-insiders` | Contractors at the organization's address or with an insider's name ("Close to Home") | Contractor (Form 990 Part VII Section B; 990-PF Part VIII) whose street address matches the organization's (letters and digits only, same ZIP) or whose normalized name equals the name of an officer, director, trustee or key employee on the same filing. Filings from organizations reporting at least $10,000,000 in revenue or $50,000,000 in total assets that year. |

Tests: `tests/test_boards.py` runs every board's SQL over hand-made fixture
rows in a throwaway schema (needs `DATABASE_URL`).

## Running locally

```sh
docker compose up -d                                   # Postgres 16 + the app on :8000
docker compose exec app python scripts/load.py bmf     # ~2M organizations
docker compose exec app python scripts/load.py fetch 2025
docker compose exec app python scripts/load.py parse 2025
docker compose exec app python scripts/load.py cluster
docker compose exec app alembic upgrade head           # trigram indexes (pg_trgm)
```

Or without Docker: Python 3.12, `python -m venv .venv && .venv/bin/pip install
-r requirements-dev.txt`, put `DATABASE_URL=postgresql://...` in `.env`, run
`alembic upgrade head`, then `uvicorn app.main:app --reload`.

Tests: `.venv/bin/python -m pytest`. The parser tests run against real filings
of each form type across schema versions in `tests/fixtures/`.

## Loading data

```
scripts/load.py bmf           Business Master File into organizations
scripts/load.py index         IRS yearly indexes (and 2011-2016 indexes from the mirror)
scripts/load.py fetch YEAR    download a year's zips (stops below 20 GB free)
scripts/load.py parse YEAR    parse and load a year (resumable)
scripts/load.py cluster       rebuild person clusters
scripts/load.py sitemap       rebuild the sitemap index
scripts/load.py all           everything: newest full year first, then backfill to 2011
scripts/load.py nightly       new IRS zips, re-cluster, leaderboards, sitemap (run by cron)
scripts/load.py boards        build or refresh the leaderboard views
scripts/load.py reparse YEAR  refresh filing fields from stored XML after a mapping fix
```

The loader prints one line a minute (to stdout and
`/var/log/np-explorer/loader.log`): elapsed time, year, filings, people,
contractors, rate, errors, disk free and ETA. Per-filing problems go to
`loader-errors.log`.

## Production (strategystudio.org)

- `np-explorer.service`: uvicorn with 4 workers on 127.0.0.1:8000.
- `np-loader.service`: `load.py all`, the long backfill. It survives SSH
  disconnects and restarts on failure, except a low-disk stop.
- `/etc/cron.d/np-explorer`: `scripts/nightly.sh` at 03:30.
- nginx proxies everything to the app except `/static`, the root icon files,
  `robots.txt` and `/sitemap.xml` and `/sitemaps/` (served from `/data/sitemaps`).

Config files live in `deploy/`.

Abuse protection and cost guardrails (no third-party services):

- nginx (`deploy/nginx/np-limits.conf` in `conf.d`, the site file, and
  `np-bad-agents.conf`): per-IP rate limits of 30 a minute (burst 10) on search
  and person pages and their JSON, 120 a minute on other pages (person popups
  count here), none on static files; 20 connections per IP; 429s get a "Slow
  down" page with `Retry-After: 60`. Empty user agents and a short list of
  abusive scrapers get 403 (search engines and browsers are never on it). 64 KB
  request bodies, short client timeouts, gzip, a year's cache on `/static`
  (style.css and site.js are linked with a content hash, so changes show at
  once). Rate-limited requests are also logged to `/var/log/nginx/np-limited.log`.
- fail2ban (`deploy/fail2ban/`): an IP with 20 rate-limited requests in five
  minutes is blocked from ports 80/443 for an hour. Localhost and this VM are
  never banned. The Debian SSH jail is switched off; SSH is managed separately.
- App: database statements from web requests stop after 5 seconds (set on the
  web pool's connections, not the loaders'); at most 10 connections per worker
  (40 in all), with a short wait queue; queries capped at 100 characters and
  results at the first 1,000 (20 pages); board pages at 200 and CSV downloads
  at 10,000 rows; identical searches and person pages within 60 seconds are
  answered from memory.
- `scripts/traffic.py [--minutes 60] [--top 20]`: top IPs (with their 429s)
  and user agents from the nginx logs.

The contact form (`/contact`) emails each message to info@strategystudio.org
through Postmark (`POSTMARK_SERVER_TOKEN` in `.env`), with the sender as
Reply-To. Nothing is stored. Spam checks, no third-party scripts: a hidden
honeypot field, a signed timestamp (`CONTACT_FORM_SECRET`) that rejects
submissions under three seconds, five sends per IP per hour, and at most two
links. If Postmark fails, the message goes to `logs/contact-failed.jsonl`
(mode 600, gitignored) so it isn't lost. Copy `.env.example` to start.

On Azure Database for PostgreSQL, `pg_trgm` must be allow-listed (server
parameter `azure.extensions`) before `alembic upgrade head` can create the
trigram indexes. Search works without it, minus trigram fuzzy matching.

## Contributing

Issues and pull requests are welcome at
<https://github.com/michaelolenick/np-explorer>.

Before your first commit, install the secret-scanning pre-commit hook:

```sh
scripts/install-hooks.sh
```

It installs a pinned, checksum-verified [gitleaks](https://github.com/gitleaks/gitleaks)
into `.venv/bin` (unless one is already on your PATH) and points git at
`.githooks/`, so every commit is scanned and blocked if it contains a secret:
API keys, private keys, a Postgres URL with a password, an Azure database
host. The rules live in `.gitleaks.toml`. CI runs the same scan over the full
history on every push and pull request (`.github/workflows/gitleaks.yml`), and
any finding fails the build. Never commit `.env`; it's git-ignored for a reason.

Useful places to start:

- Schema coverage: if a field comes out empty for some years, add the missing
  element path to `loader/mapping.py`, add a fixture filing and a test, then
  `scripts/load.py reparse YEAR`.
- Clustering mistakes: a person page URL and what's wrong helps the most.
- Keep the design as it is: black on white, Courier, no JavaScript needed.

## Credits

Data: the Internal Revenue Service, which publishes e-filed Form 990 returns
and the Exempt Organizations Business Master File. Pre-2017 returns come
through GivingTuesday's mirror of the IRS's original AWS release.

Thanks to Anthropic and Microsoft, whose credits paid for this.

## License

MIT. See [LICENSE](LICENSE).
