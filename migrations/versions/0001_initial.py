"""Initial schema: organizations, filings, people, contractors, clusters, loader bookkeeping.

Revision ID: 0001
Revises:
Create Date: 2026-10-16
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE organizations (
        ein                     text PRIMARY KEY,
        name                    text,
        name_norm               text,
        dba                     text,
        street                  text,
        city                    text,
        state                   text,
        zip                     text,
        website                 text,
        ntee                    text,
        subsection              text,
        ruling_year             integer,
        in_bmf                  boolean NOT NULL DEFAULT false,
        latest_filing_year      integer,
        latest_total_revenue    bigint,
        latest_total_expenses   bigint,
        latest_total_assets     bigint,
        latest_num_employees    integer,
        latest_num_volunteers   integer,
        name_tsv                tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(name_norm, ''))) STORED
    );
    CREATE INDEX organizations_name_tsv ON organizations USING gin (name_tsv);
    CREATE INDEX organizations_state ON organizations (state);

    CREATE TABLE filings (
        id                      bigserial PRIMARY KEY,
        ein                     text NOT NULL,
        object_id               bigint NOT NULL UNIQUE,
        form_type               text NOT NULL,
        return_version          text,
        tax_year                integer,
        tax_period_begin        date,
        tax_period_end          date,
        filed_date              date,
        org_name                text,
        dba                     text,
        street                  text,
        city                    text,
        state                   text,
        zip                     text,
        website                 text,
        total_revenue           bigint,
        total_expenses          bigint,
        total_assets_eoy        bigint,
        total_liabilities_eoy   bigint,
        net_assets_eoy          bigint,
        contributions           bigint,
        program_service_revenue bigint,
        officer_comp_total      bigint,
        num_employees           integer,
        num_volunteers          integer,
        mission                 text,
        amended                 boolean NOT NULL DEFAULT false,
        superseded              boolean NOT NULL DEFAULT false,
        xml_path                text,
        source_file             text
    );
    CREATE INDEX filings_ein ON filings (ein);
    CREATE INDEX filings_tax_year ON filings (tax_year);

    CREATE TABLE people (
        id                  bigserial PRIMARY KEY,
        filing_id           bigint NOT NULL,
        ein                 text NOT NULL,
        tax_year            integer,
        source              text,
        name_raw            text NOT NULL,
        name_norm           text NOT NULL,
        title               text,
        avg_hours           numeric,
        avg_hours_related   numeric,
        is_officer          boolean NOT NULL DEFAULT false,
        is_director         boolean NOT NULL DEFAULT false,
        is_trustee          boolean NOT NULL DEFAULT false,
        is_key_employee     boolean NOT NULL DEFAULT false,
        is_highest_comp     boolean NOT NULL DEFAULT false,
        is_former           boolean NOT NULL DEFAULT false,
        comp_org            bigint,
        comp_related        bigint,
        other_comp          bigint,
        street              text,
        city                text,
        state               text,
        zip                 text
    );
    CREATE INDEX people_filing_id ON people (filing_id);
    CREATE INDEX people_ein ON people (ein);
    CREATE INDEX people_tax_year ON people (tax_year);
    CREATE INDEX people_name_norm ON people (name_norm);

    -- Schedule J Part II rows, matched to a people row on the same filing when the names agree.
    CREATE TABLE schedule_j (
        id                  bigserial PRIMARY KEY,
        filing_id           bigint NOT NULL,
        person_id           bigint,
        ein                 text NOT NULL,
        tax_year            integer,
        name_raw            text NOT NULL,
        name_norm           text NOT NULL,
        title               text,
        base_org            bigint, base_related        bigint,
        bonus_org           bigint, bonus_related       bigint,
        other_org           bigint, other_related       bigint,
        deferred_org        bigint, deferred_related    bigint,
        nontaxable_org      bigint, nontaxable_related  bigint,
        total_org           bigint, total_related       bigint
    );
    CREATE INDEX schedule_j_filing_id ON schedule_j (filing_id);
    CREATE INDEX schedule_j_person_id ON schedule_j (person_id);

    CREATE TABLE contractors (
        id                  bigserial PRIMARY KEY,
        filing_id           bigint NOT NULL,
        ein                 text NOT NULL,
        tax_year            integer,
        source              text,
        name_raw            text NOT NULL,
        name_norm           text NOT NULL,
        street              text,
        city                text,
        state               text,
        zip                 text,
        service_description text,
        compensation        bigint,
        website             text,
        name_tsv            tsvector GENERATED ALWAYS AS (to_tsvector('simple', name_norm)) STORED
    );
    CREATE INDEX contractors_filing_id ON contractors (filing_id);
    CREATE INDEX contractors_ein ON contractors (ein);
    CREATE INDEX contractors_tax_year ON contractors (tax_year);
    CREATE INDEX contractors_name_norm ON contractors (name_norm);
    CREATE INDEX contractors_name_tsv ON contractors USING gin (name_tsv);

    -- Schedule R related organizations: clustering evidence.
    CREATE TABLE related_orgs (
        filing_id     bigint NOT NULL,
        ein           text NOT NULL,
        related_ein   text NOT NULL,
        related_name  text
    );
    CREATE INDEX related_orgs_ein ON related_orgs (ein);
    CREATE INDEX related_orgs_filing_id ON related_orgs (filing_id);

    -- A cluster's id is the smallest people.id in it, so ids stay stable as
    -- later years are added; a merged-away id redirects via person_cluster_members.
    CREATE TABLE person_clusters (
        id             bigint PRIMARY KEY,
        display_name   text NOT NULL,
        name_norm      text NOT NULL,
        n_filings      integer NOT NULL,
        n_orgs         integer NOT NULL,
        first_year     integer,
        last_year      integer,
        max_comp       bigint,
        states         text[],
        orgs           text[],
        latest_title   text,
        evidence       jsonb,
        name_tsv       tsvector GENERATED ALWAYS AS (to_tsvector('simple', name_norm)) STORED
    );
    CREATE INDEX person_clusters_name_tsv ON person_clusters USING gin (name_tsv);
    CREATE INDEX person_clusters_name_norm ON person_clusters (name_norm);

    CREATE TABLE person_cluster_members (
        person_id    bigint PRIMARY KEY,
        cluster_id   bigint NOT NULL,
        evidence     jsonb
    );
    CREATE INDEX person_cluster_members_cluster_id ON person_cluster_members (cluster_id);

    CREATE TABLE loader_progress (
        file       text PRIMARY KEY,
        kind       text,
        year       integer,
        status     text NOT NULL,
        rows       bigint,
        started    timestamptz,
        finished   timestamptz,
        error      text
    );

    -- Every object_id the loader has handled (loaded, skipped as a non-990 form, or failed).
    CREATE TABLE loaded_objects (
        object_id  bigint PRIMARY KEY,
        file       text NOT NULL,
        status     text NOT NULL
    );
    """)


def downgrade() -> None:
    op.execute("""
    DROP TABLE IF EXISTS loaded_objects, loader_progress, person_cluster_members, person_clusters,
        related_orgs, contractors, schedule_j, people, filings, organizations;
    """)
