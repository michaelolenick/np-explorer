# Topic index over the 990 filings

Ask "how many 990s mention X?" without rescanning the filings. The index is built once (about 2 hours); each question then runs in seconds.

## What's indexed

Each row is tagged with its source field, so a question can be restricted to one field.

| field | what | from |
|---|---|---|
| `name` | Organization name and DBA | `filings.org_name`, `dba` |
| `mission` | Mission statement (990 Part I/III; 990-EZ primary purpose) | `filings.mission` |
| `program` | Program service descriptions: 990 Part III lines 4a–4d, 990-EZ Part III, 990-PF Part IX-A | the XML, via `extract_text.py` |
| `schedule_o` | Schedule O narrative (990 and 990-EZ) | the XML, via `extract_text.py` |
| `grant_purpose` | Purpose of each grant made (990 Schedule I, 990-PF Part XV) | `grants.purpose` |
| `contractor_service` | What the top contractors did (990 Part VII-B) | `contractors.service_description` |

- **The NTEE code** is a column on every row (`ntee`, plus `ntee_major`, its letter), not a text field.
- **Not indexed:**
  - Part IX "other expense" descriptions and insider-loan purposes, which are short and administrative.
  - 990-PF Part IX-A in the pre-2013 schema, which uses tags `extract_text.py` doesn't read.

## Tables (schema `research`)

- **`research.filing_text`**: one row per return per field.
  - Columns: `filing_id`, `return_id` (the IRS object id), `ein`, `tax_year`, `form_type`, `superseded`, `field`, `text`, `tsv`, `ntee`, `ntee_major`, `state`, `total_revenue`.
  - Each return also has a row with `field = 'all'`, whose tsvector covers every field of that return. That row is what makes "A and B in the same filing" work across fields.
  - Indexes: GIN on `tsv`, and pg_trgm GIN on `text`.
- **`research.org_text`**: one row per organization.
  - Holds every distinct text the org has filed, across all years. Superseded returns are left out.
  - Has one tsvector per field (`tsv_name`, `tsv_mission`, …) and `tsv` for everything.
  - Also carries `revenue` (latest return), `max_revenue`, `state`, `ntee`, `first_year`, `last_year` and `n_filings`.
- **`research.topic_labels`**: model labels (`codes`) for words that terms alone can't settle (see "space" below).

## Asking a question

```sql
SELECT n, n_orgs, median_org_revenue FROM research.topic_count('"domestic violence"');            -- filings
SELECT n, n_orgs, median_org_revenue FROM research.topic_count('"domestic violence"', 'orgs');    -- organizations
SELECT n FROM research.topic_count('astronaut', 'orgs', 'mission');                                -- mission only
SELECT * FROM research.topic_breakdown('"domestic violence"');      -- by year, NTEE major group, state, size
SELECT eins FROM research.topic_count('planetarium', 'orgs');        -- the matching EINs
SELECT * FROM research.topic_match('planetarium') JOIN organizations USING (ein);                   -- your own SQL
```

- **`scope`**:
  - `'filings'` (the default) counts returns. Superseded returns are left out.
  - `'orgs'` counts organizations.
- **`field`**: `NULL` (the default) means any field. Otherwise it's one of `name`, `mission`, `program`, `schedule_o`, `grant_purpose` or `contractor_service`.
- **`median_org_revenue`**: the median, across the matching orgs, of each org's total revenue on its latest return.

### Search syntax

Words are stemmed, so `women` also matches "women's", and `girl` matches "girls". Case doesn't matter.

| you write | means |
|---|---|
| `space women` | both words (AND) |
| `"domestic violence"` | the exact phrase |
| `astronaut or cosmonaut` | either |
| `space -office` | space, and not office anywhere in the text |
| `women & (space \| astronaut)` | raw tsquery: `&` AND, `\|` OR, `!` NOT, parentheses |
| `women <-> in <-> space` | phrase, word by word |
| `women <3> space` | "space" exactly 3 words after "women" |
| `astro:*` | prefix: astronomy, astronaut, astrophysics… |
| `re:outer\s+space` | regular expression on the raw text, case-insensitive (pg_trgm index; slower) |

