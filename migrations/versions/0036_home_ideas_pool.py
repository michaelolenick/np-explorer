"""home_ideas.pool: the nightly pool (US Eastern date) an idea belongs to (app/ideas.py). NULL for ideas made
before nightly pools.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-21
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE home_ideas ADD COLUMN IF NOT EXISTS pool date;
                  CREATE INDEX IF NOT EXISTS home_ideas_pool ON home_ideas (pool)""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS home_ideas_pool; ALTER TABLE home_ideas DROP COLUMN IF EXISTS pool")
