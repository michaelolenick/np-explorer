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
    try:
        with db.pool.connection() as c:
            vals += [r["name_norm"] for r in c.execute("SELECT name_norm FROM suppressed_people WHERE active")]
    except Exception:
        pass
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


# --- the suppression list at request time (loader/suppression.py keeps the data out; this is the last line) -----------
_list: dict = {"at": 0.0, "ids": set(), "slugs": set()}


def _entries() -> tuple[set, set]:
    if time.time() - _list["at"] > 60:
        from app import db, slugs
        ids, sl = set(), set()
        try:
            with db.pool.connection() as c:
                for r in c.execute("SELECT name, person_id FROM suppressed_people WHERE active"):
                    if r["person_id"]:
                        ids.add(int(r["person_id"]))
                    if slugs.slug(r["name"]):
                        sl.add(slugs.slug(r["name"]))
        except Exception:
            ids, sl = _list["ids"], _list["slugs"]       # the table is not there yet, or a blip: keep the last list
        _list.update(at=time.time(), ids=ids, slugs=sl)
    return _list["ids"], _list["slugs"]


def is_suppressed_person(cluster_id: int | None, key: str = "") -> bool:
    """A suppressed person id, or a URL slug that is a suppressed name ("julissa-vogel-19661518")."""
    ids, sl = _entries()
    if cluster_id is not None and int(cluster_id) in ids:
        return True
    m = re.match(r"^(.*?)-?\d+$", (key or "").strip().lower())
    return bool(m and m.group(1) in sl)


def gone():
    """410 Gone: no content, and told not to index."""
    from fastapi.responses import Response
    return Response(status_code=410, headers={"X-Robots-Tag": "noindex, nofollow, noarchive", "Cache-Control": "no-store"})
