"""Leaderboards: ranked lists straight from the filings.

Each board is a materialized view (board_<slug>) built by loader/boards.py from
the SQL here, refreshed after every data load. Every view has the same leading
columns so pages, CSV, JSON and search treat them alike:

  pos, rank, subject_kind ('person' | 'org' | 'vendor'), subject_key, subject_name,
  subject_norm, subject_url, match ('EXACT' | 'FUZZY' | NULL), ein, org_name, state,
  form_type, tax_year, filing_id, object_id, value

followed by the board's own columns. Facts only: each board says exactly what it
counts, over which filings, and why an unusual number may be ordinary.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from app.config import BOARD_MIN_ASSETS, BOARD_MIN_REVENUE, BOARDS_PERSON_LEVEL

PAGE = 50
STANDING_LINE = "Unusual is not the same as improper. Many of these patterns have ordinary explanations. Check the filing."
TOP_PAID_FLOOR = 250_000
SWING_MULTIPLE = 10
SWING_PRIOR_MIN = 50_000
LOOKALIKE_SIMILARITY = 0.9
SHARED_VENDOR_MIN_ORGS = 3
COMMON_SURNAMES = 500

FORMS = {"990": "990", "990EZ": "990-EZ", "990PF": "990-PF"}


@dataclass
class Column:
    key: str
    label: str
    fmt: str = "text"     # text | money | num | multiple | years | cost | ratio | year


@dataclass
class Board:
    slug: str
    title: str
    subtitle: str
    definition: str                  # plain English
    formula: str                     # the exact rule
    sql: str
    value: Column
    columns: list[Column] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    person_level: bool = False       # hidden unless BOARDS_PERSON_LEVEL
    featured: bool = False
    forms: tuple[str, ...] = ("990", "990EZ", "990PF")

    @property
    def view(self) -> str:
        return "board_" + self.slug.replace("-", "_")

    @property
    def visible(self) -> bool:
        return BOARDS_PERSON_LEVEL or not self.person_level


# --- SQL building blocks -------------------------------------------------------------

def scope(f: str = "f") -> str:
    """The launch scope: large organizations, judged on the filing itself."""
    return f"({f}.total_revenue >= {BOARD_MIN_REVENUE} OR {f}.total_assets_eoy >= {BOARD_MIN_ASSETS})"


def _scope_text() -> str:
    return (f"Filings from organizations reporting at least ${BOARD_MIN_REVENUE:,} in revenue "
            f"or ${BOARD_MIN_ASSETS:,} in total assets that year")


TOTAL = "(coalesce(p.comp_org, 0) + coalesce(p.comp_related, 0) + coalesce(p.other_comp, 0))"
# EXACT: every record on the person's page carries the same normalized name.
# FUZZY: some were joined across name variants (a middle initial) or a care-of listing.
MATCH = """CASE WHEN c.evidence @> '[{"r": "variant"}]' OR c.evidence @> '[{"r": "care_of"}]'
                THEN 'FUZZY' ELSE 'EXACT' END"""
NORM = "trim(regexp_replace(lower({x}), '[^a-z0-9]+', ' ', 'g'))"
# Rows on people boards that aren't a person: group-return placeholders and trustees listed by title.
NOT_A_PERSON = r"""c.name_norm !~ '\m(group return|return|see schedule|schedule o|various|vacant|none)\M'"""
NOT_A_TRUSTEE_TITLE = "coalesce(p.title, '') !~* 'institutional trustee|corporate trustee'"


def norm_sql(x: str) -> str:
    return NORM.format(x=x)


def norm(q: str) -> str:
    """The same normalization in Python, for search."""
    return re.sub(r"[^a-z0-9]+", " ", (q or "").lower()).strip()


def _std(kind, key, name, url, match, f="f", value="value", org_name=None):
    org_name = org_name or f"coalesce(o.name, {f}.org_name)"
    return (f"'{kind}'::text AS subject_kind, ({key})::text AS subject_key, {name} AS subject_name, "
            f"{norm_sql(name)} AS subject_norm, {url} AS subject_url, {match}::text AS match, "
            f"{f}.ein, {org_name} AS org_name, {f}.state, {f}.form_type, {f}.tax_year, "
            f"{f}.id AS filing_id, {f}.object_id, {value} AS value")


def _ranked(inner: str, order: str) -> str:
    return (f"SELECT row_number() OVER (ORDER BY {order}) AS pos, rank() OVER (ORDER BY {order.split(',')[0]}) "
            f"AS rank, x.* FROM ({inner}) x")


# --- Phase 1 boards --------------------------------------------------------------------

def _top_paid() -> str:
    inner = f"""
        SELECT {_std('person', 'r.cluster_id', 'c.display_name', "'/person/' || r.cluster_id", MATCH,
                     f='r', value='r.total', org_name='coalesce(o.name, r.org_name)')},
               r.title, r.comp_org, r.comp_related, r.other_comp
        FROM (SELECT DISTINCT ON (m.cluster_id, f.tax_year)
                     m.cluster_id, f.id, f.object_id, f.ein, f.org_name, f.state, f.form_type, f.tax_year,
                     p.title, p.comp_org, p.comp_related, p.other_comp, {TOTAL} AS total
              FROM people p
              JOIN filings f ON f.id = p.filing_id
              JOIN person_cluster_members m ON m.person_id = p.id
              WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND {scope()} AND {TOTAL} >= {TOP_PAID_FLOOR}
                AND {NOT_A_TRUSTEE_TITLE}
              ORDER BY m.cluster_id, f.tax_year, {TOTAL} DESC, p.id) r
        JOIN person_clusters c ON c.id = r.cluster_id
        LEFT JOIN organizations o ON o.ein = r.ein
        WHERE NOT c.is_institution AND {NOT_A_PERSON}"""
    return _ranked(inner, "value DESC, tax_year DESC, subject_key")


def _top_vendors() -> str:
    inner = f"""
        SELECT {_std('vendor', 'k.name_norm', 'k.name_raw', "'/contractor/' || k.id", 'NULL',
                     value='k.compensation')},
               k.service_description
        FROM contractors k
        JOIN filings f ON f.id = k.filing_id
        LEFT JOIN organizations o ON o.ein = f.ein
        WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND {scope()} AND k.name_norm <> ''
          AND ((f.form_type = '990PF' AND k.compensation >= 50000)
            OR (f.form_type = '990' AND k.compensation >= 100000))"""
    return _ranked(inner, "value DESC, tax_year DESC, filing_id")


def _org_board(value: str, where: str, extra: str = "") -> str:
    return f"""
        SELECT {_std('org', 'f.ein', 'coalesce(o.name, f.org_name)', "'/org/' || f.ein", 'NULL', value=value)}
               {extra}
        FROM filings f
        LEFT JOIN organizations o ON o.ein = f.ein
        WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND {scope()} AND {where}"""


def _dragon_hoard() -> str:
    reserves = "coalesce(f.net_assets_eoy, f.total_assets_eoy)"
    inner = _org_board(
        f"round({reserves}::numeric / f.total_expenses, 2)",
        f"f.total_expenses >= 500000 AND {reserves} > 0",
        f""", {reserves} AS reserves,
              CASE WHEN f.net_assets_eoy IS NOT NULL THEN 'net assets' ELSE 'total assets' END AS basis,
              f.total_expenses""")
    return _ranked(inner, "value DESC, reserves DESC, filing_id")


def _expensive_dollar() -> str:
    inner = _org_board(
        "round(f.fundraising_expenses::numeric / f.contributions, 3)",
        "f.form_type = '990' AND f.contributions >= 500000 AND f.fundraising_expenses > 0",
        ", f.fundraising_expenses, f.contributions")
    return _ranked(inner, "value DESC, fundraising_expenses DESC, filing_id")


def _small_org_big_check() -> str:
    inner = f"""
        SELECT {_std('person', 'r.cluster_id', 'c.display_name', "'/person/' || r.cluster_id", MATCH,
                     f='r', value='r.total', org_name='coalesce(o.name, r.org_name)')},
               r.title, r.total_revenue, r.total_assets_eoy
        FROM (SELECT DISTINCT ON (f.id)
                     m.cluster_id, f.id, f.object_id, f.ein, f.org_name, f.state, f.form_type, f.tax_year,
                     f.total_revenue, f.total_assets_eoy, p.title, {TOTAL} AS total
              FROM filings f
              JOIN people p ON p.filing_id = f.id
              JOIN person_cluster_members m ON m.person_id = p.id
              JOIN person_clusters c ON c.id = m.cluster_id AND NOT c.is_institution AND {NOT_A_PERSON}
              WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND {scope()}
                AND f.total_revenue IS NOT NULL AND f.total_revenue < 1000000 AND {TOTAL} > 0
                AND {NOT_A_TRUSTEE_TITLE}
              ORDER BY f.id, {TOTAL} DESC, p.id) r
        JOIN person_clusters c ON c.id = r.cluster_id
        LEFT JOIN organizations o ON o.ein = r.ein"""
    return _ranked(inner, "value DESC, tax_year DESC, filing_id")


def _biggest_swings() -> str:
    revenue = f"""
        SELECT DISTINCT ON (f.ein, f.tax_year)
               {_std('org', 'f.ein', 'coalesce(o.name, f.org_name)', "'/org/' || f.ein", 'NULL',
                     value='round(f.total_revenue::numeric / g.total_revenue, 1)')},
               'Revenue'::text AS measure, g.tax_year AS prior_year, g.total_revenue AS prior_amount,
               f.total_revenue AS amount
        FROM filings f
        JOIN filings g ON g.ein = f.ein AND g.tax_year = f.tax_year - 1 AND NOT g.superseded
        LEFT JOIN organizations o ON o.ein = f.ein
        WHERE NOT f.superseded AND {scope()} AND g.total_revenue >= {SWING_PRIOR_MIN}
          AND f.total_revenue >= {SWING_MULTIPLE} * g.total_revenue
        ORDER BY f.ein, f.tax_year, f.total_revenue DESC"""
    pay = f"""
        SELECT {_std('person', 'cur.cluster_id', 'c.display_name', "'/person/' || cur.cluster_id", "'EXACT'",
                     value='round(cur.total::numeric / pri.total, 1)')},
               'Officer pay'::text AS measure, pri.tax_year AS prior_year, pri.total AS prior_amount,
               cur.total AS amount
        FROM (SELECT DISTINCT ON (p.filing_id, p.name_norm) p.filing_id, p.name_norm, p.ein, p.tax_year,
                     m.cluster_id, {TOTAL} AS total
              FROM people p
              JOIN filings f ON f.id = p.filing_id
              JOIN person_cluster_members m ON m.person_id = p.id
              WHERE NOT f.superseded AND {scope()} AND {TOTAL} >= {SWING_MULTIPLE * SWING_PRIOR_MIN}
              ORDER BY p.filing_id, p.name_norm, {TOTAL} DESC) cur
        JOIN LATERAL (SELECT p.tax_year, max({TOTAL}) AS total
                      FROM people p JOIN filings g ON g.id = p.filing_id AND NOT g.superseded
                      WHERE p.ein = cur.ein AND p.tax_year = cur.tax_year - 1 AND p.name_norm = cur.name_norm
                      GROUP BY p.tax_year) pri ON true
        JOIN filings f ON f.id = cur.filing_id
        JOIN person_clusters c ON c.id = cur.cluster_id AND NOT c.is_institution AND {NOT_A_PERSON}
        LEFT JOIN organizations o ON o.ein = f.ein
        WHERE pri.total >= {SWING_PRIOR_MIN} AND cur.total >= {SWING_MULTIPLE} * pri.total"""
    return _ranked(f"({revenue}) UNION ALL ({pay})", "value DESC, amount DESC, filing_id")


def _phantom_staff() -> str:
    inner = _org_board("f.total_revenue",
                       "f.form_type = '990' AND f.total_revenue >= 5000000 AND f.num_employees IS NOT NULL "
                       "AND f.num_employees <= 1",
                       ", f.num_employees, f.num_volunteers, f.total_expenses")
    return _ranked(inner, "value DESC, filing_id")


def _lookalikes() -> str:
    big = "(o1.latest_total_revenue >= {r} OR o1.latest_total_assets >= {a})".format(
        r=BOARD_MIN_REVENUE, a=BOARD_MIN_ASSETS)
    # One row per large organization: its closest lookalike (the largest, among equally close
    # ones) and how many lookalikes it has in all.
    inner = f"""
        SELECT {_std('org', 'x.ein1', 'x.name1', "'/org/' || x.ein1", 'NULL', value='x.sim', org_name='x.name1')},
               x.n_lookalikes, x.revenue, x.ruling_year, x.twin_name, x.twin_ein, x.twin_state, x.twin_revenue,
               x.twin_ruling_year
        FROM (SELECT DISTINCT ON (o1.ein)
                     o1.ein AS ein1, o1.name AS name1, o1.latest_total_revenue AS revenue, o1.ruling_year,
                     round(similarity(o1.name, o2.name)::numeric, 2) AS sim,
                     count(*) OVER (PARTITION BY o1.ein) AS n_lookalikes,
                     o2.name AS twin_name, o2.ein AS twin_ein, o2.state AS twin_state,
                     o2.latest_total_revenue AS twin_revenue, o2.ruling_year AS twin_ruling_year
              FROM organizations o1
              JOIN organizations o2 ON o2.name % o1.name AND o2.ein <> o1.ein
              WHERE {big} AND o1.latest_filing_year IS NOT NULL AND o2.latest_filing_year IS NOT NULL
                AND similarity(o1.name, o2.name) >= {LOOKALIKE_SIMILARITY}
              ORDER BY o1.ein, similarity(o1.name, o2.name) DESC, o2.latest_total_revenue DESC NULLS LAST,
                       o2.ein) x
        JOIN LATERAL (SELECT * FROM filings f WHERE f.ein = x.ein1 AND NOT f.superseded
                      ORDER BY f.tax_year DESC NULLS LAST, f.id DESC LIMIT 1) f ON true"""
    return _ranked(inner, "value DESC, n_lookalikes DESC, revenue DESC NULLS LAST, subject_key")


def _shared_vendors() -> str:
    inner = f"""
        SELECT 'vendor'::text AS subject_kind, g.name_norm AS subject_key, g.name_raw AS subject_name,
               {norm_sql('g.name_raw')} AS subject_norm,
               '/contractors?q=' || replace(g.name_norm, ' ', '+') AS subject_url, NULL::text AS match,
               f.ein, coalesce(o.name, f.org_name) AS org_name, f.state, f.form_type, g.tax_year,
               f.id AS filing_id, f.object_id, g.n_orgs AS value, g.total_paid
        FROM (SELECT k.name_norm, f.tax_year, count(DISTINCT f.ein) AS n_orgs, sum(k.compensation) AS total_paid,
                     (array_agg(k.name_raw ORDER BY k.compensation DESC NULLS LAST))[1] AS name_raw,
                     (array_agg(f.id ORDER BY k.compensation DESC NULLS LAST))[1] AS top_filing
              FROM contractors k JOIN filings f ON f.id = k.filing_id
              WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND {scope()} AND k.name_norm <> ''
              GROUP BY k.name_norm, f.tax_year
              HAVING count(DISTINCT f.ein) >= {SHARED_VENDOR_MIN_ORGS}) g
        JOIN filings f ON f.id = g.top_filing
        LEFT JOIN organizations o ON o.ein = f.ein"""
    return _ranked(inner, "value DESC, total_paid DESC, subject_key, tax_year")


# --- person-level boards (hidden at launch) ------------------------------------------------

def _revolving_door() -> str:
    inner = f"""
        SELECT {_std('person', 'r.cluster_id', 'c.display_name', "'/person/' || r.cluster_id", MATCH,
                     value='r.n_orgs')},
               r.orgs
        FROM (WITH ce AS (SELECT m.cluster_id, f.tax_year, f.ein, max(f.id) AS filing_id, max(f.org_name) AS org_name
                          FROM people p
                          JOIN filings f ON f.id = p.filing_id
                          JOIN person_cluster_members m ON m.person_id = p.id
                          WHERE NOT f.superseded AND f.tax_year IS NOT NULL AND {scope()}
                          GROUP BY 1, 2, 3),
                   busy AS (SELECT ce.* FROM ce JOIN (SELECT cluster_id, tax_year FROM ce GROUP BY 1, 2
                                                      HAVING count(*) >= 5) b USING (cluster_id, tax_year)),
                   -- an organization related (Schedule R) to another one counted for the same person and year
                   dup AS (SELECT DISTINCT a.cluster_id, a.tax_year, a.ein FROM busy a
                           JOIN related_orgs ro ON ro.ein = a.ein
                           JOIN busy b ON b.cluster_id = a.cluster_id AND b.tax_year = a.tax_year
                                      AND b.ein = ro.related_ein AND b.ein < a.ein)
              SELECT cluster_id, tax_year, count(*) AS n_orgs, (array_agg(org_name ORDER BY org_name))[1:12] AS orgs,
                     max(filing_id) AS filing_id
              FROM busy
              WHERE NOT EXISTS (SELECT 1 FROM dup d WHERE d.cluster_id = busy.cluster_id
                                AND d.tax_year = busy.tax_year AND d.ein = busy.ein)
              GROUP BY cluster_id, tax_year HAVING count(*) >= 5) r
        JOIN person_clusters c ON c.id = r.cluster_id AND NOT c.is_institution AND {NOT_A_PERSON}
        JOIN filings f ON f.id = r.filing_id
        LEFT JOIN organizations o ON o.ein = f.ein"""
    return _ranked(inner, "value DESC, tax_year DESC, subject_key")


def _family_plan() -> str:
    surname = r"substring(p.name_norm from '(\S+)(?: (?:jr|sr|ii|iii|iv|v))?$')"
    inner = f"""
        SELECT {_std('org', 'f.ein', 'coalesce(o.name, f.org_name)', "'/org/' || f.ein", 'NULL',
                     value='g.n_people')},
               g.surname, g.names, g.combined_pay
        FROM (SELECT p.filing_id, {surname} AS surname, count(DISTINCT p.name_norm) AS n_people,
                     array_agg(DISTINCT p.name_raw) AS names, sum({TOTAL}) AS combined_pay,
                     count(DISTINCT p.street) FILTER (WHERE p.street IS NOT NULL) AS n_streets,
                     count(p.street) AS n_with_street
              FROM people p
              JOIN filings f ON f.id = p.filing_id
              JOIN person_cluster_members m ON m.person_id = p.id
              JOIN person_clusters c ON c.id = m.cluster_id AND NOT c.is_institution
              WHERE NOT f.superseded AND {scope()}
              GROUP BY p.filing_id, {surname}
              HAVING count(DISTINCT p.name_norm) >= 2) g
        JOIN filings f ON f.id = g.filing_id
        LEFT JOIN organizations o ON o.ein = f.ein
        WHERE length(g.surname) > 1
          AND (g.n_people >= 3 OR (g.n_with_street >= 2 AND g.n_streets = 1)
               OR g.surname NOT IN (SELECT last_name FROM person_clusters WHERE last_name IS NOT NULL
                                    GROUP BY last_name ORDER BY count(*) DESC LIMIT {COMMON_SURNAMES}))"""
    return _ranked(inner, "value DESC, combined_pay DESC NULLS LAST, filing_id")


def _boards() -> list[Board]:
    s = _scope_text()
    return [
        Board("top-paid", "Highest-paid people", "The Corner Office",
              "The largest total compensation reported for one person on one filing, per person per tax year.",
              f"Total = reportable pay from the organization + reportable pay from related organizations + "
              f"other compensation (Form 990 Part VII; 990-EZ Part IV; 990-PF Part VIII). One row per person per "
              f"tax year: their largest single filing. Floor ${TOP_PAID_FLOOR:,}. Institutions (banks acting as "
              f"trustee, entries titled institutional or corporate trustee) and group-return placeholder rows "
              f"excluded. {s}.",
              _top_paid(), Column("value", "Total pay", "money"),
              [Column("title", "Title"), Column("comp_org", "From org", "money"),
               Column("comp_related", "From related", "money"), Column("other_comp", "Other", "money")],
              ["Pay from related organizations is reported on each related organization's filing too, so a "
               "person's figures can appear more than once across filings."],
              featured=True),
        Board("top-vendors", "Highest-paid vendors", "Invoice Royalty",
              "The largest payments to independent contractors, as listed by the paying organization.",
              f"Compensation to one contractor on one filing (Form 990 Part VII Section B; 990-PF Part VIII). "
              f"Thresholds: $100,000 on the 990, $50,000 on the 990-PF (the forms' own reporting floors). {s}.",
              _top_vendors(), Column("value", "Paid", "money"),
              [Column("service_description", "Service")],
              ["Each organization lists at most its top five, so this is a floor, not the full picture.",
               "Related organizations can appear as contractors: a health plan paying its own hospitals, or a "
               "foundation paying its management company."],
              featured=True, forms=("990", "990PF")),
        Board("dragon-hoard", "Cash reserves in years of spending", "Dragon Hoard",
              "How many years the organization could keep spending at this year's rate from what it holds.",
              f"Years = net assets at year end / total expenses for the year (total assets when net assets "
              f"aren't reported). Organizations with expenses under $500,000 excluded. {s}.",
              _dragon_hoard(), Column("value", "Years", "years"),
              [Column("reserves", "Reserves", "money"), Column("basis", "Basis"),
               Column("total_expenses", "Expenses", "money")],
              ["Endowments, reserves for buildings and restricted gifts are often legitimate and sometimes "
               "required. Net assets include buildings and other things that aren't cash."],
              featured=True),
        Board("expensive-dollar", "Fundraising cost per dollar raised", "The Most Expensive Dollar",
              "What it cost to raise each dollar of contributions.",
              f"Cost = total fundraising expenses (Form 990 Part I line 16b, Part IX column D) / contributions, "
              f"gifts and grants (Part VIII line 1h). Form 990 only; contributions of at least $500,000. {s}.",
              _expensive_dollar(), Column("value", "Cost per $1", "cost"),
              [Column("fundraising_expenses", "Fundraising", "money"),
               Column("contributions", "Contributions", "money")],
              ["Special events, capital campaigns and first-year donor drives often cost more than they bring in "
               "the same year. Contributions include government grants, which cost little to raise. Some "
               "organizations raise money for a related organization, so the costs land on one return and the "
               "gifts on another."],
              forms=("990",)),
        Board("small-org-big-check", "Highest single salary at organizations with under $1M revenue",
              "Small Org, Big Check",
              "The best-paid person at organizations that took in less than $1 million that year.",
              f"One row per filing: the person with the largest total pay (as on Highest-paid people) where total "
              f"revenue was under $1,000,000. Institutions excluded. {s} (so these are asset-rich organizations "
              f"with small revenue).",
              _small_org_big_check(), Column("value", "Total pay", "money"),
              [Column("title", "Title"), Column("total_revenue", "Revenue", "money"),
               Column("total_assets_eoy", "Assets", "money")],
              ["Revenue can be low in a year when investments lost value, and private foundations often pay "
               "staff from assets rather than revenue."]),
        Board("biggest-swings", "Biggest year-over-year jumps", "Biggest Swings",
              "Revenue or one person's pay at least ten times the year before.",
              f"Multiple = this year / prior year, for the same EIN in consecutive tax years. Revenue: prior year "
              f"at least ${SWING_PRIOR_MIN:,}. Officer pay: the same normalized name at the same EIN (an EXACT "
              f"match), prior year at least ${SWING_PRIOR_MIN:,}. Multiple of at least {SWING_MULTIPLE}. "
              f"{s} (in the later year).",
              _biggest_swings(), Column("value", "Multiple", "multiple"),
              [Column("measure", "Measure"), Column("prior_year", "Prior year", "year"),
               Column("prior_amount", "Prior", "money"), Column("amount", "This year", "money")],
              ["Big one-time gifts, mergers, a first full year of operation, a partial prior year, and deferred "
               "pay paid out at retirement all produce large jumps."]),
        Board("phantom-staff", "Large revenue, one employee or none", "Phantom Staff",
              "Organizations with at least $5 million in revenue that report one employee or none.",
              f"Total revenue of at least $5,000,000 and total employees (Form 990 Part I line 5) of 0 or 1. "
              f"Form 990 only. {s}.",
              _phantom_staff(), Column("value", "Revenue", "money"),
              [Column("num_employees", "Employees", "num"), Column("num_volunteers", "Volunteers", "num"),
               Column("total_expenses", "Expenses", "money")],
              ["Pass-through and supporting organizations, donor-advised funds, and groups staffed by a related "
               "organization or a management company often have no employees of their own."],
              forms=("990",)),
        Board("lookalikes", "Organizations with nearly identical names", "Lookalikes",
              "Large organizations that share a name, or almost, with other organizations.",
              f"Trigram similarity of the two names (PostgreSQL pg_trgm) of at least {LOOKALIKE_SIMILARITY}, "
              f"different EINs. One row per organization reporting ${BOARD_MIN_REVENUE:,} in revenue or "
              f"${BOARD_MIN_ASSETS:,} in assets on its latest e-filed return: its closest lookalike (the largest, "
              f"when several are equally close) and how many it has. Latest filing shown.",
              _lookalikes(), Column("value", "Similarity", "ratio"),
              [Column("n_lookalikes", "Lookalikes", "num"), Column("revenue", "Revenue", "money"), Column("ruling_year", "Ruling year", "year"),
               Column("twin_name", "Lookalike"), Column("twin_ein", "Lookalike EIN"),
               Column("twin_state", "Its state"), Column("twin_revenue", "Its revenue", "money"),
               Column("twin_ruling_year", "Its ruling year", "year")],
              ["Chapters, affiliates, foundations and their operating charities, and organizations in different "
               "states often share a name on purpose."]),
        Board("shared-vendors", "Vendors paid by many organizations", "Everybody's Contractor",
              f"Contractors listed by {SHARED_VENDOR_MIN_ORGS} or more different organizations in the same tax year.",
              f"Count of distinct EINs listing the same normalized contractor name in one tax year (Form 990 Part "
              f"VII Section B; 990-PF Part VIII), with the combined amount. {s}. The filing shown is the "
              f"largest single payment.",
              _shared_vendors(), Column("value", "Organizations", "num"),
              [Column("total_paid", "Combined", "money")],
              ["Large law firms, auditors, hospital staffing companies and fundraising firms serve many clients. "
               "Different companies with the same name are counted together."],
              forms=("990", "990PF")),
        Board("revolving-door", "Most organizations per person in one year", "Revolving Door",
              "People who appear on the filings of five or more unrelated organizations in one tax year.",
              f"Distinct EINs per person per tax year, not counting organizations related to another counted one "
              f"(Schedule R). At least 5. {s}.",
              _revolving_door(), Column("value", "Organizations", "num"),
              [Column("orgs", "Some of them")],
              ["Professional trustees, bank officers, religious orders and people who serve on many boards "
               "appear here for ordinary reasons. Linked records can join two people with the same name; check "
               "the evidence."],
              person_level=True),
        Board("family-plan", "Shared surnames on one filing", "Family Plan",
              "Filings that list two or more people with the same surname.",
              f"People on one filing grouped by last name. The {COMMON_SURNAMES} most common surnames count only "
              f"with 3 or more people or a shared street address. {s}.",
              _family_plan(), Column("value", "People", "num"),
              [Column("surname", "Surname"), Column("names", "Names"), Column("combined_pay", "Combined pay", "money")],
              ["A shared surname is not evidence of relation. Family foundations are run by families by design."],
              person_level=True),
    ]


BOARDS = _boards()
BY_SLUG = {b.slug: b for b in BOARDS}


def visible() -> list[Board]:
    return [b for b in BOARDS if b.visible]


def featured() -> list[Board]:
    return [b for b in visible() if b.featured]


def get(slug: str) -> Board | None:
    b = BY_SLUG.get(slug)
    return b if b and b.visible else None


# --- formatting -------------------------------------------------------------------------

def fmt(v, kind: str) -> str:
    if v is None or v == "":
        return "-"
    if kind == "money":
        v = int(v)
        return f"-${-v:,}" if v < 0 else f"${v:,}"
    if kind == "num":
        return f"{int(v):,}"
    if kind == "years":
        return f"{float(v):,.1f} yrs"
    if kind == "multiple":
        return f"{float(v):,.1f}x"
    if kind == "cost":
        return f"${float(v):,.2f}"
    if kind == "ratio":
        return f"{float(v):.2f}"
    if kind == "year":
        return str(v)
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v if x)
    return str(v)


def window(meta: dict | None) -> str:
    if not meta or not meta.get("year_min"):
        return "e-filed returns only"
    return f"tax years {meta['year_min']} to {meta['year_max']}, e-filed returns only"


def finding(board: Board, row: dict | None) -> str:
    """One shareable line about the top row."""
    if not row:
        return ""
    return f"Top row: {row['subject_name']}, {fmt(row['value'], board.value.fmt)}, tax year {row['tax_year']}"


# --- queries ----------------------------------------------------------------------------

_meta: dict = {"t": 0.0, "rows": {}}
META_TTL = 300


def meta() -> dict[str, dict]:
    from app import db
    if time.time() - _meta["t"] > META_TTL:
        try:
            with db.conn() as conn:
                _meta["rows"] = {r["slug"]: r for r in conn.execute("SELECT * FROM board_meta")}
        except Exception:  # noqa: BLE001 - boards not built yet
            _meta["rows"] = {}
        _meta["t"] = time.time()
    return _meta["rows"]


def _where(board: Board, filters: dict, params: dict) -> str:
    out = []
    if filters.get("year"):
        out.append("tax_year = %(year)s")
        params["year"] = filters["year"]
    if filters.get("form") in board.forms:
        out.append("form_type = %(form)s")
        params["form"] = filters["form"]
    if filters.get("state"):
        out.append("state = %(state)s")
        params["state"] = filters["state"]
    return ("WHERE " + " AND ".join(out)) if out else ""


def page(board: Board, filters: dict, page_no: int = 1, per_page: int = PAGE) -> dict:
    from app import db
    params: dict = {"lim": per_page, "off": (page_no - 1) * per_page}
    where = _where(board, filters, params)
    with db.conn() as conn:
        rows = conn.execute(f"SELECT * FROM {board.view} {where} ORDER BY pos LIMIT %(lim)s OFFSET %(off)s",
                            params).fetchall()
        if where:
            total = conn.execute(f"SELECT count(*) AS n FROM {board.view} {where}", params).fetchone()["n"]
        else:
            total = (meta().get(board.slug) or {}).get("n_rows") or \
                conn.execute(f"SELECT count(*) AS n FROM {board.view}").fetchone()["n"]
    return {"rows": rows, "total": total}


def all_rows(board: Board, filters: dict, limit: int = 100_000):
    """Every row (for CSV), streamed."""
    from app import db
    params: dict = {"lim": limit}
    where = _where(board, filters, params)
    with db.conn() as conn, conn.transaction(), conn.cursor(name=f"csv_{board.view}") as cur:
        cur.itersize = 2000
        cur.execute(f"SELECT * FROM {board.view} {where} ORDER BY pos LIMIT %(lim)s", params)
        yield from cur


def top(board: Board, n: int = 10) -> list[dict]:
    from app import db
    with db.conn() as conn:
        return conn.execute(f"SELECT * FROM {board.view} ORDER BY pos LIMIT %s", (n,)).fetchall()


def years(board: Board) -> list[int]:
    m = meta().get(board.slug)
    if not m or not m.get("year_min"):
        return []
    return list(range(m["year_max"], m["year_min"] - 1, -1))


SEARCH_LIMIT = 40


def search(q: str) -> list[dict]:
    """Everyone and everything matching q that appears on a board, with each board and best rank."""
    from app import db
    n = norm(q)
    if len(n) < 2:
        return []
    slugs = [b.slug for b in visible()]
    with db.conn() as conn:
        try:
            rows = conn.execute("""
                WITH hits AS (
                    SELECT subject_kind, subject_key, max(subject_name) AS subject_name,
                           max(subject_url) AS subject_url,
                           max(CASE WHEN subject_norm = %(n)s THEN 1 ELSE 0 END) AS exact,
                           max(word_similarity(%(n)s, subject_norm)) AS sim
                    FROM board_entries
                    WHERE slug = ANY(%(slugs)s)
                      AND (subject_norm LIKE %(prefix)s OR subject_norm LIKE %(inner)s OR %(n)s <%% subject_norm)
                    GROUP BY subject_kind, subject_key
                    ORDER BY exact DESC, sim DESC, max(subject_name) LIMIT %(lim)s)
                SELECT h.*, e.slug, e.best_rank, e.n_rows
                FROM hits h JOIN board_entries e USING (subject_kind, subject_key)
                WHERE e.slug = ANY(%(slugs)s)
                ORDER BY h.exact DESC, h.sim DESC, h.subject_name, e.best_rank""",
                {"n": n, "prefix": n + "%", "inner": "% " + n + "%", "slugs": slugs,
                 "lim": SEARCH_LIMIT}).fetchall()
        except Exception:  # noqa: BLE001 - boards not built yet
            return []
    out: dict = {}
    for r in rows:
        key = (r["subject_kind"], r["subject_key"])
        if key not in out:
            out[key] = {k: r[k] for k in ("subject_kind", "subject_key", "subject_name", "subject_url")} | {
                "boards": []}
        out[key]["boards"].append({"board": BY_SLUG[r["slug"]], "rank": r["best_rank"], "n_rows": r["n_rows"]})
    return list(out.values())


def counts(kind: str, keys: list) -> dict[str, int]:
    """{subject key: number of visible boards it appears on}, for search results."""
    from app import db
    keys = [str(k) for k in keys if k is not None]
    if not keys:
        return {}
    try:
        with db.conn() as conn:
            rows = conn.execute("""SELECT subject_key, count(DISTINCT slug) AS n FROM board_entries
                                   WHERE subject_kind = %s AND subject_key = ANY(%s) AND slug = ANY(%s)
                                   GROUP BY subject_key""",
                                (kind, keys, [b.slug for b in visible()])).fetchall()
    except Exception:  # noqa: BLE001 - boards not built yet
        return {}
    return {r["subject_key"]: r["n"] for r in rows}
