"""Securities registration (loader/registrations.py): active broker-dealers by month (SEC), investment adviser firms
and representatives (IAPD compilation reports), other business names, and links to people and firms on the site.

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-23
"""

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS bd_monthly (
        month date NOT NULL, cik text NOT NULL, name text, file_no text, street1 text, street2 text, city text,
        state text, zip text, PRIMARY KEY (month, cik));
    CREATE TABLE IF NOT EXISTS bd_firms (
        cik text PRIMARY KEY, name text, name_core text, file_no text, street1 text, street2 text, city text,
        state text, zip text, first_month date, last_month date, active boolean, crd text, names text[]);
    CREATE INDEX IF NOT EXISTS bd_firms_core ON bd_firms (name_core);
    CREATE TABLE IF NOT EXISTS iapd_firms (
        crd text PRIMARY KEY, sec_number text, legal_name text, business_name text, name_core text, street text,
        city text, state text, zip text, regulator text, status text, status_date date, feed_date date,
        other_names text[]);
    CREATE INDEX IF NOT EXISTS iapd_firms_core ON iapd_firms (name_core);
    CREATE TABLE IF NOT EXISTS iapd_individuals (
        crd text PRIMARY KEY, first_name text, middle_name text, last_name text, name text, name_norm text,
        active_broker boolean, other_names text[], exams text[], designations text[], disclosures text[],
        states text[], feed_date date);
    CREATE INDEX IF NOT EXISTS iapd_individuals_norm ON iapd_individuals (name_norm);
    CREATE INDEX IF NOT EXISTS iapd_individuals_last ON iapd_individuals (lower(last_name));
    CREATE TABLE IF NOT EXISTS iapd_employments (
        crd text NOT NULL, firm_crd text, firm_name text, current boolean NOT NULL, begin_date date, end_date date,
        reg_category text, reg_authority text, city text, state text);
    CREATE INDEX IF NOT EXISTS iapd_employments_crd ON iapd_employments (crd);
    CREATE INDEX IF NOT EXISTS iapd_employments_firm ON iapd_employments (firm_crd);
    CREATE TABLE IF NOT EXISTS sec_firm_aliases (
        alias_norm text NOT NULL, alias text NOT NULL, kind text NOT NULL, key text NOT NULL, source text,
        PRIMARY KEY (alias_norm, kind, key));
    CREATE TABLE IF NOT EXISTS registration_links (
        kind text NOT NULL, key text NOT NULL, reg_kind text NOT NULL, reg_key text NOT NULL, how text,
        PRIMARY KEY (kind, key, reg_kind, reg_key));
    CREATE INDEX IF NOT EXISTS registration_links_reg ON registration_links (reg_kind, reg_key);
    CREATE TABLE IF NOT EXISTS registration_runs (file text PRIMARY KEY, loaded timestamptz NOT NULL DEFAULT now(),
                                                  rows int)""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS registration_runs, registration_links, sec_firm_aliases, iapd_employments,
                  iapd_individuals, iapd_firms, bd_firms, bd_monthly""")
