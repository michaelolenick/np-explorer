"""Refine the institution rule: long names, two institution words, not-a-name words.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-17
"""

from alembic import op

from app.institutions import candidate_regex, function_sql, given_names_sql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(given_names_sql())
    op.execute(function_sql())
    rx = candidate_regex().replace("'", "''")
    op.execute(f"""
        UPDATE person_clusters c SET is_institution = v.inst
        FROM (SELECT id, np_institution(name_norm) AS inst FROM person_clusters WHERE name_norm ~ '{rx}') v
        WHERE c.id = v.id AND c.is_institution IS DISTINCT FROM v.inst
    """)


def downgrade() -> None:
    pass
