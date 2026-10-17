#!/usr/bin/env python3
"""Who is hitting the site: top IPs and user agents by request count.

Reads the nginx access log (combined format) and the rate-limited log.
Usage: scripts/traffic.py [--minutes 60] [--top 20]
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

ACCESS = "/var/log/nginx/access.log"
LIMITED = "/var/log/nginx/np-limited.log"
LINE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "[^"]*" (\d{3}) \S+ "[^"]*" "([^"]*)"')
LIMITED_LINE = re.compile(r'^(\S+) \[([^\]]+)\]')


def _when(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%d/%b/%Y:%H:%M:%S %z")


def read(path: str, pattern, since: datetime):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pattern.match(line)
                if m and _when(m.group(2)) >= since:
                    yield m
    except PermissionError:
        raise SystemExit(f"can't read {path}: run with sudo, or add yourself to the adm group")
    except FileNotFoundError:
        return


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    since = datetime.now(timezone.utc) - timedelta(minutes=args.minutes)

    ips, agents, limited_by_ip = Counter(), Counter(), Counter()
    statuses = Counter()
    for m in read(ACCESS, LINE, since):
        ips[m.group(1)] += 1
        agents[m.group(4) or "(empty)"] += 1
        statuses[m.group(3)] += 1
    for m in read(LIMITED, LIMITED_LINE, since):
        limited_by_ip[m.group(1)] += 1

    total = sum(ips.values())
    print(f"Last {args.minutes} minutes: {total:,} requests, {len(ips):,} IPs, "
          f"{sum(limited_by_ip.values()):,} rate-limited (429)")
    print("Status codes: " + ", ".join(f"{k} {v:,}" for k, v in sorted(statuses.items())))
    print(f"\nTop {args.top} IPs                    requests   429s")
    for ip, n in ips.most_common(args.top):
        print(f"  {ip:<36} {n:>8,} {limited_by_ip.get(ip, 0):>6,}")
    print(f"\nTop {args.top} user agents             requests")
    for ua, n in agents.most_common(args.top):
        print(f"  {n:>8,}  {ua[:110]}")


if __name__ == "__main__":
    main()
