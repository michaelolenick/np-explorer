#!/usr/bin/env python3
"""Write /etc/nginx/np-crawlers.conf from the IP ranges Google and Bing publish for their crawlers.

nginx's np-limits.conf includes it in a geo block: requests from these ranges skip the
per-visitor rate limits (see deploy/nginx/np-limits.conf). Run as root weekly by
/etc/cron.d/np-crawlers; reloads nginx only when the list changed and the config tests clean.
Standard library only, so it runs with the system python3.

Usage: sudo python3 scripts/update_crawler_ips.py
"""

import ipaddress
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

SOURCES = {
    "Googlebot": "https://developers.google.com/static/search/apis/ipranges/googlebot.json",
    "Bingbot": "https://www.bing.com/toolbox/bingbot.json",
}
DEST = Path("/etc/nginx/np-crawlers.conf")
UA = "np-explorer/1.0 (+https://strategystudio.org; crawler IP list refresh)"


def ranges(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    out = []
    for p in data.get("prefixes", []):
        cidr = p.get("ipv4Prefix") or p.get("ipv6Prefix")
        if cidr:
            out.append(str(ipaddress.ip_network(cidr, strict=False)))
    return out


def main() -> int:
    lines = ["# Written by scripts/update_crawler_ips.py; do not edit by hand.\n"]
    for name, url in SOURCES.items():
        try:
            nets = ranges(url)
        except Exception as e:  # noqa: BLE001 - keep the current file if a source is down
            print(f"{name}: could not fetch {url}: {e}; keeping {DEST}", file=sys.stderr)
            return 1
        if not nets:
            print(f"{name}: no prefixes in {url}; keeping {DEST}", file=sys.stderr)
            return 1
        lines.append(f"# {name}: {url} ({len(nets)} ranges)\n")
        lines += [f"{n} 1;\n" for n in sorted(set(nets))]
    new = "".join(lines)
    old = DEST.read_text() if DEST.exists() else None
    if new == old:
        print(f"unchanged: {DEST}")
        return 0
    backup = DEST.with_suffix(".conf.bak")
    if old is not None:
        backup.write_text(old)
    DEST.write_text(new)
    if subprocess.run(["nginx", "-t"], capture_output=True).returncode != 0:
        if old is not None:
            DEST.write_text(old)
        print("nginx -t failed with the new list; restored the old one", file=sys.stderr)
        return 1
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print(f"wrote {DEST}: {new.count(' 1;')} ranges; nginx reloaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
