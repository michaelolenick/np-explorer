-- How long does a new nonprofit take to start paying anyone, and how much? (owner, 2026-10-27)
--
-- Rerun:  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f research/new_nonprofit_pay.sql
--
-- Builds two tables once (research.npay_years: one row per org per tax year; research.npay_orgs: one row per org),
-- then every statistic below reads only those. Medians only (percentile_cont 0.5), zeros kept, n beside every number.
--
-- Definitions
--   founding year  organizations.ruling_year (the IRS ruling year from the current Business Master File). The IRS
--                  does not publish a founding date; orgs no longer in the BMF (revoked, terminated) have none and
--                  are therefore not in any cohort.
--   cohort         founding years 2010-2020, every 990 / 990-EZ filer type (501(c)(3) is ~91%). 990-PF excluded.
--   year k         tax_year - founding year (year 1 = the tax year after the ruling year).
--   return         990 and 990-EZ e-filed returns only; one per org per tax year (the original unless superseded,
--                  else the latest filed). 990-N (e-Postcard) has no money fields: used only to flag switching.
--   officer_comp   990: Part I line 5 (filings.officer_comp_total), else the Part VII total; 990-EZ: Part IV
--                  compensation column summed. Zero when the return lists nobody paid.
--   salaries       990: Part IX lines 5+6+7 (officers + disqualified persons + other salaries and wages);
--                  990-EZ: line 12 (salaries, other compensation AND employee benefits: the EZ has no split).
--                  NULL when the return's expense lines weren't parsed.
--   top_comp       highest single compensation from the organization (990 Part VII-A, 990-EZ Part IV and the EZ
--                  highest-paid-employee list), reportable comp from the org only, not related orgs.
--   paid           any of the three > 0.
--   n50            people on the return paid >= $50,000 by the org.
--   size bucket    the org's peak total revenue over all its 990 / 990-EZ returns.
-- Dollars are nominal (not inflation-adjusted).

\set ON_ERROR_STOP 1
SET statement_timeout = '15min';
CREATE SCHEMA IF NOT EXISTS research;
DROP TABLE IF EXISTS research.npay_years, research.npay_orgs;

-- 1. The cohorts ---------------------------------------------------------------------------------------------------
CREATE TABLE research.npay_orgs AS
SELECT ein, ruling_year AS founded, subsection
FROM organizations
WHERE in_bmf AND ruling_year BETWEEN 2010 AND 2020;
ALTER TABLE research.npay_orgs ADD PRIMARY KEY (ein);
-- Cohorts are 27k-72k orgs; no sampling was needed. To sample instead, keep 50,000 per cohort:
-- DELETE FROM research.npay_orgs o USING (SELECT ein, row_number() OVER (PARTITION BY founded ORDER BY md5(ein)) r
--   FROM research.npay_orgs) s WHERE s.ein = o.ein AND s.r > 50000;

-- 2. One row per org per tax year, built one cohort at a time (each statement under the timeout) ------------------
CREATE TABLE research.npay_years (
    ein text, founded int, tax_year int, k int, form_type text, filing_id bigint,
    total_revenue bigint, officer_comp bigint, salaries bigint, top_comp bigint, n50 int, paid boolean);

