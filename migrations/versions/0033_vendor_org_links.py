"""vendor_org_links: contractor records (vendors on 990 contractor lists) matched to a filing organization's EIN
by normalized name and address (loader/vendor_orgs.py).

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-20
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS vendor_org_links (
        contractor_id bigint PRIMARY KEY,
        ein           text NOT NULL,
        method        text NOT NULL          -- 'address' (name and address matched) | 'no address'
    );
    CREATE INDEX IF NOT EXISTS vendor_org_links_ein ON vendor_org_links (ein)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vendor_org_links")
