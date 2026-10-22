"""Form D: offerings marked "Indefinite", offering chains (original filing and its amendments) for the
subscription leaderboards (sec_formd_offerings is built by app/corporate.build_offerings), links from issuers and related persons to people and organizations, and search
indexes on issuer and person names.

Revision ID: 0050
Revises: 0049
Create Date: 2026-10-22
"""

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE sec_formd ADD COLUMN IF NOT EXISTS offering_indefinite boolean NOT NULL DEFAULT false;
    CREATE TABLE IF NOT EXISTS sec_formd_links (
        accession text NOT NULL, seq int NOT NULL DEFAULT 0, kind text NOT NULL, key text NOT NULL,
        PRIMARY KEY (accession, seq, kind, key));
    CREATE INDEX IF NOT EXISTS sec_formd_links_key ON sec_formd_links (kind, key)""")
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS sec_formd_issuer_trgm ON sec_formd "
                   "USING gin (lower(issuer_name) gin_trgm_ops)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS sec_formd_cik ON sec_formd (cik)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS sec_formd_prev ON sec_formd (previous_accession)")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS sec_formd_people_name ON sec_formd_people (name_norm)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sec_formd_links, sec_formd_offerings")
    op.execute("ALTER TABLE sec_formd DROP COLUMN IF EXISTS offering_indefinite")
