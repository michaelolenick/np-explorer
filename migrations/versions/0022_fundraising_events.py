"""fundraising_events: Schedule G Part II, per filing.

The form names the two largest fundraising events (by gross receipts) and combines
all others into one column; slot is event1, event2, other or total. Columns stay
NULL where the filer left a line blank (never 0 for "not reported"). keyword is a
plain match of party-style words in the event's own name (loader/parser.py
GALA_WORDS). Written by the extras loader (loader/extras.py); backfilled from
stored XML for filings reporting fundraising-event income or expenses.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-17
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS fundraising_events (
        id              bigserial PRIMARY KEY,
        filing_id       bigint NOT NULL,
        ein             text,
        tax_year        integer,
        slot            text NOT NULL,      -- event1, event2, other, total
        name            text,               -- as the organization described it (event1, event2)
        keyword         text,               -- gala-type word found in the name, or NULL
        other_count     integer,            -- number of events combined in "other"
        gross_receipts  bigint,             -- line 1 (includes contributions)
        contributions   bigint,             -- line 2: charitable contributions
        gross_revenue   bigint,             -- line 3: gross income (= Part VIII line 8a on the total)
        cash_prizes     bigint,
        noncash_prizes  bigint,
        rent_facility   bigint,
        food_beverage   bigint,
        entertainment   bigint,
        other_direct    bigint,
        direct_expenses bigint,             -- sum of the expense lines (line 10 on the total)
        net_income      bigint              -- gross revenue minus direct expenses
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS fundraising_events_filing ON fundraising_events (filing_id)")
    op.execute("CREATE INDEX IF NOT EXISTS fundraising_events_ein ON fundraising_events (ein, tax_year)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fundraising_events")
