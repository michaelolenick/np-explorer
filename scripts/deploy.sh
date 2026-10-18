#!/bin/sh
# Deploy origin/main to production. Run ON the production VM:
#     ssh michael@20.168.8.141 ~/np-explorer/scripts/deploy.sh
# Work happens on the dev box (dev.strategystudio.org) and reaches production only
# through GitHub, so production files are never edited in place.
#
# 1. Fetch origin/main and run the tests on it in a scratch worktree, before the
#    live checkout changes. A failing test stops the deploy with nothing touched.
# 2. Fast-forward the live checkout (refuses if production has local commits or edits).
# 3. Re-render the fallback pages (changed requirements are installed before the tests).
# 4. SIGHUP uvicorn: workers restart one by one, so no request is dropped.
# 5. Smoke-test a few pages.
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

git merge -q --ff-only "$NEW"
"$PY" scripts/render_static.py > /dev/null

sudo systemctl kill -s HUP --kill-whom=main np-explorer
sleep 8
fail=0
for path in / /about /search?q=smith /boards; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8000$path")"
    echo "$code $path"
    [ "$code" = 200 ] || fail=1
done
[ "$fail" -eq 0 ] || { echo "smoke test failed: check journalctl -u np-explorer"; exit 1; }
echo "deployed $(git log --oneline -1)"
