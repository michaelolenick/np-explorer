"""Federal cohort default rates on school pages; a log of the weekly student loan refresh.

  colleges.opeid            the institution's 8-digit OPE ID from IPEDS. The Department of Education's
                            cohort default rates (cohort_default_rates) are keyed by its first six digits,
                            so branch campuses share their main school's rate.
  school_rows.cdr_*         the latest federal cohort default rate for the Schools list.
  student_loan_runs         one row per refresh of the student loan trust data (loader/student_loans.py
                            refresh): when it ran, whether it finished, what it added. Pages show the last
                            successful run's date, and say so when a later run failed.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-18
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE colleges ADD COLUMN IF NOT EXISTS opeid text")
    op.execute("CREATE INDEX IF NOT EXISTS colleges_opeid6 ON colleges (left(opeid, 6))")
    op.execute("CREATE INDEX IF NOT EXISTS cohort_default_rates_opeid ON cohort_default_rates (opeid, fiscal_year)")
    for col, typ in (("cdr_rate", "numeric"), ("cdr_year", "smallint"), ("cdr_borrowers", "integer"),
                     ("cdr_defaulters", "integer")):
        op.execute(f"ALTER TABLE school_rows ADD COLUMN IF NOT EXISTS {col} {typ}")
    op.execute("""
    CREATE TABLE IF NOT EXISTS student_loan_runs (
        id          bigserial PRIMARY KEY,
        started_at  timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        ok          boolean,                -- NULL while running; false when it stopped with an error
        trusts      integer,
        new_months  integer,
        message     text
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS student_loan_runs")
    for col in ("cdr_rate", "cdr_year", "cdr_borrowers", "cdr_defaulters"):
        op.execute(f"ALTER TABLE school_rows DROP COLUMN IF EXISTS {col}")
    op.execute("DROP INDEX IF EXISTS cohort_default_rates_opeid")
    op.execute("DROP INDEX IF EXISTS colleges_opeid6")
    op.execute("ALTER TABLE colleges DROP COLUMN IF EXISTS opeid")
