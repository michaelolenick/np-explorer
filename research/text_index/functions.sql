-- Query layer for the topic index (research/text_index/README.md has the search syntax and examples).
--
--   research.topic_count(terms, scope, field)      n, n_orgs, median revenue of the matching orgs, their eins
--   research.topic_breakdown(terms, scope, field)  the same by tax year, NTEE major group, state and size
--   research.topic_match(terms, scope, field)      the matching rows themselves, to combine in your own SQL
--
-- terms: a search expression (README.md), or 'topic:sense' for one sense of an ambiguous term ('space:outer',
--        'abuse:domestic', 'shelter:animal,homeless'; the list: SELECT * FROM research.sense_defs).
-- scope: 'filings' (default; one per return, superseded returns left out) or 'orgs' (one per organization).
-- field: NULL (default, any field of the return or org) or one of name, mission, program, schedule_o,
--        grant_purpose, contractor_service.
-- Revenue: each org's total revenue on its latest return (research.org_text.revenue).

-- terms -> tsquery. Plain words, "quoted phrases", OR and -not use web-search syntax; anything with & | ! ( ) or
-- <N> is read as raw tsquery (proximity, prefix:*).
CREATE OR REPLACE FUNCTION research.tsq(terms text) RETURNS tsquery LANGUAGE sql STABLE AS $$
    SELECT CASE WHEN terms ~ '[&|!()]|<[0-9-]+>|:\*' THEN to_tsquery('english', terms)
                ELSE websearch_to_tsquery('english', terms) END
$$;

CREATE OR REPLACE FUNCTION research.topic_match(terms text, scope text DEFAULT 'filings', field text DEFAULT NULL)
RETURNS TABLE (filing_id bigint, ein text, tax_year int, ntee_major text, state text, revenue bigint)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    re boolean := terms LIKE 're:%';
    pat text := substr(terms, 4);
    v_topic text := split_part(terms, ':', 1);
    v_senses text[] := string_to_array(split_part(terms, ':', 2), ',');
    v_words text;
