#!/usr/bin/env python3
"""Download DB-IP's free IP-to-country database (CC BY 4.0) for the usage stats' country field.

Writes {NP_DATA_DIR}/geo/dbip-country-lite.mmdb. Monthly cron (deploy/cron/np-report); the
web app picks a new file up on its next restart or deploy. Without the file, country is blank.
Usage: .venv/bin/python scripts/update_geoip.py
"""

import gzip
import shutil
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import DATA_DIR  # noqa: E402

DEST = DATA_DIR / "geo" / "dbip-country-lite.mmdb"
URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz"
UA = "np-explorer/1.0 (+https://furp.org)"


def main() -> int:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    this_month = date.today().replace(day=1)
    for month in (this_month, (this_month - timedelta(days=1)).replace(day=1)):   # early in a month: last month's
        url = URL.format(month=month.strftime("%Y-%m"))
        tmp = DEST.with_suffix(".tmp")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r, gzip.GzipFile(fileobj=r) as g, open(tmp, "wb") as f:
                shutil.copyfileobj(g, f)
        except Exception as e:  # noqa: BLE001
            print(f"{url}: {e}", file=sys.stderr)
            tmp.unlink(missing_ok=True)
            continue
        tmp.chmod(0o644)
        tmp.replace(DEST)
        print(f"wrote {DEST} from {url} ({DEST.stat().st_size / 2**20:.1f} MB)")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