SELECT format($q$
INSERT INTO research.npay_years
WITH f AS (
    SELECT DISTINCT ON (f.ein, f.tax_year)
           f.id, f.ein, o.founded, f.tax_year, f.form_type, f.total_revenue, f.officer_comp_total
    FROM research.npay_orgs o
    JOIN filings f ON f.ein = o.ein
    WHERE o.founded = %1$s AND f.form_type IN ('990', '990EZ') AND f.tax_year IS NOT NULL
    ORDER BY f.ein, f.tax_year, coalesce(f.superseded, false), f.filed_date DESC NULLS LAST, f.object_id DESC
), p AS (
    SELECT p.filing_id,
           sum(p.comp_org) FILTER (WHERE p.source IN ('990-VIIA', '990EZ-IV')) AS listed_comp,
           max(p.comp_org) AS top_comp,
           count(*) FILTER (WHERE p.comp_org >= 50000) AS n50
    FROM people p
    WHERE p.filing_id IN (SELECT id FROM f)
      AND p.source IN ('990-VIIA', '990EZ-IV', '990EZ-HCE') AND NOT coalesce(p.is_duplicate, false)
    GROUP BY 1
), e AS (
    SELECT e.filing_id,
           CASE WHEN jsonb_array_length(e.lines) > 0 THEN
               (SELECT coalesce(sum((l->>3)::bigint), 0) FROM jsonb_array_elements(e.lines) l
                WHERE l->>0 IN ('pay_officers', 'pay_disqualified', 'pay_other', 'pay')) END AS salaries
    FROM expense_breakdown e
    WHERE e.filing_id IN (SELECT id FROM f)
)
SELECT f.ein, f.founded, f.tax_year, f.tax_year - f.founded, f.form_type, f.id, f.total_revenue,
       CASE WHEN f.form_type = '990' THEN coalesce(f.officer_comp_total, p.listed_comp, 0)
            ELSE coalesce(p.listed_comp, 0) END,
       e.salaries,
       coalesce(p.top_comp, 0),
       coalesce(p.n50, 0)::int,
       false
FROM f LEFT JOIN p ON p.filing_id = f.id LEFT JOIN e ON e.filing_id = f.id
$q$, y) FROM generate_series(2010, 2020) y
\gexec

UPDATE research.npay_years SET paid = (officer_comp > 0 OR coalesce(salaries, 0) > 0 OR top_comp > 0);
CREATE INDEX ON research.npay_years (ein, tax_year);
ANALYZE research.npay_years;

-- 3. One row per org ----------------------------------------------------------------------------------------------
ALTER TABLE research.npay_orgs
    ADD COLUMN returns int, ADD COLUMN first_return int, ADD COLUMN last_return int, ADD COLUMN pre_ruling int,
    ADD COLUMN peak_revenue bigint, ADD COLUMN size text, ADD COLUMN first_paid int, ADD COLUMN first_2x50k int,
    ADD COLUMN n990n int, ADD COLUMN switches int, ADD COLUMN ez_salary_null int;

UPDATE research.npay_orgs o SET
    returns = y.returns, first_return = y.first_return, last_return = y.last_return, pre_ruling = y.pre_ruling,
    peak_revenue = y.peak, first_paid = y.first_paid, first_2x50k = y.first_2x50k, ez_salary_null = y.sal_null,
    size = CASE WHEN y.peak IS NULL THEN NULL WHEN y.peak < 100000 THEN '1 under $100K'
                WHEN y.peak < 500000 THEN '2 $100K-$500K' WHEN y.peak < 1000000 THEN '3 $500K-$1M' ELSE '4 over $1M' END
FROM (SELECT ein, count(*) returns, min(tax_year) first_return, max(tax_year) last_return,
             count(*) FILTER (WHERE k < 0) pre_ruling, max(total_revenue) peak,
             min(tax_year) FILTER (WHERE paid) first_paid, min(tax_year) FILTER (WHERE n50 >= 2) first_2x50k,
             count(*) FILTER (WHERE salaries IS NULL) sal_null
      FROM research.npay_years GROUP BY ein) y
WHERE y.ein = o.ein;

-- 990-N years, and switches between 990-N and a 990 / 990-EZ from one filed tax year to the next
UPDATE research.npay_orgs o SET n990n = s.n990n, switches = s.switches
FROM (SELECT ein, count(*) FILTER (WHERE form = 'N') n990n,
             count(*) FILTER (WHERE prev IS NOT NULL AND (prev = 'N') <> (form = 'N')) switches
      FROM (SELECT ein, form, lag(form) OVER (PARTITION BY ein ORDER BY tax_year) prev
            FROM (SELECT y.ein, y.tax_year, 'R' form FROM research.npay_years y
                  UNION
                  SELECT n.ein, n.tax_year, 'N' FROM irs_epostcard n JOIN research.npay_orgs c ON c.ein = n.ein
                  WHERE NOT EXISTS (SELECT 1 FROM research.npay_years y WHERE y.ein = n.ein AND y.tax_year = n.tax_year)
                 ) a) b
      GROUP BY ein) s
