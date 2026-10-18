"""expense_breakdown.special_event_net: Form 990 Part VIII line 8c (990-EZ line 6d) as reported.

NULL when the return leaves it blank, so pages can say "Not reported" instead of showing a
computed $0. Filled for existing returns by load.py backfill-extras --only
expense_breakdown,fundraising_events (returns with fundraising events only).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-18
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE expense_breakdown ADD COLUMN IF NOT EXISTS special_event_net bigint")


def downgrade() -> None:
    op.execute("ALTER TABLE expense_breakdown DROP COLUMN IF EXISTS special_event_net")
