"""pg_trgm fuzzy-match indexes.

Needs pg_trgm allow-listed on Azure (server parameter azure.extensions).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    CREATE INDEX IF NOT EXISTS people_name_norm_trgm ON people USING gin (name_norm gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS contractors_name_norm_trgm ON contractors USING gin (name_norm gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS organizations_name_trgm ON organizations USING gin (name gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS organizations_name_norm_trgm ON organizations USING gin (name_norm gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS person_clusters_name_norm_trgm ON person_clusters USING gin (name_norm gin_trgm_ops);
    CREATE INDEX IF NOT EXISTS person_clusters_last_name_trgm ON person_clusters USING gin (last_name gin_trgm_ops);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS people_name_norm_trgm, contractors_name_norm_trgm, organizations_name_trgm,
        organizations_name_norm_trgm, person_clusters_name_norm_trgm, person_clusters_last_name_trgm;
    """)
