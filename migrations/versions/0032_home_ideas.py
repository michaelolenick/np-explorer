"""home_ideas: checked "Interesting ideas…" for the home page (app/ideas.py).

One row per idea: the question as shown, and the validated structured search (ask intent) a click runs. Rebuilt in
part daily by a model call; live "More" presses add rows; rows older than 7 days are dropped.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-20
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS home_ideas (
        id       bigserial PRIMARY KEY,
        question text NOT NULL,
        intent   jsonb NOT NULL,
        created  timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS home_ideas_created ON home_ideas (created)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS home_ideas")
