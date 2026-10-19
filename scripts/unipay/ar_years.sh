#!/bin/sh
# Arkansas ADHE survey FY2010-FY2025: verify and load one year at a time at low priority, taking the shared heavy-job
# lock per year so other jobs can run in between. A year is loaded only if pdf_more.verify_load says PASS.
# Usage: ar_years.sh [fy ...]   (default 2010..2025)
set -a; . "$HOME/np-explorer/.env"; set +a
cd "$(dirname "$0")"
YEARS=${*:-$(seq 2010 2025)}
for y in $YEARS; do
  UNIPAY_FILE="ar_adhe_fy$y.pdf" flock /tmp/unipay-heavy.lock nice -n 19 ionice -c3 "$HOME/unipay-venv/bin/python" pdf_more.py verify_load ar_adhe 2>&1 \
    | sed -u "s#postgresql://[^ ]*#<redacted>#g"
done
