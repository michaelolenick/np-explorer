"""Usage stats: page requests and actions, searches, anonymous visitors, daily aggregates,
and the history of daily reports.

Written only on production (APP_ENV=prod) by app/analytics.py; read by app/report.py.
No IP addresses are stored. Raw events and searches are deleted after
USAGE_RETENTION_DAYS (90) by the report job; daily_stats and report_history stay.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-17
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS visitors (
        id          text PRIMARY KEY,            -- random id from the first-party cookie
        first_seen  timestamptz NOT NULL,
        last_seen   timestamptz NOT NULL,
        requests    integer NOT NULL DEFAULT 0
    )""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id          bigserial PRIMARY KEY,
        ts          timestamptz NOT NULL,
        visitor_id  text,                        -- null for crawlers and automated clients
        name        text NOT NULL,               -- page, popup, year_tab, export, share_card, copy_table, ...
        route       text NOT NULL,               -- route type: home, search, person, org, boards, ...
        path        text NOT NULL,               -- path only, never the query string
        status      smallint,
        ms          real,
        referrer    text,                        -- referring domain (other sites only)
        ua_class    text NOT NULL,               -- human, googlebot, bingbot, crawler, scraper
        country     text,                        -- ISO code from a local IP database; the IP isn't kept
        meta        jsonb
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS events_ts ON events (ts)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS searches (
        id          bigserial PRIMARY KEY,
        ts          timestamptz NOT NULL,
        visitor_id  text,
        ua_class    text NOT NULL,
        q           text NOT NULL,
        search_type text NOT NULL,               -- plain, name, nl, edit, firm, daf, boards
        nl_intent   text,
        results     integer,
        zero        boolean,
        nl_fallback boolean NOT NULL DEFAULT false,
        fallback_reason text,
        ms          real
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS searches_ts ON searches (ts)")
    op.execute("""
    CREATE TABLE IF NOT EXISTS daily_stats (
        day         date PRIMARY KEY,            -- America/Chicago
        metrics     jsonb NOT NULL,
        computed_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""
    CREATE TABLE IF NOT EXISTS report_history (
        day             date PRIMARY KEY,
        created_at      timestamptz NOT NULL DEFAULT now(),
        status          text NOT NULL,           -- sent, send_failed, numbers_only
        metrics         jsonb NOT NULL,
        recommendations text,
        narrative       text
    )""")


def downgrade() -> None:
    for t in ("report_history", "daily_stats", "searches", "events", "visitors"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
