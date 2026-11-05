#!/bin/sh
# One wave of the categorization helper (owner, 2026-11-05): submit batches for both kinds up to the wave's dollars,
# wait for every batch, write the answers, rebuild nonprofit_ntee, the category counts and the cross-dataset counts,
# and email the owner if anything fails (mailer.notify_owner). Run on dev, in the background:
#     (nohup scripts/categorize-run.sh 30 12 > /bulk/ntee/categorize.log 2>&1 < /dev/null &)
# Arguments: dollars for the nonprofit wave, dollars for the Form D wave (0 skips a kind); a third argument "pass2 T"
# style is not supported here: pass 2 is run with loader.categorize submit --pass 2 --threshold T, then this script
# with 0 0 to collect.
set -u
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
PY=.venv/bin/python
NP=${1:-0}; FD=${2:-0}
alert() {
    $PY -c "import sys; from app import mailer; mailer.notify_owner('Categorization', sys.argv[1], sys.argv[2])" "$1" "$2" \
        || echo "could not email the owner: $1" >&2
}
say() { echo "$(date '+%F %T') $*"; }
fail() { say "FAILED: $1"; alert "Categorization stopped: $1" "$(tail -n 40 /bulk/ntee/categorize.log 2>/dev/null)"; exit 1; }

if [ "$NP" != 0 ]; then
    say "submitting nonprofits, wave \$$NP"
    $PY -u -m loader.categorize submit nonprofit --wave "$NP" || fail "nonprofit submit"
fi
if [ "$FD" != 0 ]; then
    say "submitting Form D, wave \$$FD"
    $PY -u -m loader.categorize submit formd --wave "$FD" || fail "Form D submit"
fi
say "collecting"
$PY -u -m loader.categorize collect || fail "collect"
say "rebuilding nonprofit_ntee, counts and cross-dataset counts"
$PY -u -m loader.categorize build || fail "build"
$PY -c "from app import categories; categories.build_cross_dataset_counts()" || fail "cross-dataset counts"
$PY -u -m loader.categorize status
say "wave done"
