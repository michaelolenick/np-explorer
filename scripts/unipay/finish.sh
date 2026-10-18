#!/bin/sh
# Post-load steps: Gray Book reload with campus filter, IPEDS averages, matching views, report, deliverables, catalog doc.
set -a; . "$HOME/np-explorer/.env"; set +a
cd "$(dirname "$0")"
PY="nice -n 19 ionice -c3 $HOME/unipay-venv/bin/python"
U=$(echo "$DATABASE_URL" | sed "s#+psycopg##")
$PY load.py il_graybook
$PY ipeds_load.py
LC_ALL=C.UTF-8 nice -n 19 psql "$U" -v ON_ERROR_STOP=1 -q -f matching.sql && echo matching ok
LC_ALL=C.UTF-8 nice -n 19 psql "$U" -q -c "ANALYZE unipay.public_payroll_records; ANALYZE unipay.payroll_institutions;"
$PY report.py
$PY deliverables.py "University of Connecticut"
$PY catalog_doc.py
