"""Build or refresh the leaderboard materialized views (definitions in app/boards.py).

A board whose SQL is unchanged is refreshed in place (REFRESH ... CONCURRENTLY, so
pages keep working). A board whose SQL changed, or that doesn't exist yet, is
built beside the live one and swapped in. board_entries (who appears on which
board, for search) is rebuilt and swapped the same way. Run by load.py boards
and after every data load.
"""

from __future__ import annotations

import hashlib

from app import boards as B
from loader import db

INDEXES = ["(pos)", "(tax_year)", "(form_type)", "(state)", "(subject_kind, subject_key)", "(ein)"]


def _exists(conn, name: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) IS NOT NULL", (name,)).fetchone()[0]


def _definition(board) -> str:
    return hashlib.sha1(board.sql.encode()).hexdigest()


def _prepare(conn) -> None:
    conn.execute("SET work_mem = '512MB'")
    conn.execute("SET statement_timeout = 0")
    conn.execute(f"SET pg_trgm.similarity_threshold = {B.LOOKALIKE_SIMILARITY}")


def refresh_board(conn, board, status=None) -> int:
    if status:
        status.phase = f"boards: {board.slug}"
    view, new = board.view, board.view + "__new"
    known = conn.execute("SELECT definition FROM board_meta WHERE slug = %s", (board.slug,)).fetchone()
    if _exists(conn, view) and known and known[0] == _definition(board):
        conn.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
    else:
        conn.execute(f"DROP MATERIALIZED VIEW IF EXISTS {new}")
        conn.execute(f"CREATE MATERIALIZED VIEW {new} AS {board.sql}")
        conn.execute(f"CREATE UNIQUE INDEX ON {new} (pos)")
        for cols in INDEXES[1:] + (["(org_pos)"] if board.per_org else []):
            conn.execute(f"CREATE INDEX ON {new} {cols}")
        conn.commit()
        conn.execute("SET lock_timeout = '30s'")
        conn.execute(f"DROP MATERIALIZED VIEW IF EXISTS {view}")
        conn.execute(f"ALTER MATERIALIZED VIEW {new} RENAME TO {view}")
        # Index names follow the view name, so later rebuilds don't collide.
        for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", (view,)).fetchall():
            if "__new" in idx:
                conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{idx.replace("__new", "")}"')
        conn.execute("SET lock_timeout = 0")
    n, y0, y1 = conn.execute(f"SELECT count(*), min(tax_year), max(tax_year) FROM {view}").fetchone()
    conn.execute("""INSERT INTO board_meta (slug, definition, refreshed_at, n_rows, year_min, year_max)
                    VALUES (%s, %s, now(), %s, %s, %s)
                    ON CONFLICT (slug) DO UPDATE SET definition = excluded.definition,
                        refreshed_at = excluded.refreshed_at, n_rows = excluded.n_rows,
                        year_min = excluded.year_min, year_max = excluded.year_max""",
                 (board.slug, _definition(board), n, y0, y1))
    conn.commit()
    if status:
        status.emit(f"boards: {board.slug} {n:,} rows, tax years {y0}-{y1}")
    return n


def entries_sql(views: list[tuple[str, str]]) -> str:
    """Best rank per subject per board, plus the lookalike twins."""
    parts = []
    for slug, view in views:
        parts.append(f"""SELECT '{slug}'::text AS slug, subject_kind, subject_key, subject_name, subject_norm,
                                subject_url, rank FROM {view}""")
        if slug == "lookalikes":
            parts.append(f"""SELECT '{slug}', 'org', twin_ein, twin_name, {B.norm_sql('twin_name')},
                                    '/org/' || twin_ein, rank FROM {view}""")
    return f"""
        SELECT e.slug, e.subject_kind, e.subject_key, max(e.subject_name) AS subject_name,
               max(e.subject_norm) AS subject_norm, max(e.subject_url) AS subject_url,
               min(e.rank) AS best_rank, max(m.n_rows) AS n_rows
        FROM ({" UNION ALL ".join(parts)}) e
        JOIN board_meta m ON m.slug = e.slug
        GROUP BY e.slug, e.subject_kind, e.subject_key"""


def refresh_entries(conn, status=None) -> int:
    if status:
        status.phase = "boards: search index"
    views = [(b.slug, b.view) for b in B.BOARDS if _exists(conn, b.view)]
    conn.execute("DROP TABLE IF EXISTS board_entries__new")
    conn.execute("CREATE TABLE board_entries__new AS " + entries_sql(views))
    conn.execute("CREATE INDEX ON board_entries__new (subject_kind, subject_key)")
    conn.execute("CREATE INDEX ON board_entries__new (subject_norm text_pattern_ops)")
    if db.has_extension(conn, "pg_trgm"):
        conn.execute("CREATE INDEX ON board_entries__new USING gin (subject_norm gin_trgm_ops)")
    conn.execute("ANALYZE board_entries__new")
    conn.commit()
    conn.execute("SET lock_timeout = '30s'")
    conn.execute("DROP TABLE IF EXISTS board_entries")
    conn.execute("ALTER TABLE board_entries__new RENAME TO board_entries")
    for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'board_entries'").fetchall():
        if "__new" in idx:
            conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{idx.replace("__new", "")}"')
    conn.commit()
    n = conn.execute("SELECT count(*) FROM board_entries").fetchone()[0]
    if status:
        status.emit(f"boards: search index {n:,} entries")
    return n


def refresh(status, only: list[str] | None = None) -> None:
    status.phase = "boards"
    with db.connect() as conn:
        _prepare(conn)
        for board in B.BOARDS:
            if only and board.slug not in only:
                continue
            refresh_board(conn, board, status)
        refresh_entries(conn, status)
