"""USPTO-derived firms: a hidden flag for firm names a model reads as a person's (loader/ip_firms.haiku_check), and
the per-name answers, cached so later runs only ask about names not seen before.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-24
"""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE ip_firms ADD COLUMN IF NOT EXISTS hidden boolean NOT NULL DEFAULT false;
    ALTER TABLE ip_firms ADD COLUMN IF NOT EXISTS hidden_why text;
    CREATE TABLE IF NOT EXISTS ip_name_checks (
        name text PRIMARY KEY, is_person boolean NOT NULL, method text NOT NULL,
        checked timestamptz NOT NULL DEFAULT now())""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS ip_name_checks;
                  ALTER TABLE ip_firms DROP COLUMN IF EXISTS hidden, DROP COLUMN IF EXISTS hidden_why""")
