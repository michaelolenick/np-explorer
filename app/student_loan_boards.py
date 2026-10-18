"""Leaderboards for student loan securitization trusts (data from SEC Form 10-D reports).

student_loan_boards() returns Board objects for app/boards.py to append to BOARDS; the
group entry (GROUP) goes in boards.GROUPS. Each board is a materialized view over
student_loan_trust_years (one row per trust per calendar year, built by
loader/student_loans.py) with the shared board columns:

  subject_kind 'trust', subject_key = the trust's CIK, subject_url = its trust page,
  ein / org_name = the sponsor (ein only where the sponsor matched a 990 filer),
  form_type '10-D', tax_year = the calendar year of the reports, filing_id / object_id NULL
  (the source report links from the trust page; there is no 990 filing).

Rates are percentages, displayed with the shared "ratio" format (two decimals) so the
shared sort treats them as numbers.
"""

from __future__ import annotations

# app.boards imports this module at its end, so its names are imported inside the functions.

GROUP_NAME = "student-loans"
GROUP = {"title": "Student loan securitizations", "subtitle": "Class of Debt",
         "definition": "Trusts holding pools of student loans that report to the SEC every month: the biggest "
                       "pools, the highest default, charge-off and delinquency rates, and where delinquency rose "
                       "fastest. From Form 10-D servicing reports."}

MIN_BALANCE = 25_000_000      # rate boards: pools under this are left out (a few loans swing the rate)
MIN_MONTHS = 6                # rate boards: at least this many monthly reports in the year

SOURCE = ("One row per trust per calendar year, from the trust's monthly servicing reports filed with the SEC "
          "(Form 10-D, or Form 8-K before 2006). The default view shows each trust once, at its top year; pick a "
          "year to see every trust that reported that year.")
FFELP_NOTE = ("FFELP loans are federally guaranteed: when a borrower defaults the guarantor pays the trust about "
              "97 to 100% of the loan, so a high FFELP default rate means many claims, not big losses. Private loans "
              "have no guarantee. The Program column says which is which.")
FAMILY_NOTE = ("Issuers define defaults, charge-offs and delinquency buckets differently. Each trust's page shows "
               "its issuer family's definitions.")


