-- Topic index over the 990 filings (owner, 2026-10-28). Build once; every question then runs against the index.
--
-- Prerequisite: research.filing_xml_text, filled by research/text_index/extract_text.py (Part III program
-- descriptions and Schedule O, read from the stored XML; the loader doesn't keep them).
-- Rerun:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/build.sql
--
-- research.filing_text  one row per filing per text field, plus one 'all' row per filing whose tsvector joins every
--                       field (so "A and B in the same filing" works across fields). Full-text tsvector (GIN) and
--                       a pg_trgm index on the text for phrase / substring / regex matches.
-- research.org_text     one row per organization: every distinct text it has filed, all years, with a tsvector per
--                       field and one for everything, for "how many organizations" questions.
-- Both carry ein, NTEE code and major group, state and total revenue (filing_text also tax_year and form), so
-- results can be cut by year, sector, geography and size without joining back.

\set ON_ERROR_STOP 1
SET statement_timeout = '3h';
SET maintenance_work_mem = '4GB';
SET max_parallel_maintenance_workers = 6;
SET work_mem = '512MB';

-- A tsvector for any text: the first 200,000 characters (a tsvector is capped at 1 MB); positions kept so phrase
-- and proximity searches work. Joining tsvectors falls back to the left one if the result would pass the cap.
CREATE OR REPLACE FUNCTION research.tsv(t text) RETURNS tsvector LANGUAGE plpgsql IMMUTABLE PARALLEL UNSAFE AS $$
BEGIN
    RETURN to_tsvector('english', left(t, 200000));
EXCEPTION WHEN program_limit_exceeded THEN
    RETURN strip(to_tsvector('english', left(t, 200000)));
END $$;
CREATE OR REPLACE FUNCTION research.tsv_join(a tsvector, b tsvector) RETURNS tsvector LANGUAGE plpgsql IMMUTABLE
    PARALLEL UNSAFE AS $$
BEGIN
    RETURN coalesce(a, ''::tsvector) || coalesce(b, ''::tsvector);
EXCEPTION WHEN program_limit_exceeded THEN
    RETURN a;
END $$;
DROP AGGREGATE IF EXISTS research.tsv_agg(tsvector);
CREATE AGGREGATE research.tsv_agg(tsvector) (SFUNC = research.tsv_join, STYPE = tsvector, INITCOND = '');

DROP TABLE IF EXISTS research.filing_text, research.org_text CASCADE;
CREATE TABLE research.filing_text (
    filing_id bigint NOT NULL, return_id bigint, ein text NOT NULL, tax_year int, form_type text,
    superseded boolean NOT NULL, field text NOT NULL, text text, tsv tsvector,
    ntee text, ntee_major text, state text, total_revenue bigint);

-- One insert per field, each under the statement timeout
CREATE TEMP VIEW f AS
SELECT f.id, f.object_id, f.ein, f.tax_year, f.form_type, coalesce(f.superseded, false) AS superseded,
       o.ntee, left(o.ntee, 1) AS ntee_major, coalesce(nullif(f.state, ''), o.state) AS state, f.total_revenue,
       f.org_name, f.dba, f.mission
FROM filings f LEFT JOIN organizations o ON o.ein = f.ein;

INSERT INTO research.filing_text
SELECT id, object_id, ein, tax_year, form_type, superseded, 'name', t, research.tsv(t), ntee, ntee_major, state, total_revenue
FROM (SELECT *, concat_ws(' / ', nullif(trim(org_name), ''), nullif(trim(dba), '')) t FROM f) x WHERE t <> '';

INSERT INTO research.filing_text
SELECT id, object_id, ein, tax_year, form_type, superseded, 'mission', t, research.tsv(t), ntee, ntee_major, state, total_revenue
FROM (SELECT *, trim(mission) t FROM f) x WHERE t <> '';

INSERT INTO research.filing_text
SELECT f.id, f.object_id, f.ein, f.tax_year, f.form_type, f.superseded, x.field, x.text, research.tsv(x.text),
       f.ntee, f.ntee_major, f.state, f.total_revenue
FROM research.filing_xml_text x JOIN f ON f.id = x.filing_id;                   -- 'program' and 'schedule_o'

INSERT INTO research.filing_text
SELECT f.id, f.object_id, f.ein, f.tax_year, f.form_type, f.superseded, 'grant_purpose', g.t, research.tsv(g.t),
       f.ntee, f.ntee_major, f.state, f.total_revenue
FROM (SELECT filing_id, string_agg(DISTINCT trim(purpose), E'\n') t FROM grants
      WHERE nullif(trim(purpose), '') IS NOT NULL GROUP BY filing_id) g
JOIN f ON f.id = g.filing_id;

INSERT INTO research.filing_text
SELECT f.id, f.object_id, f.ein, f.tax_year, f.form_type, f.superseded, 'contractor_service', c.t, research.tsv(c.t),
       f.ntee, f.ntee_major, f.state, f.total_revenue
FROM (SELECT filing_id, string_agg(DISTINCT trim(service_description), E'\n') t FROM contractors
      WHERE nullif(trim(service_description), '') IS NOT NULL GROUP BY filing_id) c
JOIN f ON f.id = c.filing_id;

-- 'all': every field of the filing in one tsvector (text left NULL: substring searches use the field rows)
INSERT INTO research.filing_text
SELECT filing_id, min(return_id), min(ein), min(tax_year), min(form_type), bool_or(superseded), 'all', NULL,
       research.tsv_agg(tsv ORDER BY field), min(ntee), min(ntee_major), min(state), min(total_revenue)
FROM research.filing_text GROUP BY filing_id;

CREATE INDEX filing_text_tsv ON research.filing_text USING gin (tsv);
CREATE INDEX filing_text_trgm ON research.filing_text USING gin (text gin_trgm_ops);
CREATE INDEX filing_text_filing ON research.filing_text (filing_id);
CREATE INDEX filing_text_ein ON research.filing_text (ein, tax_year);
ANALYZE research.filing_text;

-- Organizations: distinct texts across all years (superseded returns left out), the latest return's revenue, state
CREATE TABLE research.org_text AS
WITH per_field AS (
    SELECT ein, field, string_agg(DISTINCT text, E'\n') t
    FROM research.filing_text WHERE field <> 'all' AND NOT superseded GROUP BY ein, field
), latest AS (
    SELECT DISTINCT ON (ein) ein, tax_year, total_revenue, state, ntee, ntee_major
    FROM research.filing_text WHERE field = 'all' AND NOT superseded ORDER BY ein, tax_year DESC, filing_id DESC
), span AS (
    SELECT ein, min(tax_year) first_year, max(tax_year) last_year, count(*) n_filings, max(total_revenue) max_revenue
    FROM research.filing_text WHERE field = 'all' AND NOT superseded GROUP BY ein
), wide AS (
    SELECT l.ein, o.name, l.ntee, l.ntee_major, l.state, l.total_revenue AS revenue, s.max_revenue,
           s.first_year, s.last_year, s.n_filings,
           max(p.t) FILTER (WHERE p.field = 'name') AS name_text,
           max(p.t) FILTER (WHERE p.field = 'mission') AS mission_text,
           max(p.t) FILTER (WHERE p.field = 'program') AS program_text,
           max(p.t) FILTER (WHERE p.field = 'schedule_o') AS schedule_o_text,
           max(p.t) FILTER (WHERE p.field = 'grant_purpose') AS grant_purpose_text,
           max(p.t) FILTER (WHERE p.field = 'contractor_service') AS contractor_service_text
    FROM latest l JOIN span s USING (ein) JOIN per_field p USING (ein) LEFT JOIN organizations o ON o.ein = l.ein
    GROUP BY l.ein, o.name, l.ntee, l.ntee_major, l.state, l.total_revenue, s.max_revenue, s.first_year,
             s.last_year, s.n_filings
), v AS (
    SELECT w.*, research.tsv(name_text) tsv_name, research.tsv(mission_text) tsv_mission,
           research.tsv(program_text) tsv_program, research.tsv(schedule_o_text) tsv_schedule_o,
           research.tsv(grant_purpose_text) tsv_grant_purpose,
           research.tsv(contractor_service_text) tsv_contractor_service
    FROM wide w
)
SELECT v.*,
       research.tsv_join(research.tsv_join(research.tsv_join(research.tsv_join(research.tsv_join(
           tsv_name, tsv_mission), tsv_program), tsv_schedule_o), tsv_grant_purpose), tsv_contractor_service) AS tsv,
       concat_ws(E'\n', name_text, mission_text, program_text, schedule_o_text, grant_purpose_text,
                 contractor_service_text) AS text
FROM v;
ALTER TABLE research.org_text ADD PRIMARY KEY (ein);
CREATE INDEX org_text_tsv ON research.org_text USING gin (tsv);
CREATE INDEX org_text_tsv_name ON research.org_text USING gin (tsv_name);
CREATE INDEX org_text_tsv_mission ON research.org_text USING gin (tsv_mission);
CREATE INDEX org_text_tsv_program ON research.org_text USING gin (tsv_program);
CREATE INDEX org_text_tsv_schedule_o ON research.org_text USING gin (tsv_schedule_o);
CREATE INDEX org_text_tsv_grant_purpose ON research.org_text USING gin (tsv_grant_purpose);
CREATE INDEX org_text_tsv_contractor_service ON research.org_text USING gin (tsv_contractor_service);
CREATE INDEX org_text_trgm ON research.org_text USING gin (text gin_trgm_ops);
ANALYZE research.org_text;

-- Labels from the model for meanings words alone can't settle ("space": outer space or office space?), per org
CREATE TABLE IF NOT EXISTS research.topic_labels (
    topic text NOT NULL, ein text NOT NULL, label boolean, codes text, model text,
    labeled_at timestamptz DEFAULT now(), PRIMARY KEY (topic, ein));

\i research/text_index/functions.sql
