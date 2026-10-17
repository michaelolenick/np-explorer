"""people.is_duplicate: the same name with identical pay listed more than once on one return.

Usually a person listed both as an officer and as a highest-compensated employee
(990-PF, 990-EZ), or a line repeated by the filer. The first row stays; repeats are
flagged so pay isn't counted twice. Set by loader/finalize.py.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-17
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE people ADD COLUMN IF NOT EXISTS is_duplicate boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE people DROP COLUMN IF EXISTS is_duplicate")
