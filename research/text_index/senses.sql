-- Senses of ambiguous terms: counts, and the original questions asked again with the cleaned terms
-- (owner, 2026-10-28). Needs: build.sql, questions.sql, classify.py space, senses.py sync / rules / label.
-- Rerun:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/senses.sql

\set ON_ERROR_STOP 1
SET statement_timeout = '30min';
SET work_mem = '512MB';

-- Every org's senses per term: the phrases' (rules) and the model's; "space" from classify.py
CREATE OR REPLACE VIEW research.org_codes AS
SELECT topic, ein, coalesce(rule_codes, '') || coalesce(nullif(model_codes, '-'), '') AS codes,
       rule_codes, nullif(model_codes, '-') AS model_codes, in_name, in_mission, in_program, in_schedule_o,
       in_grant_purpose, in_contractor_service
FROM research.org_senses
UNION ALL
SELECT 'space', s.ein, CASE WHEN s.has_term THEN 'O' ELSE '' END || coalesce(s.codes, ''),
       CASE WHEN s.has_term THEN 'O' END, s.codes, NULL, NULL, NULL, NULL, NULL, NULL
FROM research.space_senses s;

-- research.topic_count / topic_breakdown / topic_match now take 'topic:sense' (functions.sql)
\i research/text_index/functions.sql

-- Exact phrase counts, no model (filings, orgs, median revenue of the orgs)
DROP TABLE IF EXISTS research.sense_phrase_counts;
CREATE TABLE research.sense_phrase_counts AS
SELECT p.topic, p.i, p.codes, p.label, c.n AS filings, c.n_orgs AS orgs, c.median_org_revenue
FROM research.sense_phrases p, LATERAL research.topic_count(p.tsq) c
WHERE p.tsq IS NOT NULL;

-- Per term and sense: orgs (from phrases, from the model, either), their filings that use the term, median revenue
DROP TABLE IF EXISTS research.sense_counts;
CREATE TABLE research.sense_counts AS
WITH t AS (SELECT DISTINCT topic, tsq FROM research.sense_defs),
     o AS (SELECT oc.topic, d.code, d.sense, oc.ein,
                  strpos(coalesce(oc.rule_codes, ''), d.code) > 0 AS by_rule,
                  strpos(coalesce(oc.model_codes, ''), d.code) > 0 AS by_model
           FROM research.org_codes oc JOIN research.sense_defs d ON d.topic = oc.topic
           WHERE strpos(oc.codes, d.code) > 0),
     f AS (SELECT o.topic, o.code, count(DISTINCT ft.filing_id) AS filings
           FROM o JOIN t USING (topic)
           JOIN research.filing_text ft ON ft.ein = o.ein AND ft.field = 'all' AND NOT ft.superseded
                                       AND ft.tsv @@ to_tsquery('english', t.tsq)
           GROUP BY 1, 2)
SELECT o.topic, o.code, o.sense, count(*) AS orgs, count(*) FILTER (WHERE o.by_rule) AS orgs_by_phrase,
       count(*) FILTER (WHERE o.by_model) AS orgs_by_model, f.filings,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY ot.revenue) AS median_org_revenue
FROM o LEFT JOIN research.org_text ot USING (ein) LEFT JOIN f USING (topic, code)
GROUP BY o.topic, o.code, o.sense, f.filings;

-- Per term: where it appears (only in the name, only in grant purposes, in the mission, ...)
DROP TABLE IF EXISTS research.sense_fields;
CREATE TABLE research.sense_fields AS
SELECT topic, count(*) AS orgs,
       count(*) FILTER (WHERE in_name AND NOT (in_mission OR in_program OR in_schedule_o OR in_grant_purpose
                                               OR in_contractor_service)) AS name_only,
       count(*) FILTER (WHERE in_grant_purpose AND NOT (in_name OR in_mission OR in_program OR in_schedule_o
                                                        OR in_contractor_service)) AS grant_only,
       count(*) FILTER (WHERE in_mission) AS in_mission, count(*) FILTER (WHERE in_program) AS in_program,
       count(*) FILTER (WHERE in_schedule_o) AS in_schedule_o, count(*) FILTER (WHERE in_grant_purpose) AS in_grant,
       count(*) FILTER (WHERE n_ambiguous > 0) AS sent_to_model,
       count(*) FILTER (WHERE n_ambiguous > 0 AND model_codes IS NULL) AS not_labeled
FROM research.org_senses GROUP BY topic;

