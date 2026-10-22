"""Database helpers for the loader (psycopg 3, COPY for bulk writes)."""

from __future__ import annotations

import psycopg

from app.config import DATABASE_URL


def connect(autocommit: bool = False) -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL, autocommit=autocommit, application_name="np-loader")
    return conn


def copy_rows(cur: psycopg.Cursor, table: str, columns: list[str], rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def has_extension(conn: psycopg.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM pg_extension WHERE extname = %s", (name,)).fetchone() is not None


def progress(conn, file: str, status: str, *, kind: str | None = None, year: int | None = None,
             rows: int | None = None, error: str | None = None) -> None:
    """Upsert a loader_progress row. 'running' stamps started, terminal states stamp finished."""
    conn.execute(
        """
        INSERT INTO loader_progress (file, kind, year, status, rows, started, finished, error)
        VALUES (%(file)s, %(kind)s, %(year)s, %(status)s, %(rows)s,
                CASE WHEN %(status)s = 'running' THEN clock_timestamp() END,
                CASE WHEN %(status)s <> 'running' THEN clock_timestamp() END, %(error)s)
        ON CONFLICT (file) DO UPDATE SET
            kind = coalesce(EXCLUDED.kind, loader_progress.kind),
            year = coalesce(EXCLUDED.year, loader_progress.year),
            status = EXCLUDED.status,
            rows = coalesce(EXCLUDED.rows, loader_progress.rows),
            started = CASE WHEN EXCLUDED.status = 'running' THEN clock_timestamp() ELSE loader_progress.started END,
            finished = CASE WHEN EXCLUDED.status <> 'running' THEN clock_timestamp() ELSE NULL END,
            error = EXCLUDED.error
        """,
        dict(file=file, kind=kind, year=year, status=status, rows=rows, error=error),
    )


def status_of(conn, file: str) -> str | None:
    row = conn.execute("SELECT status FROM loader_progress WHERE file = %s", (file,)).fetchone()
    return row[0] if row else None


def swap_table(conn: psycopg.Connection, name: str) -> None:
    """Replace table `name` with `name`_new. When `name` exists its rows are replaced in place (TRUNCATE and
    INSERT in this transaction), so views that depend on it, such as leaderboard materialized views, survive;
    otherwise `name`_new is renamed (with its indexes)."""
    exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (name,)).fetchone()[0]
    if exists:
        # Columns the new build added are added to the live table first; rows are copied by column name, so a
        # column added in the middle of the new table doesn't shift the rest (2026-10-22).
        cols = conn.execute("""SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a
                               WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped
                               ORDER BY a.attnum""", (f"{name}_new",)).fetchall()
        have = {r[0] for r in conn.execute("""SELECT attname FROM pg_attribute WHERE attrelid = %s::regclass
                                              AND attnum > 0 AND NOT attisdropped""", (name,)).fetchall()}
        for col, typ in cols:
            if col not in have:
                conn.execute(f'ALTER TABLE {name} ADD COLUMN "{col}" {typ}')
        names = ", ".join(f'"{c}"' for c, _ in cols)
        conn.execute(f"TRUNCATE {name}")
        conn.execute(f"INSERT INTO {name} ({names}) SELECT {names} FROM {name}_new")
        conn.execute(f"DROP TABLE {name}_new")
    else:
        conn.execute(f"ALTER TABLE {name}_new RENAME TO {name}")
        for (idx,) in conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", (name,)).fetchall():
            if "_new" in idx:
                new = idx.replace("_new", "")
                conn.execute(f'ALTER INDEX "{idx}" RENAME TO "{new}"')
