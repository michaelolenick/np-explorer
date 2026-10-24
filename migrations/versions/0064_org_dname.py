"""Distinctive organization names for donor matching (loader/org_dname.py): the words that appear in at least 0.5%
of organization names (inc, foundation, fund, trust, the, of...), each organization's name without them, indexed for
trigram matching, and every business contributor's precomputed link to an organization.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-24
"""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS name_generic_words (word text PRIMARY KEY, share real NOT NULL);
    CREATE TABLE IF NOT EXISTS org_dname (ein text PRIMARY KEY, state text, dname text NOT NULL);
    CREATE INDEX IF NOT EXISTS org_dname_trgm ON org_dname USING gin (dname gin_trgm_ops);
    CREATE TABLE IF NOT EXISTS donor_org_link (
        name_norm text NOT NULL, state text NOT NULL, ein text, name text, score real, method text NOT NULL,
        updated timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (name_norm, state))""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS donor_org_link, org_dname, name_generic_words")
