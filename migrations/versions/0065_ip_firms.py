"""Firms derived from USPTO data (loader/ip_firms.py): one row per company (core name and state or country) that
holds patents or owns trademarks, matched to firms FURP already has (state registries, Form D issuers, Form ADV
advisers, nonprofits, SEC filers, lobbying clients) or kept as a USPTO-only firm; firms sharing an address; and the
trademark owners' street address and state or country of organization (owner.csv nationality fields).

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-24
"""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    ALTER TABLE tm_owners ADD COLUMN IF NOT EXISTS street text;
    ALTER TABLE tm_owners ADD COLUMN IF NOT EXISTS org_state text;
    ALTER TABLE tm_owners ADD COLUMN IF NOT EXISTS org_country text;
    CREATE INDEX IF NOT EXISTS pat_assignees_name_core ON pat_assignees (name_core);
    CREATE TABLE IF NOT EXISTS ip_firms (
        firm_id text PRIMARY KEY, name text NOT NULL, name_core text NOT NULL, name_norm text, street text,
        addr_norm text, city text, state text, country text, entity_type text, org_state text, org_country text,
        n_patents int NOT NULL DEFAULT 0, n_marks int NOT NULL DEFAULT 0, n_live_marks int NOT NULL DEFAULT 0,
        assignee_ids text[], owner_keys text[], first_seen date, last_seen date,
        match_kind text, match_key text, match text, confidence text, how text,
        merge_match text, merge_how text, sources text NOT NULL, src_dates text,
        updated timestamptz NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS ip_firms_core ON ip_firms (name_core text_pattern_ops);
    CREATE INDEX IF NOT EXISTS ip_firms_match ON ip_firms (match_kind, match_key);
    CREATE INDEX IF NOT EXISTS ip_firms_addr ON ip_firms (addr_norm) WHERE addr_norm IS NOT NULL;
    CREATE TABLE IF NOT EXISTS ip_firm_related (
        firm_id text NOT NULL, kind text NOT NULL, key text NOT NULL, name text, how text,
        PRIMARY KEY (firm_id, kind, key));
    CREATE TABLE IF NOT EXISTS ip_firm_runs (
        id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), scope text NOT NULL, new int, updated int,
        merged int, uspto_only int)""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS ip_firm_runs, ip_firm_related, ip_firms;
                  DROP INDEX IF EXISTS pat_assignees_name_core;
                  ALTER TABLE tm_owners DROP COLUMN IF EXISTS street, DROP COLUMN IF EXISTS org_state,
                                        DROP COLUMN IF EXISTS org_country""")
