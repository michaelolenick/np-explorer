"""np_institution_key(): records starting with a big trustee bank's brand are that bank.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17
"""

from alembic import op

from app.institutions import key_function_sql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(key_function_sql())


def downgrade() -> None:
    pass
