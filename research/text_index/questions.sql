-- Saved questions for the topic index (owner, 2026-10-28). Each is a view in the research schema:
--     SELECT * FROM research.questions;           -- every question: scope, n, orgs, median revenue of the orgs
--     SELECT * FROM research.q_domestic_violence; -- one question
-- Rerun:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/questions.sql
-- "space" needs the model's labels: run space_prep below, then research/text_index/classify.py space, then the views.

\set ON_ERROR_STOP 1
SET statement_timeout = '30min';
CREATE TABLE IF NOT EXISTS research.topic_labels (
    topic text NOT NULL, ein text NOT NULL, label boolean, model text, labeled_at timestamptz DEFAULT now(),
    PRIMARY KEY (topic, ein));
ALTER TABLE research.topic_labels ADD COLUMN IF NOT EXISTS codes text;     -- the senses, e.g. 'OW' (classify.py)

-- ---------------------------------------------------------------- term lists (raw tsquery, English stemming)
CREATE OR REPLACE FUNCTION research.terms(name text) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE name
    -- Outer space, unambiguous on their own. Left out on purpose: "space program" (land trusts' "open space
    -- program"), "space center" (community centers), satellite (satellite offices), rocket, astronomical (costs),
    -- aerospace (the UAW's and the Machinists' names: "Aerospace Workers"; the model sorts it out).
    WHEN 'outer_space' THEN
        '(outer <-> space) | astronaut | cosmonaut | astronomy | astronomer | astrophysics | '
        'spaceflight | (space <-> flight) | spacecraft | (space <-> exploration) | (space <-> science) | '
        '(space <-> station) | (space <-> shuttle) | (space <-> camp) | (space <-> museum) | nasa | planetarium | '
        'rocketry'
    WHEN 'women' THEN 'women | woman | female | girl | mother'
    WHEN 'men' THEN 'men | man | male | boy | father'
    -- Women's issues: the group words plus issues mostly specific to women and girls
    WHEN 'womens_issues' THEN
        'women | woman | girl | female | feminism | feminist | maternal | maternity | mother | pregnancy | pregnant | '
        'prenatal | postpartum | midwife | midwifery | (breast <-> cancer) | (ovarian <-> cancer) | '
        '(cervical <-> cancer) | (reproductive <-> health) | (reproductive <-> rights) | abortion | contraception | '
        '(family <-> planning) | menopause | (violence <-> against <-> women) | (gender <-> equality) | '
        '(gender <-> equity)'
    -- Men's issues: the group words plus issues mostly specific to men and boys
    WHEN 'mens_issues' THEN
        'men | man | boy | male | father | fatherhood | paternal | paternity | (prostate <-> cancer) | '
        '(testicular <-> cancer) | masculinity | (male <-> survivors) | (men <-> of <-> color) | '
        '(responsible <-> fatherhood) | (boys <-> to <-> men)'
    WHEN 'domestic_violence' THEN
        '(domestic <-> violence) | (domestic <-> abuse) | (intimate <-> partner <-> violence) | '
        '(family <-> violence) | (dating <-> violence) | (partner <-> abuse) | battered'
    END
$$;

-- ---------------------------------------------------------------- space_prep: the senses of "space"
-- Owner: "space where rockets go is one thing; a space for women or a space for men is another"; "there's also
-- office space, parking space... disambiguate". Two ways, side by side:
-- 1. Exact phrases (research.q_space_phrases): office space, parking space, green / open space, safe space, ...
-- 2. Every org whose text says "space" or "aerospace" is labeled by the model (classify.py) with every sense that
--    applies: O outer space, W a space for women or girls, M a space for men or boys, F facility (office, meeting,
--    studio, rental...), P parking, G green / open land, S safe / quiet / personal space, X anything else.
--    Orgs with an unambiguous outer-space term count as outer space whatever the model says.
-- earthly_only is a check, not a filter: the org's "space" mentions are all plainly earthly phrases.
DROP TABLE IF EXISTS research.space_ambiguous_orgs;
DROP TABLE IF EXISTS research.space_candidates CASCADE;
CREATE TABLE research.space_candidates AS
SELECT o.ein,
       o.tsv @@ to_tsquery('english', research.terms('outer_space')) AS has_term,
       regexp_replace(regexp_replace(regexp_replace(o.text,
        -- union names: "Machinists & Aerospace Workers", "United Auto, Aerospace & Agricultural Implement Workers"
        '\maerospace(\s+(&|and))?\s+(workers|agricultural)\M', ' ', 'gi'),
        '\m(office|green|open|safe|brave|meeting|storage|parking|rental|retail|living|public|community|event|work|'
        'studio|exhibit|exhibition|performance|gallery|program|play|classroom|outdoor|indoor|commercial|warehouse|'
        'shared|sacred|creative|physical|available|additional|square|leased?|rented|free|common|activity|'
        'recreation|recreational|garden|natural|white|gathering|usable|floor|advertising|display|booth|shelf|donated|'
        'crawl|personal|cultural|civic|urban|housing|residential|learning|maker|coworking|co-working|worship|kitchen|'
        'clinic|clinical|treatment|counseling|therapy|teaching|rehearsal|practice|training|conference|banquet|'
        'lab|laboratory|museum|art|arts|artist|theater|theatre|dance|music|youth|teen|senior|wilderness|habitat|'
        'park|parks|trail|breathing|head|mental|emotional|digital|online|virtual|cyber|web|disk|server|data|blank|'
        'negative|enough|more|less|extra|limited|adequate|sufficient|ample|own|in-kind|rent-free|larger|smaller|'
        'quiet|calm)\s+spaces?\M', ' ', 'gi'),
        '\mspaces?\s+(for\s+rent|to\s+rent|rental|rentals|rent|lease|leases|available|provided|needs?|planning|'
        'heaters?|utilization|usage|allocation|costs?|expenses?|sharing|donation|donated)\M',
        ' ', 'gi') !~* '\m(spaces?|aerospace)\M' AS earthly_only
FROM research.org_text o
WHERE o.tsv @@ to_tsquery('english', 'space | aerospace');
ALTER TABLE research.space_candidates ADD PRIMARY KEY (ein);

-- The outer-space orgs: an unambiguous term, or the model's O
CREATE OR REPLACE VIEW research.space_orgs AS
SELECT ein, 'term' AS how FROM research.space_candidates WHERE has_term
UNION
SELECT ein, 'model' FROM research.topic_labels WHERE topic = 'space' AND codes LIKE '%O%';

-- Every sense per org (codes from the model, plus O for an unambiguous term)
CREATE OR REPLACE VIEW research.space_senses AS
SELECT c.ein, c.has_term, c.earthly_only, l.codes,
       c.has_term OR coalesce(l.codes LIKE '%O%', false) AS outer_space,
       coalesce(l.codes LIKE '%W%', false) AS for_women, coalesce(l.codes LIKE '%M%', false) AS for_men,
       coalesce(l.codes LIKE '%F%', false) AS facility, coalesce(l.codes LIKE '%P%', false) AS parking,
       coalesce(l.codes LIKE '%G%', false) AS green_open, coalesce(l.codes LIKE '%S%', false) AS safe_personal,
       coalesce(l.codes LIKE '%X%', false) AS other
FROM research.space_candidates c LEFT JOIN research.topic_labels l ON l.topic = 'space' AND l.ein = c.ein;

-- ---------------------------------------------------------------- one row per filing for each topic
-- (the 'all' row: any field of the return; superseded returns left out)
CREATE OR REPLACE FUNCTION research.filings_matching(q tsquery)
RETURNS TABLE (filing_id bigint, ein text) LANGUAGE sql STABLE AS $$
    SELECT filing_id, ein FROM research.filing_text WHERE field = 'all' AND NOT superseded AND tsv @@ q
$$;

CREATE OR REPLACE FUNCTION research.summarize(question text, filings bigint[], eins text[])
RETURNS TABLE (question text, filings bigint, orgs bigint, median_org_revenue double precision)
LANGUAGE sql STABLE AS $$
    SELECT question, (SELECT count(DISTINCT f) FROM unnest(filings) f), (SELECT count(DISTINCT e) FROM unnest(eins) e),
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY o.revenue)
            FROM research.org_text o WHERE o.ein IN (SELECT DISTINCT e FROM unnest(eins) e))
