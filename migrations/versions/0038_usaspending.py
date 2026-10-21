"""USAspending federal awards (loader/usaspending.py): one row per award and fiscal year, officer pay, a staging
table for loads, and a run log.

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-21
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE UNLOGGED TABLE IF NOT EXISTS usa_stage (
        award_key text, kind text, fiscal_year smallint, obligation numeric(16, 2), action_date date, agency text,
        sub_agency text, recipient_uei text, recipient_duns text, recipient_name text, parent_name text, street text,
        city text, state text, zip5 text, program_code text, program_title text, award_type text, description text,
        business_types text, nonprofit boolean, permalink text, officers text);
    CREATE TABLE IF NOT EXISTS usa_awards (
        award_key text NOT NULL, kind text NOT NULL, fiscal_year smallint NOT NULL, obligation numeric(16, 2),
        n_actions int, first_date date, last_date date, agency text, sub_agency text, recipient_uei text,
        recipient_duns text, recipient_name text, parent_name text, street text, city text, state text, zip5 text,
        program_code text, program_title text, award_type text, description text, business_types text,
        nonprofit boolean, permalink text, recipient_ein text,
        PRIMARY KEY (award_key, fiscal_year));
    CREATE INDEX IF NOT EXISTS usa_awards_ein ON usa_awards (recipient_ein) WHERE recipient_ein IS NOT NULL;
    CREATE INDEX IF NOT EXISTS usa_awards_kind_fy ON usa_awards (kind, fiscal_year);
    CREATE INDEX IF NOT EXISTS usa_awards_recipient ON usa_awards (recipient_name, zip5);
    CREATE TABLE IF NOT EXISTS usa_officers (
        award_key text NOT NULL, fiscal_year smallint NOT NULL, n smallint NOT NULL, name text, amount numeric(14, 2),
        PRIMARY KEY (award_key, fiscal_year, n));
    CREATE TABLE IF NOT EXISTS usa_runs (
        id bigserial PRIMARY KEY, fiscal_year smallint, kind text, file text, transactions bigint,
        finished timestamptz)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usa_runs, usa_officers, usa_awards, usa_stage")
