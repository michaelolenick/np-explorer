"""Daily counts for natural-language search: model calls, cache hits, fallbacks, tokens.

Counts only: no query text, no IPs. The daily cap (NL_DAILY_CAP) is checked
against this table, so it holds across all web workers.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-17
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS nl_usage (
        day           date PRIMARY KEY,
        calls         integer NOT NULL DEFAULT 0,   -- model calls made
        cache_hits    integer NOT NULL DEFAULT 0,
        skipped       integer NOT NULL DEFAULT 0,   -- plain names: no model call
        fallbacks     integer NOT NULL DEFAULT 0,   -- unknown, invalid, timeout, cap, limit
        input_tokens  bigint  NOT NULL DEFAULT 0,
        output_tokens bigint  NOT NULL DEFAULT 0
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nl_usage")