-- Women: the same senses, mission mentions vs grant-purpose mentions
DROP TABLE IF EXISTS research.sense_women_fields;
CREATE TABLE research.sense_women_fields AS
SELECT d.code, d.sense,
       count(*) FILTER (WHERE s.in_mission) AS orgs_mission,
       count(*) FILTER (WHERE s.in_grant_purpose) AS orgs_grant_purpose,
       count(*) FILTER (WHERE s.in_mission AND NOT s.in_grant_purpose) AS mission_not_grant,
       count(*) FILTER (WHERE s.in_grant_purpose AND NOT s.in_mission) AS grant_not_mission
FROM research.org_senses s JOIN research.org_codes oc USING (topic, ein)
JOIN research.sense_defs d ON d.topic = s.topic AND strpos(oc.codes, d.code) > 0
WHERE s.topic = 'women' GROUP BY d.code, d.sense;

-- ---------------------------------------------------------------- the questions, cleaned
-- "mentions women / men" = the women / men senses issues (I) or incidental (C): a real mention, not a name.
CREATE OR REPLACE VIEW research.sense_orgs AS
SELECT ein,
       bool_or(topic = 'space' AND codes LIKE '%O%') AS outer_space,
       bool_or(topic = 'women' AND codes ~ '[IC]') AS mentions_women,
       bool_or(topic = 'women' AND codes LIKE '%I%') AS womens_issues,
       bool_or(topic = 'men' AND codes ~ '[IC]') AS mentions_men,
       bool_or(topic = 'men' AND codes LIKE '%I%') AS mens_issues,
       bool_or(topic = 'girls_boys' AND codes LIKE '%G%') AS girls_programs,
       bool_or(topic IN ('domestic', 'violence', 'abuse', 'shelter', 'survivor') AND codes LIKE '%D%')
           AS domestic_violence,
       bool_or(topic = 'science' AND codes LIKE '%E%') AS science_stem
FROM research.org_codes GROUP BY ein;

DROP TABLE IF EXISTS research.clean_questions;
CREATE TABLE research.clean_questions AS
WITH s AS (SELECT s.*, o.revenue, coalesce(p.top_pay, 0) AS top_pay
           FROM research.sense_orgs s JOIN research.org_text o USING (ein)
           LEFT JOIN org_profile p USING (ein)),
q AS (
    SELECT 1 AS i, 'outer space' AS question, ein, revenue, top_pay FROM s WHERE outer_space
    UNION ALL SELECT 2, 'outer space AND mentions women (not just a name)', ein, revenue, top_pay FROM s
              WHERE outer_space AND mentions_women
    UNION ALL SELECT 3, 'outer space AND women''s issues', ein, revenue, top_pay FROM s
              WHERE outer_space AND womens_issues
    UNION ALL SELECT 4, 'women''s issues', ein, revenue, top_pay FROM s WHERE womens_issues
    UNION ALL SELECT 5, 'men''s issues', ein, revenue, top_pay FROM s WHERE mens_issues
    UNION ALL SELECT 6, 'both women''s and men''s issues', ein, revenue, top_pay FROM s WHERE womens_issues AND mens_issues
    UNION ALL SELECT 7, 'domestic violence (any term''s DV sense)', ein, revenue, top_pay FROM s WHERE domestic_violence
    UNION ALL SELECT 8, 'DV: mentions women', ein, revenue, top_pay FROM s WHERE domestic_violence AND mentions_women
    UNION ALL SELECT 9, 'DV: mentions men', ein, revenue, top_pay FROM s WHERE domestic_violence AND mentions_men
    UNION ALL SELECT 10, 'DV: mentions both', ein, revenue, top_pay FROM s
              WHERE domestic_violence AND mentions_women AND mentions_men
    UNION ALL SELECT 11, 'DV: mentions neither', ein, revenue, top_pay FROM s
              WHERE domestic_violence AND NOT coalesce(mentions_women, false) AND NOT coalesce(mentions_men, false)
    UNION ALL SELECT 12, 'science / STEM (education or research)', ein, revenue, top_pay FROM s WHERE science_stem
    UNION ALL SELECT 13, 'science / STEM AND mentions women or girls', ein, revenue, top_pay FROM s
              WHERE science_stem AND (mentions_women OR girls_programs)
)
SELECT i, question, count(*) AS orgs,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY revenue) AS median_revenue,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY top_pay) AS median_top_comp
FROM q GROUP BY i, question ORDER BY i;