WHERE s.ein = o.ein;
UPDATE research.npay_orgs SET n990n = coalesce(n990n, 0), switches = coalesce(switches, 0), returns = coalesce(returns, 0);
ANALYZE research.npay_orgs;


-- ================================================ STATISTICS =====================================================
-- "Filers" = cohort orgs with at least one 990 / 990-EZ return. Medians of years count from the founding year.

-- Q1. Share that ever paid anyone, and median years from founding to the first paid year, by cohort
SELECT founded AS cohort,
       count(*) AS cohort_orgs,
       count(*) FILTER (WHERE returns > 0) AS filers,
       round(100.0 * count(*) FILTER (WHERE first_paid IS NOT NULL) / nullif(count(*) FILTER (WHERE returns > 0), 0), 1)
           AS pct_filers_ever_paid,
       round(100.0 * count(*) FILTER (WHERE first_paid IS NOT NULL) / count(*), 1) AS pct_all_ever_paid,
       count(*) FILTER (WHERE first_paid IS NOT NULL) AS n_paid,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY first_paid - founded) AS median_years_to_first_pay,
       -- fixed windows: comparable across cohorts (later cohorts have had fewer years in which to start paying)
       round(100.0 * count(*) FILTER (WHERE first_paid - founded <= 3) / nullif(count(*) FILTER (WHERE returns > 0), 0), 1)
           AS pct_filers_paid_by_year3,
       round(100.0 * count(*) FILTER (WHERE first_paid - founded <= 5) / nullif(count(*) FILTER (WHERE returns > 0), 0), 1)
           AS pct_filers_paid_by_year5
FROM research.npay_orgs GROUP BY ROLLUP (founded) ORDER BY founded NULLS LAST;

-- Q1 sensitivity: "paid" meaning at least $1,000 in a year (some returns report $1-$9)
SELECT o.founded AS cohort, count(*) AS filers,
       count(f.first_1k) AS n_paid_1k,
       round(100.0 * count(f.first_1k) / count(*), 1) AS pct_ever_paid_1k,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY f.first_1k - o.founded) AS median_years_to_first_1k
FROM research.npay_orgs o
LEFT JOIN (SELECT ein, min(tax_year) first_1k FROM research.npay_years
           WHERE greatest(officer_comp, coalesce(salaries, 0), top_comp) >= 1000 GROUP BY ein) f USING (ein)
WHERE o.returns > 0
GROUP BY ROLLUP (o.founded) ORDER BY o.founded NULLS LAST;

-- Q2. Medians at years 1, 3, 5, 10: all filers that year (zeros kept), then orgs already paying by that year
SELECT y.founded AS cohort, y.k AS year,
       count(*) AS n_all,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.officer_comp) AS med_officer_comp_all,
       count(y.salaries) AS n_sal_all,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.salaries) AS med_salaries_all,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.top_comp) AS med_top_comp_all,
       count(*) FILTER (WHERE o.first_paid <= y.tax_year) AS n_paying,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.officer_comp) FILTER (WHERE o.first_paid <= y.tax_year) AS med_officer_comp_paying,
       count(y.salaries) FILTER (WHERE o.first_paid <= y.tax_year) AS n_sal_paying,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.salaries) FILTER (WHERE o.first_paid <= y.tax_year) AS med_salaries_paying,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.top_comp) FILTER (WHERE o.first_paid <= y.tax_year) AS med_top_comp_paying
FROM research.npay_years y JOIN research.npay_orgs o USING (ein)
WHERE y.k IN (1, 3, 5, 10)
GROUP BY ROLLUP (y.k, y.founded) HAVING y.k IS NOT NULL ORDER BY y.k, y.founded NULLS FIRST;

-- Q3a. Q1 by size bucket (filers only: the bucket needs a return), all cohorts together and by cohort
SELECT size, founded AS cohort, count(*) AS filers,
       count(*) FILTER (WHERE first_paid IS NOT NULL) AS n_paid,
       round(100.0 * count(*) FILTER (WHERE first_paid IS NOT NULL) / count(*), 1) AS pct_ever_paid,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY first_paid - founded) AS median_years_to_first_pay
