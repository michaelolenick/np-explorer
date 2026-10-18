"""International schools: foreign universities and business schools with US nonprofits that file 990s.

  intl_schools        one row per foreign school (ROR ID), with a stable id in the colleges table
                      (unitid 9,000,001 and up, a range IPEDS does not use) and whether the school itself
                      files a US return.
  intl_grants_abroad  Schedule F grants abroad reported by the schools' US affiliates (region, amount,
                      purpose as filed; Schedule F names a region, not the recipient).
  colleges            gains country, international and ror_id; foreign schools are added as rows with
                      control 'International' (no IPEDS data).

Built by load.py colleges --only intl (loader/intl_schools.py) from data/international-schools.csv
(reviewed list; EXACT links only).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-18
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE colleges ADD COLUMN IF NOT EXISTS country text")
    op.execute("ALTER TABLE colleges ADD COLUMN IF NOT EXISTS international boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE colleges ADD COLUMN IF NOT EXISTS ror_id text")
    op.execute("""
    CREATE TABLE IF NOT EXISTS intl_schools (
        ror_id           text PRIMARY KEY,
        unitid           integer NOT NULL UNIQUE,
        name             text NOT NULL,
        country          text,
        website          text,
        files_own_return boolean NOT NULL DEFAULT false
    )""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS intl_grants_abroad (
        ein         text NOT NULL,
        tax_year    smallint,
        object_id   text,
        part        text NOT NULL,          -- Schedule F Part I (activities by region) or Part II (grants to organizations)
        region      text,
        amount      bigint,
        description text
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS intl_grants_abroad_ein ON intl_grants_abroad (ein)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS intl_grants_abroad")
    op.execute("DROP TABLE IF EXISTS intl_schools")
    for col in ("country", "international", "ror_id"):
        op.execute(f"ALTER TABLE colleges DROP COLUMN IF EXISTS {col}")
