"""np_institution_key(): the name institution records are merged on.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""

from alembic import op

from app.institutions import key_function_sql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(key_function_sql())


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS np_institution_key(text)")
