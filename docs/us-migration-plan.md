# Moving strategystudio.org to the US

Investigation 2026-10-17, read-only: nothing was created, changed or deleted. No
secrets in this file. Prices are Azure pay-as-you-go list prices (retail price API),
730 hours a month, before any sponsorship credit.

## Recommendation

**Move both the web server and the database to West US 3**, by copying the VM's disk
and promoting a cross-region Postgres read replica. It's the cheapest US region that
can take both, both services are available there with no restrictions, and the
switch-over downtime is minutes.

A finding on the way: **today the VM and the database are in different countries.**
The VM `np-explorer-vm` is in Germany West Central (Frankfurt); the database
`np-explorer-pg` is in North Europe (Ireland). Each query pays a 25 ms round trip
(measured), so a page making ten queries spends a quarter of a second just waiting
on the network. Putting both in one region removes that.

## 1. Availability for this subscription

| Region | VM Standard_D8s_v5 | Postgres Flexible GP Standard_D4ds_v5 | Usable for both? |
|---|---|---|---|
| East US 2 | available, except zone 1 (`NotAvailableForSubscription`) | **restricted**: "Subscriptions are restricted from provisioning in this region" | no |
| Central US | available, zones 1-3 | available, zones 1-3, HA supported | yes |
| South Central US | (not needed: Postgres blocked) | **restricted** (same message) | no |
| **West US 3** | available, zones 1-3, no restrictions; quota 65 cores (needs 8) | available, zones 1-3, HA supported | **yes** |

East US 2 and South Central US could be opened with a support request ("Service and
subscription limits"), but there's no need.

## 2. Prices (list, per month)

| | VM D8s_v5 | VM disk P15 (256 GB) | Postgres D4ds_v5 | Postgres storage 512 GB | Total |
|---|---|---|---|---|---|
| **Now** (VM Germany West Central, DB North Europe) | $336 | $42 | $289 | $65 | **$732** |
| West US 3 | $280 | $35 | $260 | $59 | **$634** (save about $98/month) |
| Central US | $317 | $38 | $293 | $67 | $715 |
| East US 2 (blocked) | $280 | $35 | $260 | $59 | $634 |
| South Central US (blocked) | $337 | $35 | $312 | $71 | $754 |

During the move both copies run side by side for a day or two: about $20-25 a day
extra until the old ones are deleted.

## 3. Credits and restrictions

- Subscription: **Microsoft Azure Sponsorship**, state Enabled. The CLI shows no
  spending limit, budget or offer detail for sponsorship subscriptions, and can't show
  the credit balance or expiry.
- Where to look: **https://www.microsoftazuresponsorships.com/Balance** (signed in as
  the sponsorship account) shows the balance, usage and end date. The Azure portal's
  Cost Management + Billing shows spend, not the sponsorship balance.
