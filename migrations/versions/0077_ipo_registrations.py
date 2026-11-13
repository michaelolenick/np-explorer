"""IPO registrations from SEC EDGAR (owner, 2026-11-12; loader/s1.py, app/ipos.py).

ipo_filings: every S-1, S-1/A, F-1 and F-1/A in EDGAR's full index since 1993, plus the final prospectus (424B4,
424B1), notice of effectiveness (EFFECT), Rule 462(b) add-on (S-1MEF, F-1MEF) and withdrawal request (RW) of those
registrants, one row per (accession, CIK).
ipo_companies: one row per registrant (CIK) with what EDGAR's submissions data says about it (SIC, state of
incorporation, address, EIN, tickers, former names) and its registration history in numbers.
ipo_links: the FURP records each registrant ties to (SEC filers and Form D issuers by CIK; nonprofits, state
registrations, lobbying, Form 5500 sponsors and federal recipients by EIN; the rest by name and state; people via
the company's insider filings). Mirrored into xlinks as src_kind ipo_company.

The loader creates these too (CREATE TABLE IF NOT EXISTS, the same DDL); the migration is here so a fresh database
has them.

Revision ID: 0077
Revises: 0076
Create Date: 2026-11-12
"""

from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS ipo_filings (
        accession text NOT NULL, cik text NOT NULL, company_name text NOT NULL, form text NOT NULL, filed date NOT NULL,
        year integer NOT NULL, url text NOT NULL, PRIMARY KEY (accession, cik));
    CREATE INDEX IF NOT EXISTS ipo_filings_cik ON ipo_filings (cik, filed);
    CREATE INDEX IF NOT EXISTS ipo_filings_filed ON ipo_filings (filed DESC);
    CREATE INDEX IF NOT EXISTS ipo_filings_form_year ON ipo_filings (form, year);
    CREATE TABLE IF NOT EXISTS ipo_companies (
        cik text PRIMARY KEY, name text NOT NULL, index_name text, name_core text, kind text NOT NULL,
        sic text, sic_desc text, state_inc text, entity_type text, street text, city text, state text, zip text, ein text,
        tickers text, exchanges text, former_names jsonb, first_filed date NOT NULL, last_filed date NOT NULL,
        n_filings integer NOT NULL, n_reg integer NOT NULL, n_amend integer NOT NULL, priced date, effect date,
        withdrawn date, loaded timestamptz NOT NULL);
    CREATE INDEX IF NOT EXISTS ipo_companies_core ON ipo_companies (name_core);
    CREATE INDEX IF NOT EXISTS ipo_companies_first ON ipo_companies (first_filed DESC);
    CREATE INDEX IF NOT EXISTS ipo_companies_state ON ipo_companies (state);
    CREATE INDEX IF NOT EXISTS ipo_companies_sic ON ipo_companies (sic);
    CREATE INDEX IF NOT EXISTS ipo_companies_ein ON ipo_companies (ein) WHERE ein IS NOT NULL;
    CREATE TABLE IF NOT EXISTS ipo_links (
        cik text NOT NULL, dst_kind text NOT NULL, dst_key text NOT NULL, dst_name text, how text NOT NULL,
        PRIMARY KEY (cik, dst_kind, dst_key));
    CREATE INDEX IF NOT EXISTS ipo_links_dst ON ipo_links (dst_kind, dst_key)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ipo_links, ipo_filings, ipo_companies")