$$;

-- Space: any mention of the word, and outer space
CREATE OR REPLACE VIEW research.q_space AS
WITH any_word AS (SELECT * FROM research.filings_matching(to_tsquery('english', 'space'))),
     outer_f AS (SELECT * FROM research.filings_matching(to_tsquery('english', research.terms('outer_space')))
                 UNION SELECT a.* FROM any_word a JOIN research.space_orgs s USING (ein))
SELECT * FROM research.summarize('space, the word in any sense',
                                 (SELECT array_agg(filing_id) FROM any_word), (SELECT array_agg(ein) FROM any_word))
UNION ALL
SELECT * FROM research.summarize('outer space', (SELECT array_agg(filing_id) FROM outer_f),
                                 (SELECT array_agg(ein) FROM research.space_orgs));

-- The senses of "space", by exact phrase (no model)
CREATE OR REPLACE VIEW research.q_space_phrases AS
SELECT 'phrase: ' || p.label AS question, c.n AS filings, c.n_orgs AS orgs, c.median_org_revenue
FROM (VALUES (1, 'outer space', 'outer <-> space'),
             (2, 'office space', 'office <-> space'),
             (3, 'meeting / event / conference space', '(meeting | event | conference) <-> space'),
             (4, 'parking space', 'parking <-> space'),
             (5, 'green / open space', '(green | open) <-> space'),
             (6, 'safe / brave / quiet space', '(safe | brave | quiet) <-> space'),
             (7, 'studio / storage / rental space', '(studio | storage | rental | rent | leased) <-> space'),
             (8, 'space for women, women''s space', 'space <2> women | space <2> girls | women <-> space | women <2> space'),
             (9, 'space for men, men''s space', 'space <2> men | space <2> boys | men <-> space | men <2> space'))
     AS p(i, label, q),
     LATERAL research.topic_count(p.q) c
