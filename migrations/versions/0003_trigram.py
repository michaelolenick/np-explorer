"""pg_trgm fuzzy-match indexes.

Needs pg_trgm allow-listed on Azure (server parameter azure.extensions).
Every index is built CONCURRENTLY, one at a time, outside a transaction, so
search keeps working while they build. Don't run this while the loader is
running: concurrent index builds wait on every open transaction.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

INDEXES = {
    "people_name_norm_trgm": "people USING gin (name_norm gin_trgm_ops)",
    "contractors_name_norm_trgm": "contractors USING gin (name_norm gin_trgm_ops)",
    "organizations_name_trgm": "organizations USING gin (name gin_trgm_ops)",
    "organizations_name_norm_trgm": "organizations USING gin (name_norm gin_trgm_ops)",
    "person_clusters_name_norm_trgm": "person_clusters USING gin (name_norm gin_trgm_ops)",
    "person_clusters_last_name_trgm": "person_clusters USING gin (last_name gin_trgm_ops)",
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        for name, target in INDEXES.items():
            # A build cancelled part-way leaves an invalid index; drop and redo it.
            op.execute(f"""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_index x JOIN pg_class c ON c.oid = x.indexrelid
                               WHERE c.relname = '{name}' AND NOT x.indisvalid) THEN
                        EXECUTE 'DROP INDEX {name}';
                    END IF;
                END $$""")
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name in INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
