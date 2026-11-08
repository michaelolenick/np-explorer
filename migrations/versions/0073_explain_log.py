"""On-demand explanations (owner, 2026-11-08): the cost log, the stop switch, and an index so an entity page finds its
cached explanation by URL.

Revision ID: 0073
Revises: 0072
Create Date: 2026-11-08
"""

from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS explain_log (
        id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), url text NOT NULL, entity_kind text,
        outcome text NOT NULL, model text, input_tokens integer NOT NULL DEFAULT 0, output_tokens integer NOT NULL DEFAULT 0,
        cost numeric(10, 6) NOT NULL DEFAULT 0, ip_bucket text, visitor text)""")
    op.execute("CREATE INDEX IF NOT EXISTS explain_log_ts ON explain_log (ts)")
    op.execute("""CREATE TABLE IF NOT EXISTS explain_state (key text PRIMARY KEY, value jsonb NOT NULL,
                  updated timestamptz NOT NULL DEFAULT now())""")
    op.execute("CREATE INDEX IF NOT EXISTS nl_explain_url ON nl_explain (url, created DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS nl_explain_url")
    op.execute("DROP TABLE IF EXISTS explain_state")
    op.execute("DROP TABLE IF EXISTS explain_log")
