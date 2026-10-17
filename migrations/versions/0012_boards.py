"""Leaderboards: the fundraising-expense field they need, and board metadata.

The boards themselves are materialized views created and refreshed by
loader/boards.py from the definitions in app/boards.py.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE filings ADD COLUMN IF NOT EXISTS fundraising_expenses bigint")
    op.execute("""DO $$ BEGIN
        IF to_regclass('stage_filings') IS NOT NULL THEN
            ALTER TABLE stage_filings ADD COLUMN IF NOT EXISTS fundraising_expenses bigint;
        END IF; END $$""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS board_meta (
        slug          text PRIMARY KEY,
        definition    text NOT NULL,      -- hash of the view's SQL; a change rebuilds the view
        refreshed_at  timestamptz NOT NULL DEFAULT now(),
        n_rows        bigint NOT NULL DEFAULT 0,
        year_min      integer,
        year_max      integer
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS board_meta")
    op.execute("ALTER TABLE filings DROP COLUMN IF EXISTS fundraising_expenses")
