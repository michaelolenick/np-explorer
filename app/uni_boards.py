"""University boards: public university payroll, coaches (payroll blended with 990s), and the Schools list.

Same contract as the other boards (app/boards.py): each is a materialized view with the standard leading
columns, plus org_url (the institution or organization link) and source_url (the published payroll list).
tax_year holds the fiscal year as the payroll publisher reports it. Tables come from loader/colleges.py.
"""

from __future__ import annotations

PAY_FLOOR = 150_000          # Highest-paid public university employees
ATHLETICS_FLOOR = 100_000
JUMP_PRIOR_MIN = 50_000
JUMP_MIN = 50_000
HE_NTEE = r"^B(4[0-3]|50)"
TRUNCATED = "('tx', 'ok')"   # sources that publish initials only: each row is its own subject

# A payroll person's stable key: their person page when linked, else employer + name (+ row for initials-only names).
PAYROLL_KEY = (f"coalesce(l.cluster_id::text, 'payroll:' || p.state || ':' || p.label || ':' || coalesce(p.name_norm, '') "
               f"|| CASE WHEN p.withheld OR p.source_key IN {TRUNCATED} THEN ':' || p.id ELSE '' END)")
PAYROLL_NAME = "CASE WHEN p.withheld THEN 'Name withheld' ELSE p.person_name END"
INST_NAME = "coalesce(c.name, p.label)"
INST_URL = "CASE WHEN p.unitid IS NOT NULL THEN '/institution/' || p.unitid END"
ADMIN = (r"\m(president|chancellor|provost|vice president|vice chancellor|vp|dean|chief [a-z ]*officer|cfo|coo|cio|"
         r"general counsel|athletic director|director of athletics|executive director|treasurer)\M")
NOT_ADMIN = r"\m(assistant to|asst to|secretary|coordinator|specialist|assistant|associate|analyst|administrative assistant)\M"
COACH_TABLE_NOTES = [
    "From university payroll: pay as the state or university publishes it (see each row's source). From nonprofit "
    "(990): reportable pay from the organization plus other compensation, from its Form 990. Related-organization pay "
    "on a 990 can include pay from the university itself, so it is shown but never added.",
    "Combined appears only when the person link is EXACT (same full name at the same institution or one of its "
    "affiliated nonprofits) and both are for the same year. FUZZY links are shown as separate rows with their tag.",
    "When the same coach appears on more than one 990 for a year, only the filing with the largest total is used, "
    "so a payment reported on two returns is counted once.",
    "Private universities have no state payroll; they appear only through their own 990s and their foundations'.",
]


def _std_payroll(value: str) -> str:
    """Standard columns for a payroll person-year row (alias p, links l, colleges c)."""
    return (f"CASE WHEN l.cluster_id IS NOT NULL THEN 'person' ELSE 'payroll' END AS subject_kind, "
            f"{PAYROLL_KEY} AS subject_key, {PAYROLL_NAME} AS subject_name, "
            f"trim(regexp_replace(lower({PAYROLL_NAME}), '[^a-z0-9]+', ' ', 'g')) AS subject_norm, "
            f"CASE WHEN l.cluster_id IS NOT NULL THEN '/person/' || l.cluster_id END AS subject_url, "
            f"l.match::text AS match, NULL::text AS ein, {INST_NAME} AS org_name, {INST_URL} AS org_url, "
            f"p.state::text AS state, NULL::text AS form_type, p.fiscal_year::int AS tax_year, "
            f"NULL::bigint AS filing_id, NULL::text AS object_id, ({value})::numeric AS value, "
            f"p.source_url, s.title AS source_title, s.pay_basis, p.unitid, l.evidence AS link_evidence")


PAYROLL_FROM = """FROM payroll_person_years p
        JOIN payroll_sources s ON s.source_key = p.source_key
        LEFT JOIN payroll_person_links l ON l.state = p.state AND l.label = p.label AND l.name_norm = p.name_norm
                                          AND NOT p.withheld
        LEFT JOIN colleges c ON c.unitid = p.unitid"""


def ranked_latest(inner: str, order: str) -> str:
    """Like boards._ranked_by_org, but each subject's default row is its LATEST year (ties: highest value)."""
    return (f"SELECT row_number() OVER (ORDER BY {order}) AS pos, rank() OVER (ORDER BY {order.split(',')[0]}) AS rank, "
            f"CASE WHEN y.org_rn = 1 THEN row_number() OVER (PARTITION BY y.org_rn = 1 ORDER BY {order}) END AS org_pos, "
            f"y.* FROM (SELECT x.*, row_number() OVER (PARTITION BY x.subject_key "
            f"ORDER BY x.tax_year DESC NULLS LAST, x.value DESC NULLS LAST) AS org_rn FROM ({inner}) x) y")


