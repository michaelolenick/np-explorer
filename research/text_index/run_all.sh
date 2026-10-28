#!/usr/bin/env bash
# The whole topic index, start to finish, after extract_text.py has run on prod (owner, 2026-10-28). Runs unattended
# (tmux on the dev box): builds the index, labels "space" and the other ambiguous terms, answers the saved questions,
# writes RESULTS.md, then commits research/text_index to the repo. Log: ~/text-index.log
#
# Usage:  tmux new -d -s textindex 'bash research/text_index/run_all.sh >> ~/text-index.log 2>&1'
#         WAIT_FOR_BUILD=1 ...   when build.sql is already running elsewhere (waits for its BUILD_EXIT line)
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
export LC_ALL=C.UTF-8 PYTHONPATH=.
T=research/text_index
PY=.venv/bin/python
say() { echo "$(date '+%F %T') $*"; }

say "waiting for the XML extraction on prod to finish"
until [ "$(psql "$DATABASE_URL" -At -c "SELECT count(*) >= 1600 AND max(done_at) < now() - interval '5 minutes'
                                        FROM research.text_extract_done")" = "t" ]; do sleep 60; done

if [ "${WAIT_FOR_BUILD:-}" = 1 ]; then
    say "waiting for the running build"
    until grep -q "BUILD_EXIT" ~/text-index.log; do sleep 60; done
    grep -q "BUILD_EXIT 0" ~/text-index.log || { say "build failed; stopping"; exit 1; }
else
    say "build: filing_text, org_text, indexes, functions"
    psql "$DATABASE_URL" -q -v ON_ERROR_STOP=1 -f $T/build.sql
fi

say "questions and the space candidates"
psql "$DATABASE_URL" -q -v ON_ERROR_STOP=1 -f $T/questions.sql
say "space: Haiku labels (second pass retries failures)"
$PY $T/classify.py space
$PY $T/classify.py space

say "other ambiguous terms: definitions, hand-labeled test, false hits, rule pass, Haiku labels"
$PY $T/senses.py sync
$PY $T/senses.py test
$PY $T/senses.py falsehits 1
$PY $T/senses.py rules 2
$PY $T/senses.py label
$PY $T/senses.py label --small                 # second pass: smaller batches for whatever the first missed
say "sense counts and the cleaned questions"
psql "$DATABASE_URL" -q -v ON_ERROR_STOP=1 -f $T/senses.sql

say "results"
$PY $T/report.py
psql "$DATABASE_URL" -q -c "DROP SCHEMA IF EXISTS rtest CASCADE"   # the small test build from 2026-10-28

say "commit"
git add $T
.venv/bin/gitleaks protect --staged --no-banner
git commit -q -m "Topic index over the 990 filings, with senses for ambiguous terms

Part III and Schedule O text; filing_text and org_text with full-text and trigram indexes; topic_count /
topic_breakdown with 'topic:sense'; space, women, men, domestic, violence, abuse, shelter, survivor, science,
mission/launch and girls/boys split into senses (exact phrases plus Claude Haiku labels); saved questions;
RESULTS.md

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push -q origin HEAD:main
say "done: $T/RESULTS.md ($(git log -1 --format=%h))"
