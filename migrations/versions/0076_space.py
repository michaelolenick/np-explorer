"""The FURP space: named people, their folders, and the files in them (owner, 2026-11-11).

space_people: everyone who may log in to a space. One folder each; email NULL until the owner adds it (the person
then cannot log in yet). is_super: sees the whole tree, uploads anywhere, adds and removes people.
space_folders: one per person (a super admin may create more); visibility is the default for new uploads and, when
public, exposes a listing page of the folder's public files at /p/f/<token>.
space_files: one row per upload (never deleted: removed_at hides a row). Each file is private (owner and super admins
only, FURP's own analysis does not read it), furp (the default: FURP may read it internally, never exposes it) or
public (a stable URL at /p/<public_token>/<filename> that needs no login). Changing a public item back clears the
token, so the old URL stops working.

Revision ID: 0076
Revises: 0075
Create Date: 2026-11-11
"""

from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS space_people (
        id bigserial PRIMARY KEY,
        email text UNIQUE,
        name text NOT NULL,
        is_super boolean NOT NULL DEFAULT false,
        added_by text,
        added_at timestamptz NOT NULL DEFAULT now(),
        removed_at timestamptz,
        removed_by text);
    CREATE TABLE IF NOT EXISTS space_folders (
        id bigserial PRIMARY KEY,
        name text NOT NULL UNIQUE,
        person_id bigint REFERENCES space_people (id),
        visibility text NOT NULL DEFAULT 'furp' CHECK (visibility IN ('private', 'furp', 'public')),
        public_token text UNIQUE,
        public_at timestamptz,
        created_by text,
        created_at timestamptz NOT NULL DEFAULT now());
    CREATE INDEX IF NOT EXISTS space_folders_person ON space_folders (person_id);
    CREATE TABLE IF NOT EXISTS space_files (
        id bigserial PRIMARY KEY,
        folder_id bigint NOT NULL REFERENCES space_folders (id),
        owner_id bigint REFERENCES space_people (id),
        filename text NOT NULL,
        blob_path text NOT NULL UNIQUE,
        visibility text NOT NULL DEFAULT 'furp' CHECK (visibility IN ('private', 'furp', 'public')),
        public_token text UNIQUE,
        public_at timestamptz,
        uploader text NOT NULL,
        uploaded_at timestamptz NOT NULL DEFAULT now(),
        size bigint NOT NULL,
        content_type text NOT NULL,
        sha256 text,
        removed_at timestamptz,
        removed_by text);
    CREATE INDEX IF NOT EXISTS space_files_folder ON space_files (folder_id, uploaded_at);
    CREATE TABLE IF NOT EXISTS space_log (
        id bigserial PRIMARY KEY,
        at timestamptz NOT NULL DEFAULT now(),
        who text,
        action text NOT NULL,
        folder text,
        file_id bigint,
        detail text);
    INSERT INTO space_people (email, name, is_super, added_by) VALUES ('mfolenick@gmail.com', 'Michael Olenick', true, 'migration 0076')
        ON CONFLICT (email) DO UPDATE SET is_super = true, removed_at = NULL;
    INSERT INTO space_people (email, name, is_super, added_by)
        SELECT NULL, 'Mike Leidig', false, 'migration 0076' WHERE NOT EXISTS (SELECT 1 FROM space_people WHERE name = 'Mike Leidig');
    INSERT INTO space_folders (name, person_id, created_by)
        SELECT 'Olenick', id, 'migration 0076' FROM space_people WHERE email = 'mfolenick@gmail.com' ON CONFLICT (name) DO NOTHING;
    INSERT INTO space_folders (name, person_id, created_by)
        SELECT 'Leidig', id, 'migration 0076' FROM space_people WHERE name = 'Mike Leidig' ON CONFLICT (name) DO NOTHING""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS space_log, space_files, space_folders, space_people")
