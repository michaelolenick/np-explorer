"""Leaderboards for private funds on Form ADV (app/adv.py, loader/adv.py): the biggest funds by reported gross asset
value, the fastest-growing, the ones with the most investors and the highest minimum investments, the advisers
running the most private fund money, and the funds public pensions have put money into (pension_fund_matches).
Slugs start with sec-adv- so loader/sec_bulk.py's weekly boards() refresh includes them. One row per fund (its
latest year on file); Year = the year reported. Shown only where SEC_PUBLIC=1 (owner, 2026-11-13)."""

from __future__ import annotations

GROUP_NAME = "funds"
GROUP = {"title": "Private funds", "subtitle": "Behind the Velvet Rope",
         "definition": "The biggest hedge, private equity, venture and real estate funds by the asset value their "
                       "advisers report, the fastest-growing, the funds with the most investors and the steepest "
                       "minimum investments, the advisers running the most private fund money, and the funds public "
                       "pensions have put money into. From SEC Form ADV."}
SOURCE = ("From SEC Form ADV data (Schedule D section 7.B.1, the private funds reported by registered and exempt "
          "reporting advisers, November 2011 through the latest SEC file), the adviser's latest filing in each year. "
          "Gross asset value, investor counts and minimums are what the adviser reports and are not audited. A year "
          "over $250 billion for one fund is an entry error and is left out.")
# The latest year of every fund, with its adviser's name. MATERIALIZED: without it the planner guesses one row after
# a filter on owners or min_investment and nests a re-sort of adv_filings inside the join (a build that ran for hours).
LATEST = """
        WITH y AS MATERIALIZED (SELECT DISTINCT ON (fund_id, year) fund_id, year, gav, owners, min_investment, fund_name, crd, fund_type,
                          state, country, master_fund, feeder_fund
                   FROM adv_funds WHERE fund_id IS NOT NULL AND fund_name IS NOT NULL AND gav IS NOT NULL AND gav < 250e9
                   ORDER BY fund_id, year DESC, gav DESC),
             l AS MATERIALIZED (SELECT DISTINCT ON (fund_id) * FROM y ORDER BY fund_id, year DESC),
             a AS MATERIALIZED (SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name) AS adviser FROM adv_filings
                   WHERE crd IS NOT NULL ORDER BY crd, submitted DESC NULLS LAST)"""


def _funds(value: str, where: str, extra: str = "", joins: str = "", ctes: str = "",
           order: str = "value DESC, gav DESC, subject_key") -> str:
    """One row per fund (its latest year) with the standard columns, the fund's figures, plus extra columns."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""{LATEST}{ctes}
        SELECT 'fund'::text AS subject_kind, l.fund_id AS subject_key, l.fund_name AS subject_name,
               {norm_sql('l.fund_name')} AS subject_norm, '/corporate/fund/' || l.fund_id AS subject_url,
               NULL::text AS match, NULL::text AS ein, a.adviser AS org_name, l.state, 'ADV'::text AS form_type,
               l.year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value,
               NULL::text AS org_url, 'https://adviserinfo.sec.gov/firm/summary/' || l.crd AS source_url,
               l.gav, l.owners, l.min_investment, l.fund_type, l.country,
               CASE WHEN l.feeder_fund THEN 'Feeder' WHEN l.master_fund THEN 'Master' END AS structure{extra}
        FROM l LEFT JOIN a ON a.crd = l.crd {joins}
        WHERE {where}"""
    return _ranked_by_org(inner, order)


GROWTH = """,
             f AS MATERIALIZED (SELECT DISTINCT ON (fund_id) fund_id, year AS first_year, gav AS first_gav FROM y
                   WHERE gav >= 5000000 ORDER BY fund_id, year)"""
PENSIONS = """,
             c AS (SELECT DISTINCT ON (pension, fund_name) * FROM pension_commitments ORDER BY pension, fund_name, as_of DESC),
             p AS MATERIALIZED (SELECT m.key AS fund_id, sum(c.committed) AS committed, string_agg(DISTINCT c.pension, ', ') AS pensions,
                          max(c.net_irr) AS net_irr, max(c.vintage) AS vintage
                   FROM pension_fund_matches m JOIN c ON c.pension = m.pension AND c.fund_name = m.fund_name
                   WHERE m.kind = 'adv' AND m.confidence <> 'low' GROUP BY 1)"""


