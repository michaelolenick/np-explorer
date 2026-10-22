"""Daily LinkedIn posts of FURP findings (app/linkedin.py): one row per weekday, draft to posted.

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-22
"""

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS linkedin_posts (
        day date PRIMARY KEY, status text NOT NULL, text text, comment text, items jsonb, post_urn text,
        comment_urn text, error text, drafted_at timestamptz, posted_at timestamptz, skipped_by text)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS linkedin_posts")
