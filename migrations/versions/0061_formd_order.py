"""formd_order: how Form D offerings list on search and entity pages (loader/formd_order.py): fund family, kind
(main fund, SPV, series, other), series label, natural sort order within the family, and the parent fund of each SPV
or series, with how it was placed and how confident.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-24
"""

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS formd_order (
        root_accession text PRIMARY KEY, family_key text NOT NULL, fund_kind text NOT NULL, series_label text,
        sort_order double precision, parent_root text, confidence text NOT NULL, method text NOT NULL,
        name_hash text NOT NULL, reason text, updated timestamptz NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS formd_order_family ON formd_order (family_key);
    CREATE INDEX IF NOT EXISTS formd_order_parent ON formd_order (parent_root);
    CREATE INDEX IF NOT EXISTS formd_order_review ON formd_order (updated) WHERE confidence = 'low'""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS formd_order")
