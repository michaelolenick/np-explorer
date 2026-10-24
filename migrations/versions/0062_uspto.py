"""USPTO patents and trademarks (loader/patents.py, loader/trademarks.py, loader/uspto.py): granted patents with
their assignees, inventors and CPC subclasses (PatentsView, PVGPATDIS), patent assignments and security interests
(ECORSEXC), trademark case files with owners and classes (TRCFECO2), trademark assignments (TRASECO); assignee,
inventor and owner links to other records with EXACT or FUZZY and a confidence; the API request tally and runs.

Every data row carries its provenance: src_product (the USPTO bulk product ID) and src_date (that file's release
date). Secondary indexes are built by the loaders after a bulk load (loader/uspto.py indexes()).

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-24
"""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS uspto_runs (
        product text NOT NULL, file text NOT NULL, file_date date, part text NOT NULL DEFAULT '', rows bigint,
        loaded timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (product, file, part));
    CREATE TABLE IF NOT EXISTS uspto_api_usage (
        id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), kind text NOT NULL, product text,
        url text, n int NOT NULL DEFAULT 1);

    CREATE TABLE IF NOT EXISTS pat_patents (
        patent_id text PRIMARY KEY, patent_type text, kind text, granted date, title text, abstract text,
        num_claims int, filed date, application_id text, withdrawn boolean NOT NULL DEFAULT false,
        src_product text NOT NULL, src_file text, src_date date, loaded timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS pat_assignees (
        patent_id text NOT NULL, seq smallint NOT NULL, assignee_id text, name text, name_core text,
        is_person boolean NOT NULL DEFAULT false, assignee_type smallint, city text, state text, country text,
        src_product text NOT NULL, src_date date, PRIMARY KEY (patent_id, seq));
    CREATE TABLE IF NOT EXISTS pat_inventors (
        patent_id text NOT NULL, seq smallint NOT NULL, inventor_id text, first_name text, last_name text,
        name_norm text, city text, state text, country text, src_product text NOT NULL, src_date date,
        PRIMARY KEY (patent_id, seq));
    CREATE TABLE IF NOT EXISTS pat_cpc (
        patent_id text NOT NULL, subclass text NOT NULL, cpc_group text, seq smallint, src_product text NOT NULL,
        src_date date, PRIMARY KEY (patent_id, subclass));
    CREATE TABLE IF NOT EXISTS pat_cpc_titles (
        subclass text PRIMARY KEY, title text, class_title text, src_product text NOT NULL, src_date date);

    CREATE TABLE IF NOT EXISTS pat_assignments (
        rf_id bigint PRIMARY KEY, reel_no int, frame_no int, record_date date, convey_text text, convey_type text,
        is_security boolean NOT NULL DEFAULT false, employer_assign boolean NOT NULL DEFAULT false,
        src_product text NOT NULL, src_date date);
    CREATE TABLE IF NOT EXISTS pat_assignment_parties (
        rf_id bigint NOT NULL, role text NOT NULL, seq smallint NOT NULL, name text, name_core text, exec_date date,
        city text, state text, country text, src_product text NOT NULL, src_date date,
        PRIMARY KEY (rf_id, role, seq));
    CREATE TABLE IF NOT EXISTS pat_assignment_docs (
        rf_id bigint NOT NULL, patent_id text NOT NULL, appno text, appno_date date, title text,
        src_product text NOT NULL, src_date date, PRIMARY KEY (rf_id, patent_id));

    CREATE TABLE IF NOT EXISTS pat_assignee_orgs (
        assignee_id text PRIMARY KEY, name text, name_core text, is_person boolean, assignee_type smallint,
        city text, state text, country text, n_patents int, first_grant date, last_grant date, n_security int,
        src_product text NOT NULL, src_date date);
    CREATE TABLE IF NOT EXISTS pat_inventor_people (
        inventor_id text PRIMARY KEY, name text, name_norm text, n_patents int, states text[], places text,
        first_grant date, last_grant date, top_assignee text, top_assignee_id text, src_product text NOT NULL,
        src_date date);
    CREATE TABLE IF NOT EXISTS pat_uni_stats (
        unitid int PRIMARY KEY, name text, ein text, state text, patents int, research_grants numeric,
        years text, built timestamptz NOT NULL DEFAULT now());

    CREATE TABLE IF NOT EXISTS tm_marks (
        serial_no text PRIMARY KEY, registration_no text, mark text, mark_norm text, filing_date date,
        registration_date date, status_code text, status_date date, abandon_date date, cancel_date date,
        renewal_date date, mark_draw_code text, live boolean, classes text, goods text,
        src_product text NOT NULL, src_date date, loaded timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS tm_owners (
        serial_no text NOT NULL, seq smallint NOT NULL, owner_type text, name text, name_core text, owner_key text,
        entity text, city text, state text, country text, src_product text NOT NULL, src_date date,
        PRIMARY KEY (serial_no, seq, owner_type));
    CREATE TABLE IF NOT EXISTS tm_owner_orgs (
        owner_key text PRIMARY KEY, name text, name_core text, state text, country text, entity text,
        n_marks int, n_live int, first_filed date, last_filed date, src_product text NOT NULL, src_date date);
    CREATE TABLE IF NOT EXISTS tm_assignments (
        rf_id text PRIMARY KEY, reel_no int, frame_no int, record_date date, convey_text text, convey_type text,
        src_product text NOT NULL, src_date date);
    CREATE TABLE IF NOT EXISTS tm_assignment_parties (
        rf_id text NOT NULL, role text NOT NULL, seq smallint NOT NULL, name text, name_core text, exec_date date,
        city text, state text, country text, entity text, src_product text NOT NULL, src_date date,
        PRIMARY KEY (rf_id, role, seq));
    CREATE TABLE IF NOT EXISTS tm_assignment_docs (
        rf_id text NOT NULL, serial_no text NOT NULL, registration_no text, src_product text NOT NULL, src_date date,
        PRIMARY KEY (rf_id, serial_no));

    CREATE TABLE IF NOT EXISTS ip_links (
        src_kind text NOT NULL, src_key text NOT NULL, target_kind text NOT NULL, target_key text NOT NULL,
        match text NOT NULL, confidence text NOT NULL, how text, built timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (src_kind, src_key, target_kind, target_key));
    CREATE INDEX IF NOT EXISTS ip_links_target ON ip_links (target_kind, target_key)""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS ip_links, tm_assignment_docs, tm_assignment_parties, tm_assignments,
                  tm_owner_orgs, tm_owners, tm_marks, pat_uni_stats, pat_inventor_people, pat_assignee_orgs,
                  pat_assignment_docs, pat_assignment_parties, pat_assignments, pat_cpc_titles, pat_cpc,
                  pat_inventors, pat_assignees, pat_patents, uspto_api_usage, uspto_runs""")
