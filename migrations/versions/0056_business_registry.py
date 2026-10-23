"""State business registries (loader/business_registry.py): entities, their officers, agents and other names, from
states' official free bulk data and open-data APIs, plus every on-demand lookup's results.

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-23
"""

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS biz_entities (
        state text NOT NULL, entity_id text NOT NULL, name text NOT NULL, name_core text, entity_type text,
        status text, formed date, street text, city text, addr_state text, zip text, agent_name text,
        agent_address text, jurisdiction text, source text NOT NULL, loaded timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (state, entity_id));
    CREATE INDEX IF NOT EXISTS biz_entities_core ON biz_entities (name_core);
    CREATE INDEX IF NOT EXISTS biz_entities_core_trgm ON biz_entities USING gin (name_core gin_trgm_ops);
    CREATE TABLE IF NOT EXISTS biz_people (
        state text NOT NULL, entity_id text NOT NULL, name text NOT NULL, name_norm text, role text,
        is_entity boolean NOT NULL DEFAULT false, address text, source text NOT NULL);
    CREATE INDEX IF NOT EXISTS biz_people_entity ON biz_people (state, entity_id);
    CREATE INDEX IF NOT EXISTS biz_people_norm ON biz_people (name_norm);
    CREATE INDEX IF NOT EXISTS biz_people_source ON biz_people (source);
    CREATE TABLE IF NOT EXISTS biz_names (
        state text NOT NULL, entity_id text NOT NULL, name text NOT NULL, name_core text, kind text NOT NULL,
        source text NOT NULL, PRIMARY KEY (state, entity_id, name, kind));
    CREATE INDEX IF NOT EXISTS biz_names_core ON biz_names (name_core);
    CREATE TABLE IF NOT EXISTS biz_links (
        state text NOT NULL, entity_id text NOT NULL, kind text NOT NULL, key text NOT NULL, how text,
        PRIMARY KEY (state, entity_id, kind, key));
    CREATE INDEX IF NOT EXISTS biz_links_key ON biz_links (kind, key);
    CREATE TABLE IF NOT EXISTS biz_lookups (
        query_core text NOT NULL, state text NOT NULL, asked timestamptz NOT NULL DEFAULT now(), found int,
        PRIMARY KEY (query_core, state));
    CREATE TABLE IF NOT EXISTS biz_runs (source text PRIMARY KEY, loaded timestamptz NOT NULL DEFAULT now(),
                                         rows int)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS biz_runs, biz_lookups, biz_links, biz_names, biz_people, biz_entities")
