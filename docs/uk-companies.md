# UK companies (Companies House) - 2026-11-14

Schema `uk_companies`; code: `loader/uk_companies.py` (download, load, psc, psc_us, summarize, nightly), `loader/uk_companies_xref.py`
(match, publish, sample), `app/uk_companies.py` (pages), `app/uk_company_boards.py` (3 boards). Raw files: `/bulk/companies_house/`
(`basic.zip` 0.5 GB, `psc.zip` 2.7 GB zipped / 15 GB of JSON lines). Status log: `~/claude_scripts/companies_house/status.log`.

## Sources and terms
- Free Company Data Product, https://download.companieshouse.gov.uk/en_output.html: `BasicCompanyDataAsOneFile-YYYY-MM-DD.zip`,
  every LIVE company (about 5.7 million), refreshed within five working days of month end. "Provided free of charge and will not be supported."
  Dissolved companies are not in it.
- PSC snapshot, https://download.companieshouse.gov.uk/en_pscdata.html: `persons-with-significant-control-snapshot-YYYY-MM-DD.zip`
  (daily; we refetch when ours is 25+ days old or a new basic file appears).
- Officers: there is no free bulk officers file. They come from the REST API (`api.company-information.service.gov.uk`) with the free key
  the owner supplied (2026-11-14): `COMPANIES_HOUSE_API_KEY` in `.env` on dev and prod, never in code, logs or URLs. See "Officers and profiles" below.
  The streaming API (stream.companieshouse.gov.uk) needs a separate STREAM key: not created, not used (it would keep companies current between monthly snapshots).
- Licence: Open Government Licence v3.0. Attribution everywhere the data shows: "Contains public sector information licensed under the
  Open Government Licence v3.0. Source: Companies House." (`app/uk_companies.ATTRIBUTION`, /data#uk-companies).
- Privacy: for individual PSCs we keep name, nationality, country of residence, birth month/year (page shows the year) and nature of control;
  the address and day of birth are dropped. `psc_us_state` keeps only the state of US-resident individuals, for the person link.

## Commands
```
python -m loader.uk_companies download load psc psc_us summarize     # first load (about 40 minutes on dev)
python -m loader.uk_companies nightly                                # exit 10 = new snapshot loaded, 0 = nothing new
python -m loader.uk_companies_xref match | publish | sample METHOD --n 50 | status
```
`publish` (writes xlinks, linker `ukco:<method>`) runs automatically from `nightly` only after the first manual `publish` (meta key `xlinks`),
which waits for the prod deploy. Boards: `scripts/load.py boards --only uk-companies-new-by-sic,uk-psc-networks,uk-company-status-by-region`.

## Tables
company, previous_name, psc (loaded as *_new then swapped), company_psc, psc_person, sic, psc_us_state, xmatch, psc_match, meta.

## Cross-reference methods
See the docstring of `loader/uk_companies_xref.py`: charity_number, biz_uk_home, biz_same_zip, biz_us_origin, sec_plc, formd_uk, psc_person.
SEC Exhibit 21 subsidiary lists are not in FURP, so there is no subsidiary-list rule.

## Officers and profiles (REST API, 2026-11-14)
Code: `loader/uk_officers.py` (fetcher), `loader/uk_officers_xref.py` (cross-references). Pages: officers on `/uk/company/<number>`, `/uk/officer/<id>`
(the officer id from the API's `links.officer.appointments`), officer matches in `/uk/companies/search`, three boards in group `uk-companies`
(`uk-officers-most-appointments`, `uk-officers-also-trustees`, `uk-officers-also-us`).
- Terms (developer.company-information.service.gov.uk): 600 requests per rolling 5 minutes per key, 429 beyond; applications that regularly exceed it may be banned.
  We use a sliding-window limiter at **575 per rolling 300 s**, shared by 3 worker threads, firing the next request the moment a slot opens, 24/7 (about 165,000
  requests a day). 429 or Retry-After: logged in `~/claude_scripts/companies_house/walls.log`, wait until allowed, resume. Fixed User-Agent
  "furp.org data loader (info@furp.org)". 401/403 stops the fetcher and writes `AUTH_FAIL` (the watchdog waits an hour).
- One key, one limit, ONE fetcher: dev only. A Postgres advisory lock (id 778102, shared database) makes a second copy exit at once; `ensure` only starts it where
  `~/claude_scripts/companies_house/RUN_HERE` exists (dev). Watchdog: dev cron every 3 minutes and at reboot, plus `scripts/nightly.sh`. The limiter window is rebuilt
  from `uk_companies.fetch_bucket` on restart so a restart never bursts.
- Data kept: officer name, role, appointed/resigned, nationality, country of residence, occupation, birth month and year, correspondence address as country and UK
  postcode area only. Never the day of birth or residential address. Profile: accounts and confirmation-statement dates and overdue flags, charges, insolvency history,
  can_file, jurisdiction, previous names, SIC, officer counts.
- Queue `uk_companies.fetch_queue` (priority, ord = days since incorporation so newest first, state pending/working/done/notfound/error): 1 UK charity company number;
  2 linked to US entities, SEC or Form D filers; 3 PSC matched a FURP person; 4 PSC network of 5+ companies; 5 SIC codes of holding, funds, charities, education, health, social care,
  membership bodies; 6 everything else. Priorities 1-5 get profile and officers (about 2.1 requests per company), priority 6 officers only (about 1.1). The SEC and Form D linked
  companies (about 1,000) were moved to the front of priority 1 on 2026-11-14 so the US cross-references could be sampled early. Priority 1-3 companies are refetched every 45 days;
  `enqueue` (nightly) adds companies from new monthly snapshots.
- Status line every 30 minutes in `status.log` (done, queued per priority, real rate, wall hits); daily counters in `uk_companies.fetch_daily`.
- Commands: `python -m loader.uk_officers enqueue | run | ensure | status | summarize`; `python -m loader.uk_officers_xref match | publish | sample METHOD --n 50 | status | refresh`.
- Officer cross-references (linker `ukoff:<method>`, xlinks kind `uk_officer`, key = officer id): `trustee_linked_charity` (high), `trustee_linked_charity_fl` (medium),
  `us_insider_same_company` (high), `formd_party_same_issuer` (high), and `us_unique_name` (low, never published). A name alone never links: a shared charity or company is required.
  Published only after the prod deploy (first `publish` is manual; the nightly `refresh` keeps it current).
- Boards count only companies fetched so far; coverage grows daily, which each board's method text says.
