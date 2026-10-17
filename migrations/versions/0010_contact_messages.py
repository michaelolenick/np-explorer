"""Messages sent through the site's contact form.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE contact_messages (
        id          bigserial PRIMARY KEY,
        created_at  timestamptz NOT NULL DEFAULT now(),
        name        text NOT NULL,
        email       text NOT NULL,
        subject     text,
        message     text NOT NULL,
        ip          text,
        user_agent  text,
        handled     boolean NOT NULL DEFAULT false
    );
    CREATE INDEX contact_messages_created ON contact_messages (created_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contact_messages")
