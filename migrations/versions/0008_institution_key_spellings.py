"""np_institution_key(): treat spacing variants of big names as one (JP Morgan / JPMorgan...).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-17
"""

from alembic import op

from app.institutions import key_function_sql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(key_function_sql())


def downgrade() -> None:
    pass