- **Which syntax is used:** anything containing `& | ! ( )`, `<N>` or `:*` is read as raw tsquery. Everything else is read as web-search syntax.
- **Proximity:** tsquery has exact distance (`<N>`) but no "within N words". To get "within 3 words", OR the distances together: `women <1> space | women <2> space | women <3> space`.
- **Stop words:** they're dropped, but they still count for distance. So `"women in space"` becomes `women <2> space`.

### One sense of an ambiguous term

`'topic:sense'` counts only the orgs with that sense of the term, and only the filings that use the term at those orgs. A comma list means any of the senses.

```sql
SELECT n, n_orgs, median_org_revenue FROM research.topic_count('space:outer', 'orgs');
SELECT n, n_orgs FROM research.topic_count('abuse:domestic');                    -- filings
SELECT n, n_orgs FROM research.topic_count('shelter:animal,homeless', 'orgs');
SELECT * FROM research.topic_breakdown('survivor:cancer', 'orgs');
SELECT topic, code, sense, description FROM research.sense_defs ORDER BY 1, 2;   -- every term and sense
```

## Saved questions

`questions.sql` holds the term lists (`research.terms(name)`) and one view per question:

```sql
SELECT * FROM research.questions;                -- all of them
SELECT * FROM research.q_space;
SELECT * FROM research.q_space_phrases;          -- office / parking / green / safe space ... by phrase
SELECT * FROM research.q_space_senses;           -- the same by the model's labels
SELECT * FROM research.q_women_in_space;
SELECT * FROM research.q_womens_mens_issues;
SELECT * FROM research.q_domestic_violence;
```

### The senses of "space"

"Space where rockets go" and "a space for women" are different questions, and so are office, parking and green space. Each sense is counted two ways.

