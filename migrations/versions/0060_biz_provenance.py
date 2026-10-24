"""Business registry rows carry their provenance (file, quarter, load time), an EIN where the state publishes one
(Florida's FEI number), and the rest of the record (extra) so nothing filed is thrown away.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-24
"""

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE biz_entities ADD COLUMN IF NOT EXISTS ein text;
    ALTER TABLE biz_entities ADD COLUMN IF NOT EXISTS provenance text;
    ALTER TABLE biz_entities ADD COLUMN IF NOT EXISTS extra jsonb;
    ALTER TABLE biz_people ADD COLUMN IF NOT EXISTS provenance text;
    CREATE INDEX IF NOT EXISTS biz_entities_ein ON biz_entities (ein) WHERE ein IS NOT NULL""")


def downgrade() -> None:
    op.execute("""ALTER TABLE biz_entities DROP COLUMN IF EXISTS ein, DROP COLUMN IF EXISTS provenance,
                  DROP COLUMN IF EXISTS extra; ALTER TABLE biz_people DROP COLUMN IF EXISTS provenance""")
