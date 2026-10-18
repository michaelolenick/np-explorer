#!/bin/sh
# Load the given source keys (DB writes; load.py waits out the 04:30-06:30 UTC window). Usage: load_keys.sh key [key ...]
set -a; . "$HOME/np-explorer/.env"; set +a
cd "$(dirname "$0")"
exec flock /tmp/unipay-heavy.lock nice -n 19 ionice -c3 "$HOME/unipay-venv/bin/python" load.py "$@" 2>&1 | sed -u "s#postgresql://[^ ]*#<redacted>#g"
