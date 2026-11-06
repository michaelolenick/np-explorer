"""Vendor key (owner, 2026-11-06): merge name variants of the same contractor. vendor_key(text) uppercases, turns
punctuation into spaces, drops trailing INC, LLC, CORP, LTD, CO (and their long forms) and AFFILIATES (so "& Affiliates"
goes too), and collapses whitespace. contractors.vendor_key holds it: the loader fills it at insert (loader/ingest.py),
this migration backfills every existing row in batches. No model calls.

Revision ID: 0072
Revises: 0071
Create Date: 2026-11-06
"""

from alembic import op
from sqlalchemy import text

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None

FUNCTION = r"""
CREATE OR REPLACE FUNCTION vendor_key(raw text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT nullif(regexp_replace(
               trim(regexp_replace(upper(raw), '[^A-Z0-9]+', ' ', 'g')),
               '( (INC|INCORPORATED|LLC|CORP|CORPORATION|LTD|LIMITED|CO|COMPANY|AFFILIATES))+$', ''), '')
$$"""


def upgrade() -> None:
    op.execute(FUNCTION)
    op.execute("SET lock_timeout = '20s'")
    op.execute("ALTER TABLE contractors ADD COLUMN IF NOT EXISTS vendor_key text")
    conn = op.get_bind()
    lo, hi = conn.execute(text("SELECT min(id), max(id) FROM contractors")).fetchone()
    if lo is not None:
        step = 100_000
        for start in range(lo, hi + 1, step):
            conn.execute(text("UPDATE contractors SET vendor_key = vendor_key(name_raw) "
                              "WHERE id >= :a AND id < :b AND vendor_key IS NULL"), {"a": start, "b": start + step})
    op.execute("CREATE INDEX IF NOT EXISTS contractors_vendor_key ON contractors (vendor_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS contractors_vendor_key")
    op.execute("ALTER TABLE contractors DROP COLUMN IF EXISTS vendor_key")
    op.execute("DROP FUNCTION IF EXISTS vendor_key(text)")
