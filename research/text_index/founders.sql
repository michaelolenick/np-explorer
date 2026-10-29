-- Founders with no visible background in the field (owner, 2026-10-28).
-- Nonprofits founded 2010-2020 (research.npay_orgs / npay_years from research/new_nonprofit_pay.sql): who led the
-- first return, and what FURP holds on that person before the founding year.
--
-- Rerun:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/founders.sql
--
-- Definitions
--   founder        the top officer on the org's first 990 / 990-EZ in npay_years: executive director or CEO first,
--                  then president, then chair (vice, past, former, elect, assistant, deputy titles excluded); ties
--                  go to the higher pay. Orgs whose first return names none of these have no founder here.
--   the person     the founder's person cluster (people grouped by name plus shared filings, addresses and states).
--                  Institutions (banks, trust companies) are left out.
--   low confidence the cluster's name has no middle name or initial, or another cluster has the same name.
--   prior          a record dated before the founding year (founded = IRS ruling year):
--                    990       any role (officer, director, key employee) at another filer, tax year < founded
--                    Form D    named on a Form D filed before Jan 1 of the founding year
--                    ADV       owner or control person on an adviser's Form ADV, year < founded
--                    payroll   public payroll row, fiscal year < founded
--                    patent    first patent granted before the founding year
--                    business  officer, principal or agent of a state-registered business formed before then
--                  990, Form D, ADV, payroll and business links are by name plus state (fuzzy); patents carry their
--                  own match confidence.
--   field          the org's NTEE major group (first letter) and its senses from the text index (research.org_codes:
--                  women's issues, outer space, research and education, domestic violence, ...; names, incidental
--                  mentions and generic senses left out).
--   same sector    a prior 990 role at an org in the same NTEE major group.
--   background in the field   same sector, or a prior org sharing one of the new org's senses.
--   success        peak total revenue on any 990 / 990-EZ >= $500K (and separately >= $1M); "never passed $100K"
--                  is peak revenue < $100K.
-- Limits: FURP sees only public filings. 990 e-file data starts with 2010-2011 returns, so founders of the 2010-2012
-- cohorts have little or no visible prior 990 history. "No visible background" means no record in our data.

\set ON_ERROR_STOP 1
SET statement_timeout = '90min';
SET work_mem = '256MB';

-- Senses that say what an org works on (not names, passing mentions or generic senses)
CREATE OR REPLACE VIEW research.org_fields AS
SELECT DISTINCT oc.ein,
       CASE WHEN d.code = 'D' AND oc.topic IN ('domestic', 'violence', 'abuse', 'shelter', 'survivor')
            THEN 'domestic_violence' ELSE oc.topic || ':' || d.sense END AS field
FROM research.org_codes oc JOIN research.sense_defs d ON d.topic = oc.topic AND strpos(oc.codes, d.code) > 0
WHERE d.sense NOT IN ('name', 'other_name', 'incidental', 'other', 'facility', 'parking', 'green', 'personal',
                      'mission_statement', 'figurative', 'production', 'travel', 'vs_foreign', 'tax', 'kids');

-- 1. The founders ----------------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS research.fnd_orgs CASCADE;
CREATE TABLE research.fnd_orgs AS
WITH y AS (SELECT ein, min(founded) AS founded, min(tax_year) AS first_year, max(total_revenue) AS max_rev
           FROM research.npay_years GROUP BY ein),
first AS (SELECT DISTINCT ON (v.ein) v.ein, v.filing_id FROM research.npay_years v JOIN y USING (ein)
          WHERE v.tax_year = y.first_year ORDER BY v.ein, v.filing_id),
cand AS (SELECT f.ein, p.id AS person_id, p.name_raw, p.title, p.state, p.comp_org,
                CASE WHEN p.title ~* '(exec\w*\.?\s*dir|\mceo\M|chief\s+exec)' THEN 1
                     WHEN p.title ~* '\mpres' THEN 2
                     WHEN p.title ~* '\mchair' THEN 3 END AS rnk
         FROM first f JOIN people p ON p.filing_id = f.filing_id
         WHERE NOT coalesce(p.is_duplicate, false)
           AND p.title !~* '(vice|\mvp\M|past|former|elect|assist|asst|deputy|interim)'),
pick AS (SELECT DISTINCT ON (ein) * FROM cand WHERE rnk IS NOT NULL
         ORDER BY ein, rnk, comp_org DESC NULLS LAST, person_id)
SELECT y.ein, y.founded, y.first_year, y.max_rev, left(o.ntee, 1) AS ntee_major, o.ntee,
       pk.person_id, m.cluster_id, pk.name_raw AS founder, pk.title AS founder_title, pk.state AS founder_state,
       pc.display_name, pc.is_institution
FROM y JOIN organizations o USING (ein)
LEFT JOIN pick pk USING (ein)
LEFT JOIN person_cluster_members m ON m.person_id = pk.person_id
LEFT JOIN person_clusters pc ON pc.id = m.cluster_id;
ALTER TABLE research.fnd_orgs ADD PRIMARY KEY (ein);
CREATE INDEX ON research.fnd_orgs (cluster_id);

