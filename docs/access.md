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
(its `ignoreip` lists the VM's own IPs), nightly cron `/etc/cron.d/np-explorer` at 03:30
UTC, logs in `/var/log/np-explorer/`.

## Before the move (fallback until deleted)

| What | Value |
|---|---|
| VM | `np-explorer-vm` in resource group `NP-EXPLORER`, Germany West Central, IP 51.116.181.34 |
| Database | `np-explorer-pg`, North Europe |
