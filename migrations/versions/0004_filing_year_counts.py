"""Per-tax-year filing counts for the site's coverage notice.

Refreshed by the loader's finalize step, so pages don't count filings.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-17
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE filing_year_counts (tax_year integer PRIMARY KEY, n integer NOT NULL);
    INSERT INTO filing_year_counts SELECT tax_year, count(*) FROM filings WHERE tax_year IS NOT NULL GROUP BY tax_year;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS filing_year_counts")
