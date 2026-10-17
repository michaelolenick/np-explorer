#!/bin/sh
# Nightly (cron): check IRS for new monthly zips, load them, re-cluster, rebuild the sitemap.
# If the backfill loader holds the lock (exit 3), wait and retry; it re-clusters as it goes.
cd "$(dirname "$0")/.." || exit 1
while :; do
    .venv/bin/python scripts/load.py nightly
    rc=$?
    [ "$rc" -eq 3 ] || exit "$rc"
    sleep 600
done
