"""The suppression list (owner, 2026-11-23): suppressed_people, suppression_hits, the insert guard on people.

The loader module creates the same objects (loader/suppression.py ensure); the migration is here so a fresh database has them.

Revision ID: 0080
Revises: 0079
Create Date: 2026-11-23
"""
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from loader.suppression import DDL
    op.execute(DDL)


def downgrade() -> None:
    # Deliberately keeps the data: dropping the list would let suppressed people come back with the next rebuild.
    pass
