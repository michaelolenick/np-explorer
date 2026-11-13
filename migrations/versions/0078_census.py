"""Census cross-reference tables (owner, 2026-11-12; loader/census.py, app/census.py).

census_zip_county, census_zip_tract: the Census Bureau's 2020 ZCTA-to-county and ZCTA-to-tract relationship files
(share of each ZIP's land in each county or tract; `dominant` marks the one holding most of it).
census_shapes: simplified TIGER/Line 2026 outlines of states, counties, places and tracts for the SVG maps.
census_area: one row per state, county, place and census tract with the headline measures from the IPUMS NHGIS
tables (schema nhgis, loader/nhgis.py): population, median household income, poverty rate, median age, education,
housing, race and ethnicity.
census_links: every FURP record with an address (nonprofits, contractors, schools, Form D issuers, lobbying clients,
committees, plan sponsors, Open Payments recipients, recall firms, patent owners, IPO registrants, federal
recipients) and the state, county, place and tract it was placed in, with how (zip, city, state).
census_area_furp and census_area_people: per-area summaries the pages and leaderboards read.
census_city_norm(text): the SQL twin of loader/geo.py place_norm for matching city names to Census places.

The loader creates these too (CREATE TABLE IF NOT EXISTS, the same DDL); the migration is here so a fresh database
has them.

Revision ID: 0078
Revises: 0077
Create Date: 2026-11-12
"""

from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from loader.census import SCHEMA_SQL
    op.execute(SCHEMA_SQL)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS census_area_people, census_area_furp, census_links, census_area, census_shapes,
        census_zip_tract, census_zip_county, census_meta;
    DROP FUNCTION IF EXISTS census_city_norm(text);
    """)
