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
# IPO registrations (loader/s1.py): the current quarter's EDGAR index, the submissions zip (1.5 GB, weekly) and the ties.
[ "$(date -u +%u)" = 7 ] && { .venv/bin/python -m loader.s1 || echo "s1 failed" >&2; }
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
# Minnesota business registry (loader/minnesota_registry.py): a file the owner requests from the state and drops in
# /bulk/registry/mn/YYYY-MM-DD/ (docs/minnesota-business-layout.md). Checked nightly; loads only when the newest file
# isn't the one last loaded.
.venv/bin/python -m loader.minnesota_registry --if-new || echo "minnesota registry failed" >&2
# FARA registrations (loader/fara.py): the Justice Department's three bulk files (a few MB, updated daily), then links.
.venv/bin/python -m loader.fara || echo "fara failed" >&2
# Form 5500 (loader/form5500.py): DOL republishes the yearly files around the 1st of each month; on the 3rd, download
# any changed file, reload, rebuild the sponsor table and the registry supplement.
[ "$(date -u +%d)" = 03 ] && { .venv/bin/python -m loader.form5500 download load summarize supplement || echo "form5500 failed" >&2; }
# State and city payroll (loader/gov_payroll.py): on the 6th, refetch every source and rebuild the payroll tables.
[ "$(date -u +%d)" = 06 ] && { .venv/bin/python -m loader.gov_payroll all && .venv/bin/python -m loader.gov_payroll finish || echo "gov payroll failed" >&2; }
# Open Payments (loader/openpayments.py) is reloaded by hand when CMS publishes (June and January): 100 million rows.
# Cross-links between the four datasets above and the rest of the site (loader/xlinks.py), after the loads and links.
.venv/bin/python -m loader.xlinks || echo "xlinks failed" >&2
# NTEE codes (loader/ntee.py): the taxonomy, nonprofit_ntee (published + inferred) and the category counts. The
# inference run itself is by hand ("loader.ntee infer --budget N").
.venv/bin/python -m loader.ntee all || echo "ntee failed" >&2
# The categories page's "across datasets" counts (app/categories.py build_cross_dataset_counts): minutes of joins.
.venv/bin/python -c "from app import categories; categories.build_cross_dataset_counts()" || echo "category xref counts failed" >&2
# Abbreviations and full names (loader/name_aliases.py): "IBM" = International Business Machines, after the registry
# loads above. The registry pairs are recomputed only when the registry tables changed.
.venv/bin/python -m loader.name_aliases || echo "name aliases failed" >&2
# USDA FSIS meat, poultry and egg recalls (loader/fsis_recalls.py): ONE request a night to the FSIS recall API, as agreed
# with FSIS (owner, 2026-11-02; done-marker per day); new and changed recalls upserted, then firms, links and boards.
.venv/bin/python -m loader.fsis_recalls || echo "fsis recalls failed" >&2
# USPTO patents and trademarks (loader/uspto.py): weekly, Sunday night, like the business registries. One listing
# request per product; a product reloads only when USPTO has published a newer release (quarterly or yearly).
[ "$(date -u +%u)" = 7 ] && { .venv/bin/python -m loader.uspto refresh || echo "uspto refresh failed" >&2; }
# Public pension private equity reports (loader/pensions.py): the 1st of each month (CalPERS quarterly, CalSTRS yearly).
[ "$(date -u +%d)" = 01 ] && { .venv/bin/python -m loader.pensions || echo "pensions failed" >&2; }
# Yesterday's bot traffic that passed as human (scripts/reclass_bots.py), before the 07:00 report reads the day.
.venv/bin/python scripts/reclass_bots.py --days 1 || echo "reclass bots failed" >&2
# The closing mark: app/report.py reads it (a night that ends without it did not finish).
echo "=== nightly done (exit $rc) $(date -u '+%Y-%m-%d %H:%M') UTC ==="
exit "$rc"
