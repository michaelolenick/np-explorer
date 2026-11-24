#!/bin/sh
# Nightly (cron, 05:00 UTC): check IRS for new monthly zips and BMF updates, load them, re-cluster, rebuild the sitemap.
# If the backfill loader holds the lock (exit 3), wait and retry; it re-clusters as it goes.
cd "$(dirname "$0")/.." || exit 1
# Every source below runs through src NAME COMMAND...: a failure logs one clear line with the exit code and the last error
# line the loader printed (curl and urllib errors carry the HTTP status) and never stops the sources after it.
src() {
    _n=$1; shift
    _t=$(mktemp)
    { { "$@" 2>&1 1>&3 3>&-; echo $? > "$_t.rc"; } | tee "$_t" >&2; } 3>&1
    _c=$(cat "$_t.rc" 2>/dev/null); _c=${_c:-1}
    if [ "$_c" -ne 0 ]; then
        echo "$_n failed (exit $_c): $(grep -iE 'HTTP|curl:|error|exception' "$_t" | tail -1 | cut -c1-300)" >&2
    fi
    rm -f "$_t" "$_t.rc"
    return "$_c"
}
# The start mark: the site check (scripts/health.py) reads only the latest run's lines after it.
echo "=== nightly run $(date -u '+%Y-%m-%d %H:%M') UTC ==="
# Re-render nginx's fallback pages first so dates in them (the footer year) stay current.
src "render_static" .venv/bin/python scripts/render_static.py > /dev/null
# Sundays every IRS year is rechecked (files already downloaded and loaded are skipped); other nights the
# current and previous year.
# The suppression list (loader/suppression.py): the insert guard on people, then a sweep of every other person table, before the
# loads, after the IRS and registry loads, and at the end, so a suppressed person who reappears is removed and logged (hits go in the report).
src "suppression sweep" .venv/bin/python -m loader.suppression sweep
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
src "suppression sweep" .venv/bin/python -m loader.suppression sweep
src "irs status" .venv/bin/python -m loader.irs_status
# SEC Form ADV (loader/adv.py): loads any new filing-data file the SEC has posted (a few a year), then relinks.
src "form adv" .venv/bin/python -m loader.adv
# --- SEC data kept current (loader/sec_bulk.py, loader/adv.py) ---
# Weekly, Sunday night: insider Forms 3/4/5 and Form D quarters newer than the last one loaded (a quarter not yet
# published is skipped and tried next week), exec pay from XBRL, derived tables and the SEC leaderboards. Before
# buybacks below, so its insider sales see the new quarters.
[ "$(date -u +%u)" = 7 ] && { src "sec refresh" .venv/bin/python -m loader.sec_bulk refresh; }
# IPO registrations (loader/s1.py): the current quarter's EDGAR index, the submissions zip (1.5 GB, weekly) and the ties.
[ "$(date -u +%u)" = 7 ] && { src "s1" .venv/bin/python -m loader.s1; }
# Offering terms (loader/s1_terms.py): the prospectus cover pages of registrants not read yet (a few hundred a week), the
# roll-ups onto ipo_companies and ipo_underwriters, then the pricing and underwriter boards (app/ipo_terms_boards.py).
[ "$(date -u +%u)" = 7 ] && { src "s1 terms" .venv/bin/python -m loader.s1_terms --limit 4000; }
# Major companies (loader/major_companies.py): the list weekly; every night the filings of those with a new 10-K, 20-F or S-1 are read
# ahead of time for the strategic profile (app/s1profile.py), so their pages load instantly. Bounded to three hours.
src "major companies" .venv/bin/python -m loader.major_companies refresh --budget 10800
[ "$(date -u +%u)" = 7 ] && { src "ipo terms boards" .venv/bin/python scripts/load.py boards --only ipo-biggest,ipo-priced-below-range,ipo-priced-above-range,ipo-busiest-underwriters; }
# IPO and benefit plan leaderboards (app/ipo_boards.py, app/form5500_boards.py): weekly, after the S-1 and SEC refreshes
# above. The private fund boards (sec-adv-*, app/fund_boards.py) are refreshed by loader.sec_bulk's boards step.
[ "$(date -u +%u)" = 7 ] && { src "ipo/5500 boards" .venv/bin/python scripts/load.py boards --only ipo-most-amended,ipo-longest-withdrawn,ipo-serial-registrants,ipo-federal-awards,ipo-lobbying,ipo-nonprofit-insiders,ipo-benefit-plans,f5500-most-plans,f5500-nonprofit-plans,f5500-gone-quiet,f5500-federal-awards,f5500-lobbying; }
# Monthly, from the 5th: the SEC's monthly adviser reports (posted on the 1st or 2nd), any not loaded yet, then
# relinks. Retried every night until a run succeeds for the month (done-marker per month).
adv_done=/data/raw/.adv-monthly-$(date -u +%Y-%m)
[ "$(date -u +%d)" -ge 5 ] && [ ! -e "$adv_done" ] && {
    if .venv/bin/python -m loader.adv --monthly; then touch "$adv_done"; else echo "form adv monthly failed" >&2; fi; }
