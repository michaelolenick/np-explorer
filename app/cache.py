"""A small in-memory LRU cache with a time limit, per worker process.

Repeated identical searches and person pages within a minute are answered from
memory instead of the database.
"""

from __future__ import annotations

import functools
import threading
import time
from collections import OrderedDict

TTL = 60
MAX_ENTRIES = 1024


def ttl_lru(ttl: float = TTL, maxsize: int = MAX_ENTRIES):
    def wrap(fn):
        store: OrderedDict = OrderedDict()
        lock = threading.Lock()

        @functools.wraps(fn)
        def cached(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.monotonic()
            with lock:
                hit = store.get(key)
                if hit and now - hit[0] < ttl:
                    store.move_to_end(key)
                    return hit[1]
            value = fn(*args, **kwargs)
            with lock:
                store[key] = (now, value)
                store.move_to_end(key)
                while len(store) > maxsize:
                    store.popitem(last=False)
            return value

        cached.cache_clear = store.clear
        return cached
    return wrap
