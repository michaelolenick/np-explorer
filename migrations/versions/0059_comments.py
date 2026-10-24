"""Anonymous comments on entity pages (app/comments.py).

comments holds no IP address or anything that identifies a commenter (owner, 2026-10-23); its timestamp is kept to
the second so a comment can be matched to the web server's access log if ever needed. Rate limits and bans work on
a salted hash of the IP (the salt changes every month), kept in separate tables: comment_rate (times only, kept a
day), comment_hash_map (which hash posted which comment, for "ban this poster", kept 62 days), comment_posters
(approved count, ban).

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-23
"""

from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS comments (
        id bigserial PRIMARY KEY, entity_type text NOT NULL, entity_id text NOT NULL, entity_name text, page_path text,
        display_name text NOT NULL DEFAULT 'Anonymous', body text NOT NULL,
        created timestamp(0) with time zone NOT NULL DEFAULT date_trunc('second', now()),
        status text NOT NULL CHECK (status IN ('published', 'pending', 'deleted')), label text, reason text,
        reports int NOT NULL DEFAULT 0, edited boolean NOT NULL DEFAULT false, reviewed_at timestamptz);
    CREATE INDEX IF NOT EXISTS comments_entity ON comments (entity_type, entity_id, created DESC);
    CREATE INDEX IF NOT EXISTS comments_queue ON comments (created) WHERE status = 'pending' OR (reports > 0 AND reviewed_at IS NULL);
    CREATE INDEX IF NOT EXISTS comments_recent ON comments (created DESC) WHERE status = 'published';
    CREATE TABLE IF NOT EXISTS comment_rate (hash text NOT NULL, ts timestamptz NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS comment_rate_hash ON comment_rate (hash, ts);
    CREATE TABLE IF NOT EXISTS comment_hash_map (comment_id bigint PRIMARY KEY, hash text NOT NULL,
                                                 created timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS comment_posters (hash text PRIMARY KEY, approved int NOT NULL DEFAULT 0,
                                                banned boolean NOT NULL DEFAULT false, updated timestamptz NOT NULL DEFAULT now())""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comment_posters, comment_hash_map, comment_rate, comments")
