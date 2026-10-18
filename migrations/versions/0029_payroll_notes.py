"""Payroll notes: a published $0 shown as Not reported, and years that are derived or not published.

  payroll_rows.pay_note / payroll_person_years.pay_note    e.g. "The source published $0" (pay is then NULL on
                                                            the site; the staged row keeps the $0)
  payroll_rows.year_note / payroll_person_years.year_note  "Year derived from the PDF's creation date", or
                                                            "Year not published" (fiscal_year NULL: shown, but left
                                                            out of yearly totals, boards and comparisons)

Set by loader/colleges.py from flags in unipay.public_payroll_records.pay_components.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-18
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for t in ("payroll_rows", "payroll_person_years"):
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS pay_note text")
        op.execute(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS year_note text")


def downgrade() -> None:
    for t in ("payroll_rows", "payroll_person_years"):
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS pay_note")
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS year_note")