BEGIN
    -- 'topic:sense' (or 'topic:sense1,sense2'): orgs with that sense of the term (research.org_codes, senses.py);
    -- filings = their returns that use the term
    IF terms ~ '^[a-z_]+:[a-z_,]+$' AND to_regclass('research.sense_defs') IS NOT NULL THEN
        SELECT max(d.tsq) INTO v_words FROM research.sense_defs d WHERE d.topic = v_topic;
        IF v_words IS NOT NULL THEN
            IF NOT EXISTS (SELECT 1 FROM research.sense_defs d WHERE d.topic = v_topic
                           AND d.sense = ANY(v_senses)) THEN
                RAISE EXCEPTION 'unknown sense in %: see SELECT sense FROM research.sense_defs WHERE topic = %',
                    terms, quote_literal(v_topic);
            END IF;
            IF scope = 'filings' THEN
                RETURN QUERY
                SELECT t.filing_id, t.ein, t.tax_year, t.ntee_major, t.state, t.total_revenue
                FROM research.filing_text t
                WHERE t.field = coalesce(topic_match.field, 'all') AND NOT t.superseded
                  AND t.tsv @@ to_tsquery('english', v_words)
                  AND t.ein IN (SELECT oc.ein FROM research.org_codes oc JOIN research.sense_defs d
                                  ON d.topic = oc.topic AND strpos(oc.codes, d.code) > 0
                                WHERE oc.topic = v_topic AND d.sense = ANY(v_senses));
            ELSE
                RETURN QUERY EXECUTE format(
                    'SELECT NULL::bigint, o.ein, o.last_year, o.ntee_major, o.state, o.revenue FROM research.org_text o
                     WHERE o.%I @@ to_tsquery(''english'', $1)
                       AND o.ein IN (SELECT oc.ein FROM research.org_codes oc JOIN research.sense_defs d
                                       ON d.topic = oc.topic AND strpos(oc.codes, d.code) > 0
                                     WHERE oc.topic = $2 AND d.sense = ANY($3))',
                    'tsv' || coalesce('_' || field, '')) USING v_words, v_topic, v_senses;
            END IF;
            RETURN;
        END IF;
    END IF;
    IF scope NOT IN ('filings', 'orgs') THEN
        RAISE EXCEPTION 'scope must be filings or orgs, not %', scope;
    END IF;
    IF field IS NOT NULL AND field NOT IN ('name', 'mission', 'program', 'schedule_o', 'grant_purpose',
                                           'contractor_service') THEN
        RAISE EXCEPTION 'unknown field %', field;
    END IF;
    IF scope = 'filings' AND NOT re THEN
        RETURN QUERY
        SELECT t.filing_id, t.ein, t.tax_year, t.ntee_major, t.state, t.total_revenue
        FROM research.filing_text t
        WHERE t.field = coalesce(topic_match.field, 'all') AND NOT t.superseded AND t.tsv @@ research.tsq(terms);
    ELSIF scope = 'filings' THEN                       -- regex / substring: the field rows (trigram index)
        RETURN QUERY
        SELECT DISTINCT ON (t.filing_id) t.filing_id, t.ein, t.tax_year, t.ntee_major, t.state, t.total_revenue
        FROM research.filing_text t
        WHERE t.field <> 'all' AND (topic_match.field IS NULL OR t.field = topic_match.field) AND NOT t.superseded
          AND t.text ~* pat;
    ELSIF NOT re THEN
        RETURN QUERY EXECUTE format(
            'SELECT NULL::bigint, o.ein, o.last_year, o.ntee_major, o.state, o.revenue FROM research.org_text o
             WHERE o.%I @@ research.tsq($1)', 'tsv' || coalesce('_' || field, '')) USING terms;
    ELSIF field IS NULL THEN
        RETURN QUERY
        SELECT NULL::bigint, o.ein, o.last_year, o.ntee_major, o.state, o.revenue
        FROM research.org_text o WHERE o.text ~* pat;
    ELSE                                               -- regex in one field: matching filings' orgs
        RETURN QUERY
        SELECT NULL::bigint, o.ein, o.last_year, o.ntee_major, o.state, o.revenue
        FROM research.org_text o
        WHERE o.ein IN (SELECT t.ein FROM research.filing_text t WHERE t.field = topic_match.field
                        AND NOT t.superseded AND t.text ~* pat);
    END IF;
END $$;

CREATE OR REPLACE FUNCTION research.topic_count(terms text, scope text DEFAULT 'filings', field text DEFAULT NULL)
RETURNS TABLE (n bigint, n_orgs bigint, median_org_revenue double precision, eins text[])
LANGUAGE sql STABLE AS $$
    WITH m AS (SELECT * FROM research.topic_match(terms, scope, field)),
         orgs AS (SELECT DISTINCT m.ein, o.revenue FROM m LEFT JOIN research.org_text o USING (ein))
    SELECT (SELECT CASE WHEN scope = 'filings' THEN count(DISTINCT filing_id) ELSE count(*) END FROM m),
           (SELECT count(*) FROM orgs),
           (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY revenue) FROM orgs),
           (SELECT array_agg(ein ORDER BY ein) FROM orgs)
$$;

CREATE OR REPLACE FUNCTION research.topic_breakdown(terms text, scope text DEFAULT 'filings', field text DEFAULT NULL)
RETURNS TABLE (dimension text, value text, n bigint, n_orgs bigint, median_org_revenue double precision)
LANGUAGE sql STABLE AS $$
    WITH m AS (SELECT m.*, o.revenue AS org_revenue
               FROM research.topic_match(terms, scope, field) m LEFT JOIN research.org_text o USING (ein)),
    d AS (
        SELECT 'year' AS dimension, tax_year::text AS value, filing_id, ein, org_revenue FROM m
        UNION ALL SELECT 'ntee_major', coalesce(ntee_major, '?'), filing_id, ein, org_revenue FROM m
        UNION ALL SELECT 'state', coalesce(state, '?'), filing_id, ein, org_revenue FROM m
        UNION ALL SELECT 'size', CASE WHEN org_revenue IS NULL THEN '?' WHEN org_revenue < 100000 THEN '1 under $100K'
                                      WHEN org_revenue < 1000000 THEN '2 $100K-$1M'
                                      WHEN org_revenue < 10000000 THEN '3 $1M-$10M' ELSE '4 $10M+' END,
                         filing_id, ein, org_revenue FROM m
    )
    , c AS (SELECT dimension, value,
                   CASE WHEN scope = 'filings' THEN count(DISTINCT filing_id) ELSE count(*) END AS n,
                   count(DISTINCT ein) AS n_orgs
            FROM d GROUP BY dimension, value),
    r AS (SELECT dimension, value, percentile_cont(0.5) WITHIN GROUP (ORDER BY org_revenue) AS med
          FROM (SELECT DISTINCT dimension, value, ein, org_revenue FROM d) x GROUP BY dimension, value)
    SELECT c.dimension, c.value, c.n, c.n_orgs, r.med FROM c JOIN r USING (dimension, value)
    ORDER BY c.dimension, c.value
$$;