# --- end SEC data ---
# Form D and ADV people in person search (loader/fund_people.py): after the Form D and ADV loads above, and nightly
# because re-clustering can renumber the people they link to.
src "fund people" .venv/bin/python -m loader.fund_people
# Nearby + Similar (loader/similar.py): organizations placed by ZIP, word frequencies of the 990 text index, and
# funder-recipient links, after the IRS and grants loads.
src "similar" .venv/bin/python -m loader.similar
# Share buybacks (loader/buybacks.py): new Financial Statement Data Sets, 10b5-1 flags, 8-K announcements and
# monthly repurchase tables from new filings, then insider sales against buybacks.
src "buybacks" .venv/bin/python -m loader.buybacks run
# Securities registration (loader/registrations.py): the SEC broker-dealer list (monthly) and the IAPD
# compilation reports (daily), other business names, links to people and firms.
src "registrations" .venv/bin/python -m loader.registrations
# State business registries (loader/business_registry.py): weekly, Sunday night (states update daily to monthly).
[ "$(date -u +%u)" = 7 ] && { src "business registry" .venv/bin/python -m loader.business_registry; }
# Minnesota business registry (loader/minnesota_registry.py): a file the owner requests from the state and drops in
# /bulk/registry/mn/YYYY-MM-DD/ (docs/minnesota-business-layout.md). Checked nightly; loads only when the newest file
# isn't the one last loaded.
src "minnesota registry" .venv/bin/python -m loader.minnesota_registry --if-new
src "suppression sweep" .venv/bin/python -m loader.suppression sweep
# FARA registrations (loader/fara.py): the Justice Department's three bulk files (a few MB, updated daily), then links.
src "fara" .venv/bin/python -m loader.fara
# Form 5500 (loader/form5500.py): DOL republishes the yearly files around the 1st of each month; on the 3rd, download
# any changed file, reload, rebuild the sponsor table and the registry supplement.
[ "$(date -u +%d)" = 03 ] && { src "form5500" .venv/bin/python -m loader.form5500 download load summarize supplement; }
# State and city payroll (loader/gov_payroll.py): on the 6th, refetch every source and rebuild the payroll tables.
[ "$(date -u +%d)" = 06 ] && { src "gov payroll all" .venv/bin/python -m loader.gov_payroll all && src "gov payroll finish" .venv/bin/python -m loader.gov_payroll finish; }
# UK companies (loader/uk_companies.py, owner 2026-11-14): Companies House's monthly Free Company Data snapshot and PSC snapshot. One
# page listing check a night; when a new snapshot is published: reload, summaries, cross-references; then the UK company boards
# (exit 10 = changed, 0 = unchanged). NP_NOW=1: the night already is the quiet window.
NP_NOW=1 .venv/bin/python -m loader.uk_companies nightly; ukco_rc=$?
[ "$ukco_rc" = 10 ] && { src "uk company boards" env NP_NOW=1 .venv/bin/python scripts/load.py boards --only uk-companies-new-by-sic,uk-psc-networks,uk-company-status-by-region; }
[ "$ukco_rc" != 0 ] && [ "$ukco_rc" != 10 ] && echo "uk companies failed (exit $ukco_rc)" >&2
# Companies House officers and profiles (loader/uk_officers.py, owner 2026-11-14): ONE fetcher runs continuously on dev (dev and prod share one
# API key and its 600-requests-per-5-minutes limit; a Postgres advisory lock keeps a second copy out). `ensure` restarts it if it is not running
# (only on the box with ~/claude_scripts/companies_house/RUN_HERE; dev's cron also runs it every 3 minutes). Then officer_stats, the officer
# cross-references (published after the first manual publish) and the three officer boards.
src "uk officers ensure" .venv/bin/python -m loader.uk_officers ensure
src "uk officers enqueue" .venv/bin/python -m loader.uk_officers enqueue
src "uk officers xref" .venv/bin/python -m loader.uk_officers_xref refresh
src "uk officer boards" .venv/bin/python scripts/load.py boards --only uk-officers-most-appointments,uk-officers-also-trustees,uk-officers-also-us
# Open Payments (loader/openpayments.py) is reloaded by hand when CMS publishes (June and January): 100 million rows.
# Cross-links between the four datasets above and the rest of the site (loader/xlinks.py), after the loads and links.
src "xlinks" .venv/bin/python -m loader.xlinks
# The continuous cross-referencing engine (loader/xref.py, owner 2026-11-13): every record kind to every other, and to
# its interests. Dev sweeps new records every two hours (its crontab); the full rebuild runs here weekly, Sunday night,
# after the xlinks rebuild above (NP_NOW=1: the night already is the quiet window).
[ "$(date -u +%u)" = 7 ] && { src "xref rebuild" env NP_NOW=1 .venv/bin/python -m loader.xref rebuild; }
src "xref sweep" .venv/bin/python -m loader.xref sweep --budget 600
# UK charities (loader/uk_charities.py, owner 2026-11-14): one conditional download per Charity Commission extract file (nothing is
# fetched when Last-Modified/ETag are unchanged); only when the register changed: reload, summary, UK to US matches, xlinks rows,
# then the UK boards (exit 10 = changed, 0 = unchanged). NP_NOW=1: the night already is the quiet window.
NP_NOW=1 .venv/bin/python -m loader.uk_charities nightly; uk_rc=$?
[ "$uk_rc" = 10 ] && { src "uk boards" env NP_NOW=1 .venv/bin/python scripts/load.py boards --only uk-largest-income,uk-most-trustees,uk-fastest-growing,uk-staff-over-60k,uk-with-us-counterpart,uk-us-grants,uk-income-by-region; }
[ "$uk_rc" != 0 ] && [ "$uk_rc" != 10 ] && echo "uk charities failed (exit $uk_rc)" >&2
# NTEE codes (loader/ntee.py): the taxonomy, nonprofit_ntee (published + inferred) and the category counts. The
# inference run itself is by hand ("loader.ntee infer --budget N").
src "ntee" .venv/bin/python -m loader.ntee all
# The categories page's "across datasets" counts (app/categories.py build_cross_dataset_counts): minutes of joins.
.venv/bin/python -c "from app import categories; categories.build_cross_dataset_counts()" || echo "category xref counts failed" >&2
# Abbreviations and full names (loader/name_aliases.py): "IBM" = International Business Machines, after the registry
# loads above. The registry pairs are recomputed only when the registry tables changed.
src "name aliases" .venv/bin/python -m loader.name_aliases
# USDA FSIS meat, poultry and egg recalls (loader/fsis_recalls.py): ONE request a night to the FSIS recall API, as agreed
# with FSIS (owner, 2026-11-02; done-marker per day); new and changed recalls upserted, then firms, links and boards.
src "fsis recalls" .venv/bin/python -m loader.fsis_recalls
# USPTO patents and trademarks (loader/uspto.py): weekly, Sunday night, like the business registries. One listing
# request per product; a product reloads only when USPTO has published a newer release (quarterly or yearly).
[ "$(date -u +%u)" = 7 ] && { src "uspto refresh" .venv/bin/python -m loader.uspto refresh; }
# Public pension private equity reports (loader/pensions.py): the 1st of each month (CalPERS quarterly, CalSTRS yearly).
[ "$(date -u +%d)" = 01 ] && { src "pensions" .venv/bin/python -m loader.pensions; }
# GDELT news (loader/gdelt.py, owner 2026-11-14): yesterday's GKG files filtered and loaded (NP_NOW=1: the loader waits for the quiet hours itself
# on weekdays), the per-entity counts and the /news-index totals rebuilt; the name dictionaries are rebuilt every Sunday.
[ "$(date -u +%u)" = 7 ] && { src "gdelt dict" .venv/bin/python -m loader.gdelt dict && src "gdelt maps" .venv/bin/python -m loader.gdelt maps; }
src "gdelt daily" .venv/bin/python -m loader.gdelt daily
# FRED (loader/fred.py): weekly, Sunday night: new observations for every series FRED has updated since the last fetch
# (county unemployment arrives monthly), then fred.area_latest, fred.county_trend and the FRED boards. Needs FRED_API_KEY in .env.
[ "$(date -u +%u)" = 7 ] && { src "fred refresh" .venv/bin/python -m loader.fred refresh; }
src "suppression sweep" .venv/bin/python -m loader.suppression sweep
# Yesterday's bot traffic that passed as human (scripts/reclass_bots.py), before the 07:00 report reads the day.
src "reclass bots" .venv/bin/python scripts/reclass_bots.py --days 1
# The closing mark: app/report.py reads it (a night that ends without it did not finish).
echo "=== nightly done (exit $rc) $(date -u '+%Y-%m-%d %H:%M') UTC ==="
exit "$rc"
