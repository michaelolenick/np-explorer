"""Form D related persons as people and organizations (loader/formd_parties.py): one row per distinct person (name
and state) or entity (name) named on Form D filings, with stable ids for their pages, and each filing's related
persons mapped to them.

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-23
"""

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS sec_formd_parties (
        id bigserial PRIMARY KEY, kind text NOT NULL, key text NOT NULL UNIQUE, name text NOT NULL, state text,
        name_norm text, filings int, last_date date, cluster_id bigint);
    CREATE INDEX IF NOT EXISTS sec_formd_parties_norm ON sec_formd_parties (name_norm);
    CREATE TABLE IF NOT EXISTS sec_formd_people_party (
        accession text NOT NULL, seq int NOT NULL, party_id bigint NOT NULL, PRIMARY KEY (accession, seq));
    CREATE INDEX IF NOT EXISTS sec_formd_people_party_party ON sec_formd_people_party (party_id)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sec_formd_people_party, sec_formd_parties")
