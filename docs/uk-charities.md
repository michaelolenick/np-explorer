# UK charities (Charity Commission for England and Wales)

Owner request, 2026-11-14: "UK 990s", treated like the American nonprofit data.

## Source and licence

- Page: https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download. It says "All content is
  available under the Open Government Licence v3.0, except where otherwise stated" (checked 2026-11-14), so reuse is allowed with
  attribution. The data definition document is `/bulk/uk_charities/doc/dd.docx` (text in `dd.txt`).
- Files: `https://ccewuksprdoneregsadata1.blob.core.windows.net/data/txt/publicextract.<name>.zip` (tab-delimited; a JSON variant
  exists under `/data/json/`), updated daily. Thirteen are loaded (list in `loader/uk_charities.py` FILES). Raw zips are in
  `/bulk/uk_charities/raw`. The loader sends one conditional GET per file with the User-Agent
  `furp.org data loader (info@furp.org)` and pauses three seconds between files.
- Attribution on every UK page and in `/data#uk-charities`: "Contains public sector information licensed under the Open Government
  Licence v3.0. Source: Charity Commission for England and Wales."
- England and Wales only (Scotland's OSCR and Northern Ireland's CCNI keep their own registers). The register has no pay for
  individuals: the nearest figures are the number of staff paid over 60,000 pounds (bands) and whether trustees were paid.

## Tables (schema `uk`, created by `loader/uk_charities.py`)

| table | what | rows (2026-11-14) |
|---|---|---|
| `charity` | every registered, removed and linked charity (main charity = `linked_number` 0) | 399,178 |
| `charity_main` | one row per registered number: latest figures, postcode area, region, web domain, trustees, previous year's income | 358,947 |
| `return_history` | income and spending per financial year | 1,253,226 |
| `parta`, `partb` | annual return Part A (all charities) and Part B (income over 500k) | 669,214; 80,430 |
| `trustee` | current trustees; `trustee_id` is the Commission's own person number, `name_norm` is the match key | 921,318 |
| `classification`, `area`, `other_name`, `governing`, `policy`, `event`, `regulator`, `report` | what/how/who codes, areas of operation, previous and working names, objects, policies, history, other regulators, reports | |
| `us_match`, `us_grant`, `person_match` | the UK to US cross-references (below) | |
| `meta` | per file ETag and Last-Modified, rows loaded, when | |

The region is the postcode area (the letters at the start), mapped offline in `loader/uk_charities.py` AREA_REGION: approximate,
labelled as such on the pages.

## Commands

    python -m loader.uk_charities download load summarize     # what the first load did (about two minutes)
    python -m loader.uk_charities nightly                     # the scheduled run: exit 10 when the register changed, 0 when not
    python -m loader.uk_charities status
    python -m loader.uk_xref match                            # recompute uk.us_match, us_grant, person_match (about a minute)
    python -m loader.uk_xref sample name:medium --n 50        # judge precision (METHOD or METHOD:confidence)
    python -m loader.uk_xref publish                          # copy the matches into xlinks (see below)
    scripts/load.py boards --only uk-largest-income,uk-most-trustees,uk-fastest-growing,uk-staff-over-60k,uk-with-us-counterpart,uk-us-grants,uk-income-by-region

`scripts/nightly.sh` runs `nightly` and, when it exits 10, refreshes the seven UK boards (the search index of boards is rebuilt as
part of that). Everything in `uk` is rebuilt from the whole extract; a rerun with unchanged Last-Modified does nothing.

## Pages

`/uk` (index, search box, boards, regions), `/uk/search?q=` (name, previous or working name, or registered number),
`/uk/charity/<number>` (facts, finances over time with Part A and Part B, trustees, what/how/who, areas, history, linked charities,
US matches, US grants), `/uk/trustee/<id>` (every charity a trustee serves; US person matches). The home of the code is
`app/uk_charities.py` and `templates/uk*.html`. The menu entry is in the Research dropdown (no new top-level item). The search page
has a "UK charities (England and Wales)" group; plain-text questions that mention UK charities or the Charity Commission go to
`/uk/search` (`nl_route`). US organization pages show "Also in the UK" (matches and grants made to UK charities) and US person pages
show UK trustee pages with the same name at a matched organization.

## Boards (`app/uk_boards.py`, group `uk`)

Largest by income; most trustees; fastest growing (both years at least 1 million pounds); most staff paid over 60,000 pounds; UK
charities with a US counterpart; UK charities receiving the most US foundation grants; income by region. Column format `gbp` was
added to `app/boards.py`.

## UK to US cross-references (`loader/uk_xref.py`)

All matches are in `uk.us_match` (method, relation, confidence, evidence); registered charities only.

| method | rule | confidence |
|---|---|---|
| `domain` | same website domain (blocklist of social and hosting domains; at most 3 charities and 3 nonprofits on a domain) | high |
| `american_friends` | US nonprofit "American Friends of X", "US Friends of X" or "Friends of X USA" and a charity X | high |
| `name` | same name core (`loader.recalls.core`) of two or more words with a distinctive word, at most two holders on each side; kinds: nonprofits, federal award recipients, lobbying clients, colleges | high with trustees in common, medium when the charity works in or mentions the US, otherwise low |
| `affix` | same name once USA/US/America/North America (US side) or UK/United Kingdom/Britain/GB/England (UK side) is removed | medium; the bare-US-name form is medium only with a US signal, else low |
| `fara_principal` | a charity's name is a FARA foreign principal in the UK | medium |
| `grant` | a US 990 grant whose recipient the filing places in the UK (state UK, GB, England...) and whose name equals a registered charity's (table `us_grant`, relation `grantor`) | high |
| `shared_trustee` | a UK trustee's normalised name equals a person on the matched US nonprofit's 990; lifts the pair to high; the trustee gets a link to the person page (`person_match`) | high |

"Low" matches are shown as "possible" on the pages and are never in xlinks or the API. A UK trustee is never linked to a US
person by name alone: the shared organization is the corroboration. Not matched: company numbers (no US dataset carries them);
Schedule F regions have no recipient names (`intl_grants_abroad`), so only the grant schedules are used.

`publish` writes the high and medium matches, the grants and the trustee-person links into `xlinks` (both directions, linker
`uk:<method>`, kinds `uk_charity` and `uk_trustee`), and counters into `xref_counts` and `xref_state`, so they appear in
`/api/v1/xlinks`, the MCP tool `get_links` and `/data#xref`. Publishing waits until prod has the code, because dev and prod share
one database and the xlinks rows would otherwise show on prod pages without a label. After the first publish, `nightly` refreshes
them whenever the register changes.

## Precision (50-row-class samples judged by hand, 2026-11-14)

See the memory note and the final report for the numbers: domain and American Friends matches are almost all the same organization
or its direct counterpart; same-name-only matches are about one in three and are labelled possible.
