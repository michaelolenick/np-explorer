"""Food recalls (loader/recalls.py): FDA food enforcement reports, the recalling firms, and links from firms to the
nonprofits, lobbying clients, SEC issuers, federal award recipients and political committees on the site.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-22
"""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS food_recalls (
        source text NOT NULL, recall_number text NOT NULL, event_id text, status text, classification text,
        product_type text, recalling_firm text NOT NULL, firm_id text NOT NULL, address text, city text, state text,
        country text, postal_code text, product_description text, product_quantity text, reason_for_recall text,
        distribution_pattern text, voluntary_mandated text, initial_firm_notification text, code_info text,
        recall_initiation_date date, center_classification_date date, report_date date, termination_date date,
        source_url text, data_url text, loaded timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (source, recall_number));
    CREATE INDEX IF NOT EXISTS food_recalls_firm ON food_recalls (firm_id);
    CREATE INDEX IF NOT EXISTS food_recalls_started ON food_recalls (recall_initiation_date);
    CREATE TABLE IF NOT EXISTS food_recall_firms (
        firm_id text PRIMARY KEY, firm_key text NOT NULL, name text NOT NULL, city text, state text,
        recalls int NOT NULL, events int NOT NULL, class1 int NOT NULL, class2 int NOT NULL, class3 int NOT NULL,
        first_recall date, last_recall date,
        fed_contracts numeric, fed_food_contracts numeric, lobby_spent numeric, has_pac boolean NOT NULL DEFAULT false);
    CREATE TABLE IF NOT EXISTS food_recall_links (
        firm_id text NOT NULL, kind text NOT NULL, key text NOT NULL, name text, PRIMARY KEY (firm_id, kind, key));
    CREATE INDEX IF NOT EXISTS food_recall_links_key ON food_recall_links (kind, key)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS food_recall_links, food_recall_firms, food_recalls")
