"""Mark donor-advised fund sponsors on organizations.

daf_sponsor is true when any of the organization's (non-superseded) returns says
it maintained donor-advised funds or reports any on Schedule D Part I;
daf_last_year is the latest such tax year. Set by loader/finalize.py.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-17
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS daf_sponsor boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS daf_last_year integer")


def downgrade() -> None:
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS daf_last_year")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS daf_sponsor")
