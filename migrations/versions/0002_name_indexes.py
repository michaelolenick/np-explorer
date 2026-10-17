"""Name indexing: Soundex codes, first/last name keys, prefix (text_pattern_ops) indexes.

Soundex gives misspelling-tolerant matching ("olenik" finds "olenick") without
any extension, so it works on Azure even before pg_trgm is allow-listed.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Soundex of one word: first letter plus three digits. H and W don't separate
# letters with the same code; vowels do.
NP_SOUNDEX = r"""
CREATE OR REPLACE FUNCTION np_soundex(w text) RETURNS text
LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE AS $$
DECLARE
    s text := upper(regexp_replace(w, '[^A-Za-z]', '', 'g'));
    out text;
    prev text;
    code text;
    i int;
BEGIN
    IF s = '' THEN
        RETURN '';
    END IF;
    out := substr(s, 1, 1);
    prev := translate(out, 'AEIOUYHWBFPVCGJKQSXZDTLMNR', '00000099111122222222334556');
    FOR i IN 2..length(s) LOOP
        code := translate(substr(s, i, 1), 'AEIOUYHWBFPVCGJKQSXZDTLMNR', '00000099111122222222334556');
        CONTINUE WHEN code = '9';
        IF code <> '0' AND code <> prev THEN
            out := out || code;
            EXIT WHEN length(out) = 4;
        END IF;
        prev := code;
    END LOOP;
    RETURN rpad(out, 4, '0');
END
$$;

-- Soundex of every word of two or more letters ("john a smith" -> "j500 s530").
CREATE OR REPLACE FUNCTION np_soundex_tokens(n text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT coalesce(string_agg(np_soundex(t), ' ' ORDER BY ord), '')
    FROM unnest(string_to_array(n, ' ')) WITH ORDINALITY AS u(t, ord)
    WHERE length(t) > 1
$$;

-- Last name of a normalized person name, ignoring a trailing suffix.
CREATE OR REPLACE FUNCTION np_last_name(n text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT CASE WHEN array_length(t, 1) > 1 AND t[array_length(t, 1)] IN ('jr','sr','ii','iii','iv','v')
                THEN t[array_length(t, 1) - 1] ELSE t[array_length(t, 1)] END
    FROM (SELECT string_to_array(n, ' ') AS t) x
$$;

CREATE OR REPLACE FUNCTION np_first_name(n text) RETURNS text
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT split_part(n, ' ', 1)
$$;
"""


def upgrade() -> None:
    op.execute(NP_SOUNDEX)
    op.execute("""
    -- person_clusters is rebuilt by the loader's cluster step, which adds the same
    -- columns and indexes to each new table (loader/cluster.py, CLUSTER_INDEXES).
    ALTER TABLE person_clusters
        ADD COLUMN first_name text GENERATED ALWAYS AS (np_first_name(name_norm)) STORED,
        ADD COLUMN last_name text GENERATED ALWAYS AS (np_last_name(name_norm)) STORED,
        ADD COLUMN sound_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', np_soundex_tokens(name_norm))) STORED;
    CREATE INDEX person_clusters_name_prefix ON person_clusters (name_norm text_pattern_ops);
    CREATE INDEX person_clusters_last_first ON person_clusters (last_name, first_name);
    CREATE INDEX person_clusters_first ON person_clusters (first_name);
    CREATE INDEX person_clusters_sound ON person_clusters USING gin (sound_tsv);
    CREATE INDEX person_clusters_states ON person_clusters USING gin (states);
    CREATE INDEX person_clusters_years ON person_clusters (first_year, last_year);
    CREATE INDEX person_clusters_max_comp ON person_clusters (max_comp);
    CREATE INDEX person_clusters_n_filings ON person_clusters (n_filings DESC);

    CREATE INDEX people_name_prefix ON people (name_norm text_pattern_ops);
    CREATE INDEX people_ein_name ON people (ein, name_norm);
    CREATE INDEX people_last_name ON people (np_last_name(name_norm));
    CREATE INDEX people_title_lower ON people (lower(title) text_pattern_ops);

    CREATE INDEX schedule_j_name_norm ON schedule_j (name_norm);

    CREATE INDEX contractors_name_prefix ON contractors (name_norm text_pattern_ops);
    ALTER TABLE contractors
        ADD COLUMN sound_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', np_soundex_tokens(name_norm))) STORED;
    CREATE INDEX contractors_sound ON contractors USING gin (sound_tsv);

    CREATE INDEX organizations_name_norm ON organizations (name_norm);
    CREATE INDEX organizations_name_prefix ON organizations (name_norm text_pattern_ops);
    ALTER TABLE organizations
        ADD COLUMN sound_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', np_soundex_tokens(coalesce(name_norm, '')))) STORED;
    CREATE INDEX organizations_sound ON organizations USING gin (sound_tsv);

    CREATE INDEX filings_org_name_lower ON filings (lower(org_name) text_pattern_ops);
    """)


def downgrade() -> None:
    op.execute("""
    DROP INDEX IF EXISTS person_clusters_name_prefix, person_clusters_last_first, person_clusters_first,
        person_clusters_sound, person_clusters_states, person_clusters_years, person_clusters_max_comp,
        person_clusters_n_filings, people_name_prefix, people_ein_name, people_last_name, people_title_lower,
        schedule_j_name_norm, contractors_name_prefix, contractors_sound, organizations_name_norm,
        organizations_name_prefix, organizations_sound, filings_org_name_lower;
    ALTER TABLE person_clusters DROP COLUMN IF EXISTS first_name, DROP COLUMN IF EXISTS last_name,
        DROP COLUMN IF EXISTS sound_tsv;
    ALTER TABLE contractors DROP COLUMN IF EXISTS sound_tsv;
    ALTER TABLE organizations DROP COLUMN IF EXISTS sound_tsv;
    DROP FUNCTION IF EXISTS np_soundex_tokens(text), np_soundex(text), np_last_name(text), np_first_name(text);
    """)
