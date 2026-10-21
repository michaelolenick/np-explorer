"""Search interpretation: an index for short names typed with or without spaces ("red cross" finds the website
name "redcross"), and search_review, the searches that found nothing on the live site, kept for review so the
search test set (tests/search_cases.yml) grows from real failures.

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-21
"""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS org_alt_names_squash "
                   "ON org_alt_names (replace(alias_norm, ' ', ''))")
    op.execute("""
    CREATE TABLE IF NOT EXISTS search_review (
        q_norm text PRIMARY KEY, q text NOT NULL, first_seen date NOT NULL, last_seen date NOT NULL,
        searches int NOT NULL DEFAULT 0, status text NOT NULL DEFAULT 'new')""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS search_review")
    op.execute("DROP INDEX IF EXISTS org_alt_names_squash")
