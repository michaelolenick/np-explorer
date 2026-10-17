# Performance report: strategystudio.org / np-explorer

Measured 2026-10-17, 14:15-14:30 ET, while the expense backfill
(`load.py backfill-extras --only expense_breakdown`, 6 parse workers) was also
running. That adds write and read load, so cold timings here are somewhat worse
than an idle night; warm timings are representative. No secrets in this file.

## Summary

- **The bottleneck is reading cold data from disk, not CPU, not query plans.**
  Every page query uses the right index; there are no sequential scans on big
  tables in any page query. The same search that takes 5.7 s cold takes 0.59 s
  warm.
- **Common-name searches can hit the 5 s web statement timeout and fail** (8 in
  10 minutes during testing, all from our own tests). Name search p95 is 5.1 s;
  everything else is fast (person page p95 0.25 s, org page p95 1.5 s, boards
  p95 0.08 s).
- The fix is to make search read less, not a bigger server: a slim search table
  (about a quarter of the size of `person_clusters`) that stays in memory.
- Azure tier, metrics and IOPS: **not yet measured** (needs `az login`; see
  section 2).

## 1. Database size and shape

Total: **65 GB** (PostgreSQL 16.15). Buffer-cache hit ratio since the stats
reset: 97.2%.

| Table | Total | Heap | Rows | Notes |
|---|---|---|---|---|
| people | 18 GB | 9.8 GB | 64.8 M | one row per person per filing |
| person_cluster_members | 17 GB | 15 GB | 64.9 M | **15 GB heap for 3 columns**: the per-member `evidence` JSON is large |
| person_clusters | 7.9 GB | 4.9 GB | 15.5 M | search reads this; wide rows (evidence, org arrays) |
| grants | 7.2 GB | 5.0 GB | 26.7 M | Schedule I + 990-PF grants |
| filings | 4.2 GB | 3.5 GB | 7.45 M | 384 K dead rows from the fundraising backfill (vacuum will clear) |
| expense_breakdown | 4.0 GB (growing) | | 4.1 M of ~7.4 M | backfill in progress |
| organizations | 1.5 GB | 0.7 GB | 2.15 M | |
| related_orgs | 1.0 GB | | 9.5 M | |
| schedule_j | 1.0 GB | | 3.45 M | |
| loaded_objects | 0.8 GB | | 7.7 M | loader bookkeeping |
| daf_stats | 0.7 GB | | 6.2 M | |
| contractors | 0.7 GB | | 1.56 M | |
| board_* views | 0.3 GB and less each | | | |

Largest indexes: `people_name_norm_trgm` 1.75 GB, `people_pkey` 1.4 GB,
`person_cluster_members` pkey 1.39 GB, `people_ein_name` 1.2 GB,
`grants_recipient_trgm` 1.08 GB, `person_cluster_members` cluster_id 0.76 GB,
`people_name_norm` and `people_name_prefix` 0.73 GB each.

Statistics: ANALYZE was run on filings, organizations, related_orgs,
schedule_j, contractors, person_cluster_members and loaded_objects (12 s; all had
been bulk-changed since their last analyze). The new tables (grants, daf_stats,
pf_payout, insider_loans) were analyzed by the backfill. expense_breakdown will
be analyzed when its backfill finishes.

Autovacuum: on, 3 workers, scale factors 0.2 (vacuum) and 0.1 (analyze).
Dead rows are small everywhere except filings (384 K, about 5%), which
autovacuum will reach on its own.

## 2. Azure Postgres server

From inside Postgres (read-only):

| Setting | Value |
|---|---|
| shared_buffers | 4 GB |
| effective_cache_size | 12 GB (so about 16 GB RAM) |
| work_mem | 4 MB |
| maintenance_work_mem | 268 MB |
| max_connections | 1718 |
| random_page_cost | 2 |
| effective_io_concurrency | 1 |
| max_parallel_workers_per_gather | 2 |
| shared_preload_libraries | includes **pg_stat_statements** (already loaded) |
| azure.extensions | PG_TRGM only |

**Pending:** SKU, vCores, storage size, provisioned IOPS and 24-hour metrics
(CPU, memory, IOPS %, disk queue depth, connections). The az CLI is installed;
this VM has no managed identity, so it needs `az login --use-device-code` once.
The commands that will be run (all read-only):

```
az postgres flexible-server show -g <rg> -n np-explorer-pg
az postgres flexible-server parameter show -g <rg> -s np-explorer-pg -n shared_buffers   (and the others)
az monitor metrics list --resource <server id> --interval PT1H --offset 24h \
  --metrics cpu_percent memory_percent disk_iops_consumed_percentage disk_queue_depth active_connections
```

