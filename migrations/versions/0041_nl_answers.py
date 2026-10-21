"""nl_answers: the short plain-English answer shown above a plain-text search result, cached by the search's
static URL (app/answer.py). An empty html means no good answer (cached too, so the model isn't asked again).

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-21
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS nl_answers (
                      key text PRIMARY KEY, url text, html text NOT NULL, created timestamptz NOT NULL DEFAULT now())""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nl_answers")
