"""Connection pool for the web app."""

from __future__ import annotations

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, open=False,
                      kwargs={"row_factory": dict_row, "application_name": "np-explorer", "autocommit": True})

_features: dict[str, bool] = {}


@contextmanager
def conn():
    with pool.connection() as c:
        yield c


def has_trgm() -> bool:
    if "trgm" not in _features:
        with conn() as c:
            _features["trgm"] = c.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'").fetchone() is not None
            if _features["trgm"]:
                c.execute("SET pg_trgm.similarity_threshold = 0.3")
    return _features["trgm"]
