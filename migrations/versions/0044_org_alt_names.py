"""org_alt_names: short names, acronyms and DBAs for every organization (loader/alt_names.py), one row per
(normalized name, EIN, source); org_alt_names_asked remembers which organizations the model was asked about.

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-21
"""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS org_alt_names (
        alias_norm text NOT NULL, ein text NOT NULL, source text NOT NULL, alias text NOT NULL,
        created timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (alias_norm, ein, source));
    CREATE INDEX IF NOT EXISTS org_alt_names_ein ON org_alt_names (ein);
    CREATE TABLE IF NOT EXISTS org_alt_names_asked (ein text PRIMARY KEY, asked timestamptz NOT NULL DEFAULT now())""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_alt_names_asked, org_alt_names")
