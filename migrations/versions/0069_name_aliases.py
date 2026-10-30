"""Abbreviations and full names (owner, 2026-10-30): "IBM" is "International Business Machines", "3M" is "Minnesota
Mining and Manufacturing". One row per pair, both names normalized the way business registry names are
(loader.recalls.core: lower case, punctuation and legal endings dropped). source is 'manual' (the hand-picked list in
loader/name_aliases.py, or a row the owner added) or 'derived' (initials of names FURP holds, with evidence; rebuilt
nightly). status 'off' turns a row off without deleting it; the nightly rebuild leaves manual rows and 'off' rows
alone, so edits stick.

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-30
"""

from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS name_aliases (
        short_norm text NOT NULL,
        long_norm text NOT NULL,
        short text NOT NULL,
        long text NOT NULL,
        source text NOT NULL CHECK (source IN ('manual', 'derived')),
        support integer NOT NULL DEFAULT 0,
        evidence text,
        status text NOT NULL DEFAULT 'live' CHECK (status IN ('live', 'off')),
        created timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (short_norm, long_norm));
    CREATE INDEX IF NOT EXISTS name_aliases_long ON name_aliases (long_norm)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS name_aliases")
