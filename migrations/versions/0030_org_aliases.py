"""org_aliases: common names and acronyms for organizations whose filed names nobody would type.

One row per (alias, organization). role 'primary' is the organization the common name means; 'affiliate' rows are
related organizations listed beneath it. status 'live' rows are used by search; 'proposed' rows wait for review
(scripts/propose_aliases.py writes them; nothing goes live automatically). note says where the alias came from.

Seeded with INSEAD: its own US filer files as "INSTITUT EUPROPEEN D ADMINISTRATION DES AFFAIRES INSEAD" (sic).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-18
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS org_aliases (
        alias_norm text NOT NULL,           -- normalized common name: lower case, punctuation and Inc/the dropped
        alias      text NOT NULL,           -- as written
        ein        text NOT NULL,
        role       text NOT NULL CHECK (role IN ('primary', 'affiliate')),
        status     text NOT NULL DEFAULT 'proposed' CHECK (status IN ('live', 'proposed', 'rejected')),
        note       text NOT NULL,           -- where the alias came from
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (alias_norm, ein)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS org_aliases_ein ON org_aliases (ein)")
    op.execute("""
    INSERT INTO org_aliases (alias_norm, alias, ein, role, status, note) VALUES
      ('insead', 'INSEAD', '311551644', 'primary', 'live',
       'INSEAD''s own US filer; its returns spell the name "Institut Eupropeen d Administration des Affaires" (sic). Added by the site owner, 2026-10-18.'),
      ('insead', 'INSEAD', '311734079', 'affiliate', 'live',
       'INSEAD North America Inc, the school''s US affiliate. Added by the site owner, 2026-10-18.')
    ON CONFLICT (alias_norm, ein) DO NOTHING""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_aliases")
