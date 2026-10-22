"""Form D SPV links: a name index on SEC insider-filing issuers, so an SPV's company is found by name quickly.

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-22
"""

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS sec_insider_filings_issuer_trgm ON sec_insider_filings "
                   "USING gin (lower(issuer_name) gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sec_insider_filings_issuer_trgm")
