#!/usr/bin/env python3
"""Natural-language search: today's calls, tokens, estimated cost, and p50/p95 timings.

Counts come from the nl_usage table (no query text); timings from logs/nl-timings.log.
Prices are per million tokens: NL_PRICE_IN and NL_PRICE_OUT (defaults are claude-sonnet-5-5
list prices at the time of writing; set them to your plan's rates).
Usage: .venv/bin/python scripts/nl_cost.py [--days 7]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import ROOT as APP_ROOT  # noqa: E402
from loader import db  # noqa: E402

PRICE_IN = float(os.environ.get("NL_PRICE_IN", "2.00"))
PRICE_OUT = float(os.environ.get("NL_PRICE_OUT", "10.00"))
TIMINGS = APP_ROOT / "logs" / "nl-timings.log"


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))] if xs else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=1)
    args = ap.parse_args()
    with db.connect() as conn:
        rows = conn.execute("""SELECT day, calls, cache_hits, skipped, fallbacks, input_tokens, output_tokens
                               FROM nl_usage WHERE day > current_date - %s ORDER BY day DESC""",
                            (args.days,)).fetchall()
    print(f"{'day':<12}{'calls':>7}{'cached':>8}{'skipped':>9}{'fallback':>10}{'in tok':>10}{'out tok':>9}{'est $':>9}")
    for day, calls, hits, skipped, fb, tin, tout in rows:
        cost = tin / 1e6 * PRICE_IN + tout / 1e6 * PRICE_OUT
        print(f"{day!s:<12}{calls:>7}{hits:>8}{skipped:>9}{fb:>10}{tin:>10,}{tout:>9,}{cost:>9.4f}")
    if not rows:
        print("(no natural-language searches yet)")
    print(f"prices: ${PRICE_IN}/M input, ${PRICE_OUT}/M output (NL_PRICE_IN, NL_PRICE_OUT)")

    since = time.time() - args.days * 86400
    by = defaultdict(list)
    try:
        for line in TIMINGS.read_text().splitlines():
            ts, total, _parse, outcome = line.split(" ", 3)
            if int(ts) >= since:
                by[outcome.split(":")[0]].append(float(total))
    except FileNotFoundError:
        pass
    print(f"\nend-to-end time (ms), last {args.days} day(s):")
    for how, xs in sorted(by.items()):
        print(f"  {how:<16} n={len(xs):<6} p50={pct(xs, 50):>6.0f}  p95={pct(xs, 95):>6.0f}")
    if not by:
        print("  (none)")


if __name__ == "__main__":
    main()
