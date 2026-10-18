#!/bin/sh
# Nightly (cron, 05:00 UTC): check IRS for new monthly zips and BMF updates, load them, re-cluster, rebuild the sitemap.
# If the backfill loader holds the lock (exit 3), wait and retry; it re-clusters as it goes.
cd "$(dirname "$0")/.." || exit 1
# Re-render nginx's fallback pages first so dates in them (the footer year) stay current.
.venv/bin/python scripts/render_static.py > /dev/null || echo "render_static failed" >&2
while :; do
    .venv/bin/python scripts/load.py nightly
    rc=$?
    [ "$rc" -eq 3 ] || exit "$rc"
    sleep 600
done