FROM research.npay_orgs WHERE returns > 0 AND size IS NOT NULL
GROUP BY ROLLUP (size, founded) HAVING size IS NOT NULL ORDER BY size, founded NULLS FIRST;

-- Q3b. Q2 by size bucket, all cohorts together
SELECT o.size, y.k AS year,
       count(*) AS n_all,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.officer_comp) AS med_officer_comp_all,
       count(y.salaries) AS n_sal_all,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.salaries) AS med_salaries_all,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.top_comp) AS med_top_comp_all,
       count(*) FILTER (WHERE o.first_paid <= y.tax_year) AS n_paying,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.officer_comp) FILTER (WHERE o.first_paid <= y.tax_year) AS med_officer_comp_paying,
       count(y.salaries) FILTER (WHERE o.first_paid <= y.tax_year) AS n_sal_paying,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.salaries) FILTER (WHERE o.first_paid <= y.tax_year) AS med_salaries_paying,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY y.top_comp) FILTER (WHERE o.first_paid <= y.tax_year) AS med_top_comp_paying
FROM research.npay_years y JOIN research.npay_orgs o USING (ein)
WHERE y.k IN (1, 3, 5, 10) AND o.size IS NOT NULL
GROUP BY o.size, y.k ORDER BY o.size, y.k;

-- Q4. Two or more people paid >= $50K on the same return: share and median years from founding, by cohort and size
SELECT founded AS cohort, size, count(*) AS filers,
       count(*) FILTER (WHERE first_2x50k IS NOT NULL) AS n_2x50k,
       round(100.0 * count(*) FILTER (WHERE first_2x50k IS NOT NULL) / count(*), 1) AS pct_2x50k,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY first_2x50k - founded) AS median_years_to_2x50k
FROM research.npay_orgs WHERE returns > 0
GROUP BY GROUPING SETS ((founded), (size), ())
HAVING NOT (GROUPING(size) = 0 AND size IS NULL) ORDER BY founded NULLS LAST, size NULLS LAST;

-- Data quality ------------------------------------------------------------------------------------------------------
SELECT
    (SELECT count(*) FROM organizations WHERE NOT in_bmf) AS orgs_not_in_bmf_no_ruling_year,
    (SELECT count(*) FROM organizations WHERE in_bmf AND ruling_year IS NULL) AS bmf_orgs_missing_ruling_year,
    count(*) AS cohort_orgs,
    count(*) FILTER (WHERE returns = 0 AND n990n > 0) AS only_990n,
    count(*) FILTER (WHERE returns = 0 AND n990n = 0) AS no_990_990ez_or_990n,
    count(*) FILTER (WHERE returns > 0 AND n990n > 0) AS both_990n_and_990_ez,
    count(*) FILTER (WHERE switches >= 2) AS switched_twice_or_more,
    count(*) FILTER (WHERE pre_ruling > 0) AS returns_before_ruling_year,
    count(*) FILTER (WHERE first_paid < founded) AS first_paid_before_ruling_year,
    count(*) FILTER (WHERE returns > 0 AND last_return - first_return + 1 > returns) AS gaps_in_returns,
    count(*) FILTER (WHERE ez_salary_null > 0) AS orgs_with_unparsed_expense_lines
FROM research.npay_orgs;

SELECT form_type, count(*) AS returns,
       count(*) FILTER (WHERE salaries IS NULL) AS salaries_missing,
       count(*) FILTER (WHERE officer_comp > 0 AND coalesce(salaries, 0) = 0) AS officer_pay_but_no_salary_line,
       count(*) FILTER (WHERE top_comp > greatest(total_revenue, 0) * 5 AND top_comp > 250000) AS top_comp_over_5x_revenue,
       count(*) FILTER (WHERE total_revenue < 0) AS negative_revenue
FROM research.npay_years GROUP BY ROLLUP (form_type);
