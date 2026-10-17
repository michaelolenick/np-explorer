"""Donors (990-PF Schedule B Part I) and grant-list summary lines.

donors: contributor name, city and state (never the street), total and noncash
amounts, per filing. 990-PF only: public charities' Schedule B names are not public.
grants.is_summary: a line that stands for a list kept in a separate attachment
("Education ... See Statement 26"), not one grant; the itemized list isn't in the
public XML.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE grants ADD COLUMN IF NOT EXISTS is_summary boolean NOT NULL DEFAULT false")
    op.execute("""
    CREATE TABLE IF NOT EXISTS donors (
        id              bigserial PRIMARY KEY,
        filing_id       bigint NOT NULL,
        ein             text NOT NULL,              -- the recipient (the filer)
        tax_year        integer,
        contributor_num integer,
        name            text,
        name_norm       text,
        is_person       boolean,
        city            text,
        state           text,
        total_amount    bigint,
        noncash_amount  bigint
    );
    CREATE INDEX IF NOT EXISTS donors_filing_id ON donors (filing_id);
    CREATE INDEX IF NOT EXISTS donors_ein ON donors (ein, tax_year);
    DO $$ BEGIN
        IF to_regclass('stage_grants') IS NOT NULL THEN
            ALTER TABLE stage_grants ADD COLUMN IF NOT EXISTS is_summary boolean;
        END IF; END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS donors")
    op.execute("ALTER TABLE grants DROP COLUMN IF EXISTS is_summary")
