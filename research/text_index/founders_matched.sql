-- Question 2, continued (owner, 2026-10-28): is the founder-background gap between successful and small nonprofits
-- real, or an artifact of how visible each group is? And the women-in-space cohort's founders.
-- Needs research/text_index/founders.sql (fnd_orgs, fnd_prior, fnd_flags) and women_in_space.sql (wis_profile = research.wis_rows2).
--
-- Matching  Big orgs file more returns over more years, so more of their history is in view. Each org gets a stratum:
--           founding year x returns filed (1..10+) x years observed, first to last return (1..10+). Shares for the
--           small group are reweighted to the successful group's mix of strata (direct standardization), using only
--           strata both groups have. If the gap holds after that, visibility doesn't explain it.
-- Confidence each founder link is labeled: "high" = the person's name has a middle name or initial and no other
--           person in FURP has the same name; "low" otherwise. Every share is also shown for high-confidence only.

\set ON_ERROR_STOP 1
SET statement_timeout = '30min';

DROP TABLE IF EXISTS research.fnd_strata;
CREATE TABLE research.fnd_strata AS
SELECT y.ein, min(y.founded) AS founded, least(count(*), 10) AS returns_b,
       least(max(y.tax_year) - min(y.tax_year) + 1, 10) AS span_b
FROM research.npay_years y GROUP BY y.ein;
ALTER TABLE research.fnd_strata ADD PRIMARY KEY (ein);

ALTER TABLE research.fnd_orgs ADD COLUMN IF NOT EXISTS match_confidence text;
UPDATE research.fnd_orgs SET match_confidence = CASE WHEN cluster_id IS NULL THEN 'no founder'
                                                     WHEN low_confidence THEN 'low' ELSE 'high' END;

-- Raw and matched shares: successful ($500K+, $1M+) vs never passed $100K
DROP TABLE IF EXISTS research.fnd_matched;
CREATE TABLE research.fnd_matched AS
WITH f AS (SELECT fl.*, s.founded AS f_year, s.returns_b, s.span_b
           FROM research.fnd_flags fl JOIN research.fnd_strata s USING (ein) WHERE fl.has_founder),
grp AS (SELECT 'successful $500K+' AS g, 500000 AS lo UNION ALL SELECT 'successful $1M+', 1000000),
conf AS (SELECT 'all links' AS c UNION ALL SELECT 'high confidence only'),
measures AS (SELECT * FROM (VALUES ('any prior nonprofit role'), ('prior role in the same sector'),
                                   ('background in the field'), ('no visible background at all')) m(m)),
x AS (SELECT grp.g, conf.c, measures.m, f.*,
             CASE measures.m WHEN 'any prior nonprofit role' THEN f.prior_nonprofit
                             WHEN 'prior role in the same sector' THEN f.prior_same_sector
                             WHEN 'background in the field' THEN f.prior_in_field
                             ELSE NOT f.any_prior END::int AS v,
             f.max_rev >= grp.lo AS succ, f.max_rev < 100000 AS small
      FROM f, grp, conf, measures
      WHERE conf.c = 'all links' OR NOT f.low_confidence),
cell AS (SELECT g, c, m, f_year, returns_b, span_b,
                count(*) FILTER (WHERE succ) AS n_s, avg(v) FILTER (WHERE succ) AS p_s,
                count(*) FILTER (WHERE small) AS n_b, avg(v) FILTER (WHERE small) AS p_b
         FROM x GROUP BY 1, 2, 3, 4, 5, 6)
SELECT g AS successful_group, c AS links, m AS measure,
       sum(n_s) AS n_successful, round(sum(n_s * p_s) / nullif(sum(n_s), 0), 3) AS share_successful,
       sum(n_b) AS n_small, round(sum(n_b * p_b) / nullif(sum(n_b), 0), 3) AS share_small_raw,
       sum(n_s) FILTER (WHERE n_b > 0) AS n_successful_matched,
       round(sum(n_s * p_s) FILTER (WHERE n_b > 0) / nullif(sum(n_s) FILTER (WHERE n_b > 0), 0), 3) AS share_successful_matched,
       round(sum(n_s * p_b) FILTER (WHERE n_b > 0) / nullif(sum(n_s) FILTER (WHERE n_b > 0), 0), 3) AS share_small_matched
FROM cell GROUP BY 1, 2, 3 ORDER BY 1, 2, 3;

-- The women-in-space cohort's founders (orgs founded 2010-2020). Background here = a prior role at an org whose
-- text index senses include women's issues, girls' programs, research/education (science, STEM) or outer space.
DROP TABLE IF EXISTS research.fnd_wis;
CREATE TABLE research.fnd_wis AS
WITH w AS (SELECT f.* FROM research.fnd_orgs f JOIN research.wis_profile p USING (ein)),
bg AS (SELECT DISTINCT p.ein FROM research.fnd_prior p JOIN w USING (ein)
       JOIN research.org_fields of ON of.ein = p.prior_ein
       WHERE p.source = '990' AND of.field IN ('women:issues', 'girls_boys:girls', 'science:research_education', 'space:outer'))
SELECT count(*) AS orgs, count(*) FILTER (WHERE w.cluster_id IS NOT NULL) AS with_founder,
       count(*) FILTER (WHERE w.match_confidence = 'high') AS high_confidence,
       count(*) FILTER (WHERE fl.prior_nonprofit) AS any_prior_nonprofit,
       count(*) FILTER (WHERE fl.prior_same_sector) AS prior_same_sector,
       count(*) FILTER (WHERE w.ein IN (SELECT ein FROM bg)) AS background_women_stem_space,
       count(*) FILTER (WHERE w.cluster_id IS NOT NULL AND NOT fl.any_prior) AS no_visible_background,
       count(*) FILTER (WHERE fl.max_rev >= 500000) AS successful_500k,
       count(*) FILTER (WHERE fl.max_rev >= 500000 AND fl.prior_nonprofit) AS successful_500k_with_prior_role,
       count(*) FILTER (WHERE fl.max_rev < 100000) AS never_100k,
       count(*) FILTER (WHERE fl.max_rev < 100000 AND fl.prior_nonprofit) AS never_100k_with_prior_role
FROM w JOIN research.fnd_flags fl USING (ein);

SELECT * FROM research.fnd_matched WHERE links = 'all links';
SELECT * FROM research.fnd_matched WHERE links = 'high confidence only';
SELECT * FROM research.fnd_wis;
