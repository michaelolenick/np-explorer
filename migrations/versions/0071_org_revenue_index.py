"""Index organizations by latest revenue, largest first, so category lists (one NTEE broad category or major group
holds up to a million organizations) take the first page off the index instead of sorting the whole set.

Revision ID: 0071
Revises: 0070
Create Date: 2026-11-05
"""

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS organizations_revenue ON organizations (latest_total_revenue DESC NULLS LAST, ein)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS organizations_revenue")
