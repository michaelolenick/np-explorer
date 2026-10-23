#!/bin/sh
# Nightly (cron, 05:00 UTC): check IRS for new monthly zips and BMF updates, load them, re-cluster, rebuild the sitemap.
# If the backfill loader holds the lock (exit 3), wait and retry; it re-clusters as it goes.
cd "$(dirname "$0")/.." || exit 1
# Re-render nginx's fallback pages first so dates in them (the footer year) stay current.
.venv/bin/python scripts/render_static.py > /dev/null || echo "render_static failed" >&2
while :; do
    .venv/bin/python scripts/load.py nightly
    rc=$?
    [ "$rc" -ne 3 ] && break
    sleep 600
done
# IRS exempt status for every organization (loader/irs_status.py): the full BMF rows just refreshed above, 990-N
# e-postcards, Pub 78 and auto-revocations (re-downloaded only when the IRS republishes them).
.venv/bin/python -m loader.irs_status || echo "irs status failed" >&2
# SEC Form ADV (loader/adv.py): loads any new filing-data file the SEC has posted (a few a year), then relinks.
.venv/bin/python -m loader.adv || echo "form adv failed" >&2
# Share buybacks (loader/buybacks.py): new Financial Statement Data Sets, 10b5-1 flags, 8-K announcements and
# monthly repurchase tables from new filings, then insider sales against buybacks.
.venv/bin/python -m loader.buybacks run || echo "buybacks failed" >&2
# Securities registration (loader/registrations.py): the SEC broker-dealer list (monthly) and the IAPD
# compilation reports (daily), other business names, links to people and firms.
.venv/bin/python -m loader.registrations || echo "registrations failed" >&2
# State business registries (loader/business_registry.py): weekly, Sunday night (states update daily to monthly).
[ "$(date -u +%u)" = 7 ] && { .venv/bin/python -m loader.business_registry || echo "business registry failed" >&2; }
exit "$rc"
