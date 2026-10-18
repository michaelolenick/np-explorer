"""Colleges and universities, public university payroll, and their links to 990 data.

  colleges                 one row per IPEDS institution (UNITID): name, place, system, control,
                           enrollment, and the EIN IPEDS lists for it.
  college_orgs             each institution's related nonprofits in our 990 data (the institution
                           itself, its foundation, alumni, athletic and booster, research and hospital
                           organizations), EXACT or FUZZY, with the evidence.
  payroll_sources          the state and university payroll publications loaded (one per source).
  payroll_labels           each published employer label mapped to an IPEDS institution where we can.
  payroll_rows             public payroll records as published (copied from the unipay staging schema).
  payroll_person_years     one row per person, employer and year (lines summed only where a publisher
                           splits one person's year into several lines).
  college_payroll_years    per institution and fiscal year: headcount, total, median and top pay.
  college_faculty_salaries IPEDS average faculty salaries by rank (averages, not individual pay).
  payroll_person_links     a payroll person linked to a person page (person cluster), EXACT or FUZZY,
                           with the evidence; never on a common name.
  school_rows              the Schools list: one row per school and payroll year, blending IPEDS, payroll,
                           affiliated nonprofits' 990s, funders, event costs and coaches.
  coach_titles             each distinct coach title (and department) with its sport and role from
                           the fixed rules in app/coach_class.py.

Built by load.py colleges (loader/colleges.py). Tables are refilled in place because the
university leaderboard views depend on them.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-18
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS colleges (
        unitid          integer PRIMARY KEY,
        name            text NOT NULL,
        name_norm       text NOT NULL,
        core_norm       text NOT NULL,       -- name without "the" and campus suffixes, for matching
        alias           text,
        street          text,
        city            text,
        state           char(2),
        zip             text,
        ein             text,                -- as IPEDS lists it
        website         text,
        sector          smallint,
        control         text,                -- Public | Private nonprofit | Private for-profit
        level           text,                -- Four or more years | At least 2 but less than 4 years | ...
        system_name     text,
        hbcu            boolean,
        medical         boolean,
        landgrant       boolean,
        enrollment      integer,
        enrollment_year smallint,
        closed          boolean NOT NULL DEFAULT false,
        name_tsv        tsvector
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS colleges_state ON colleges (state)")
    op.execute("CREATE INDEX IF NOT EXISTS colleges_ein ON colleges (ein)")
    op.execute("CREATE INDEX IF NOT EXISTS colleges_name_trgm ON colleges USING gin (name_norm gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS colleges_tsv ON colleges USING gin (name_tsv)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS college_orgs (
        unitid   integer NOT NULL,
        ein      text NOT NULL,
        relation text NOT NULL,              -- self | foundation | alumni | athletic | research | hospital
        match    text NOT NULL,              -- EXACT | FUZZY
        evidence jsonb NOT NULL,
        PRIMARY KEY (unitid, ein)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS college_orgs_ein ON college_orgs (ein)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS payroll_sources (
        source_key     text PRIMARY KEY,
        state          char(2) NOT NULL,
        title          text NOT NULL,
        publisher      text,
        pay_basis      text,
        url            text,
        first_year     smallint,
        last_year      smallint,
        n_rows         integer,
        n_institutions integer,
        names_truncated boolean NOT NULL DEFAULT false
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS payroll_labels (
        state  char(2) NOT NULL,
        label  text NOT NULL,
        unitid integer,
        match  text,                         -- EXACT | FUZZY | NULL (no single institution: a system or agency)
        how    text,
        n_rows integer,
        PRIMARY KEY (state, label)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS payroll_rows (
        id          bigint PRIMARY KEY,
        source_key  text NOT NULL,
        state       char(2) NOT NULL,
        label       text NOT NULL,
        unitid      integer,
        person_name text,
        name_norm   text,
        withheld    boolean NOT NULL DEFAULT false,
        title       text,
        department  text,
        base_pay    numeric,
        other_pay   numeric,
        total_pay   numeric,
        fiscal_year smallint,
        source_url  text
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS payroll_rows_unitid ON payroll_rows (unitid, fiscal_year, total_pay DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS payroll_rows_state ON payroll_rows (state, fiscal_year, total_pay DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS payroll_rows_person ON payroll_rows (state, label, name_norm)")
    op.execute("CREATE INDEX IF NOT EXISTS payroll_rows_pay ON payroll_rows (total_pay DESC NULLS LAST)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS payroll_person_years (
        id          bigint PRIMARY KEY,      -- the first published row's id
        source_key  text NOT NULL,
        state       char(2) NOT NULL,
        label       text NOT NULL,
        unitid      integer,
        person_name text,
        name_norm   text,
        withheld    boolean NOT NULL DEFAULT false,
        title       text,
        department  text,
        base_pay    numeric,
        other_pay   numeric,
        total_pay   numeric,
        n_lines     integer NOT NULL DEFAULT 1,
        fiscal_year smallint,
        source_url  text
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS ppy_unitid ON payroll_person_years (unitid, fiscal_year, total_pay DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS ppy_state ON payroll_person_years (state, fiscal_year, total_pay DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS ppy_person ON payroll_person_years (state, label, name_norm)")
    op.execute("CREATE INDEX IF NOT EXISTS ppy_pay ON payroll_person_years (total_pay DESC NULLS LAST)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS college_payroll_years (
        unitid      integer NOT NULL,
        fiscal_year smallint NOT NULL,
        headcount   integer,
        n_rows      integer,
        n_pay       integer,
        total_pay   numeric,
        median_pay  numeric,
        max_pay     numeric,
        source_keys text[],
        PRIMARY KEY (unitid, fiscal_year)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS college_faculty_salaries (
        unitid        integer NOT NULL,
        academic_year text NOT NULL,
        arank         smallint NOT NULL,
        rank_label    text,
        staff_count   integer,
        avg_salary    numeric,
        avg_men       numeric,
        avg_women     numeric,
        PRIMARY KEY (unitid, academic_year, arank)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS payroll_person_links (
        state      char(2) NOT NULL,
        label      text NOT NULL,
        name_norm  text NOT NULL,
        unitid     integer,
        cluster_id bigint NOT NULL,
        match      text NOT NULL,            -- EXACT | FUZZY
        evidence   jsonb NOT NULL,
        PRIMARY KEY (state, label, name_norm)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS payroll_person_links_cluster ON payroll_person_links (cluster_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS coach_titles (
        src        text NOT NULL,            -- payroll | 990
        title      text NOT NULL,
        department text NOT NULL DEFAULT '',
        is_coach   boolean NOT NULL,
        sport      text,
        role       text,                     -- head | assistant | other
        reason     text,
        PRIMARY KEY (src, title, department)
    )""")

    op.execute(SCHOOL_ROWS)


