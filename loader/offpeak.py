"""Keep maintenance off peak (owner, 2026-11-06). Prod reads the same Postgres as the loaders, and a rebuild's
ALTER TABLE, CREATE INDEX, DROP/RENAME or long COPY blocks page queries into their 5-second statement timeout: the
235 timeouts of 2026-11-05 clustered at 13:00-14:00 and 23:00 Central, when rebuilds ran by hand and the nightly
began. Heavy rebuilds call wait() first: between QUIET_END and QUIET_START Central they wait for QUIET_START
(printing why), unless NP_NOW=1 is set (an emergency, or a rebuild the owner wants now)."""

from __future__ import annotations

import datetime as dt
import os
import time
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
# The owner's window for heavy work (2026-11-12): 8 PM Eastern to 9 AM CET, i.e. 19:00 to 02:00 Central
# (the US has gone home, Europe is not up yet). Standard time; a DST mismatch shifts an edge by an hour.
QUIET_START = 19        # 19:00 Central (8 PM Eastern): the quiet hours begin
QUIET_END = 2           # 02:00 Central (9 AM CET): they end


def is_quiet(now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(CHICAGO)
    return now.hour >= QUIET_START or now.hour < QUIET_END


def seconds_until_quiet(now: dt.datetime | None = None) -> float:
    now = now or dt.datetime.now(CHICAGO)
    if is_quiet(now):
        return 0.0
    start = now.replace(hour=QUIET_START, minute=0, second=0, microsecond=0)
    return (start - now).total_seconds()


def wait(label: str, status=print, sleep=time.sleep) -> bool:
    """Wait for the quiet hours before a heavy rebuild; True if it waited. NP_NOW=1 skips the wait."""
    if os.environ.get("NP_NOW") == "1":
        return False
    secs = seconds_until_quiet()
    if secs <= 0:
        return False
    status(f"{label}: waiting {secs / 60:.0f} min for the quiet hours ({QUIET_START}:00 Central; NP_NOW=1 runs now)")
    sleep(secs)
    return True
