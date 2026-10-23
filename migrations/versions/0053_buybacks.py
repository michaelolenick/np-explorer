"""Share buybacks (loader/buybacks.py): buyback spending and net income from the SEC's Financial Statement Data
Sets, monthly issuer repurchase tables from 10-Q and 10-K filings, 8-K buyback announcements, 10b5-1 plan flags on
Form 4 filings, links from companies to lobbying clients and PACs, and insider sales made while the company was
buying back stock.

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-22
"""

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS sec_fin_subs (
        adsh text PRIMARY KEY, cik text NOT NULL, name text, form text, period date, fy int, fp text, filed date,
        instance text, quarter text);
    CREATE INDEX IF NOT EXISTS sec_fin_subs_cik ON sec_fin_subs (cik, filed);
    CREATE TABLE IF NOT EXISTS sec_fin_facts (
        adsh text NOT NULL, tag text NOT NULL, ddate date NOT NULL, qtrs int NOT NULL, value numeric NOT NULL,
        PRIMARY KEY (adsh, tag, ddate, qtrs));
    CREATE TABLE IF NOT EXISTS sec_buybacks (
        cik text NOT NULL, name text, period_end date NOT NULL, qtrs int NOT NULL, buybacks numeric,
        net_income numeric, adsh text, filed date, form text, derived boolean NOT NULL DEFAULT false,
        PRIMARY KEY (cik, period_end, qtrs));
    CREATE TABLE IF NOT EXISTS sec_buyback_auth (
        cik text NOT NULL, ddate date NOT NULL, authorized numeric, remaining numeric, adsh text, filed date,
        PRIMARY KEY (cik, ddate));
    CREATE TABLE IF NOT EXISTS sec_buyback_months (
        adsh text NOT NULL, row_no int NOT NULL, cik text NOT NULL, label text, period_start date, period_end date,
        shares numeric, avg_price numeric, plan_shares numeric, remaining_value numeric, remaining_shares numeric,
        is_total boolean NOT NULL DEFAULT false, filed date, url text, PRIMARY KEY (adsh, row_no));
    CREATE INDEX IF NOT EXISTS sec_buyback_months_cik ON sec_buyback_months (cik, period_end);
    CREATE TABLE IF NOT EXISTS sec_buyback_docs (adsh text PRIMARY KEY, fetched timestamptz NOT NULL DEFAULT now(),
                                                 status text, rows int);
    CREATE TABLE IF NOT EXISTS sec_buyback_announcements (
        accession text NOT NULL, cik text NOT NULL, filed date NOT NULL, items text, document text,
        PRIMARY KEY (accession, cik));
    CREATE INDEX IF NOT EXISTS sec_buyback_announcements_cik ON sec_buyback_announcements (cik, filed);
    CREATE TABLE IF NOT EXISTS sec_buyback_ann_runs (cik text PRIMARY KEY, checked timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS sec_insider_plans (
        accession text PRIMARY KEY, aff10b5one boolean, footnote boolean NOT NULL DEFAULT false);
    CREATE TABLE IF NOT EXISTS sec_company_links (
        cik text NOT NULL, kind text NOT NULL, key text NOT NULL, name text, PRIMARY KEY (cik, kind, key));
    CREATE TABLE IF NOT EXISTS sec_buyback_sales (
        accession text NOT NULL, sk bigint NOT NULL, issuer_cik text NOT NULL, owner_cik text, owner_name text,
        trans_date date NOT NULL, shares numeric, price numeric, value numeric, plan boolean NOT NULL DEFAULT false,
        quarter_end date, quarter_buybacks numeric, heavy boolean NOT NULL DEFAULT false,
        ann_accession text, ann_filed date, days_after int, PRIMARY KEY (accession, sk));
    CREATE INDEX IF NOT EXISTS sec_buyback_sales_issuer ON sec_buyback_sales (issuer_cik, trans_date);
    CREATE INDEX IF NOT EXISTS sec_buyback_sales_owner ON sec_buyback_sales (owner_cik);
    CREATE TABLE IF NOT EXISTS sec_buyback_runs (file text PRIMARY KEY, loaded timestamptz NOT NULL DEFAULT now(),
                                                 rows int)""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS sec_buyback_runs, sec_buyback_sales, sec_company_links, sec_insider_plans,
                  sec_buyback_ann_runs, sec_buyback_announcements, sec_buyback_docs, sec_buyback_months,
                  sec_buyback_auth, sec_buybacks, sec_fin_facts, sec_fin_subs""")