What the evidence so far suggests: warm queries are fast and the slow ones are
dominated by reads (`Shared Read Blocks`), so **storage IOPS / memory, not
CPU, is the likely limit**. The metrics will confirm.

## 3. Query performance

Every page's SQL was captured from the real page code and run with
`EXPLAIN (ANALYZE, BUFFERS)`. Times are warm (second run).

| Page | Statements | Warm SQL time | Trigram GIN used | Seq scans on big tables |
|---|---|---|---|---|
| Name search, rare ("mauborgne") | 3 | 66 ms | yes (`person_clusters_name_norm_trgm`) | none |
| Name search, typo ("renee mauborgen") | 3 | 157 ms | yes | none |
| Name search, common ("john smith") | 3 | 590 ms warm, **5.7 s cold** | yes | none |
| Name search, single surname ("smith") | 2 | **12.5 s cold** | yes | none |
| Institutions ("smith") | 1 | 13 ms | n/a | none |
| Organizations ("red cross") | 1 | 14 ms | no (full-text index) | none |
| Organizations by place (Austin, TX) | 1 | 15 ms | n/a (`organizations_city`) | none |
| Contractors ("deloitte") | 1 | 22 ms | yes | none |
| Person page, small record | 5 | under 2 ms | n/a | none |
| Person page, Wells Fargo (68K filings) | 5 | 245 ms SQL; 3.4 s wall (Python building the page) | n/a | none |
| Org page, REDM | 10 | 125 ms | yes (grants received) | none |
| Org page, Red Cross | 10 | 910 ms; two grants-received queries at about 450 ms each | yes, **wrongly**: see below | none |
| Every leaderboard, page 1 | 1-2 | under 1 ms each | n/a (`pos` index) | none |
| Leaderboard with filters (top-paid, NY, 2022) | 2 | 28 ms warm, 1.7 s cold | n/a | none |
| Boards search ("roger goodell") | 1 | 9 ms | n/a | none |

Synthetic load (25 random real surnames, person ids and EINs, through the app):

| Page | p50 | p95 | max |
|---|---|---|---|
| Name search | 0.92 s | **5.07 s** | 5.14 s |
| Person page | 0.14 s | 0.25 s | 0.28 s |
| Org page | 0.90 s | 1.46 s | 1.51 s |
| Leaderboard pages | 0.06 s | 0.08 s | 0.09 s |

### Why common-name search is slow

The search gathers up to 1,000 candidates per branch (exact words, prefixes,
trigram) from `person_clusters`, then ranks and counts them. A cold run reads
each candidate's heap page. Those rows are wide (evidence JSON, org-name
arrays), so 15.5 M of them make a 4.9 GB heap that doesn't stay in a 4 GB
buffer cache shared with everything else. A common name touches thousands of
pages at random. Bare surnames ("smith") are worst: every Smith is a candidate.

### Missing indexes

- `grants_recipient_name` (partial btree on `recipient_name_norm, state` for
  990-PF grants): defined in code but **not built**. The first backfill ran with
  code that predated it. Without it, the org page's "matched by name and state"
  lookup falls back to the trigram GIN index (about 450 ms on the Red Cross).
  It will be built automatically when the expense backfill finishes
  (`ensure_indexes`), or now with `CREATE INDEX CONCURRENTLY`.
- No other missing indexes on page paths.

### Unused or nearly unused indexes (scans since stats reset; candidates to drop)

| Index | Size | Scans | Why unused |
|---|---|---|---|
| people_name_norm_trgm | 1.75 GB | 7 | search runs on person_clusters, not people |
| people_name_prefix | 734 MB | 2 | same |
| people_title_lower | 500 MB | 0 | the title filter applies after candidates are found |
| people_last_name | 454 MB | 0 | search uses person_clusters.last_name |
| people_tax_year | 425 MB | 2 | year filters apply after candidates |
| person_clusters name_norm (two duplicates) | 363 MB each | 13 and 0 | duplicate of each other |
| person_clusters_last_name_trgm | 310 MB | 0 | not used by any query |
| person_clusters last_name+first_name, first_name, max_comp, first/last year, n_filings | 100-324 MB each | 0-4 | sort and filter columns never used by the planner |
| filings_org_name_lower, organizations_name_prefix, related_orgs_filing_id, related_orgs_ein, schedule_j_name_norm | 58-134 MB each | 0-2 | not used on any page; the loaders don't need them either |

