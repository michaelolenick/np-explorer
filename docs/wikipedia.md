# Wikipedia and Wikidata bios (owner, 2026-11-14)

Short bios of the people and organizations in FURP that also have an English Wikipedia article, shown as an
"About (Wikipedia)" block on the matched page, in the cross-references, in the API and MCP `get_links`, and in three
leaderboards. Code: `loader/wikipedia.py` (schema `wiki`), `app/wikipedia.py`, `app/wikipedia_boards.py`,
`templates/_wikipedia_about.html`; tests: `tests/test_wikipedia.py`.

## Sources and terms

* Wikidata entity dump `latest-all.json.gz` (https://dumps.wikimedia.org/wikidatawiki/entities/): structured data under
  **CC0**. One download, two polite connections (the dumps' limit), User-Agent `furp.org data loader (info@furp.org)`.
  (The bzip2 file is a third smaller but needs ten hours of single-core decompression on the dev box; gzip is
  decompressed in minutes per 10 GB.)
* English Wikipedia `pages-articles-multistream.xml.bz2` and its index: article text under **CC BY-SA 4.0** (and GFDL).
  Only the short description and the first sentence or two of the lead (at most 300 characters) are stored, with the
  article title and the Wikidata QID. Dump terms: https://dumps.wikimedia.org/legal.html. Nothing is fetched from the
  live site per page.
* Attribution on every page that shows a bio: "From Wikipedia, CC BY-SA 4.0" linked to the article, a link to the
  article's history (the authors), the Wikidata item, and `/data#wikipedia`. API and MCP answers carry the same
  attribution and the licence URL.
* Living people (no death date and born after 1900, or birth year unknown): only the article's own short description and
  lead are shown, nothing from Wikidata (no years, occupations or employers), and never a photo (none is stored).
* Every block has "Report a wrong match" (`/contact?topic=Corrections&subject=...`, the Correction or removal request
  topic, message pre-filled).

## Steps (rerun monthly by hand; heavy parts run any time on weekends, 19:00-02:00 Central on weekdays)

1. `~/claude_scripts/wikipedia/download.sh` downloads the Wikidata gz into `/bulk/wikipedia` (two halves, resumable);
   `follow.py | gzip -dc | wd_filter.py` (`run_filter.sh`) makes one pass with 4 worker processes and writes
   `/bulk/wikipedia/extract/{people,orgs,labels}.N.*` (humans with an English article; non-humans with an article and
   an organization-like property, plus any item with an IRS EIN, P1297; the English label of every item).
   `dl_enwiki.sh` fetches the Wikipedia dump and index.
2. `python -m loader.wikipedia load` replaces `wiki.entity`, `wiki.label`, `wiki.person_name`, `wiki.org_name`.
3. `python -m loader.wikipedia match` rebuilds `wiki.link` (below).
4. `python -m loader.wikipedia sample METHOD --n 50` prints a random sample; judge it and record
   `python -m loader.wikipedia judge METHOD 50 <correct>`.
5. `python -m loader.wikipedia publish` sets `wiki.link.show` for the methods judged at 50 or more with at least 90%
   correct, writes the xlinks rows (kind `wikipedia`, key = QID, linker `wikipedia`, both directions) and the
   leaderboard source tables `wiki.board_people`, `wiki.board_orgs`, `wiki.board_orgs_wp`.
6. `python -m loader.wikipedia lead` reads short description and lead of the shown articles from the Wikipedia dump (only
   the dump streams that hold them).
7. `python scripts/load.py boards --only wikipedia-nonprofit-leaders,wikipedia-notable-boards,wikipedia-big-nonprofits`.

## Match methods

People (kind `person` = person page id, `sec_insider` = CIK without zeros):

| method | rule | confidence |
|---|---|---|
| `person_cik` | Wikidata's SEC CIK (P5531) is the insider's own CIK | high, EXACT |
| `person_org_ein` / `_fl` | same name (or same first and last name with compatible middles) and Wikidata lists an employer (P108), membership (P463) or board seat (P3320, from the organization side) that is an organization with an IRS EIN the person is on in the filings | high / medium |
| `person_org_name` / `_fl` | the same, the organization matched by its name (name core unique among at most 3 FURP nonprofits) | medium |
| `insider_issuer` / `_fl` | the same name, at a company whose CIK Wikidata gives as the person's employer, membership or board; the insider filings name the person at that issuer | high / medium |
| `person_name_rare` | the full name is unique on Wikipedia and in FURP, the Wikipedia person is a US citizen, alive in the filing years, born 1915-2006, and first x last name would collide by chance fewer than 0.03 times in FURP | low (flagged "name only") |
| `person_name_uncommon` | the same for expected collisions of 0.03 to 0.3 | low (flagged) |
| `person_name_only` | the same without the rarity test | low (flagged, never shown) |

Organizations (kind `org` = EIN, `college` = IPEDS unit id, `sec` = CIK):

| method | rule |
|---|---|
| `org_ein`, `college_ein` | Wikidata's EIN (P1297) equals the EIN, EXACT |
| `sec_cik` | Wikidata's CIK equals the SEC filer's CIK, EXACT |
| `org_website`, `college_website` | the official website's domain is the filing's website domain, unique on both sides |
| `org_name_city` | the same name core (at most four nonprofits share it) and Wikidata's headquarters or location label is the filing's city |
| `org_name_only`, `college_name` | the same name, unique on Wikipedia and in FURP |
Places (cities, counties, countries) are never matched to organizations except by EIN or CIK.

Precision is judged on random samples of at least 50 per method and kept in `wiki.precision` (shown on `/data#wikipedia`).
Methods below 90% are stored but not shown.
