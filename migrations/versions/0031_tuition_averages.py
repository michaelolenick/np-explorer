"""tuition_averages: national average undergraduate tuition, fees, room and board by academic year, from NCES
Digest of Education Statistics Table 330.10 (loader/tuition.py; refreshed weekly with the student loan data).

One row per (control, level, academic year). Dollars as published: current dollars and constant dollars of the
edition's latest year (constant_base, e.g. '2023-24'). A newer Digest edition replaces every row.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-19
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS tuition_averages (
        control               text    NOT NULL,   -- all | public | private | private_nonprofit | private_for_profit
        level                 text    NOT NULL,   -- all | 4-year | 2-year
        year_start            integer NOT NULL,   -- 1976 = academic year 1976-77
        academic_year         text    NOT NULL,   -- as published, e.g. '1976-77'
        tuition_fees_current  numeric,
        tuition_fees_constant numeric,
        total_current         numeric,            -- tuition, fees, room and board
        total_constant        numeric,
        constant_base         text    NOT NULL,   -- the constant-dollar year, e.g. '2023-24'
        edition_year          integer NOT NULL,   -- Digest edition, e.g. 2024
        source_url            text    NOT NULL,
        file_sha256           text    NOT NULL,
        retrieved_at          timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (control, level, year_start)
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tuition_averages")