SCHOOL_ROWS = """
    CREATE TABLE IF NOT EXISTS school_rows (
        unitid          integer NOT NULL,
        fiscal_year     smallint,            -- payroll year; NULL for a school with no payroll loaded
        latest          boolean NOT NULL,    -- the school's latest row (the default view)
        name            text NOT NULL,
        name_norm       text NOT NULL,
        state           char(2),
        city            text,
        control         text,
        sector          text,
        enrollment      integer,
        international   boolean NOT NULL DEFAULT false,
        country         text,
        payroll_total   numeric,
        headcount       integer,
        payroll_years   text,
        payroll_sources text,
        top_person      text,
        top_title       text,
        top_pay         numeric,
        top_url         text,
        fac_prof        numeric,
        fac_assoc       numeric,
        fac_asst        numeric,
        fac_year        text,
        n_orgs          integer,
        n_orgs_fuzzy    integer,
        has_orgs        boolean NOT NULL DEFAULT false,
        org_revenue     numeric,
        org_expenses    numeric,
        org_net_assets  numeric,
        org_year        smallint,
        org_top_person  text,
        org_top_pay     numeric,
        org_top_url     text,
        org_top_org     text,
        self_ein        text,
        self_expenses   numeric,
        grants_received numeric,
        n_funders       integer,
        top_funder      text,
        top_funder_ein  text,
        top_funder_total numeric,
        event_direct    numeric,
        event_net       numeric,
        coach_name      text,
        coach_pay       numeric,
        coach_sport     text,
        coach_url       text,
        coach_year      smallint,
        sort_value      numeric,
        sort_basis      text
    )"""


def downgrade() -> None:
    for t in ("school_rows", "coach_titles", "payroll_person_links", "college_faculty_salaries", "college_payroll_years",
              "payroll_person_years", "payroll_rows", "payroll_labels", "payroll_sources", "college_orgs", "colleges"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
