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
- Officers: there is no free bulk officers file. The REST API (`api.company-information.service.gov.uk`, 600 requests per 5 minutes) and the
  streaming API need a free API key; none was created or requested. With a key the owner could add officers per company on demand, and
  the streaming API would keep companies current between monthly snapshots (key from developer.company-information.service.gov.uk).
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
