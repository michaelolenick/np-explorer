"""Student loan asset-backed securities (SLABS) from SEC EDGAR.

student_loan_trusts: one row per securitization trust that files with the SEC (keyed
by the trust's CIK), with its parties as named in its filings and its issuer family
(templates and field definitions repeat within a family; see app/student_loans.py
FAMILIES for each family's definitions).

student_loan_trust_months: one row per trust per reporting month, parsed from the
monthly servicing report attached to Form 10-D (or 8-K before 10-D existed).
Every measure is NULL where the issuer did not report it (shown "Not reported",
never 0). Dollar amounts are principal balances as the issuer reports them.
delinquency holds the issuer's own bucket labels; the fixed delinq_* columns map
those buckets onto 30-59 / 60-89 / 90-119 / 120+ only when the issuer's buckets line up
(otherwise NULL, with the reason in parse_notes).

student_loan_parties: sponsors, depositors, servicers, administrators and trustees
named in the filings, matched to organizations in the 990 data where they are
nonprofits (EXACT: same normalized name and state; FUZZY: similar name), with evidence.

student_loan_trust_stats (one row per trust: latest month, 12-month changes, rates) and
student_loan_trust_years (one row per trust per calendar year, for the boards) are
recomputed after each load.

cohort_default_rates: the Department of Education's official federal cohort default
rates by school (OPEID), as published by Federal Student Aid.

Every CREATE uses IF NOT EXISTS: the loader may have created these tables on the
shared database before this revision is recorded.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-18
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

TABLES = """
CREATE TABLE IF NOT EXISTS student_loan_trusts (
    cik              bigint PRIMARY KEY,
    name             text NOT NULL,
    family           text NOT NULL,          -- issuer family slug (app/student_loans.py FAMILIES)
    sponsor          text,
    depositor        text,
    servicer         text,
    administrator    text,
    trustee          text,                   -- indenture / eligible lender trustee, as named
    edgar_state      text,                   -- state of the trust's EDGAR business address (its sponsor's office)
    closing_date     date,
    original_balance numeric,                -- initial pool balance as reported
    program_type     text,                   -- FFELP | private | refi | mixed (NULL if unknown)
    first_report     date,
    last_report      date,
    n_filings        integer,                -- monthly reports found on EDGAR
    months_parsed    integer,
    months_failed    integer,
    filing_url       text,                   -- the trust's EDGAR filing index
    prospectus_url   text,
    retrieved_at     timestamptz,
    notes            text
);
CREATE INDEX IF NOT EXISTS student_loan_trusts_family ON student_loan_trusts (family);

CREATE TABLE IF NOT EXISTS student_loan_trust_months (
    cik                  bigint NOT NULL,
    period               date NOT NULL,      -- first day of the month the collection period ended
    distribution_date    date,
    collection_start     date,
    collection_end       date,
    period_months        integer,            -- months the report covers (1 monthly, 3 quarterly)
    pool_balance         numeric,            -- principal balance of the pool at period end
    loan_count           integer,
    borrower_count       integer,
    repayment_balance    numeric,            -- in repayment (current + delinquent), if reported
    current_balance      numeric,            -- in repayment and current
    delinq_30_59         numeric,
    delinq_60_89         numeric,
    delinq_90_119        numeric,
    delinq_120_plus      numeric,
    delinq_total         numeric,            -- every delinquent bucket the issuer reports, summed
    delinquency          jsonb,              -- [{label, balance, count}] in the issuer's own words
    forbearance          numeric,
    deferment            numeric,
    school_grace         numeric,            -- in school or grace
    claims_in_process    numeric,            -- FFELP: claims filed with the guarantor, not yet paid
    defaults             numeric,            -- defaulted / claims in this period (definition per family)
    charge_offs          numeric,            -- charged off in this period
    recoveries           numeric,            -- recovered in this period
    cum_defaults         numeric,            -- cumulative, as reported
    cum_default_pct      numeric,            -- cumulative defaults as % of initial pool, as reported
    prepayment_rate      numeric,            -- CPR % as reported (constant prepayment rate, annualized)
    wa_interest_rate     numeric,            -- weighted average borrower interest rate %, as reported
    form_type            text,
    accession            text,
    filing_date          date,
    filing_url           text,
    document_url         text,
    retrieved_at         timestamptz,
    parser               text,
    parse_notes          text,
    PRIMARY KEY (cik, period)
);

