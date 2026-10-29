"""Accounts (Google sign-in and email magic links), server-side sessions, and the Deep Queries log (owner, 2026-10-29).

users: one row per email; name asked at signup; two email opt-ins (unchecked by default), each with the time it was
last changed. login_tokens: one-time magic links (sha256 of the token only), 15 minutes, single use. user_sessions:
sha256 of the session cookie's token. deep_queries: every deep query, its plan and estimate, what it actually used
(tokens, dollars, seconds) and who ran it.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-29
"""

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id bigserial PRIMARY KEY,
        email text NOT NULL UNIQUE,
        name text,
        auth_method text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        last_login timestamptz,
        status text NOT NULL DEFAULT 'new',
        daily_blast boolean NOT NULL DEFAULT false,
        daily_blast_at timestamptz,
        newsletter boolean NOT NULL DEFAULT false,
        newsletter_at timestamptz);
    CREATE TABLE IF NOT EXISTS login_tokens (
        token_hash text PRIMARY KEY,
        email text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        used_at timestamptz,
        ip text);
    CREATE INDEX IF NOT EXISTS login_tokens_email ON login_tokens (email, created_at);
    CREATE TABLE IF NOT EXISTS user_sessions (
        token_hash text PRIMARY KEY,
        user_id bigint NOT NULL REFERENCES users (id),
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        last_seen timestamptz NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS user_sessions_user ON user_sessions (user_id);
    CREATE TABLE IF NOT EXISTS deep_queries (
        id bigserial PRIMARY KEY,
        user_id bigint NOT NULL REFERENCES users (id),
        question text NOT NULL,
        plan jsonb,
        estimate jsonb,
        status text NOT NULL DEFAULT 'estimated',
        created_at timestamptz NOT NULL DEFAULT now(),
        confirmed_at timestamptz,
        finished_at timestamptz,
        runtime_seconds numeric,
        input_tokens bigint NOT NULL DEFAULT 0,
        output_tokens bigint NOT NULL DEFAULT 0,
        cost_usd numeric NOT NULL DEFAULT 0,
        result jsonb,
        error text);
    CREATE INDEX IF NOT EXISTS deep_queries_user ON deep_queries (user_id, created_at)""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deep_queries, user_sessions, login_tokens, users")
