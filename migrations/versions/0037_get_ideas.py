"""Get Ideas email for reporters (app/reporters.py): subscribers, what was sent, and an event log for the report.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-21
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS idea_subscribers (
        id bigserial PRIMARY KEY, email text NOT NULL UNIQUE, token text NOT NULL UNIQUE,
        status text NOT NULL DEFAULT 'pending',          -- pending | active | unsubscribed
        created timestamptz NOT NULL DEFAULT now(), confirmed timestamptz, unsubscribed timestamptz);
    CREATE TABLE IF NOT EXISTS idea_email_sends (
        subscriber_id bigint NOT NULL REFERENCES idea_subscribers (id), day date NOT NULL, idea_ids bigint[],
        sent timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (subscriber_id, day));
    CREATE TABLE IF NOT EXISTS idea_email_events (
        id bigserial PRIMARY KEY, ts timestamptz NOT NULL DEFAULT now(), kind text NOT NULL,
        subscriber_id bigint, detail text);
    CREATE INDEX IF NOT EXISTS idea_email_events_ts ON idea_email_events (ts)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idea_email_events, idea_email_sends, idea_subscribers")
