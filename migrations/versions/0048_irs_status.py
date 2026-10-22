"""IRS exempt-status sources for every organization, including new and small ones (loader/irs_status.py): the
full Business Master File row, Form 990-N e-postcards, Pub 78 deductibility and the auto-revocation list.

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-22
"""

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS irs_bmf_detail (
        ein text PRIMARY KEY, ico text, group_exemption text, subsection text, affiliation text, classification text,
        ruling text, deductibility text, foundation text, activity text, organization text, status text,
        tax_period text, filing_req text, asset_amt bigint, income_amt bigint, revenue_amt bigint);
    CREATE TABLE IF NOT EXISTS irs_epostcard (
        ein text NOT NULL, tax_year int NOT NULL, legal_name text, small boolean, terminated boolean,
        period_begin date, period_end date, website text, officer_name text, officer_city text, officer_state text,
        street text, city text, state text, zip text, country text, dba text, PRIMARY KEY (ein, tax_year));
    CREATE TABLE IF NOT EXISTS irs_pub78 (
        ein text PRIMARY KEY, name text, city text, state text, country text, codes text);
    CREATE TABLE IF NOT EXISTS irs_revocations (
        ein text NOT NULL, legal_name text, dba text, street text, city text, state text, zip text, country text,
        exemption_type text, revocation_date date NOT NULL, posting_date date, reinstatement_date date,
        PRIMARY KEY (ein, revocation_date))""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS irs_revocations, irs_pub78, irs_epostcard, irs_bmf_detail")