1. **Exact phrases, with no model** (`research.q_space_phrases`): outer space, office space, meeting/event/conference space, parking space, green/open space, safe/brave/quiet space, studio/storage/rental space, "space for women" / "women's space", and "space for men" / "men's space".
2. **Model labels on every org whose text says "space" or "aerospace"** (`research.q_space_senses`; per org in `research.space_senses`). `classify.py` labels each org with every code that applies:

   | code | sense |
   |---|---|
   | O | outer space (exploration, astronomy, astronauts, rockets, satellites, aerospace) |
   | W | a place set aside for women or girls ("a brave space for girls") |
   | M | a place set aside for men or boys ("a space where men can gather") |
   | F | facility: office, meeting, studio, classroom, storage, rental space |
   | P | parking |
   | G | green, open or natural land |
   | S | a safe, quiet or personal space not specifically for women or men; "space to heal" |
   | X | other: "the X space" meaning a field or sector, a gap, aerospace workers' unions, aviation alone |

   - W and M need "space" itself to mean a place for that group. A program or scholarship for women in aerospace is O, not W.
   - **What the model sees:** the org's name, the first 300 characters of its mission, and three 200-character snippets around the word. Mentions near women/men or astronomy words are picked first.
   - **Model choice:** Claude Haiku 5.5 through OpenRouter, about $1–2 for every "space" org.
     - Mistral-small agreed with it on O, W and M for 199 of 200 orgs each, but its misses were the ones that matter: it missed "a brave space for girls", and it called a survivors' support group a space for men.
     - On the hand-labeled cases in `space_test.py` (safe, quiet and brave space; "a space of her own"; office, green and parking space; men's sheds; Girls Inc; astronomy clubs; Space Camp) Haiku scored 22 of 22.
   - Orgs with an unambiguous outer-space term count as outer space whatever the model says:
     - The terms: "outer space", astronaut, cosmonaut, astronomy, astronomer, astrophysics, spaceflight, spacecraft, "space exploration/science/station/shuttle/camp/museum", NASA, planetarium, rocketry.
     - Left out on purpose: "space program" (land trusts' "open space program"), "space center" (community centers), satellite, rocket, "astronomical (costs)" and aerospace (union names).
   - `earthly_only` is a check, not a filter. It flags orgs whose every "space" mention is a plainly earthly phrase.
3. **Outer-space counts in `research.q_space`:**
   - An org counts if it has an unambiguous term or the code O.
   - A filing counts if it has an unambiguous term, or it says "space" and its org has O. The sense views count only the filings that say "space" or "aerospace".

## The other ambiguous terms

`senses.py` handles the other ambiguous terms the same way as "space": exact phrase counts with no model, plus sense labels, side by side. The terms are women, men, domestic, violence, abuse, shelter, survivor, science/STEM, mission/launch/rocket/orbit/flight, and girls/boys.

- **Definitions:** each term has its words, its senses and the phrases that settle a sense on their own (`TOPICS`).
- **Word boundaries:** words match only as whole words. As a substring, "men" also finds women, freshmen, Mennonite, abdomen and management; RESULTS.md shows the false-hit rate before and after.
- **Exact phrase counts** come from the index with no model (`research.sense_phrase_counts`). Phrases that begin with a small word, such as "our mission", can't be searched in the index. Those work only in the rule pass.
- **The rule pass** (`senses.py rules`) reads every org's text once:
  - A mention inside one of the phrases takes that phrase's sense.
  - For women, men and girls/boys, a mention in the org's own name that no phrase settles is the name sense.
  - The pass also records which fields the term appears in, which gives the share of orgs where it appears only in the name or only in grant purposes.
- **Haiku labels** (`senses.py label`) cover only the mentions the phrases didn't settle:
  - The model sees the org's name, its mission and up to three snippets.
  - A second pass with smaller batches retries failures.
- **Hand-labeled checks:** `sense_tests.py` holds 30 tricky cases per term. Haiku's score per term is in RESULTS.md and in `research.sense_test_results`.
- **Tables:**
  - `research.org_senses`: per term and org, the fields, `rule_codes`, `model_codes` and snippets.
  - `research.org_codes`: the combined codes, "space" included.
  - `research.sense_counts`, `research.sense_fields` and `research.clean_questions`.
- **The cleaned questions** (`senses.sql`):
  - "Mentions women" or "mentions men" means the issues or incidental sense, not just a name.
  - "Domestic violence" means the DV sense of any of domestic, violence, abuse, shelter or survivor.
  - "Top comp" is `org_profile.top_pay`: the highest total pay on the latest return, with $0 when no one is listed.

## Rebuild

1. **Extract Part III and Schedule O from the XML.** This runs on prod, which holds `/data/xml`. It takes about 50 minutes with 4 workers, and a rerun only does what's new.

   ```
   nice -n 19 .venv/bin/python research/text_index/extract_text.py 4
   ```

2. **Build the tables, indexes and functions.** This takes about 2 hours.

   ```
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/build.sql
   ```

3. **Prepare the saved questions and the space candidates.**

   ```
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/questions.sql
   ```

4. **Label every "space" org with its senses.** A rerun only labels new ones and retries failures.

   ```
   .venv/bin/python research/text_index/classify.py space
   ```

5. **The other ambiguous terms.** Run these in order. The rule pass takes about 20 minutes, and labeling takes a few hours (Haiku, about $15).

   ```
   .venv/bin/python research/text_index/senses.py sync
   .venv/bin/python research/text_index/senses.py test
   .venv/bin/python research/text_index/senses.py falsehits 1
   .venv/bin/python research/text_index/senses.py rules 2
   .venv/bin/python research/text_index/senses.py label
   .venv/bin/python research/text_index/senses.py label --small
   ```

6. **Count the senses and answer the cleaned questions.** Then write the report.

   ```
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/senses.sql
   .venv/bin/python research/text_index/report.py
   ```

Or all of it, unattended, after step 1: `tmux new -d -s textindex 'bash research/text_index/run_all.sh >> ~/text-index.log 2>&1'`. It writes `RESULTS.md` and commits.

Every build statement runs under `statement_timeout`: 3 hours in `build.sql`, and 30 minutes in `questions.sql` and `senses.sql`.