def _sql(value: str, where: str, order: str, extra: str = "") -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'trust'::text AS subject_kind, y.cik::text AS subject_key, t.name AS subject_name,
               {norm_sql('t.name')} AS subject_norm, '/student-loans/trust/' || y.cik AS subject_url,
               NULL::text AS match, p.ein, t.sponsor AS org_name, p.state, '10-D'::text AS form_type,
               y.year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, {value} AS value,
               coalesce(t.program_type, 'Not reported') AS program, to_char(y.last_period, 'YYYY-MM') AS as_of,
               y.months, y.pool_balance, y.loan_count {extra}
        FROM student_loan_trust_years y
        JOIN student_loan_trusts t ON t.cik = y.cik
        LEFT JOIN student_loan_parties p ON p.party = t.sponsor
        WHERE {value} IS NOT NULL AND {where}"""
    return _ranked_by_org(inner, order)


RATE_SCOPE = f"y.months >= {MIN_MONTHS} AND y.avg_balance >= {MIN_BALANCE}"


def student_loan_boards() -> list:
    """The boards, as app.boards.Board objects."""
    from app.boards import Board, Column
    common = [Column("program", "Program"), Column("as_of", "Latest report"), Column("months", "Reports", "num"),
              Column("pool_balance", "Pool balance", "money")]
    scope = (f"Rate boards: trust-years with at least {MIN_MONTHS} monthly reports and an average pool balance of "
             f"at least ${MIN_BALANCE:,}.")
    return [
        Board("student-loan-largest", "Largest student loan pools", "Mount Tuition",
              "The student loan trusts holding the most loan principal, by pool balance at the last report of "
              "each year.",
              f"Value = pool balance in the trust's last monthly report of the calendar year, as the issuer reports "
              f"it (principal, plus interest to be capitalized where the issuer includes it). {SOURCE}",
              _sql("y.pool_balance", "true", "value DESC, tax_year DESC, subject_key"),
              Column("value", "Pool balance", "money"),
              [Column("program", "Program"), Column("as_of", "Latest report"), Column("loan_count", "Loans", "num?")],
              ["A trust's balance falls every month as borrowers repay, consolidate or default; the largest "
               "pools are usually the newest."],
              per_org=True, forms=(), group=GROUP_NAME, kind="sla", year_label="Year", org_label="Sponsor",
              unit="trust", source_label="SEC Form 10-D servicing reports"),
        Board("student-loan-defaults", "Highest student loan default rates", "The Deep End",
              "Trusts where the most loan principal defaulted in a year, relative to the size of the pool.",
              f"Rate = defaults reported in the year's monthly reports / average pool balance over those reports, "
              f"as a percent. {scope} {SOURCE}",
              _sql("y.default_rate", RATE_SCOPE, "value DESC, pool_balance DESC, subject_key",
                   ", y.defaults, y.chargeoff_rate"),
              Column("value", "Default rate (%)", "ratio"),
              common + [Column("defaults", "Defaults in year", "money"),
                        Column("chargeoff_rate", "Charge-off rate (%)", "ratio")],
              [FFELP_NOTE, FAMILY_NOTE],
              per_org=True, forms=(), group=GROUP_NAME, kind="sla", year_label="Year", org_label="Sponsor",
              unit="trust", source_label="SEC Form 10-D servicing reports"),
        Board("student-loan-chargeoffs", "Highest student loan charge-off rates", "Written Off",
              "Trusts that charged off the most loan principal in a year, relative to the size of the pool.",
              f"Rate = charge-offs reported in the year's monthly reports / average pool balance over those reports, "
              f"as a percent. For FFELP trusts a charge-off is the uninsured share of a guarantor claim. {scope} "
              f"{SOURCE}",
              _sql("y.chargeoff_rate", RATE_SCOPE, "value DESC, pool_balance DESC, subject_key",
                   ", y.charge_offs, y.recoveries"),
              Column("value", "Charge-off rate (%)", "ratio"),
              common + [Column("charge_offs", "Charge-offs in year", "money"),
                        Column("recoveries", "Recoveries in year", "money?")],
              [FFELP_NOTE, FAMILY_NOTE],
              per_org=True, forms=(), group=GROUP_NAME, kind="sla", year_label="Year", org_label="Sponsor",
              unit="trust", source_label="SEC Form 10-D servicing reports"),
        Board("student-loan-delinquency", "Highest student loan delinquency rates", "Past Due Honor Roll",
              "Trusts with the largest share of loans in repayment behind on payments.",
              f"Rate = principal in every delinquent bucket the issuer reports (usually 31 days and over) / "
              f"principal in repayment (current plus delinquent), at the last report of the year, as a percent. "
              f"Where a report doesn't break out loans in repayment, the pool balance is the denominator (Basis "
              f"column). {scope} {SOURCE}",
              _sql("y.delinq_rate", RATE_SCOPE, "value DESC, pool_balance DESC, subject_key", ", y.delinq_basis"),
              Column("value", "Delinquency rate (%)", "ratio"),
              common + [Column("delinq_basis", "Basis")],
              ["Loans in deferment or forbearance are not counted as delinquent, so a trust with heavy "
               "forbearance can show a low delinquency rate.", FAMILY_NOTE],
              per_org=True, forms=(), group=GROUP_NAME, kind="sla", year_label="Year", org_label="Sponsor",
              unit="trust", source_label="SEC Form 10-D servicing reports"),
        Board("student-loan-deterioration", "Fastest-rising student loan delinquency", "Going South",
              "Trusts whose delinquency rate rose the most over twelve months.",
              f"Change = delinquency rate at the last report of the year minus the rate in the report for the same "
              f"month a year earlier (no comparison when that month's report is missing), in percentage points (same definition as Highest delinquency rates). {scope} {SOURCE}",
              _sql("y.delinq_change_12", RATE_SCOPE + " AND y.delinq_change_12 > 0",
                   "value DESC, pool_balance DESC, subject_key", ", y.delinq_rate, y.delinq_rate_prior"),
              Column("value", "Change (points)", "ratio"),
              common + [Column("delinq_rate_prior", "Rate a year earlier (%)", "ratio"),
                        Column("delinq_rate", "Rate now (%)", "ratio")],
              ["Delinquency moves with the economy and with policy: forbearance programs (for example after "
               "hurricanes, or during the 2020 pandemic) push rates down, and their end pushes them up.",
               FAMILY_NOTE],
              per_org=True, forms=(), group=GROUP_NAME, kind="sla", year_label="Year", org_label="Sponsor",
              unit="trust", source_label="SEC Form 10-D servicing reports"),
    ]


# Working titles and alternatives, for the editors (not shown on the site).
ALTERNATIVES = {
    "student-loan-largest": ["Mount Tuition", "The Big Balance", "Debt Mountain", "Heavy Backpack"],
    "student-loan-defaults": ["The Deep End", "Dropouts", "Skipped Class", "Default Mode"],
    "student-loan-chargeoffs": ["Written Off", "Failing Grade", "Expelled", "Incomplete"],
    "student-loan-delinquency": ["Past Due Honor Roll", "Late to Class", "Tardy Slip", "Detention Hall"],
    "student-loan-deterioration": ["Going South", "Grade Slide", "Slipping Grades", "Downhill Semester"],
}
