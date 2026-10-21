"""Lobbying Disclosure Act filings (loader/lda.py): raw API JSON, crawl progress, and the parsed tables.

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-20
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS lda_filings_raw (
        filing_uuid uuid PRIMARY KEY, filing_year smallint, filing_period text, doc jsonb NOT NULL,
        fetched timestamptz NOT NULL DEFAULT now(), parsed boolean NOT NULL DEFAULT false);
    CREATE INDEX IF NOT EXISTS lda_filings_raw_unparsed ON lda_filings_raw (filing_year) WHERE NOT parsed;
    CREATE TABLE IF NOT EXISTS lda_crawl (
        year smallint, period text, pages_done int, pages_total int, updated timestamptz,
        PRIMARY KEY (year, period));
    CREATE TABLE IF NOT EXISTS lda_filings (
        filing_uuid uuid PRIMARY KEY, filing_type text, filing_type_display text, filing_year smallint,
        filing_period text, document_url text, income numeric(14, 2), expenses numeric(14, 2), dt_posted timestamptz,
        termination_date date, registrant_id int, registrant_name text, registrant_state text,
        client_id int, client_name text, client_description text, client_state text, client_ein text,
        registrant_ein text, self_filer boolean);
    CREATE INDEX IF NOT EXISTS lda_filings_client ON lda_filings (client_id);
    CREATE INDEX IF NOT EXISTS lda_filings_registrant ON lda_filings (registrant_id);
    CREATE INDEX IF NOT EXISTS lda_filings_client_ein ON lda_filings (client_ein) WHERE client_ein IS NOT NULL;
    CREATE INDEX IF NOT EXISTS lda_filings_registrant_ein ON lda_filings (registrant_ein) WHERE registrant_ein IS NOT NULL;
    CREATE TABLE IF NOT EXISTS lda_activities (
        filing_uuid uuid NOT NULL, n smallint NOT NULL, issue_code text, issue text, description text,
        entities text[], PRIMARY KEY (filing_uuid, n));
    CREATE TABLE IF NOT EXISTS lda_activity_lobbyists (
        filing_uuid uuid NOT NULL, n smallint NOT NULL, lobbyist_id int, name text, name_norm text,
        covered_position text, new boolean, PRIMARY KEY (filing_uuid, n, lobbyist_id));
    CREATE INDEX IF NOT EXISTS lda_activity_lobbyists_lobbyist ON lda_activity_lobbyists (lobbyist_id);
    CREATE INDEX IF NOT EXISTS lda_activity_lobbyists_name ON lda_activity_lobbyists (name_norm)""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS lda_activity_lobbyists, lda_activities, lda_filings, lda_crawl,
                  lda_filings_raw""")
