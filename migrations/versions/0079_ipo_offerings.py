"""IPO offering terms (owner, 2026-11-13; loader/s1_terms.py, app/ipos.py, app/ipo_terms_boards.py).

ipo_offerings: one row per prospectus or registration statement read from EDGAR: the price range, final price,
shares offered (by the company and by selling holders), gross proceeds, exchange and ticker, the underwriters
(jsonb, normalised names) and the leads, with the document URL and a parse note.
ipo_offering_underwriters: one row per underwriter per document (rank, shares allocated, lead).
ipo_underwriters: the roll-up per firm (deals, as lead, proceeds, by year, the broker-dealer and adviser records
with the same name).
ipo_companies gains the headline terms (price_low, price_high, offer_price, offer_shares, offer_proceeds,
offer_exchange, offer_ticker, offer_date, offer_is_ipo, lead_underwriters, n_underwriters), filled by
loader.s1_terms rollup() and again after every loader.s1 load.

The loader creates these too (CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, the same DDL); the migration
is here so a fresh database has them.

Revision ID: 0079
Revises: 0078
Create Date: 2026-11-13
"""

from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from loader.s1_terms import DDL
    op.execute(DDL)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS ipo_offering_underwriters, ipo_offerings, ipo_underwriters;
    ALTER TABLE ipo_companies DROP COLUMN IF EXISTS price_low, DROP COLUMN IF EXISTS price_high,
        DROP COLUMN IF EXISTS offer_price, DROP COLUMN IF EXISTS offer_shares, DROP COLUMN IF EXISTS offer_proceeds,
        DROP COLUMN IF EXISTS offer_exchange, DROP COLUMN IF EXISTS offer_ticker, DROP COLUMN IF EXISTS offer_date,
        DROP COLUMN IF EXISTS offer_is_ipo, DROP COLUMN IF EXISTS lead_underwriters, DROP COLUMN IF EXISTS n_underwriters""")
