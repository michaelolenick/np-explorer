"""idea_rejects: suggested lookups the nightly checker dropped, and why (app/ideas.py), so the owner can see what
the plain-text query mode can't handle yet.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-21
"""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS idea_rejects (
                      id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), pool date, question text,
                      reason text, parsed jsonb);
                  CREATE INDEX IF NOT EXISTS idea_rejects_ts ON idea_rejects (ts)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idea_rejects")
