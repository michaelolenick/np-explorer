-- Task 3: candidate links between public payroll names and 990 people (prepare only; nothing on the site uses this).
-- Small lookup of distinct payroll institutions (a few hundred rows) so the view does not scan 6M rows to find them.
CREATE TABLE IF NOT EXISTS unipay.payroll_institutions (
  state char(2) NOT NULL,
  institution text NOT NULL,
  inst_norm text NOT NULL,
  n_rows integer,
  PRIMARY KEY (state, institution)
);
TRUNCATE unipay.payroll_institutions;
INSERT INTO unipay.payroll_institutions (state, institution, inst_norm, n_rows)
SELECT state, institution,
       btrim(regexp_replace(regexp_replace(lower(replace(institution, '''', '')), '[^a-z0-9 ]+', ' ', 'g'), '\s+', ' ', 'g')),
       count(*)
FROM unipay.public_payroll_records WHERE institution IS NOT NULL GROUP BY 1, 2;

CREATE INDEX IF NOT EXISTS public_payroll_records_inst ON unipay.public_payroll_records (state, institution);
CREATE INDEX IF NOT EXISTS public_payroll_records_name ON unipay.public_payroll_records (name_norm);

-- 990 filers that are the institution itself (same normalized name, same state) or an affiliated foundation
-- (organization name contains the institution name and the word 'foundation', same state).
CREATE OR REPLACE VIEW unipay.payroll_institution_990_orgs AS
SELECT i.state, i.institution, o.ein, o.name AS org_name,
       CASE WHEN o.name_norm = i.inst_norm OR o.name_norm = 'the ' || i.inst_norm THEN 'institution' ELSE 'foundation' END AS org_relation
FROM unipay.payroll_institutions i
JOIN public.organizations o
  ON o.state = i.state
 AND (o.name_norm = i.inst_norm OR o.name_norm = 'the ' || i.inst_norm
      OR (o.name_norm LIKE '%' || i.inst_norm || '%' AND o.name_norm LIKE '%foundation%'))
WHERE length(i.inst_norm) >= 8;

-- EXACT: same normalized name at a matching 990 filer. FUZZY: trigram similarity >= 0.9 at a matching filer,
-- blocked on the same last-name token (np_last_name) to keep the comparison set small.
CREATE OR REPLACE VIEW unipay.payroll_990_link_candidates AS
SELECT 'EXACT'::text AS match_type, 1.0::real AS name_similarity,
       r.id AS payroll_record_id, r.state, r.institution, r.person_name, r.name_norm, r.title AS payroll_title,
       r.fiscal_year, r.base_pay, r.total_pay,
       p.id AS people_id, p.name_raw AS people_name, p.title AS people_title, p.tax_year, p.comp_org, p.comp_related, p.other_comp,
       o.ein, o.org_name, o.org_relation
FROM unipay.public_payroll_records r
JOIN unipay.payroll_institution_990_orgs o ON o.state = r.state AND o.institution = r.institution
JOIN public.people p ON p.ein = o.ein AND p.name_norm = r.name_norm AND NOT p.is_duplicate
UNION ALL
SELECT 'FUZZY', similarity(p.name_norm, r.name_norm),
       r.id, r.state, r.institution, r.person_name, r.name_norm, r.title,
       r.fiscal_year, r.base_pay, r.total_pay,
       p.id, p.name_raw, p.title, p.tax_year, p.comp_org, p.comp_related, p.other_comp,
       o.ein, o.org_name, o.org_relation
FROM unipay.public_payroll_records r
JOIN unipay.payroll_institution_990_orgs o ON o.state = r.state AND o.institution = r.institution
JOIN public.people p ON p.ein = o.ein AND NOT p.is_duplicate
 AND public.np_last_name(p.name_norm) = public.np_last_name(r.name_norm)
 AND p.name_norm <> r.name_norm
 AND similarity(p.name_norm, r.name_norm) >= 0.9;

COMMENT ON VIEW unipay.payroll_990_link_candidates IS
  'Proposed (unreviewed) links between public payroll rows and 990 people at the same institution or its affiliated foundations. EXACT = same normalized name; FUZZY = trigram similarity >= 0.9 with same last name.';
