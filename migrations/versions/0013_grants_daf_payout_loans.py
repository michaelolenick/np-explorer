"""Grants (Schedule I Part II, 990-PF grants paid), donor-advised fund figures
(Part IV flag, Schedule D Part I), 990-PF payout figures, and Schedule L loans.

Filled by the loader for new filings and by load.py backfill-extras for filings
already loaded.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS grants (
        id                  bigserial PRIMARY KEY,
        filing_id           bigint NOT NULL,
        ein                 text NOT NULL,           -- the grantor
        tax_year            integer,
        source              text NOT NULL,           -- 990-I (Schedule I Part II) | 990PF-XV (grants paid)
        recipient_name      text,                    -- NULL for grants to individuals (not kept)
        recipient_name_norm text,
        recipient_ein       text,                    -- as filed; 990-PF grants carry none
        recipient_is_person boolean NOT NULL DEFAULT false,
        city                text,
        state               text,
        cash_amount         bigint,
        noncash_amount      bigint,
        purpose             text,
        irc_section         text,
        foundation_status   text,
        relationship        text
    );
    CREATE TABLE IF NOT EXISTS daf_stats (
        filing_id           bigint PRIMARY KEY,
        ein                 text NOT NULL,
        tax_year            integer,
        form_type           text,
        maintains_dafs      boolean,                 -- Form 990 Part IV line 6 / 990-EZ
        daf_count           bigint,                  -- Schedule D Part I, column (a)
        daf_contributions   bigint,
        daf_grants          bigint,
        daf_value_eoy       bigint,
        other_count         bigint,                  -- column (b): funds and other accounts
        other_contributions bigint,
        other_grants        bigint,
        other_value_eoy     bigint
    );
    CREATE TABLE IF NOT EXISTS pf_payout (
        filing_id                bigint PRIMARY KEY,
        ein                      text NOT NULL,
        tax_year                 integer,
        noncharitable_assets     bigint,             -- Part X line 5
        min_investment_return    bigint,             -- Part X line 6 (5% of line 5)
        distributable_amount     bigint,             -- Part XI line 7
        qualifying_distributions bigint              -- Part XII line 4
    );
    CREATE TABLE IF NOT EXISTS insider_loans (
        id                 bigserial PRIMARY KEY,
        filing_id          bigint NOT NULL,
        ein                text NOT NULL,
        tax_year           integer,
        name_raw           text,
        name_norm          text,
        relationship       text,
        purpose            text,
        to_org             boolean,                  -- loan to the organization
        from_org           boolean,                  -- loan from the organization
        original_principal bigint,
        balance_due        bigint,
        in_default         boolean,
        board_approved     boolean,
        written_agreement  boolean
    );
    -- Only what the loader needs; the search indexes are built after the backfill
    -- (loader/extras.py INDEXES), since building them first would slow it badly.
    CREATE INDEX IF NOT EXISTS grants_filing_id ON grants (filing_id);
    CREATE INDEX IF NOT EXISTS insider_loans_filing_id ON insider_loans (filing_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS grants, daf_stats, pf_payout, insider_loans")