About **6 GB** of indexes that cost write time on every load and memory for no
reads. Several were added early "for lots of name indexing"; the search design
since moved to person_clusters. Dropping them is safe but should be a deliberate
step (they can be rebuilt).

Seq scans that do happen are in the batch jobs (cluster rebuild, leaderboard
builds, backfills), where they are the right plan.

pg_stat_statements: already in `shared_preload_libraries`, so **no restart is
needed**. It only needs `PG_STAT_STATEMENTS` added to the `azure.extensions`
allow-list (a dynamic parameter), then `CREATE EXTENSION pg_stat_statements;`.
Not done: it's a server parameter change, so it needs your go-ahead (command in
section 5).

## 4. App side

- Web pool (`app/db.py`): 10 connections per worker, 4 workers (40 maximum), a
  10 s wait for a free connection, at most 64 waiting; `statement_timeout = 5s`
  on web connections only.
- **The web app and the loaders use the same database role** (one login) and the
  same server. The loaders open their own connections without the timeout. A
  backfill or cluster rebuild competes with the site for the same CPU, memory and
  IOPS; that's visible in the cold timings above.
- In-process caches: 60 s for searches, person pages and org pages (per worker).
- nginx: the access log uses the default format, which has **no response time**,
  so p50/p95 for the last day can't be computed from it. The table above is a
  synthetic test instead. Recommendation 7 adds `$request_time` to the log.

## 5. Recommendations (ranked)

| # | Fix | Expected impact | Cost |
|---|---|---|---|
| 1 | **Slim search table**: `person_search` with only what results show (id, name_norm, display name, counts, years, max pay, states, latest title, institution flag), about 1-1.5 GB instead of 4.9 GB, with its own trigram and full-text indexes; rebuilt with the clusters. Search reads it instead of person_clusters. | Common-name search from 5-12 s cold to well under 1 s; it fits in memory. Ends the timeouts. | A few hours of work; about 2.5 GB disk; rebuild adds a few minutes to the nightly. |
| 2 | Cap the candidate sets for very common names (for example, count but don't rank past 2,000), and make the people-count a fast estimate ("2,000+") | Bounds the worst case even cold | Small |
| 3 | Build `grants_recipient_name` now (`CREATE INDEX CONCURRENTLY`) | Org pages of big grant recipients from about 1 s to about 0.1 s | Minutes, about 0.6 GB |
| 4 | Drop the unused indexes above (about 6 GB) | Faster loads; frees about 6 GB of cache for useful pages | Minutes; reversible by rebuilding |
| 5 | Shrink `person_cluster_members` (15 GB heap): move the per-member evidence JSON into the cluster or a side table | Person pages and cluster rebuilds read far less; frees about 10 GB | Half a day; done in the next cluster rebuild |
| 6 | Precomputed person summaries (by year, by org) for very large records (institutions like Wells Fargo) | Big person pages from about 3 s to under 0.5 s | Small; part of the cluster rebuild |
| 7 | nginx `log_format` with `$request_time` and `$upstream_response_time` | Real p50/p95 from then on | Minutes (config change + reload) |
| 8 | Raise the web statement timeout for search only to 10 s until fix 1 ships, so common names slow down instead of failing | No more 500s on common names | One line |
| 9 | Separate read role for the web app (read-only grants, its own connection limit), and run heavy backfills at night | Loader load can't starve the site; least privilege | An hour; needs a new password in .env (yours to add) |
| 10 | Server tuning: `work_mem` 16-32 MB for the web role, `effective_io_concurrency` 200 (SSD), `random_page_cost` 1.1 | Modest: better plans for sorts and bitmap scans | Parameter change, no restart; needs your go-ahead |
| 11 | A bigger tier, only if the metrics show sustained IOPS or memory saturation **after** 1-5 | More memory = bigger cache | See below |

### Bigger tier

Not justified yet: warm queries are fast, and fixes 1-5 cut the working set by
more than half. If the metrics (section 2) show IOPS pinned at 100%, the cheaper
lever is storage IOPS (Premium SSD v2 or a larger disk tier) rather than vCores.
Azure Flexible Server compute can be scaled up for a load and back down after;
each change restarts the server (a minute or two of downtime). Exact SKU, monthly
cost and commands go here once `az` shows the current tier.

Commands to run only with your approval (not run):

```
# allow pg_stat_statements (no restart; pg_stat_statements is already preloaded)
az postgres flexible-server parameter set -g <rg> -s np-explorer-pg -n azure.extensions --value PG_TRGM,PG_STAT_STATEMENTS
# then, in psql:  CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```
