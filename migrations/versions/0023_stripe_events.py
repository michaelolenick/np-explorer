"""stripe_events: every verified Stripe webhook event for the Support page, once.

Ids, amounts and statuses only: no names, emails or card details (Stripe keeps those).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-17
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS stripe_events (
        event_id     text PRIMARY KEY,
        type         text NOT NULL,
        created      timestamptz NOT NULL,
        livemode     boolean NOT NULL,
        object_id    text,
        mode         text,               -- payment or subscription (Checkout Sessions)
        amount       bigint,             -- cents
        currency     text,
        status       text,
        subscription text,
        customer     text,               -- Stripe customer id (no personal data stored here)
        received_at  timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS stripe_events_created ON stripe_events (created)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_events")
