"""A light per-IP token bucket for the JSON API (per worker process)."""

from __future__ import annotations

import threading
import time

RATE = 1.0      # tokens per second
BURST = 60      # bucket size


class RateLimiter:
    def __init__(self, rate: float = RATE, burst: int = BURST) -> None:
        self.rate, self.burst = rate, burst
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            tokens, last = self.buckets.get(key, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens < 1:
                self.buckets[key] = (tokens, now)
                return False
            self.buckets[key] = (tokens - 1, now)
            if len(self.buckets) > 100_000:
                self.buckets.clear()
            return True
