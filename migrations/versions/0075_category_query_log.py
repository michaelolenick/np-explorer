"""Find a category query log (owner, 2026-11-09): every query typed into the single box on /categories with the
reading Claude Haiku gave it (lookup, describe or grants), the model's confidence, how the reading was made (rule,
model, guess or an old link) and the number of results shown. Nothing about the visitor is kept.

Revision ID: 0075
Revises: 0074
Create Date: 2026-11-09
"""

from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS category_query_log (
        id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), q text NOT NULL, intent text NOT NULL,
        confidence numeric(4, 3), results integer, source text)""")
    op.execute("CREATE INDEX IF NOT EXISTS category_query_log_ts ON category_query_log (ts)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS category_query_log")