def ranked_best(inner: str, order: str) -> str:
    """Each subject's default row is its highest-value row (as boards._ranked_by_org)."""
    return (f"SELECT row_number() OVER (ORDER BY {order}) AS pos, rank() OVER (ORDER BY {order.split(',')[0]}) AS rank, "
            f"CASE WHEN y.org_rn = 1 THEN row_number() OVER (PARTITION BY y.org_rn = 1 ORDER BY {order}) END AS org_pos, "
            f"y.* FROM (SELECT x.*, row_number() OVER (PARTITION BY x.subject_key ORDER BY {order}) AS org_rn "
            f"FROM ({inner}) x) y")


def top_paid() -> str:
    inner = f"""SELECT {_std_payroll('p.total_pay')}, p.title, p.department
        {PAYROLL_FROM}
        WHERE p.total_pay >= {PAY_FLOOR} AND p.fiscal_year IS NOT NULL"""
    return ranked_best(inner, "value DESC NULLS LAST, subject_norm, tax_year DESC")


ATHLETIC_ROW = r"""(p.department ~* '\m(athletic|athletics|intercollegiate|sports?)\M'
                    OR p.title ~* '\m(athletic director|director of athletics|athletics)\M'
                    OR EXISTS (SELECT 1 FROM coach_titles ct WHERE ct.src = 'payroll' AND ct.title = p.title
                               AND ct.department = coalesce(p.department, '') AND ct.is_coach))"""


def athletics() -> str:
    inner = f"""SELECT {_std_payroll('p.total_pay')}, p.title, p.department,
               ct.sport, ct.role
        {PAYROLL_FROM}
        LEFT JOIN coach_titles ct ON ct.src = 'payroll' AND ct.title = p.title AND ct.department = coalesce(p.department, '')
                                 AND ct.is_coach
        WHERE p.total_pay >= {ATHLETICS_FLOOR} AND p.fiscal_year IS NOT NULL AND {ATHLETIC_ROW}"""
    return ranked_best(inner, "value DESC NULLS LAST, subject_norm, tax_year DESC")


def pay_jump() -> str:
    inner = f"""SELECT {_std_payroll('p.total_pay - q.total_pay')}, p.title, q.title AS prior_title,
               q.total_pay AS prior_pay, p.total_pay AS pay, round(p.total_pay / nullif(q.total_pay, 0), 2) AS multiple
        {PAYROLL_FROM}
        JOIN payroll_person_years q ON q.source_key = p.source_key AND q.state = p.state AND q.label = p.label
             AND q.name_norm = p.name_norm AND q.fiscal_year = p.fiscal_year - 1 AND NOT q.withheld
        WHERE NOT p.withheld AND p.name_norm IS NOT NULL AND p.source_key NOT IN {TRUNCATED}
          AND q.total_pay >= {JUMP_PRIOR_MIN} AND p.total_pay - q.total_pay >= {JUMP_MIN}
          AND NOT EXISTS (SELECT 1 FROM payroll_person_years d WHERE d.state = p.state AND d.label = p.label
                          AND d.name_norm = p.name_norm AND d.fiscal_year IN (p.fiscal_year, p.fiscal_year - 1)
                          AND d.id NOT IN (p.id, q.id))"""
    return ranked_best(inner, "value DESC NULLS LAST, subject_norm, tax_year DESC")


def admin_faculty() -> str:
    inner = f"""
        WITH adm AS (
            SELECT p.unitid, p.fiscal_year, count(*) AS n_admin,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY p.total_pay) AS admin_median,
                   max(p.total_pay) AS admin_max,
                   (array_agg(p.person_name || ' (' || p.title || ')' ORDER BY p.total_pay DESC))[1] AS top_admin
            FROM payroll_person_years p
            WHERE p.unitid IS NOT NULL AND NOT p.withheld AND p.total_pay > 0
              AND p.title ~* '{ADMIN}' AND p.title !~* '{NOT_ADMIN}'
            GROUP BY p.unitid, p.fiscal_year HAVING count(*) >= 3),
        fac AS (
            SELECT unitid, (left(academic_year, 4)::int + 1) AS fiscal_year,
                   max(avg_salary) FILTER (WHERE arank = 1) AS prof_avg,
                   max(avg_salary) FILTER (WHERE arank = 7) AS all_avg,
                   max(staff_count) FILTER (WHERE arank = 7) AS faculty_count
            FROM college_faculty_salaries WHERE academic_year ~ '^\\d{{4}}' GROUP BY 1, 2)
        SELECT 'org'::text AS subject_kind, a.unitid::text AS subject_key, c.name AS subject_name,
               c.name_norm AS subject_norm, '/institution/' || a.unitid AS subject_url, NULL::text AS match,
               NULL::text AS ein, c.name AS org_name, '/institution/' || a.unitid AS org_url, c.state::text AS state,
               NULL::text AS form_type, a.fiscal_year::int AS tax_year, NULL::bigint AS filing_id,
               NULL::text AS object_id, round((a.admin_median / nullif(f.all_avg, 0))::numeric, 2) AS value,
               NULL::text AS source_url, a.unitid, a.n_admin, a.admin_median, a.admin_max, a.top_admin,
               f.prof_avg, f.all_avg, f.faculty_count, c.control
        FROM adm a JOIN fac f ON f.unitid = a.unitid AND f.fiscal_year = a.fiscal_year
        JOIN colleges c ON c.unitid = a.unitid
        WHERE f.all_avg > 0"""
    return ranked_latest(inner, "value DESC NULLS LAST, subject_norm, tax_year DESC")


