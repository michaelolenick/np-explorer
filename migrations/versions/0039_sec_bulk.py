"""SEC structured data (loader/sec_bulk.py): insider filings (Forms 3, 4, 5), Form D offerings and related
persons, executive pay from proxy XBRL, and a run log.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-21
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS sec_insider_filings (
        accession text PRIMARY KEY, quarter text, filing_date date, period date, form text, issuer_cik text,
        issuer_name text, ticker text);
    CREATE INDEX IF NOT EXISTS sec_insider_filings_issuer ON sec_insider_filings (issuer_cik);
    CREATE TABLE IF NOT EXISTS sec_insider_owners (
        accession text NOT NULL, owner_cik text, owner_name text, name_norm text, relationship text, title text,
        city text, state text);
    CREATE INDEX IF NOT EXISTS sec_insider_owners_acc ON sec_insider_owners (accession);
    CREATE INDEX IF NOT EXISTS sec_insider_owners_cik ON sec_insider_owners (owner_cik);
    CREATE INDEX IF NOT EXISTS sec_insider_owners_name ON sec_insider_owners (name_norm);
    CREATE TABLE IF NOT EXISTS sec_insider_trans (
        accession text NOT NULL, sk bigint NOT NULL, security_title text, trans_date date, code text,
        shares numeric, price numeric, acq_disp text, shares_after numeric, direct_indirect text,
        PRIMARY KEY (accession, sk));
    CREATE TABLE IF NOT EXISTS sec_formd (
        accession text PRIMARY KEY, quarter text, filing_date date, form text, cik text, issuer_name text,
        entity_type text, street text, city text, state text, zip text, jurisdiction text, industry text,
        fund_type text, exemptions text, is_amendment boolean, previous_accession text, sale_date date,
        min_investment numeric, offering_amount numeric, amount_sold numeric, investors numeric,
        revenue_range text, nav_range text, issuer_ein text);
    CREATE INDEX IF NOT EXISTS sec_formd_cik ON sec_formd (cik);
    CREATE INDEX IF NOT EXISTS sec_formd_ein ON sec_formd (issuer_ein) WHERE issuer_ein IS NOT NULL;
    CREATE TABLE IF NOT EXISTS sec_formd_people (
        accession text NOT NULL, seq int NOT NULL, name text, name_norm text, relationships text,
        clarification text, city text, state text, PRIMARY KEY (accession, seq));
    CREATE INDEX IF NOT EXISTS sec_formd_people_name ON sec_formd_people (name_norm);
    CREATE TABLE IF NOT EXISTS sec_exec_pay (
        cik text NOT NULL, entity_name text, period_end date NOT NULL, peo_total numeric, neo_avg_total numeric,
        accession text, PRIMARY KEY (cik, period_end));
    CREATE TABLE IF NOT EXISTS sec_runs (
        id bigserial PRIMARY KEY, dataset text, quarter text, rows bigint, finished timestamptz DEFAULT now())""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS sec_runs, sec_exec_pay, sec_formd_people, sec_formd, sec_insider_trans,
                  sec_insider_owners, sec_insider_filings""")
