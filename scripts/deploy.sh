#!/bin/sh
# Deploy origin/main to production. Run ON the production VM:
#     ssh michael@20.168.8.141 ~/np-explorer/scripts/deploy.sh
# Work happens on the dev box (dev.furp.org) and reaches production only
# through GitHub, so production files are never edited in place.
#
# 1. Fetch origin/main and run the tests on it in a scratch worktree, before the
#    live checkout changes. A failing test stops the deploy with nothing touched.
# 2. Fast-forward the live checkout (refuses if production has local commits or edits).
# 3. Re-render the fallback pages (changed requirements are installed before the tests).
# 4. SIGHUP uvicorn: workers restart one by one, so no request is dropped.
# 5. Smoke-test a few pages.
# The whole script is one { ... } block, so bash reads all of it before running any of it:
# this script is itself updated by the git merge below.
{
set -eu
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"

git fetch -q origin main
OLD="$(git rev-parse HEAD)"
NEW="$(git rev-parse origin/main)"
if [ "$OLD" = "$NEW" ]; then
    echo "already at $(git log --oneline -1)"
    exit 0
fi
echo "deploying:"; git log --oneline "$OLD..$NEW"

TMP="$(mktemp -d)"
trap 'git worktree remove --force "$TMP" 2>/dev/null || true; rm -rf "$TMP"' EXIT
git worktree add -q --detach "$TMP" "$NEW"
# New requirements go in before the tests, so the tests run against what the commit needs.
if git diff --name-only "$OLD" "$NEW" | grep -q '^requirements.txt$'; then
    "$ROOT/.venv/bin/pip" install -q -r "$TMP/requirements.txt"
fi
( cd "$TMP" && set -a && . "$ROOT/.env" && set +a && "$PY" -m pytest -q ) || { echo "tests failed: nothing deployed"; exit 1; }
# The fallback pages must render with the new templates too, before the live checkout changes (2026-10-22: a
# template global missing here stopped a deploy after the merge, and old workers served new templates: 500s).
( cd "$TMP" && set -a && . "$ROOT/.env" && set +a && "$PY" scripts/render_static.py > /dev/null ) \
    || { echo "render_static failed: nothing deployed"; exit 1; }
# The search test set (tests/search_cases.yml) on the new code against the live database: the pass rate is
# reported and logged for the nightly report; it does not block a deploy.
( cd "$TMP" && set -a && . "$ROOT/.env" && set +a && timeout 900 "$PY" scripts/search_eval.py --quiet \
      --log "$ROOT/logs/search-eval.log" 2>/dev/null | tail -n 1 ) || echo "search test set did not finish"

git merge -q --ff-only "$NEW"
"$PY" scripts/render_static.py > /dev/null

sudo systemctl kill -s HUP --kill-whom=main np-explorer
sleep 8
# Workers restart one by one; give the last ones up to 30 more seconds before judging.
for _ in 1 2 3 4 5 6; do
    curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/" | grep -q 200 \
        && curl -s "http://127.0.0.1:8000/about" | grep -q "<title>About " && break
    sleep 5
done
fail=0
# Status and the page's own title (a route once rendered another page with a 200).
for check in "/|furp.org |" "/about|About |" "/data|Data |" "/privacy|Privacy |" \
             "/support|Support FURP |" "/search?q=smith|Search: smith" "/boards|Leaderboards |"; do
    path="${check%%|*}"; want="${check#*|}"
    body="$(curl -s -w '\n%{http_code}' "http://127.0.0.1:8000$path")"
    code="$(printf '%s' "$body" | tail -n 1)"
    title="$(printf '%s' "$body" | grep -o '<title>[^<]*' | head -n 1 | sed 's/<title>//')"
    echo "$code $path  ($title)"
    [ "$code" = 200 ] && case "$title" in *"$want"*) ;; *) fail=1 ;; esac || fail=1
done
[ "$fail" -eq 0 ] || { echo "smoke test failed: check journalctl -u np-explorer"; exit 1; }
echo "deployed $(git log --oneline -1)"
exit 0
}