ALTER TABLE research.fnd_orgs ADD COLUMN low_confidence boolean;
UPDATE research.fnd_orgs f SET low_confidence =
       array_length(regexp_split_to_array(trim(pc.name_norm), '\s+'), 1) < 3
       OR EXISTS (SELECT 1 FROM person_clusters o WHERE o.name_norm = pc.name_norm AND o.id <> pc.id)
FROM person_clusters pc WHERE pc.id = f.cluster_id;

-- 2. Prior records, one row each -------------------------------------------------------------------------------------
DROP TABLE IF EXISTS research.fnd_prior;
CREATE TABLE research.fnd_prior (ein text, source text, prior_key text, prior_name text, prior_ein text,
                                 prior_year int, same_sector boolean, shared_fields text[], confidence text);

-- 990 roles at other filers
INSERT INTO research.fnd_prior
SELECT f.ein, '990', p.ein, max(p.name_raw), p.ein, min(p.tax_year),
       left(min(po.ntee), 1) = f.ntee_major, NULL::text[], 'name + filings (cluster)'
FROM research.fnd_orgs f
JOIN person_cluster_members m ON m.cluster_id = f.cluster_id
JOIN people p ON p.id = m.person_id
LEFT JOIN organizations po ON po.ein = p.ein
WHERE f.cluster_id IS NOT NULL AND NOT coalesce(f.is_institution, false)
  AND p.ein <> f.ein AND p.tax_year < f.founded
GROUP BY f.ein, f.ntee_major, p.ein;

-- Form D (linked one by one, and through Form D parties)
INSERT INTO research.fnd_prior
SELECT DISTINCT f.ein, 'formd', d.accession, d.issuer_name, NULL::text, extract(year FROM d.filing_date)::int, NULL::boolean, NULL::text[],
       'name + state'
FROM research.fnd_orgs f
JOIN sec_person_links l ON l.cluster_id = f.cluster_id AND l.source = 'formd'
JOIN sec_formd d ON d.accession = split_part(l.key, ':', 1)
WHERE d.filing_date < make_date(f.founded, 1, 1);
INSERT INTO research.fnd_prior
SELECT DISTINCT f.ein, 'formd', d.accession, d.issuer_name, NULL::text, extract(year FROM d.filing_date)::int, NULL::boolean, NULL::text[],
       'name + state'
FROM research.fnd_orgs f
JOIN sec_formd_parties x ON x.cluster_id = f.cluster_id
JOIN sec_formd_people_party pp ON pp.party_id = x.id
JOIN sec_formd d ON d.accession = pp.accession
WHERE d.filing_date < make_date(f.founded, 1, 1);

-- Form ADV owners and control persons
INSERT INTO research.fnd_prior
SELECT f.ein, 'adv', a.crd::text, max(a.name), NULL::text, min(a.year), NULL::boolean, NULL::text[], 'name + state'
FROM research.fnd_orgs f
JOIN adv_person_links l ON l.cluster_id = f.cluster_id
JOIN adv_owners a ON a.crd = l.crd AND a.name_norm = l.name_norm
WHERE a.year < f.founded
GROUP BY f.ein, a.crd;

-- Public payroll
INSERT INTO research.fnd_prior
SELECT f.ein, 'payroll', y.label, max(y.label), NULL::text, min(y.fiscal_year), NULL::boolean, NULL::text[], 'name + institution'
FROM research.fnd_orgs f
JOIN payroll_person_links l ON l.cluster_id = f.cluster_id
JOIN payroll_person_years y ON y.state = l.state AND y.label = l.label AND y.name_norm = l.name_norm
WHERE y.fiscal_year < f.founded
GROUP BY f.ein, y.label;

-- Patents
INSERT INTO research.fnd_prior
SELECT f.ein, 'patent', i.inventor_id::text, i.top_assignee, NULL::text, extract(year FROM i.first_grant::date)::int, NULL::boolean, NULL::text[], l.confidence
FROM research.fnd_orgs f
JOIN ip_links l ON l.target_kind = 'person' AND l.target_key = f.cluster_id::text AND l.src_kind = 'inventor'
JOIN pat_inventor_people i ON i.inventor_id::text = l.src_key
WHERE extract(year FROM i.first_grant::date) < f.founded;

-- State business registrations
INSERT INTO research.fnd_prior
SELECT f.ein, 'business', e.state || ':' || e.entity_id, e.name, NULL::text, extract(year FROM e.formed::date)::int, NULL::boolean, NULL::text[], 'name + state'
FROM research.fnd_orgs f
JOIN biz_links l ON l.kind = 'person' AND l.key = f.cluster_id::text
JOIN biz_entities e ON e.state = l.state AND e.entity_id = l.entity_id
WHERE extract(year FROM e.formed::date) < f.founded;

