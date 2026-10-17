"""Index organizations by state and city, for firm search by location.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-17
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS organizations_city ON organizations (upper(city), state)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS organizations_city")
