"""Where the money went: every expense line per filing.

Form 990 Part IX (with program, management and fundraising columns and the
filer's own descriptions of "other" lines), 990-EZ Part I and 990-PF Part I
column (a), plus fundraising-event figures (990 Part VIII line 8, 990-EZ line 6).
Filled by the loader and by load.py backfill-extras --only expense_breakdown.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-17
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS expense_breakdown (
        filing_id              bigint PRIMARY KEY,
        ein                    text NOT NULL,
        tax_year               integer,
        form_type              text,
        total_expenses         bigint,
        pay_total              bigint,     -- officer and staff pay, benefits, payroll taxes
        grants_total           bigint,     -- grants to organizations, individuals, abroad
        event_lines_total      bigint,     -- "other" lines the filer describes as events
        conferences_total      bigint,     -- conferences, conventions, meetings
        special_event_expenses bigint,     -- direct expenses of fundraising events
        special_event_gross    bigint,     -- gross income from fundraising events
        lines                  jsonb       -- [key, label, description, total, program, management, fundraising, is_event]
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_breakdown")
