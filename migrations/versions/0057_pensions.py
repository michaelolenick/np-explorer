"""Public pension funds' private equity commitments (loader/pensions.py): CalPERS and CalSTRS fund-by-fund
performance, every as-of date kept, and matches to Form D offerings and Form ADV private funds.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-23
"""

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS pension_commitments (
        pension text NOT NULL, fund_name text NOT NULL, fund_core text, vintage int, committed numeric,
        cash_in numeric, cash_out numeric, total_value numeric, net_irr numeric, multiple numeric, as_of date NOT NULL,
        source_url text, PRIMARY KEY (pension, fund_name, as_of));
    CREATE INDEX IF NOT EXISTS pension_commitments_core ON pension_commitments (fund_core);
    CREATE TABLE IF NOT EXISTS pension_fund_matches (
        pension text NOT NULL, fund_name text NOT NULL, kind text NOT NULL, key text NOT NULL, confidence text NOT NULL,
        score numeric, PRIMARY KEY (pension, fund_name, kind, key));
    CREATE INDEX IF NOT EXISTS pension_fund_matches_key ON pension_fund_matches (kind, key);
    CREATE TABLE IF NOT EXISTS pension_sources (url text PRIMARY KEY, pension text, as_of date, rows int,
                                                loaded timestamptz NOT NULL DEFAULT now())""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pension_sources, pension_fund_matches, pension_commitments")