def _advisers() -> str:
    """One row per adviser (CRD): the private fund assets on its latest filing."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'adviser'::text AS subject_kind, f.crd AS subject_key, coalesce(f.business_name, f.legal_name) AS subject_name,
               {norm_sql('coalesce(f.business_name, f.legal_name)')} AS subject_norm, NULL::text AS subject_url,
               NULL::text AS match, NULL::text AS ein,
               CASE f.kind WHEN 'ERA' THEN 'Exempt reporting adviser' ELSE 'Registered adviser' END AS org_name,
               f.state, 'ADV'::text AS form_type, f.year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               f.private_fund_assets AS value, NULL::text AS org_url,
               'https://adviserinfo.sec.gov/firm/summary/' || f.crd AS source_url,
               f.private_funds, f.aum, f.employees, f.city, f.submitted
        FROM (SELECT DISTINCT ON (crd) * FROM adv_filings
              WHERE crd IS NOT NULL AND coalesce(business_name, legal_name) IS NOT NULL AND private_fund_assets > 0
              ORDER BY crd, submitted DESC NULLS LAST, filing_id DESC) f
        WHERE f.private_fund_assets < 5e12"""
    return _ranked_by_org(inner, "value DESC, private_funds DESC, subject_key")


def fund_boards() -> list:
    from app.boards import Board, BoardFilter, Column
    from app.corporate import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="adv", year_label="Year reported", org_label="Adviser",
              source_label="SEC Form ADV private fund data", search=True, unit="fund",
              filters=[BoardFilter("type", "Fund type", "fund_type", all_label="All fund types")])
    base = [Column("gav", "Gross asset value", "money"), Column("fund_type", "Fund type"), Column("owners", "Investors", "num?"),
            Column("min_investment", "Minimum investment", "money?"), Column("structure", "Structure"), Column("country", "Country")]
    return [
        Board("sec-adv-biggest-funds", "Biggest private funds", "The Whales",
              "Hedge, private equity, venture, real estate and other private funds with the highest gross asset value "
              "their advisers report on Form ADV, each fund's latest year on file.",
              f"Value = the fund's gross asset value on the latest Form ADV reporting it. {SOURCE}",
              _funds("l.gav", "l.gav > 0"), Column("value", "Gross asset value", "money"), base[1:],
              ["A master fund and its feeder funds report the same money more than once; the Structure column marks "
               "them. Gross asset value counts borrowed money, so a leveraged hedge fund looks bigger than its "
               "investors' capital."], **kw),
        Board("sec-adv-fastest-growing", "Private funds that grew the most", "Rocket Ships",
              "Private funds whose reported gross asset value rose the most, in percent, from their first year on "
              "Form ADV to their latest.",
              f"Value = the percent rise from the fund's first reported gross asset value (at least $5 million) to its "
              f"latest, for funds reporting in at least two years whose value at least doubled; ties go to the bigger "
              f"dollar rise. Left out as entry errors: a latest value that matches the first in thousands or millions. "
              f"{SOURCE}",
              _funds("round(100 * (l.gav - f.first_gav) / f.first_gav, 1)",
                     "l.year > f.first_year AND l.gav >= f.first_gav * 2 "
                     "AND NOT (l.gav BETWEEN f.first_gav * 500 AND f.first_gav * 2000 "
                     "OR l.gav BETWEEN f.first_gav * 500000 AND f.first_gav * 2000000)",
                     ", f.first_gav, f.first_year, l.gav - f.first_gav AS rise", "JOIN f ON f.fund_id = l.fund_id", GROWTH,
                     "value DESC, rise DESC, subject_key"),
              Column("value", "Rise from first year", "pct"),
              [Column("rise", "Dollar rise", "money"), Column("first_gav", "First value", "money"),
               Column("first_year", "First year", "year"), base[0], base[1], base[2]],
              ["New money raised and gains in the holdings both raise gross asset value; the filing doesn't say which."],
              **kw),
        Board("sec-adv-most-investors", "Private funds with the most investors", "The Crowd",
              "Private funds whose advisers report the most beneficial owners on Form ADV, each fund's latest year on "
              "file.",
              f"Value = the number of beneficial owners reported for the fund on its latest Form ADV, for counts under "
              f"one million (above that is an entry error). {SOURCE}",
              _funds("l.owners", "l.owners > 0 AND l.owners < 1000000", order="value DESC, gav DESC, subject_key"),
              Column("value", "Investors", "num"), [base[0], base[1], base[3], base[4], base[5]],
              ["Funds sold through wealth managers and retirement plans count every account holder; a fund of one "
               "pension reports one owner."], **kw),
        Board("sec-adv-highest-minimum", "Private funds with the highest minimum investment", "Velvet Rope",
              "Private funds whose advisers report the steepest minimum investment on Form ADV, each fund's latest "
              "year on file.",
              f"Value = the minimum investment reported for the fund on its latest Form ADV, for minimums under $5 "
              f"billion (above that is an entry error). {SOURCE}",
              _funds("l.min_investment", "l.min_investment > 0 AND l.min_investment < 5e9"),
              Column("value", "Minimum investment", "money"), [base[0], base[1], base[2], base[4], base[5]],
              ["A fund with one or two institutional investors may report its whole commitment as the minimum."], **kw),
        Board("sec-adv-top-advisers", "Advisers running the most private fund money", "The Managers",
              "Investment advisers (registered and exempt reporting) whose latest Form ADV reports the most private "
              "fund assets.",
              "Value = gross private fund assets on the adviser's latest Form ADV filing (Item 7.B, the sum of its "
              "funds' gross asset values), for totals under $5 trillion (above that is an entry error). Regulatory "
              "assets under management is the adviser's Item 5.F figure, which also counts separately managed "
              "accounts. From SEC Form ADV filing data and monthly adviser reports (2001 through the latest file).",
              _advisers(), Column("value", "Private fund assets", "money"),
              [Column("private_funds", "Private funds", "num?"), Column("aum", "Regulatory AUM", "money?"),
               Column("employees", "Employees", "num?"), Column("city", "City"), Column("submitted", "Filed")],
              ["A multi-strategy adviser reports a master fund and its feeders, so the sum can count the same money "
               "more than once."],
              **{**kw, "org_label": "Registration", "unit": "adviser", "year_label": "Year filed", "filters": []}),
        Board("sec-adv-pension-backed", "Private funds holding public pension money", "Pension Backed",
              "Private funds on Form ADV that CalPERS or CalSTRS report a commitment to, matched by fund name and "
              "vintage, ranked by the money committed.",
              f"Value = capital committed by CalPERS and CalSTRS (each pension's latest fund-by-fund private equity "
              f"report) to the fund, for matches of medium or high confidence. Net IRR is the pension's since-inception "
              f"figure net of fees (the higher one when both pensions report). {SOURCE}",
              _funds("p.committed", "p.committed > 0", ", p.pensions, p.net_irr, p.vintage", "JOIN p ON p.fund_id = l.fund_id", PENSIONS),
              Column("value", "Pension commitments", "money"),
              [Column("pensions", "Pensions"), Column("net_irr", "Net IRR", "pct?"), Column("vintage", "Vintage", "year"),
               base[0], base[1], base[2]],
              ["The Form ADV value is the whole fund; the pension's commitment is one slice of it."],
              **{**kw, "filters": []}),
    ]


ALTERNATIVES = {
    "sec-adv-biggest-funds": ["The Whales", "Biggest Pools", "Heavyweights"],
    "sec-adv-fastest-growing": ["Rocket Ships", "Up and to the Right", "Growth Spurt"],
    "sec-adv-most-investors": ["The Crowd", "Everybody's In", "Full House"],
    "sec-adv-highest-minimum": ["Velvet Rope", "Members Only", "The Price of Entry"],
    "sec-adv-top-advisers": ["The Managers", "Who Runs the Money", "Asset Giants"],
    "sec-adv-pension-backed": ["Pension Backed", "Retirement Money at Work", "Sacramento's Picks"],
}
