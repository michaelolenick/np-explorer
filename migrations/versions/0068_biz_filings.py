"""Business registry filing histories (owner, 2026-10-29): every filing a state lists for an entity (original filing,
annual renewals, amendments, dissolutions...), starting with Minnesota's bulk order file (loader/minnesota_registry.py).

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-29
"""

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS biz_filings (
        state text NOT NULL,
        entity_id text NOT NULL,
        filing_number text,
        original_filing_number text,
        action text,
        rank text,
        filing_date date,
        effective_date date,
        source text NOT NULL,
        provenance text
    );
    CREATE INDEX IF NOT EXISTS biz_filings_entity ON biz_filings (state, entity_id)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS biz_filings")
