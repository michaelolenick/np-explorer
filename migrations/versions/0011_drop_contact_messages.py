"""The contact form now emails messages instead of storing them.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-17
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_messages")


def downgrade() -> None:
    pass
