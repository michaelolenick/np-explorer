"""USPTO load checkpoints and status (loader/uspto.py): where each dataset's load stands (part, step, rows, newest
and oldest dates reached, what happens next and when), so a stopped load resumes where it left off, and a status
line after each step.

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-24
"""

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS uspto_state (
        dataset text PRIMARY KEY, part text, step text, rows bigint, newest date, oldest date, status text,
        next_action text, next_at timestamptz, updated timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS uspto_status (
        id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), line text NOT NULL)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS uspto_status, uspto_state")
