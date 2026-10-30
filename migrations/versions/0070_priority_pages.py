"""Priority pages for search engines (owner, 2026-10-30): the organizations, funders and people FURP submits to
Google first, rebuilt nightly by loader/priority.py. The /top hub lists them, so each is three clicks from the
home page, and the main sitemap index (/sitemap.xml) lists only these and the hub pages.

kind is 'org' (largest by revenue, then the most visited), 'funder' (most granted) or 'person' (highest paid);
rank is the position within the kind; why says which list put the row there.

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-30
"""

from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS priority_pages (
        kind text NOT NULL CHECK (kind IN ('org', 'funder', 'person')),
        rank integer NOT NULL,
        ident text NOT NULL,
        name text NOT NULL,
        figure numeric,
        detail text,
        why text NOT NULL,
        built timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (kind, rank))""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS priority_pages")
