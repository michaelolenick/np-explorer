"""Connection pool for the web app."""

from __future__ import annotations

from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL

def _configure(conn) -> None:
    # Word-similarity cut-off for the `<%` candidate test. 0.6 (pg_trgm's default)
    # still catches typos ("renee mauborgen") while cutting weak candidates.
    # A dotted setting is accepted even before the extension is installed.
    conn.execute("SET pg_trgm.word_similarity_threshold = 0.6")
    # Web requests only: a runaway query is cancelled instead of tying up the database.
    # The loaders open their own connections (loader/db.py) without this limit.
    conn.execute(f"SET statement_timeout = '{STATEMENT_TIMEOUT}'")


# Hard ceiling per worker process (4 workers: at most 40 connections). A burst waits up to
# POOL_WAIT seconds for a free connection; past POOL_QUEUE waiting requests, it fails fast.
POOL_MAX = 10
POOL_WAIT = 10
POOL_QUEUE = 64
STATEMENT_TIMEOUT = "5s"

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=POOL_MAX, timeout=POOL_WAIT, max_waiting=POOL_QUEUE,
                      open=False, configure=_configure,
                      kwargs={"row_factory": dict_row, "application_name": "np-explorer", "autocommit": True})

_features: dict[str, bool] = {}


@contextmanager
def conn():
    with pool.connection() as c:
        yield c


def has_trgm() -> bool:
    if "trgm" not in _features:
        with conn() as c:
            # Use trigram search only once the person_clusters trigram index exists;
            # without it the `<%` test would scan every cluster.
            _features["trgm"] = c.execute("""
                SELECT 1 FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid JOIN pg_class t ON t.oid = x.indrelid
                JOIN pg_am am ON am.oid = i.relam
                WHERE t.relname = 'person_clusters' AND am.amname = 'gin' AND x.indisvalid
                  AND pg_get_indexdef(x.indexrelid) LIKE '%%gin_trgm_ops%%'""").fetchone() is not None
    return _features["trgm"]
