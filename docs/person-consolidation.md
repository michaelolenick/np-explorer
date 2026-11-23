# Person consolidation (owner, 2026-11-23)

The same person listed under different spellings is one person. loader/cluster.py (the rebuild) does it in step 3e with
loader/consolidate.py; raw names in `people` are never changed.

Rules, inside one organization (EIN), best first: swap (first/last exchanged, high), nickname (app/nicknames.py, high),
spelling (last names one or two edits apart, medium), hyphenated (one surname is a middle/second token of the other,
medium), name_change (same first and full middle name, different surname, years that do not overlap, low).
Guardrails: two names listed as separate people in the same filing are never merged, directly or through a chain;
pairs in `person_merge_blocks` are never merged. Across organizations nothing is loosened: people link across EINs only
by the existing evidence (related orgs, shared address, co-board overlap).

Tables: `person_merge_log` (every merge: EIN, both names, rule, confidence, years, the person it became, status),
`person_merge_blocks` (reverts), `person_aliases` (the names a merged person is listed under; shown as "Also listed as" on
the person page; the alias words are also in the search vector so "Mike Marcin" still finds "Michael Marcin").
Display name: the most recent, most complete form in first-last order, with the credential (np_display_name,
np_credentials in loader/consolidate.py). Titles: app/titles.py fixes typos when shown ("BAORD" to "BOARD").

Reverse a merge: `python -m loader.consolidate revert EIN "name a" "name b"`; it takes effect at the next cluster rebuild.
Preview one organization: `python -m loader.consolidate preview EIN`. Counts: `python -m loader.consolidate report`.
