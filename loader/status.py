"""The loader's once-a-minute status line, plus a separate error log.

Stdout and loader.log get exactly one line every 60 seconds. Per-filing
problems (parse errors, unknown schema versions) go to loader-errors.log.
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
from datetime import datetime

from app.config import DATA_DIR, LOG_DIR

INTERVAL = 60


def disk_free_gb(path=DATA_DIR) -> float:
    return shutil.disk_usage(path).free / 2**30


def _fmt_dur(sec: float) -> str:
    sec = int(max(sec, 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


class Status:
    def __init__(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.start = time.time()
        self.lock = threading.Lock()
        self.phase = "starting"
        self.year: int | None = None
        self.year_total = 0          # filings expected this year (from the IRS index)
        self.year_done_before = 0    # filings already loaded for this year when we started it
        self.year_started = time.time()
        self.year_parsed = 0
        self.filings = 0
        self.people = 0
        self.contractors = 0
        self.errors = 0
        self._last_filings = 0
        self._last_t = time.time()
        self._stop = threading.Event()
        self._log = open(LOG_DIR / "loader.log", "a", buffering=1)
        self._err = open(LOG_DIR / "loader-errors.log", "a", buffering=1)
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start_ticker(self) -> None:
        self._thread.start()

    def begin_year(self, year: int, total: int, already: int) -> None:
        with self.lock:
            self.year, self.year_total, self.year_done_before = year, total, already
            self.year_parsed = 0
            self.year_started = time.time()

    def add(self, filings=0, people=0, contractors=0, errors=0) -> None:
        with self.lock:
            self.filings += filings
            self.year_parsed += filings
            self.people += people
            self.contractors += contractors
            self.errors += errors

    def error(self, msg: str) -> None:
        with self.lock:
            self.errors += 1
        self._err.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")

    def warn(self, msg: str) -> None:
        self._err.write(f"{datetime.now().isoformat(timespec='seconds')} WARN {msg}\n")

    def line(self) -> str:
        now = time.time()
        with self.lock:
            dt = max(now - self._last_t, 1e-6)
            rate = (self.filings - self._last_filings) / dt * 60
            self._last_filings, self._last_t = self.filings, now
            year_rate = self.year_parsed / max(now - self.year_started, 1e-6) * 60
            remaining = max(self.year_total - self.year_done_before - self.year_parsed, 0)
            eta = _fmt_dur(remaining / year_rate * 60) if year_rate > 0 and self.year else "-"
            done = self.year_done_before + self.year_parsed
            year = f"{self.year} {done:,}/{self.year_total:,}" if self.year else "-"
            return (f"[{datetime.now():%H:%M}] elapsed {_fmt_dur(now - self.start)} | {self.phase} | "
                    f"year {year} | filings {self.filings:,} | people {self.people:,} | "
                    f"contractors {self.contractors:,} | {rate:,.0f}/min | errors {self.errors:,} | "
                    f"disk free {disk_free_gb():.0f} GB | ETA {eta}")

    def emit(self, text: str | None = None) -> None:
        text = text or self.line()
        print(text, flush=True)
        self._log.write(text + "\n")

    def _run(self) -> None:
        while not self._stop.wait(INTERVAL):
            try:
                self.emit()
            except Exception as e:  # never let the ticker kill the loader
                print(f"status error: {e}", file=sys.stderr)

    def stop(self) -> None:
        self._stop.set()
        self.emit()
