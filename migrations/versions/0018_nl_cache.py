"""Parsed natural-language intents, shared by all web workers, kept 24 hours.

Keyed by a SHA-256 of the normalized question (the text itself is not stored); holds
only the structured search it became. No IP addresses. Rows older than a day are
deleted as new ones arrive.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS nl_cache (
        key      text PRIMARY KEY,                  -- sha256 of the normalized question
        intent   jsonb NOT NULL,
        created  timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS nl_cache_created ON nl_cache (created)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS nl_cache")