ORDER BY p.i;

-- The senses of "space", by the model (orgs; filings = their returns that say "space")
CREATE OR REPLACE VIEW research.q_space_senses AS
WITH f AS (SELECT * FROM research.filings_matching(to_tsquery('english', 'space | aerospace'))),
     s AS (SELECT * FROM research.space_senses)
SELECT x.* FROM (VALUES
    (1, 'outer space'), (2, 'a space for women or girls'), (3, 'a space for men or boys'),
    (4, 'facility space (office, meeting, studio, rental)'), (5, 'parking'), (6, 'green / open space'),
    (7, 'safe / quiet / personal space'), (8, 'other (a field or sector, a gap, union names)')) v(i, sense),
LATERAL (
    SELECT * FROM research.summarize('sense: ' || v.sense,
        (SELECT array_agg(f.filing_id) FROM f JOIN s USING (ein) WHERE CASE v.i WHEN 1 THEN s.outer_space
             WHEN 2 THEN s.for_women WHEN 3 THEN s.for_men WHEN 4 THEN s.facility WHEN 5 THEN s.parking
             WHEN 6 THEN s.green_open WHEN 7 THEN s.safe_personal ELSE s.other END),
        (SELECT array_agg(s.ein) FROM s WHERE CASE v.i WHEN 1 THEN s.outer_space
             WHEN 2 THEN s.for_women WHEN 3 THEN s.for_men WHEN 4 THEN s.facility WHEN 5 THEN s.parking
             WHEN 6 THEN s.green_open WHEN 7 THEN s.safe_personal ELSE s.other END))) x
ORDER BY v.i;

-- Women in space: the phrase, and women AND outer space in the same filing
CREATE OR REPLACE VIEW research.q_women_in_space AS
WITH phrase AS (SELECT * FROM research.filings_matching(to_tsquery('english', 'women <-> in <-> space'))),
     outer_f AS (SELECT * FROM research.filings_matching(to_tsquery('english', research.terms('outer_space')))
                 UNION SELECT a.* FROM research.filings_matching(to_tsquery('english', 'space')) a
                       JOIN research.space_orgs s USING (ein)),
     both_f AS (SELECT o.* FROM outer_f o
                JOIN research.filings_matching(to_tsquery('english', research.terms('women'))) w USING (filing_id))
SELECT * FROM research.summarize('"women in space" (the phrase)', (SELECT array_agg(filing_id) FROM phrase),
                                 (SELECT array_agg(ein) FROM phrase))
UNION ALL
SELECT * FROM research.summarize('women AND outer space, same filing', (SELECT array_agg(filing_id) FROM both_f),
                                 (SELECT array_agg(ein) FROM both_f));

-- Women's issues and men's issues
CREATE OR REPLACE VIEW research.q_womens_mens_issues AS
WITH w AS (SELECT * FROM research.filings_matching(to_tsquery('english', research.terms('womens_issues')))),
     m AS (SELECT * FROM research.filings_matching(to_tsquery('english', research.terms('mens_issues'))))
SELECT * FROM research.summarize('women''s issues', (SELECT array_agg(filing_id) FROM w), (SELECT array_agg(ein) FROM w))
UNION ALL
SELECT * FROM research.summarize('men''s issues', (SELECT array_agg(filing_id) FROM m), (SELECT array_agg(ein) FROM m));

-- Domestic violence, and of those, mentioning women / men (same filing)
CREATE OR REPLACE VIEW research.q_domestic_violence AS
WITH dv AS (SELECT * FROM research.filings_matching(to_tsquery('english', research.terms('domestic_violence')))),
     w AS (SELECT dv.* FROM dv JOIN research.filings_matching(to_tsquery('english', research.terms('women'))) x
           USING (filing_id)),
     m AS (SELECT dv.* FROM dv JOIN research.filings_matching(to_tsquery('english', research.terms('men'))) x
           USING (filing_id))
SELECT * FROM research.summarize('domestic violence', (SELECT array_agg(filing_id) FROM dv), (SELECT array_agg(ein) FROM dv))
UNION ALL
SELECT * FROM research.summarize('domestic violence + women', (SELECT array_agg(filing_id) FROM w), (SELECT array_agg(ein) FROM w))
UNION ALL
SELECT * FROM research.summarize('domestic violence + men', (SELECT array_agg(filing_id) FROM m), (SELECT array_agg(ein) FROM m));

CREATE OR REPLACE VIEW research.questions AS
SELECT * FROM research.q_space
UNION ALL SELECT * FROM research.q_space_phrases
UNION ALL SELECT * FROM research.q_space_senses
UNION ALL SELECT * FROM research.q_women_in_space
UNION ALL SELECT * FROM research.q_womens_mens_issues
UNION ALL SELECT * FROM research.q_domestic_violence;
