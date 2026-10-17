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
  Schedule J and Schedule R rows.
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
4. **Otherwise they stay separate.** A cluster never holds conflicting middle
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

## JSON API

Same data as the pages, rate-limited to about one request a second per IP:

- `GET /api/search?q=NAME[&state=&year_from=&year_to=&title=&min_comp=&org=&page=]`
- `GET /api/person/{id}`
- `GET /api/org/{ein}`

OpenAPI docs at `/api/docs`.

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
scripts/load.py nightly       new IRS zips, re-cluster, sitemap (run by cron)
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

On Azure Database for PostgreSQL, `pg_trgm` must be allow-listed (server
parameter `azure.extensions`) before `alembic upgrade head` can create the
trigram indexes. Search works without it, minus trigram fuzzy matching.

## Contributing

Issues and pull requests are welcome at
<https://github.com/molenick/np-explorer>. Useful places to start:

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
