"""explain_flags: numbers the "Explain what I'm seeing" explainer found odd, with the page and its reason
(app/explain.py), so the daily report can show whether any point to a data problem.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-21
"""

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS explain_flags (
                      id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), url text, version text,
                      figure text, reason text);
                  CREATE INDEX IF NOT EXISTS explain_flags_ts ON explain_flags (ts)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS explain_flags")
