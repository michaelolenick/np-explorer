"""nl_explain: cached "Explain what I'm seeing" text, by page URL and a hash of the data it explains
(app/explain.py). An empty html means no good explanation (cached too).

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-21
"""

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS nl_explain (
                      key text PRIMARY KEY, url text, version text, html text NOT NULL,
                      created timestamptz NOT NULL DEFAULT now());
                  CREATE INDEX IF NOT EXISTS nl_explain_url ON nl_explain (url)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nl_explain")
