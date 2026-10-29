-- Question 1: women-in-space nonprofits: who funded them, how much, and what their principals were paid, year by
-- year (owner, 2026-10-28). FUZZY: the cohort comes from the text index (research/text_index) and Claude Haiku labels.
--
-- Rerun:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/text_index/women_in_space.sql
-- Needs:  research.wis_rows2, research.npay_years (research/new_nonprofit_pay.sql)
--
-- Cohort    research.wis_rows2 as it stands (owner's choice, 2026-10-28): orgs whose mission, program or Schedule O
--           text matches a women-in-space row (outer-space flag plus a women/girls mention; or women/girls in the same
--           sentence as aerospace, astronaut, astronomy, STEM plus a space word, or rocketry/satellite/spacecraft), every
--           row gated by the outer-space flag (term list OR anthropic/claude-haiku-5.5, 2026-10-28). The flag's
--           hand-checked precision was roughly two-thirds (n=100), so the cohort is FUZZY.
-- Founding  organizations.ruling_year (IRS ruling year), as in the pay study.
-- Returns   one per org per tax year: the latest-filed return that is not superseded (990, 990-EZ and 990-PF).
-- Funders   every Schedule I grant line (from any filer's return in FURP) whose recipient EIN is the org's EIN.
--           Grants listed without the recipient's EIN are not counted.
-- Pay       officer_comp: filings.officer_comp_total. Top paid: the highest reportable compensation from the org on
--           that return (Part VII-A / EZ Part IV), with name and title. n50: people paid >= $50,000 by the org.
-- Baselines the pay study (research.npay_years: every 990 / 990-EZ filer founded 2010-2020). Cohort pay statistics are
--           computed the same way, on the cohort's orgs founded 2010-2020.

\set ON_ERROR_STOP 1
SET statement_timeout = '30min';

-- 1. The orgs -------------------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS research.wis_profile CASCADE;
CREATE TABLE research.wis_profile AS
SELECT c.ein, o.name, o.state, o.ruling_year, o.ntee, o.latest_filing_year, o.latest_total_revenue,
       o.latest_filing_year >= 2023 AS still_filing,
       c.r1, c.r3, c.r4, c.r5, c.r6, c.r7
FROM research.wis_rows2 c JOIN organizations o USING (ein);
ALTER TABLE research.wis_profile ADD PRIMARY KEY (ein);

-- 2. Year by year: revenue, contributions, officer comp, top-paid person ---------------------------------------------
DROP TABLE IF EXISTS research.wis_years;
CREATE TABLE research.wis_years AS
WITH f AS (SELECT DISTINCT ON (f.ein, f.tax_year) f.*
           FROM filings f JOIN research.wis_profile p USING (ein)
           ORDER BY f.ein, f.tax_year, f.superseded, f.filed_date DESC NULLS LAST, f.id DESC),
top AS (SELECT DISTINCT ON (pe.filing_id) pe.filing_id, pe.name_raw, pe.title, pe.comp_org
        FROM people pe JOIN f ON f.id = pe.filing_id
        WHERE NOT coalesce(pe.is_duplicate, false) AND coalesce(pe.comp_org, 0) > 0
        ORDER BY pe.filing_id, pe.comp_org DESC),
n50 AS (SELECT pe.filing_id, count(*) AS n50 FROM people pe JOIN f ON f.id = pe.filing_id
        WHERE NOT coalesce(pe.is_duplicate, false) AND pe.comp_org >= 50000 GROUP BY 1)
SELECT f.ein, f.tax_year, f.tax_year - p.ruling_year AS k, f.form_type, f.id AS filing_id,
       f.total_revenue, f.contributions, f.officer_comp_total AS officer_comp,
       t.comp_org AS top_comp, t.name_raw AS top_name, t.title AS top_title, coalesce(n.n50, 0) AS n50
FROM f JOIN research.wis_profile p USING (ein)
LEFT JOIN top t ON t.filing_id = f.id LEFT JOIN n50 n ON n.filing_id = f.id;
CREATE INDEX ON research.wis_years (ein, tax_year);

-- 3. Funders: every Schedule I grant into a cohort org ----------------------------------------------------------------
DROP TABLE IF EXISTS research.wis_funders;
CREATE TABLE research.wis_funders AS
SELECT g.recipient_ein AS ein, g.ein AS grantor_ein, coalesce(go.name, gf.org_name) AS grantor_name, g.tax_year,
       coalesce(g.cash_amount, 0) + coalesce(g.noncash_amount, 0) AS amount, g.purpose
FROM grants g JOIN research.wis_profile p ON p.ein = g.recipient_ein
JOIN filings gf ON gf.id = g.filing_id AND NOT gf.superseded
LEFT JOIN organizations go ON go.ein = g.ein
WHERE NOT coalesce(g.is_summary, false);

-- 4. Summary against the pay-study baselines --------------------------------------------------------------------------
-- Per-org pay facts on the npay_years definitions (founded 2010-2020), for the cohort and for everyone.
DROP TABLE IF EXISTS research.wis_summary;
CREATE TABLE research.wis_summary AS
WITH o AS (SELECT y.ein, (y.ein IN (SELECT ein FROM research.wis_profile)) AS in_cohort,
                  min(y.k) FILTER (WHERE y.paid) AS first_paid_k, bool_or(y.paid) AS ever_paid,
                  max(y.n50) AS max_n50
           FROM research.npay_years y GROUP BY y.ein),
k AS (SELECT y.k, y.top_comp, (y.ein IN (SELECT ein FROM research.wis_profile)) AS in_cohort
      FROM research.npay_years y WHERE y.k IN (1, 3, 5)),
grp(g, cohort) AS (VALUES ('women-in-space cohort, founded 2010-2020', true), ('all nonprofits founded 2010-2020 (baseline)', false))
SELECT grp.g AS group_,
       (SELECT count(*) FROM o WHERE in_cohort OR NOT grp.cohort) AS orgs,
       (SELECT count(*) FROM o WHERE (in_cohort OR NOT grp.cohort) AND ever_paid) AS ever_paid,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY first_paid_k) FROM o
         WHERE (in_cohort OR NOT grp.cohort) AND ever_paid) AS median_years_to_first_pay,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY top_comp) FROM k WHERE (in_cohort OR NOT grp.cohort) AND k = 1) AS median_top_comp_y1,
       (SELECT count(*) FROM k WHERE (in_cohort OR NOT grp.cohort) AND k = 1) AS n_y1,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY top_comp) FROM k WHERE (in_cohort OR NOT grp.cohort) AND k = 3) AS median_top_comp_y3,
       (SELECT count(*) FROM k WHERE (in_cohort OR NOT grp.cohort) AND k = 3) AS n_y3,
       (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY top_comp) FROM k WHERE (in_cohort OR NOT grp.cohort) AND k = 5) AS median_top_comp_y5,
       (SELECT count(*) FROM k WHERE (in_cohort OR NOT grp.cohort) AND k = 5) AS n_y5,
       (SELECT round(avg((max_n50 >= 2)::int), 3) FROM o WHERE in_cohort OR NOT grp.cohort) AS share_ever_two_paid_50k
FROM grp;

-- Whole cohort (any founding year): size, still filing, revenue
DROP TABLE IF EXISTS research.wis_cohort_stats;
CREATE TABLE research.wis_cohort_stats AS
SELECT count(*) AS orgs, count(*) FILTER (WHERE still_filing) AS still_filing,
       count(*) FILTER (WHERE ruling_year BETWEEN 2010 AND 2020) AS founded_2010_2020,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY latest_total_revenue) AS median_latest_revenue,
       count(latest_total_revenue) AS n_revenue,
       (SELECT count(DISTINCT ein) FROM research.wis_funders) AS orgs_with_listed_grants,
       (SELECT count(*) FROM research.wis_funders) AS grant_lines,
       (SELECT sum(amount) FROM research.wis_funders) AS grant_dollars
FROM research.wis_profile;

SELECT * FROM research.wis_cohort_stats;
SELECT * FROM research.wis_summary;
