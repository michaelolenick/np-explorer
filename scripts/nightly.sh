#!/bin/sh
# Nightly (cron, 05:00 UTC): check IRS for new monthly zips and BMF updates, load them, re-cluster, rebuild the sitemap.
# If the backfill loader holds the lock (exit 3), wait and retry; it re-clusters as it goes.
cd "$(dirname "$0")/.." || exit 1
# The start mark: the site check (scripts/health.py) reads only the latest run's lines after it.
echo "=== nightly run $(date -u '+%Y-%m-%d %H:%M') UTC ==="
# Re-render nginx's fallback pages first so dates in them (the footer year) stay current.
.venv/bin/python scripts/render_static.py > /dev/null || echo "render_static failed" >&2
# Sundays every IRS year is rechecked (files already downloaded and loaded are skipped); other nights the
# current and previous year.
all_years=
[ "$(date -u +%u)" = 7 ] && all_years=--all-years
while :; do
    .venv/bin/python scripts/load.py nightly $all_years
    rc=$?
    [ "$rc" -ne 3 ] && break
    sleep 600
done
[ "$rc" -ne 0 ] && echo "irs nightly failed (exit $rc)" >&2
# IRS exempt status for every organization (loader/irs_status.py): the full BMF rows just refreshed above, 990-N
# e-postcards, Pub 78 and auto-revocations (re-downloaded only when the IRS republishes them).
.venv/bin/python -m loader.irs_status || echo "irs status failed" >&2
# SEC Form ADV (loader/adv.py): loads any new filing-data file the SEC has posted (a few a year), then relinks.
.venv/bin/python -m loader.adv || echo "form adv failed" >&2
# --- SEC data kept current (loader/sec_bulk.py, loader/adv.py) ---
# Weekly, Sunday night: insider Forms 3/4/5 and Form D quarters newer than the last one loaded (a quarter not yet
# published is skipped and tried next week), exec pay from XBRL, derived tables and the SEC leaderboards. Before
# buybacks below, so its insider sales see the new quarters.
[ "$(date -u +%u)" = 7 ] && { .venv/bin/python -m loader.sec_bulk refresh || echo "sec refresh failed" >&2; }
# Monthly, from the 5th: the SEC's monthly adviser reports (posted on the 1st or 2nd), any not loaded yet, then
# relinks. Retried every night until a run succeeds for the month (done-marker per month).
adv_done=/data/raw/.adv-monthly-$(date -u +%Y-%m)
[ "$(date -u +%d)" -ge 5 ] && [ ! -e "$adv_done" ] && {
    if .venv/bin/python -m loader.adv --monthly; then touch "$adv_done"; else echo "form adv monthly failed" >&2; fi; }
# --- end SEC data ---
# Form D and ADV people in person search (loader/fund_people.py): after the Form D and ADV loads above, and nightly
# because re-clustering can renumber the people they link to.
.venv/bin/python -m loader.fund_people || echo "fund people failed" >&2
# Nearby + Similar (loader/similar.py): organizations placed by ZIP, word frequencies of the 990 text index, and
# funder-recipient links, after the IRS and grants loads.
.venv/bin/python -m loader.similar || echo "similar failed" >&2
# Share buybacks (loader/buybacks.py): new Financial Statement Data Sets, 10b5-1 flags, 8-K announcements and
# monthly repurchase tables from new filings, then insider sales against buybacks.
.venv/bin/python -m loader.buybacks run || echo "buybacks failed" >&2
# Securities registration (loader/registrations.py): the SEC broker-dealer list (monthly) and the IAPD
# compilation reports (daily), other business names, links to people and firms.
.venv/bin/python -m loader.registrations || echo "registrations failed" >&2
# State business registries (loader/business_registry.py): weekly, Sunday night (states update daily to monthly).
[ "$(date -u +%u)" = 7 ] && { .venv/bin/python -m loader.business_registry || echo "business registry failed" >&2; }
# USPTO patents and trademarks (loader/uspto.py): weekly, Sunday night, like the business registries. One listing
# request per product; a product reloads only when USPTO has published a newer release (quarterly or yearly).
[ "$(date -u +%u)" = 7 ] && { .venv/bin/python -m loader.uspto refresh || echo "uspto refresh failed" >&2; }
# Public pension private equity reports (loader/pensions.py): the 1st of each month (CalPERS quarterly, CalSTRS yearly).
[ "$(date -u +%d)" = 01 ] && { .venv/bin/python -m loader.pensions || echo "pensions failed" >&2; }
exit "$rc"
