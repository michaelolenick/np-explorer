"""Find a category log (owner, 2026-11-08): every "Describe what it does" lookup on /categories with the words typed,
the model's raw output, the method that answered (cache, model, keywords, fuzzy, majors) and any error, so the
failures can be read later.

Revision ID: 0074
Revises: 0073
Create Date: 2026-11-08
"""

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS category_find_log (
        id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), q text NOT NULL, model text, raw text,
        codes jsonb, method text NOT NULL, error text, ms integer, cost numeric(10, 6))""")
    op.execute("CREATE INDEX IF NOT EXISTS category_find_log_ts ON category_find_log (ts)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS category_find_log")