def coaches() -> str:
    inner = f"""
    WITH pc AS (
        SELECT p.*, ct.sport, ct.role, l.cluster_id, l.match, l.evidence, s.title AS source_title, s.pay_basis
        FROM payroll_person_years p
        JOIN payroll_sources s ON s.source_key = p.source_key
        JOIN coach_titles ct ON ct.src = 'payroll' AND ct.title = p.title AND ct.department = coalesce(p.department, '')
                             AND ct.is_coach
        LEFT JOIN payroll_person_links l ON l.state = p.state AND l.label = p.label AND l.name_norm = p.name_norm
                                          AND NOT p.withheld
        WHERE coalesce(p.total_pay, 0) > 0 AND p.fiscal_year IS NOT NULL),
    -- Each person's 990 rows: per person and tax year, the one filing with the largest total (a payment
    -- reported on two returns, e.g. as related-organization pay, is counted once).
    np AS (
        SELECT DISTINCT ON (m.cluster_id, p.tax_year) m.cluster_id, p.tax_year, p.ein, p.title, f.id AS filing_id,
               f.object_id, f.form_type, coalesce(o.name, f.org_name) AS org_name, f.state, o.ntee,
               p.comp_org, p.comp_related, p.other_comp,
               coalesce(p.comp_org, 0) + coalesce(p.other_comp, 0) AS own_pay,
               coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0) AS total
        FROM people p JOIN filings f ON f.id = p.filing_id
        JOIN person_cluster_members m ON m.person_id = p.id
        LEFT JOIN organizations o ON o.ein = p.ein
        WHERE NOT f.superseded AND NOT p.is_duplicate AND p.tax_year IS NOT NULL
          AND (EXISTS (SELECT 1 FROM coach_titles ct WHERE ct.src = '990' AND ct.title = p.title AND ct.is_coach)
               OR m.cluster_id IN (SELECT cluster_id FROM pc WHERE match = 'EXACT'))
        ORDER BY m.cluster_id, p.tax_year, total DESC, p.id),
    -- EXACT payroll links with a 990 row the same year at the same institution or an affiliated nonprofit.
    combo AS (
        SELECT pc.id AS payroll_id, np.*
        FROM pc JOIN np ON np.cluster_id = pc.cluster_id AND np.tax_year = pc.fiscal_year
        JOIN college_orgs co ON co.unitid = pc.unitid AND co.ein = np.ein
        WHERE pc.match = 'EXACT' AND np.own_pay > 0),
    nc AS (
        SELECT np.*, ct.sport, ct.role,
               (SELECT co.unitid FROM college_orgs co WHERE co.ein = np.ein ORDER BY co.match LIMIT 1) AS unitid
        FROM np JOIN coach_titles ct ON ct.src = '990' AND ct.title = np.title AND ct.is_coach
        WHERE np.total > 0
          AND NOT EXISTS (SELECT 1 FROM combo WHERE combo.cluster_id = np.cluster_id AND combo.tax_year = np.tax_year))
    SELECT 'person'::text AS subject_kind, pc.cluster_id::text AS subject_key, pc.person_name AS subject_name,
           trim(regexp_replace(lower(pc.person_name), '[^a-z0-9]+', ' ', 'g')) AS subject_norm,
           '/person/' || pc.cluster_id AS subject_url, 'EXACT'::text AS match, combo.ein,
           coalesce(c.name, pc.label) AS org_name, '/institution/' || pc.unitid AS org_url, pc.state::text AS state,
           combo.form_type, pc.fiscal_year::int AS tax_year, combo.filing_id, combo.object_id,
           (pc.total_pay + combo.own_pay)::numeric AS value,
           pc.source_url, pc.unitid, pc.sport, pc.role, 'Public payroll; University or foundation 990'::text AS source_type,
           pc.title, pc.total_pay AS from_payroll, combo.own_pay::numeric AS from_nonprofit,
           combo.comp_related::numeric AS related_not_added, (pc.total_pay + combo.own_pay)::numeric AS combined,
           combo.org_name AS nonprofit_name, pc.evidence AS link_evidence
    FROM pc JOIN combo ON combo.payroll_id = pc.id LEFT JOIN colleges c ON c.unitid = pc.unitid
    UNION ALL
    SELECT CASE WHEN pc.cluster_id IS NOT NULL THEN 'person' ELSE 'payroll' END,
           -- A FUZZY link never merges rows: the payroll row keeps its own key (and still links, tagged).
           CASE WHEN pc.match = 'EXACT' THEN pc.cluster_id::text
                ELSE 'payroll:' || pc.state || ':' || pc.label || ':' || coalesce(pc.name_norm, '')
                     || CASE WHEN pc.withheld OR pc.source_key IN {TRUNCATED} THEN ':' || pc.id ELSE '' END END,
           CASE WHEN pc.withheld THEN 'Name withheld' ELSE pc.person_name END,
           trim(regexp_replace(lower(coalesce(pc.person_name, '')), '[^a-z0-9]+', ' ', 'g')),
           CASE WHEN pc.cluster_id IS NOT NULL THEN '/person/' || pc.cluster_id END, pc.match, NULL,
           coalesce(c.name, pc.label), CASE WHEN pc.unitid IS NOT NULL THEN '/institution/' || pc.unitid END,
           pc.state::text, NULL, pc.fiscal_year::int, NULL, NULL, pc.total_pay::numeric,
           pc.source_url, pc.unitid, pc.sport, pc.role, 'Public payroll', pc.title, pc.total_pay, NULL, NULL, NULL,
           NULL, pc.evidence
    FROM pc LEFT JOIN colleges c ON c.unitid = pc.unitid
    WHERE NOT EXISTS (SELECT 1 FROM combo WHERE combo.payroll_id = pc.id)
    UNION ALL
    SELECT 'person', nc.cluster_id::text, pcl.display_name, pcl.name_norm, '/person/' || nc.cluster_id,
           CASE WHEN pcl.evidence @> '[{{"r": "variant"}}]' OR pcl.evidence @> '[{{"r": "care_of"}}]'
                THEN 'FUZZY' ELSE 'EXACT' END,
           nc.ein, nc.org_name, '/org/' || nc.ein, nc.state::text, nc.form_type, nc.tax_year::int, nc.filing_id,
           nc.object_id, nc.total::numeric, NULL, nc.unitid, nc.sport, nc.role,
           CASE WHEN nc.unitid IS NOT NULL OR nc.ntee ~ '{HE_NTEE}'
                     OR nc.org_name ~* '\\m(university|college|boosters?)\\M'
                     OR (nc.org_name ~* '\\mathletics? (foundation|fund|association)\\M' AND nc.org_name !~* '\\m(youth|little league|aau)\\M')
                THEN 'University or foundation 990' ELSE 'Other nonprofit 990' END,
           nc.title, NULL, nc.own_pay::numeric, nc.comp_related::numeric, NULL, NULL, NULL
    FROM nc JOIN person_clusters pcl ON pcl.id = nc.cluster_id"""
    return ranked_latest(inner, "value DESC NULLS LAST, subject_norm, tax_year DESC")


