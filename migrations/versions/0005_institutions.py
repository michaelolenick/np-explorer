"""Tag institutions (banks, trust companies, firms) listed as officers.

Adds person_clusters.is_institution, the given_names table the rule consults,
and np_institution(name_norm), generated from app/institutions.py. Only names
matching an institution word are updated, so this is quick even on 15M rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-17
"""

from alembic import op

from app.institutions import sql_strong_regex, sql_weak_regex

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# A first word counts as a given name when this many person clusters with no
# institution words start with it.
GIVEN_NAME_MIN = 100


def function_sql() -> str:
    strong = sql_strong_regex().replace("'", "''")
    weak = sql_weak_regex().replace("'", "''")
    return f"""
    CREATE OR REPLACE FUNCTION np_institution(n text) RETURNS boolean LANGUAGE sql STABLE PARALLEL SAFE AS $$
        SELECT n ~ '{strong}'
            OR (n ~ '{weak}' AND NOT EXISTS (SELECT 1 FROM given_names g WHERE g.name = split_part(n, ' ', 1)))
    $$;
    """


def given_names_sql() -> str:
    strong = sql_strong_regex().replace("'", "''")
    weak = sql_weak_regex().replace("'", "''")
    return f"""
    TRUNCATE given_names;
    INSERT INTO given_names
    SELECT first_name FROM person_clusters
    WHERE length(first_name) > 1 AND name_norm !~ '{strong}' AND name_norm !~ '{weak}'
    GROUP BY first_name HAVING count(*) >= {GIVEN_NAME_MIN};
    """


def upgrade() -> None:
    op.execute("CREATE TABLE given_names (name text PRIMARY KEY)")
    op.execute(given_names_sql())
    op.execute(function_sql())
    op.execute("ALTER TABLE person_clusters ADD COLUMN is_institution boolean NOT NULL DEFAULT false")
    weak_or_strong = f"({sql_strong_regex()})|({sql_weak_regex()})".replace("'", "''")
    op.execute(f"""
        UPDATE person_clusters SET is_institution = true
        WHERE name_norm ~ '{weak_or_strong}' AND np_institution(name_norm)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE person_clusters DROP COLUMN IF EXISTS is_institution")
    op.execute("DROP FUNCTION IF EXISTS np_institution(text)")
    op.execute("DROP TABLE IF EXISTS given_names")
