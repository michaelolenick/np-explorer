# Access notes

No secrets in this file. Passwords and API tokens live only in `~/np-explorer/.env` on
the server (chmod 600, gitignored).

## Since the move to West US 3 (October 2026)

**Your ssh command changed:** the server has a new IP address.

    ssh michael@20.168.8.141

(The old command, `ssh michael@51.116.181.34`, reaches the old German VM, which stays
up for a short time as a fallback and is then deleted.)

| What | Value |
|---|---|
| Region | West US 3 (`westus3`), availability zone 1 |
| Resource group | `np-explorer-us` |
| VM | `np-explorer-vm`, Standard_D8s_v5, Ubuntu, OS disk Premium SSD 256 GB |
| Public IP | **20.168.8.141** (static, resource `np-explorer-vm-ip`) |
| Private IP | 10.1.0.4 (VNet `np-explorer-vnet` 10.1.0.0/16, subnet `default`) |
| Network security group | `np-explorer-vm-nsg`: allows 22, 80, 443 only |
| Database | `np-explorer-pg-us` (Azure Database for PostgreSQL Flexible Server 16, General Purpose D4ds_v5, 512 GB); its host name is in `.env` |
| Database firewall | rule `allow-vm-us` = 20.168.8.141 |
| DNS | AWS (Route 53 / Lightsail DNS page): A records `strategystudio.org` and `www` -> 20.168.8.141 |
| Mail | inbound ImprovMX (MX), outbound contact form via Postmark API; neither depends on the server IP |
| TLS | Let's Encrypt via certbot on the VM (HTTP-01), auto-renew |

On the server: app `systemctl status np-explorer`, nginx, fail2ban jail `np-ratelimit`
(its `ignoreip` lists the VM's own IPs), nightly cron `/etc/cron.d/np-explorer` at 05:00 UTC
(00:00 CDT / 23:00 CST; the server clock is America/Chicago), logs in `/var/log/np-explorer/`.

## Dev box: dev.strategystudio.org (October 2026)

    ssh michael@20.25.183.168

| What | Value |
|---|---|
| VM | `np-explorer-dev`, Standard_B2s (2 vCPU, 4 GB), Ubuntu 24.04, OS disk Standard SSD 64 GB, resource group `np-explorer-us` |
| Public IP | **20.25.183.168** (static, resource `np-explorer-dev-ip`) |
| Private IP | 10.1.0.5 (same VNet and subnet as production) |
| Network security group | `np-explorer-dev-nsg`: allows 22, 80, 443 only |
| Database | **the production database** (`np-explorer-pg-us`), same `.env` as production except `SITE_URL`; firewall rule `allow-vm-dev` = 20.25.183.168 |
| DNS | A record `dev.strategystudio.org` -> 20.25.183.168 |
| Access | HTTP basic auth, user `dev`; password in `~/dev-basic-auth.txt` on the dev box. `noindex` header and a disallow-all robots.txt |
| GitHub | fetches over HTTPS; pushes with its own deploy key (`~/.ssh/id_ed25519` on the dev box, added to the repo with write access) |

The dev box runs the app only (2 workers): no loader, no nightly cron, no sitemaps.
Because it shares the production database, anything that writes (Ask usage counts,
the Ask cache, the contact form's email) is real. Don't run loader commands there.

### Workflow

1. Change and test on the dev box (`~/np-explorer`, then `sudo systemctl kill -s HUP
   --kill-whom=main np-explorer` to load new Python; templates reload by themselves).
2. Commit and push from the dev box.
3. Deploy: `ssh michael@20.168.8.141 ~/np-explorer/scripts/deploy.sh`. It tests the new
   commit in a scratch worktree before touching the live checkout, fast-forwards,
   re-renders the fallback pages and reloads the workers one by one (no dropped requests).

Don't edit files in production's checkout: templates go live the moment they are saved,
before any Python they depend on is loaded.

## Before the move (fallback until deleted)

| What | Value |
|---|---|
| VM | `np-explorer-vm` in resource group `NP-EXPLORER`, Germany West Central, IP 51.116.181.34 |
| Database | `np-explorer-pg`, North Europe |
