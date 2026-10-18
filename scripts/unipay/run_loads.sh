#!/bin/sh
# Runs all pending loads (waits for the 01:30 end of the production load window inside load.py).
set -a; . "$HOME/np-explorer/.env"; set +a
cd "$(dirname "$0")"
exec nice -n 19 ionice -c3 "$HOME/unipay-venv/bin/python" load.py all-pending 2>&1 | sed -u "s#postgresql://[^ ]*#<redacted>#g"