-- Fields shared between each prior 990 org and the new org
UPDATE research.fnd_prior p SET shared_fields = s.shared
FROM (SELECT p.ein, p.prior_ein, array_agg(DISTINCT a.field) AS shared
      FROM research.fnd_prior p
      JOIN research.org_fields a ON a.ein = p.ein
      JOIN research.org_fields b ON b.ein = p.prior_ein AND b.field = a.field
      WHERE p.source = '990' GROUP BY 1, 2) s
WHERE p.source = '990' AND p.ein = s.ein AND p.prior_ein = s.prior_ein;
CREATE INDEX ON research.fnd_prior (ein);

-- 3. One row per org -------------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS research.fnd_flags CASCADE;
CREATE TABLE research.fnd_flags AS
SELECT f.ein, f.founded, f.max_rev, f.ntee_major, f.cluster_id IS NOT NULL AS has_founder, f.low_confidence,
       coalesce(bool_or(p.source = '990'), false) AS prior_nonprofit,
       coalesce(bool_or(p.source = '990' AND p.same_sector), false) AS prior_same_sector,
       coalesce(bool_or(p.source = '990' AND (p.same_sector OR p.shared_fields IS NOT NULL)), false) AS prior_in_field,
       coalesce(bool_or(p.source IN ('formd', 'adv')), false) AS prior_finance,
       coalesce(bool_or(p.source = 'payroll'), false) AS prior_payroll,
       coalesce(bool_or(p.source = 'patent'), false) AS prior_patent,
       coalesce(bool_or(p.source = 'business'), false) AS prior_business,
       count(p.*) > 0 AS any_prior
FROM research.fnd_orgs f LEFT JOIN research.fnd_prior p USING (ein)
GROUP BY f.ein, f.founded, f.max_rev, f.ntee_major, f.cluster_id, f.low_confidence;
ALTER TABLE research.fnd_flags ADD PRIMARY KEY (ein);

-- 4. Shares for a group of orgs (only orgs with an identified founder; n on every share) ------------------------------
CREATE OR REPLACE FUNCTION research.fnd_shares(p_group text, p_eins text[])
RETURNS TABLE (grp text, orgs bigint, with_founder bigint, low_conf bigint, any_prior_nonprofit numeric,
               prior_same_sector numeric, background_in_field numeric, no_background_in_field numeric,
               no_visible_background numeric, prior_finance numeric, prior_payroll numeric, prior_patent numeric,
               prior_business numeric)
LANGUAGE sql STABLE AS $$
    SELECT p_group, count(*), count(*) FILTER (WHERE has_founder), count(*) FILTER (WHERE low_confidence),
           round(avg(prior_nonprofit::int) FILTER (WHERE has_founder), 3),
           round(avg(prior_same_sector::int) FILTER (WHERE has_founder), 3),
           round(avg(prior_in_field::int) FILTER (WHERE has_founder), 3),
           round(avg((NOT prior_in_field)::int) FILTER (WHERE has_founder), 3),
           round(avg((NOT any_prior)::int) FILTER (WHERE has_founder), 3),
           round(avg(prior_finance::int) FILTER (WHERE has_founder), 3),
           round(avg(prior_payroll::int) FILTER (WHERE has_founder), 3),
           round(avg(prior_patent::int) FILTER (WHERE has_founder), 3),
           round(avg(prior_business::int) FILTER (WHERE has_founder), 3)
    FROM research.fnd_flags WHERE ein = ANY(p_eins)
$$;

DROP TABLE IF EXISTS research.fnd_results;
CREATE TABLE research.fnd_results AS
SELECT 1 AS i, s.* FROM research.fnd_shares('all orgs founded 2010-2020',
       (SELECT array_agg(ein) FROM research.fnd_flags)) s
UNION ALL SELECT 2, s.* FROM research.fnd_shares('successful: peak revenue >= $500K',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev >= 500000)) s
UNION ALL SELECT 3, s.* FROM research.fnd_shares('successful: peak revenue >= $1M',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev >= 1000000)) s
UNION ALL SELECT 4, s.* FROM research.fnd_shares('never passed $100K',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev < 100000)) s
UNION ALL SELECT 5, s.* FROM research.fnd_shares('$500K+, founded 2013-2020 (more visible history)',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev >= 500000 AND founded >= 2013)) s
UNION ALL SELECT 6, s.* FROM research.fnd_shares('never passed $100K, founded 2013-2020',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev < 100000 AND founded >= 2013)) s
UNION ALL SELECT 7, s.* FROM research.fnd_shares('$500K+, high-confidence founder match only',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev >= 500000 AND NOT low_confidence)) s
UNION ALL SELECT 8, s.* FROM research.fnd_shares('never passed $100K, high-confidence only',
       (SELECT array_agg(ein) FROM research.fnd_flags WHERE max_rev < 100000 AND NOT low_confidence)) s;

SELECT * FROM research.fnd_results ORDER BY i;
