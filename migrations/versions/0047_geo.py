"""Map-ready places (loader/geo.py): ZIP (ZCTA) and city (Census place) center points, the districts each falls in
(congressional, 119th and 120th Congress; state senate; state house), each ZIP's share of area in every district
it crosses, and the districts themselves.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-22
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS geo_districts (
        kind text NOT NULL, code text NOT NULL, state text, name text, lat double precision, lon double precision,
        PRIMARY KEY (kind, code));
    CREATE TABLE IF NOT EXISTS geo_zips (
        zip5 text PRIMARY KEY, lat double precision NOT NULL, lon double precision NOT NULL,
        cd119 text, cd120 text, sldu text, sldl text);
    CREATE TABLE IF NOT EXISTS geo_places (
        state text NOT NULL, place_norm text NOT NULL, name text NOT NULL, geoid text, lat double precision NOT NULL,
        lon double precision NOT NULL, cd119 text, cd120 text, sldu text, sldl text, PRIMARY KEY (state, place_norm));
    CREATE TABLE IF NOT EXISTS geo_zip_districts (
        zip5 text NOT NULL, kind text NOT NULL, code text NOT NULL, share real NOT NULL, PRIMARY KEY (zip5, kind, code));
    CREATE INDEX IF NOT EXISTS geo_zip_districts_code ON geo_zip_districts (kind, code)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS geo_zip_districts, geo_places, geo_zips, geo_districts")
