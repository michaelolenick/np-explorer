"""SEC Form ADV (loader/adv.py): investment advisers (registered and exempt reporting) by filing, their owners
and control persons (Schedules A/B), and their private funds (Schedule D 7.B.1), with links to Form D offerings
and to people on the site.

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-22
"""

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS adv_filings (
        filing_id bigint PRIMARY KEY, kind text NOT NULL, crd text, sec_number text, legal_name text,
        business_name text, street text, city text, state text, country text, postal text, submitted date,
        year int, aum numeric, accounts int, source text);
    CREATE INDEX IF NOT EXISTS adv_filings_crd ON adv_filings (crd, submitted);
    CREATE TABLE IF NOT EXISTS adv_owners (
        filing_id bigint NOT NULL, crd text, year int, name text NOT NULL, name_norm text, entity_kind text,
        title text, status_acquired text, ownership_code text, control_person boolean, owner_id text);
    CREATE INDEX IF NOT EXISTS adv_owners_crd ON adv_owners (crd, year);
    CREATE INDEX IF NOT EXISTS adv_owners_name ON adv_owners (name_norm);
    CREATE TABLE IF NOT EXISTS adv_funds (
        filing_id bigint NOT NULL, crd text, year int, fund_name text NOT NULL, fund_id text, state text,
        country text, fund_type text, gav numeric, min_investment numeric, owners int, master_fund boolean,
        feeder_fund boolean);
    CREATE INDEX IF NOT EXISTS adv_funds_fund ON adv_funds (fund_id, year);
    CREATE INDEX IF NOT EXISTS adv_funds_crd ON adv_funds (crd, year);
    CREATE TABLE IF NOT EXISTS adv_fund_links (
        fund_id text NOT NULL, root_accession text NOT NULL, PRIMARY KEY (fund_id, root_accession));
    CREATE INDEX IF NOT EXISTS adv_fund_links_root ON adv_fund_links (root_accession);
    CREATE TABLE IF NOT EXISTS adv_person_links (
        crd text NOT NULL, name_norm text NOT NULL, cluster_id bigint NOT NULL, PRIMARY KEY (crd, name_norm));
    CREATE INDEX IF NOT EXISTS adv_person_links_cluster ON adv_person_links (cluster_id);
    CREATE TABLE IF NOT EXISTS adv_runs (file text PRIMARY KEY, loaded timestamptz NOT NULL DEFAULT now(),
                                         filings int, owners int, funds int)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS adv_runs, adv_person_links, adv_fund_links, adv_funds, adv_owners, adv_filings")
