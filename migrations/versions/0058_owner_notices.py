"""owner_notices: updates for the owner, sent together in one daily email (app/mailer.py; owner, 2026-10-23:
"Send me email updates batched! Not individual.").

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-23
"""

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS owner_notices (
        id bigserial PRIMARY KEY, created timestamptz NOT NULL DEFAULT now(), topic text NOT NULL, subject text NOT NULL,
        body text NOT NULL, reply_to text, sent_at timestamptz);
    CREATE INDEX IF NOT EXISTS owner_notices_unsent ON owner_notices (created) WHERE sent_at IS NULL""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS owner_notices")