CREATE TABLE IF NOT EXISTS student_loan_parties (
    id          bigserial PRIMARY KEY,
    party       text NOT NULL,               -- as named in the filings
    party_norm  text NOT NULL,
    slug        text NOT NULL,               -- /student-loans/issuer/{slug}
    roles       text[] NOT NULL,             -- sponsor, depositor, servicer, administrator, trustee, securitizer
    state       text,                        -- from the filings, when stated
    ein         text,                        -- 990 organization, when matched
    match       text,                        -- EXACT | FUZZY | NULL
    evidence    jsonb,
    sec_cik     bigint,                      -- the party's own SEC filer number, when it files
    abs15g      jsonb,                       -- {"filings", "first", "last"}: Form ABS-15G filed as a securitizer
    retrieved_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS student_loan_parties_norm ON student_loan_parties (party_norm);
CREATE INDEX IF NOT EXISTS student_loan_parties_slug ON student_loan_parties (slug);
CREATE INDEX IF NOT EXISTS student_loan_parties_ein ON student_loan_parties (ein);

CREATE TABLE IF NOT EXISTS student_loan_trust_stats (
    cik                 bigint PRIMARY KEY,
    months              integer,
    first_period        date,
    last_period         date,
    missing_months      integer,             -- calendar months between first and last with no report
    pool_balance        numeric,             -- latest
    loan_count          integer,
    delinq_rate         numeric,             -- latest: delinq_total / pool_balance, %
    delinq_rate_12      numeric,             -- 12 months before the latest
    delinq_change_12    numeric,             -- percentage points
    default_rate_12     numeric,             -- defaults over the latest 12 reported months / avg balance, %
    chargeoff_rate_12   numeric,
    peak_balance        numeric,
    balance_12          numeric,
    updated_at          timestamptz
);

CREATE TABLE IF NOT EXISTS student_loan_trust_years (
    cik                 bigint NOT NULL,
    year                integer NOT NULL,    -- calendar year of the reporting months
    months              integer,             -- monthly reports parsed that year
    last_period         date,
    pool_balance        numeric,             -- at the year's last report
    loan_count          integer,
    avg_balance         numeric,             -- average pool balance over the year's reports
    defaults            numeric,             -- summed over the year's reports (NULL if none reported)
    charge_offs         numeric,
    recoveries          numeric,
    default_rate        numeric,             -- defaults / avg_balance, %
    chargeoff_rate      numeric,
    delinq_rate         numeric,             -- at the year's last report, %
    delinq_basis        text,                -- repayment | pool
    delinq_rate_prior   numeric,             -- 12 reporting months earlier
    delinq_change_12    numeric,             -- percentage points
    PRIMARY KEY (cik, year)
);

CREATE TABLE IF NOT EXISTS cohort_default_rates (
    opeid           text NOT NULL,           -- OPE school code as FSA publishes it (6 digits: the main campus OPEID)
    fiscal_year     integer NOT NULL,        -- cohort fiscal year
    school_name     text,
    city            text,
    state           text,
    program_length  text,                    -- FSA code, as published
    school_type     text,                    -- FSA code, as published (1 public, 2 private nonprofit, 3 proprietary ...)
    borrowers       integer,                 -- borrowers entering repayment in the cohort (Denom)
    defaulters      integer,                 -- of those, in default within three years (Num)
    rate            numeric,                 -- official 3-year cohort default rate, %
    source_url      text,
    retrieved_at    timestamptz,
    PRIMARY KEY (opeid, fiscal_year)
);
"""


def upgrade() -> None:
    op.execute(TABLES)


def downgrade() -> None:
    for t in ("cohort_default_rates", "student_loan_trust_years", "student_loan_trust_stats", "student_loan_parties",
              "student_loan_trust_months", "student_loan_trusts"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