def schools() -> str:
    inner = """
        SELECT 'school'::text AS subject_kind, s.unitid::text AS subject_key, s.name AS subject_name,
               s.name_norm AS subject_norm, '/institution/' || s.unitid AS subject_url, NULL::text AS match,
               s.self_ein AS ein, s.name AS org_name, '/institution/' || s.unitid AS org_url, s.state::text AS state,
               NULL::text AS form_type, s.fiscal_year::int AS tax_year, NULL::bigint AS filing_id,
               NULL::text AS object_id, s.sort_value AS value, NULL::text AS source_url,
               s.unitid, s.fiscal_year, s.latest, s.name, s.name_norm, s.city, s.control, s.sector, s.enrollment, s.international, s.country, s.payroll_total, s.headcount, s.payroll_years, s.payroll_sources, s.top_person, s.top_title, s.top_pay, s.top_url, s.fac_prof, s.fac_assoc, s.fac_asst, s.fac_year, s.n_orgs, s.n_orgs_fuzzy, s.has_orgs, s.org_revenue, s.org_expenses, s.org_net_assets, s.org_year, s.org_top_person, s.org_top_pay, s.org_top_url, s.org_top_org, s.self_ein, s.self_expenses, s.grants_received, s.n_funders, s.top_funder, s.top_funder_ein, s.top_funder_total, s.event_direct, s.event_net, s.coach_name, s.coach_pay, s.coach_sport, s.coach_url, s.coach_year, s.sort_value, s.sort_basis
        FROM school_rows s"""
    return ranked_latest(inner, "value DESC NULLS LAST, subject_norm, tax_year DESC")
