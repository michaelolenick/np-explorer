"""Privacy removals: names, addresses and phone numbers the owner has removed on request.

The values live in the privacy_suppressions table (kind, value). Every filing page and raw XML download runs through
`redact`, so a removed person's name, home address and phone number never show, whatever year's filing they are in.
The rows removed from the people tables are kept (private) in privacy_removed so a removal can be reversed.
"""
from __future__ import annotations

import re
import time

_cache: dict = {"at": 0.0, "rx": None}
MARK = "[removed at the person's request]"


def _load() -> re.Pattern | None:
    from app import db  # late: tests and loaders import this without a pool
    try:
        with db.pool.connection() as c:
            vals = [r["value"] for r in c.execute("SELECT value FROM privacy_suppressions ORDER BY length(value) DESC")]
    except Exception:
        return None
    vals = [v.strip() for v in vals if v and v.strip()]
    return re.compile("|".join(re.escape(v) for v in vals), re.I) if vals else None


def pattern() -> re.Pattern | None:
    if time.time() - _cache["at"] > 60:
        _cache["rx"], _cache["at"] = _load(), time.time()
    return _cache["rx"]


def redact(data: bytes) -> bytes:
    rx = pattern()
    if rx is None:
        return data
    return rx.sub(MARK, data.decode("utf-8", "replace")).encode("utf-8")