- Policies: only "ASC Default" (Microsoft Defender for Cloud's audit initiative). **No
  allowed-locations or allowed-SKU policy**, so nothing restricts regions or services
  beyond the Postgres region restrictions above, which come from Azure capacity rules,
  not from a policy.

## 4. Migration plan

What moves: the VM (Ubuntu, nginx, Let's Encrypt certificate, systemd units
`np-explorer`, `np-loader`, `fail2ban`, cron `/etc/cron.d/np-explorer` at 03:30, the
repo, `.venv`, `.env`, `/data/xml` 56 GB, `/data/raw` 34 GB, `/data/sitemaps`, logs) and
the database (61 GB, PostgreSQL 16, extensions pg_trgm and pg_stat_statements).

### Option B (recommended): replica, then promote

Database:
1. Create a read replica of `np-explorer-pg` in West US 3 (same tier, D4ds_v5, 512 GB).
   Flexible Server supports cross-region read replicas for General Purpose.
   `az postgres flexible-server replica create --replica-name np-explorer-pg-us -g np-explorer --source-server np-explorer-pg --location westus3`
   Initial copy about 61 GB, an estimated 30-90 minutes; the live site is unaffected.
2. Check the replica: server parameters (`azure.extensions`, `pg_stat_statements.track`)
   and firewall rules may need setting again on the replica (verify after creation).
3. At switch-over (below): stop the loaders, wait for replica lag to reach 0, then
   **promote** the replica to a standalone server (a few minutes). It becomes writable
   with a new hostname.

VM:
1. Snapshot the OS disk (incremental), copy the snapshot to West US 3
   (`az snapshot create ... --incremental true` then `az snapshot copy-start` to
   `westus3`), create a disk from it and a D8s_v5 VM on it, with a new public IP and
   an NSG that only allows 22, 80 and 443, like today. The disk copy carries
   everything as-is: nginx, the certificate, systemd units, cron, the repo, `.venv` and
   `.env`. **`.env` never leaves the encrypted disk and is never printed.** About 100 GB
   used; copy time an estimated 30-60 minutes.
   Option to shrink the copy: delete `/data/raw` (34 GB of IRS zips that can be
   downloaded again) before the snapshot. The 56 GB of stored XML must stay: the filing
   viewer and the backfills read it.
2. On the new VM, before it serves traffic: disable cron and the loader timer, and
   point `DATABASE_URL` at the replica's hostname with an in-place `sed` on `.env`
   (nothing printed). Change the fail2ban `ignoreip` from the old VM's IP to the new one
   (`deploy/fail2ban/jail.d/np-explorer.conf` in the repo and `/etc/fail2ban`).

Switch-over (downtime about 5-15 minutes, plus DNS caching):
1. Lower the Route 53 TTL on `strategystudio.org` and `www` to 60 s a day ahead.
2. Stop the nightly cron and any tmux loaders on the old VM; wait for the replica to catch up.
3. Promote the replica. Add a firewall rule on it allowing the new VM's IP.
4. Start `np-explorer` on the new VM; test with `curl --resolve strategystudio.org:443:<new IP>`.
5. In Route 53, point the A records (`strategystudio.org`, `www`) at the new IP.
6. Re-enable cron on the new VM. `certbot renew --dry-run` there to confirm renewals
   work (the certificate is valid until 2027-01-14 and moves with the disk).
7. Keep the old VM and database stopped, not deleted, for a week as a rollback; then
   delete them.

Cost: about $1-2 for the hours both databases run in parallel, about $20-25 a day
while both VMs exist, plus data transfer (below). Risk: low. Until DNS changes, the
old site keeps serving; rollback is pointing DNS back.

### Option A: pg_dump and restore

1. New Postgres server in West US 3 (empty), new VM as above.
2. `pg_dump -Fd -j 8` from the new VM against the old database (parallel dump across
   the Atlantic), then `pg_restore -j 8` into the new server. Data (about 35 GB of the 61)
   loads in 30-60 minutes; rebuilding the indexes (about 25 GB, many of them trigram GIN)
   and the leaderboard views takes an estimated 2-4 hours more. Re-create
   `pg_trgm`/`pg_stat_statements` and set the server parameters first.
3. The site keeps running on the old database meanwhile (pause the loaders: the only
   live writes are the natural-language usage counts and cache, which can be lost),
   then switch as in option B.

Downtime: similar (minutes), but a 3-5 hour copy window with the loaders paused, more
steps, and a chance of a missed setting. Advantage: the new database is freshly packed
(no bloat), and you can choose a different tier at the same time.

### Data copy and egress

| What | Size | Estimated time | Data transfer cost |
|---|---|---|---|
| Postgres replica, initial copy | about 61 GB | 30-90 min | about $1-3 |
| VM disk snapshot copy (used space) | about 100 GB (66 GB without /data/raw) | 30-60 min | about $2-5 |
| Total | about 160 GB | | **under $10** |

Inter-region transfer from Europe is listed at $0.02-0.05 per GB depending on route;
data into the US region is free.

## 5. Things tied to the current location

| Item | Today | Needs |
|---|---|---|
| Postgres firewall | rule `allow-vm` = 51.116.181.34 (the current VM) | a rule for the new VM's IP on the new server |
| VM public IP | 51.116.181.34 (Germany West Central) | a new IP in West US 3 |
| DNS (AWS Route 53) | A records -> 51.116.181.34 | A records -> new IP (lower the TTL first) |
| fail2ban `ignoreip` | 51.116.181.34 and private 10.0.0.4 (repo and /etc) | the new public and private IPs |
| VM network security group | allows 22, 80, 443 from anywhere | recreate the same on the new VM |
| `DATABASE_URL` in `.env` | the North Europe server's hostname | the promoted server's hostname (edited in place, never printed) |
| Postmark | sends through its API with the server token; SPF includes `spf.mtasv.net` | nothing: domain-based, no IP allow-list |
| ImprovMX | MX `mx1/mx2.improvmx.com`; SPF includes `spf.improvmx.com` | nothing: mail doesn't touch the VM |
| Let's Encrypt certificate | strategystudio.org + www, valid to 2027-01-14 | moves with the disk; HTTP-01 renewals work once DNS points at the new VM |
| Anthropic API, IRS downloads, GivingTuesday mirror | outbound only | nothing |
| GitHub | repo and Actions | nothing |
| Other VMs in this subscription | several unrelated VMs and a second Postgres server (`krohn-db`) | not part of this move |

GDPR note: once both the VM and the database are in a US region and the European copies
are deleted, no part of the site's data or processing runs in the EU. (Where your
visitors are is a separate question from where the servers are.)
