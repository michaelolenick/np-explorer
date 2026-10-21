"""FEC bulk data: committees, candidates and individual contributions (loader/fec.py).

fec_contributions is partitioned by two-year cycle, so a cycle reloads by truncating its partition. Columns keep
the FEC's meaning; name_norm is app.names.normalize_name(name), zip5 the first five digits of ZIP_CODE.
fec_person_links ties contributions to people already on the site (person_clusters) when the contributor's name
matches and the employer is one of the person's organizations.

Revision ID: 0034
Revises: 0033
Create Date: 2026-10-20
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS fec_committees (
        cycle smallint NOT NULL, cmte_id text NOT NULL, name text, treasurer text, street1 text, street2 text,
        city text, state text, zip text, designation text, cmte_type text, party text, filing_freq text,
        org_type text, connected_org text, cand_id text,
        PRIMARY KEY (cycle, cmte_id));
    CREATE INDEX IF NOT EXISTS fec_committees_id ON fec_committees (cmte_id);
    CREATE TABLE IF NOT EXISTS fec_candidates (
        cycle smallint NOT NULL, cand_id text NOT NULL, name text, party text, election_year smallint,
        office_state text, office text, district text, ici text, status text, pcc text, street1 text,
        street2 text, city text, state text, zip text,
        PRIMARY KEY (cycle, cand_id));
    CREATE INDEX IF NOT EXISTS fec_candidates_id ON fec_candidates (cand_id);
    CREATE TABLE IF NOT EXISTS fec_contributions (
        cycle smallint NOT NULL, sub_id bigint NOT NULL, cmte_id text NOT NULL, amendment text, report_type text,
        pgi text, image_num text, tran_type text, entity_type text, name text, name_norm text, city text,
        state text, zip5 text, employer text, occupation text, tran_date date, amount numeric(14, 2),
        other_id text, tran_id text, file_num bigint, memo_cd text, memo_text text
    ) PARTITION BY LIST (cycle);
    CREATE TABLE IF NOT EXISTS fec_runs (
        id bigserial PRIMARY KEY, started timestamptz NOT NULL DEFAULT now(), finished timestamptz,
        cycle smallint, status text NOT NULL DEFAULT 'running', rows bigint, note text);
    CREATE TABLE IF NOT EXISTS fec_person_links (
        cycle smallint NOT NULL, sub_id bigint NOT NULL, cluster_id bigint NOT NULL, ein text,
        PRIMARY KEY (cycle, sub_id));
    CREATE INDEX IF NOT EXISTS fec_person_links_cluster ON fec_person_links (cluster_id)""")


def downgrade() -> None:
    op.execute("""DROP TABLE IF EXISTS fec_person_links, fec_runs, fec_contributions, fec_candidates,
                  fec_committees""")
