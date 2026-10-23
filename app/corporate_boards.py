"""Leaderboards for SEC data (app/corporate.py, loader/sec_bulk.py): insider sales, private offerings, CEO pay,
and people on nonprofit returns who are also corporate insiders. Views read the summary tables corporate.build()
makes (sec_insider_sales, sec_person_links) and sec_formd / sec_exec_pay. Shown only where SEC_PUBLIC=1.
"""

from __future__ import annotations

GROUP_NAME = "corporate"
GROUP = {"title": "Corporate insiders and private money", "subtitle": "Suite Life",
         "definition": "Corporate insiders cashing out, the biggest private fundraisings filed on Form D, CEO pay "
                       "from proxy statements, and nonprofit board members who are also corporate insiders. From "
                       "SEC EDGAR structured data."}
EDGAR = "'https://www.sec.gov/Archives/edgar/data/' || ltrim({cik}, '0') || '/' || replace({acc}, '-', '') || '/' || {acc} || '-index.htm'"


def _sales() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'insider'::text AS subject_kind, s.owner_cik AS subject_key, s.owner_name AS subject_name,
               {norm_sql('s.owner_name')} AS subject_norm, '/corporate/insider/' || ltrim(s.owner_cik, '0') AS subject_url,
               NULL::text AS match, NULL::text AS ein, s.issuer_name AS org_name, s.state, 'SEC'::text AS form_type,
               s.year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, s.sold AS value,
               '/corporate/company/' || ltrim(s.issuer_cik, '0') AS org_url, s.ticker, s.roles, s.filings,
               {EDGAR.format(cik='s.issuer_cik', acc='s.last_accession')} AS source_url
        FROM sec_insider_sales s WHERE s.sold > 0"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _formd() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'offering'::text AS subject_kind, d.accession AS subject_key, d.issuer_name AS subject_name,
               {norm_sql('d.issuer_name')} AS subject_norm, '/corporate/form-d/' || d.accession AS subject_url,
               NULL::text AS match, d.issuer_ein AS ein, coalesce(d.fund_type, d.industry) AS org_name, d.state,
               'D'::text AS form_type, extract(year FROM d.filing_date)::int AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, d.amount_sold AS value, d.industry, d.investors,
               {EDGAR.format(cik='d.cik', acc='d.accession')} AS source_url
        FROM sec_formd d
        WHERE d.amount_sold > 0 AND d.amount_sold < 1e11 AND NOT d.is_amendment"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _subscription(where: str, value: str) -> str:
    """One row per offering (sec_formd_offerings): the latest filing's amount sold against its total offering
    amount, with the original target alongside."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'offering'::text AS subject_kind, o.root_accession AS subject_key, o.issuer_name AS subject_name,
               {norm_sql('o.issuer_name')} AS subject_norm, '/corporate/form-d/' || o.latest_accession AS subject_url,
               NULL::text AS match, NULL::text AS ein, coalesce(o.fund_type, o.industry) AS org_name, o.state,
               'D'::text AS form_type, extract(year FROM o.latest_date)::int AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, ({value})::numeric AS value, o.initial_offering, o.latest_offering,
               o.latest_sold, CASE WHEN o.initial_offering > 0 THEN round(o.latest_sold / o.initial_offering, 2) END AS ratio,
               o.filings, o.investors, o.first_date,
               {EDGAR.format(cik='o.cik', acc='o.latest_accession')} AS source_url
        FROM sec_formd_offerings o
        WHERE o.latest_sold IS NOT NULL AND o.latest_sold < 1e11 AND {where}"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _adv_shrinking() -> str:
    """Private funds (Form ADV Schedule D 7.B.1, loader/adv.py) by the fall from their peak gross asset value to the
    lowest value reported in a later year."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        WITH y AS (SELECT DISTINCT ON (fund_id, year) fund_id, year, gav, owners, fund_name, crd, fund_type, state
                   FROM adv_funds WHERE gav IS NOT NULL AND gav < 250e9 AND fund_id IS NOT NULL ORDER BY fund_id, year, gav DESC),
             r AS (SELECT y.*, row_number() OVER (PARTITION BY fund_id ORDER BY gav DESC, year) AS rn FROM y),
             p AS (SELECT fund_id, max(year) FILTER (WHERE rn = 1) AS peak_year, max(gav) FILTER (WHERE rn = 1) AS peak,
                          max(owners) FILTER (WHERE rn = 1) AS peak_owners, max(gav) FILTER (WHERE rn = 2) AS second
                   FROM r WHERE rn <= 2 GROUP BY fund_id HAVING max(gav) FILTER (WHERE rn = 1) >= 5000000),
             l AS (SELECT DISTINCT ON (y.fund_id) y.*, p.peak_year, p.peak, p.peak_owners, p.second
                   FROM y JOIN p USING (fund_id) WHERE y.year > p.peak_year ORDER BY y.fund_id, y.gav, y.year DESC),
             a AS (SELECT DISTINCT ON (crd) crd, coalesce(business_name, legal_name) AS adviser FROM adv_filings
                   WHERE crd IS NOT NULL ORDER BY crd, submitted DESC NULLS LAST)
        SELECT 'fund'::text AS subject_kind, l.fund_id AS subject_key, l.fund_name AS subject_name,
               {norm_sql('l.fund_name')} AS subject_norm, '/corporate/fund/' || l.fund_id AS subject_url,
               NULL::text AS match, NULL::text AS ein, a.adviser AS org_name, l.state, 'ADV'::text AS form_type,
               l.year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, round(100 * (l.peak - l.gav) / l.peak, 1) AS value,
               (l.peak - l.gav) AS drop, l.peak, l.peak_year, l.gav AS low,
               l.peak_owners, l.owners AS low_owners, l.fund_type,
               'https://adviserinfo.sec.gov/firm/summary/' || l.crd AS source_url
        FROM l LEFT JOIN a ON a.crd = l.crd
        WHERE l.gav < l.peak * 0.99 
          AND coalesce(l.second, 0) >= l.peak / 10
          AND NOT (l.gav > 0 AND (l.gav * 1000 BETWEEN l.peak / 2 AND l.peak * 2
                                  OR l.gav * 1000000 BETWEEN l.peak / 2 AND l.peak * 2))"""
    return _ranked_by_org(inner, "value DESC, drop DESC, subject_key")


def _buyback_years(where: str, value: str) -> str:
    """One row per company per fiscal year (sec_buybacks, qtrs 4): buyback spending against net income."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'company'::text AS subject_kind, b.cik AS subject_key, coalesce(n.name, b.name) AS subject_name,
               {norm_sql('coalesce(n.name, b.name)')} AS subject_norm, '/corporate/company/' || b.cik || '#buybacks' AS subject_url,
               NULL::text AS match, NULL::text AS ein, NULL::text AS org_name, NULL::text AS state, '10-K'::text AS form_type,
               extract(year FROM b.period_end)::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               ({value})::numeric AS value, b.buybacks, b.net_income, b.period_end,
               CASE WHEN b.net_income > 0 THEN round(100 * b.buybacks / b.net_income, 1) END AS pct_of_profit,
               'https://www.sec.gov/Archives/edgar/data/' || b.cik || '/' || replace(b.adsh, '-', '') || '/' || b.adsh || '-index.htm' AS source_url
        FROM sec_buybacks b
        LEFT JOIN (SELECT DISTINCT ON (cik) cik, name FROM sec_fin_subs ORDER BY cik, filed DESC) n ON n.cik = b.cik
        WHERE b.qtrs = 4 AND b.buybacks > 0 AND b.buybacks < 2e11 AND {where}
          AND coalesce(n.name, b.name) !~* '\\m(etf|spdr|ishares|proshares|grayscale|direxion|invesco db|united states (oil|gasoline|natural gas)|gold trust|silver trust|bitcoin)\\M'"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _buyback_sellers(where: str) -> str:
    """One row per insider, company and year: open-market sales (sec_buyback_sales) matching where."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'insider'::text AS subject_kind, s.owner_cik || ':' || s.issuer_cik AS subject_key, s.owner_name AS subject_name,
               {norm_sql('s.owner_name')} AS subject_norm, '/corporate/insider/' || ltrim(s.owner_cik, '0') || '#trades' AS subject_url,
               NULL::text AS match, NULL::text AS ein, coalesce(n.name, s.issuer_cik) AS org_name, NULL::text AS state,
               '4'::text AS form_type, s.year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               s.sold AS value, s.sales, s.plan_sold, cb.buybacks AS company_buybacks,
               '/corporate/company/' || s.issuer_cik || '#buybacks' AS org_url,
               '/corporate/company/' || s.issuer_cik || '#buybacks' AS source_url
        FROM (SELECT x.owner_cik, x.issuer_cik, min(x.owner_name) AS owner_name, extract(year FROM x.trans_date)::int AS year,
                     sum(x.value) AS sold, count(*) AS sales, sum(x.value) FILTER (WHERE x.plan) AS plan_sold
              FROM (SELECT DISTINCT ON (y.issuer_cik, y.trans_date, y.shares, y.price) y.*
                    FROM sec_buyback_sales y
                    JOIN sec_insider_owners o ON o.accession = y.accession AND o.owner_cik = y.owner_cik
                    WHERE y.owner_cik IS NOT NULL AND (o.relationship ILIKE '%%officer%%' OR o.relationship ILIKE '%%director%%')
                    ORDER BY y.issuer_cik, y.trans_date, y.shares, y.price, y.owner_cik) x
              WHERE {where}
              GROUP BY x.owner_cik, x.issuer_cik, extract(year FROM x.trans_date)) s
        LEFT JOIN (SELECT cik, extract(year FROM period_end - 20)::int AS year, sum(buybacks) AS buybacks
                   FROM sec_buybacks WHERE qtrs = 1 GROUP BY 1, 2) cb ON cb.cik = s.issuer_cik AND cb.year = s.year
        LEFT JOIN (SELECT DISTINCT ON (cik) cik, name FROM sec_fin_subs ORDER BY cik, filed DESC) n ON n.cik = s.issuer_cik"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _buyback_boards(kw: dict) -> list:
    from app.boards import Board, Column
    fsds = ("From the SEC's Financial Statement Data Sets (XBRL from 10-K filings, 2009 onward): cash paid to "
            "repurchase common stock (PaymentsForRepurchaseOfCommonStock, or PaymentsForRepurchaseOfEquity when that "
            "is the only tag) and net income (NetIncomeLoss, or ProfitLoss), the latest filing's figures for each "
            "fiscal year.")
    sales = ("Sales: open-market sales (Form 4 code S, shares times price) by officers and directors, one reporting "
             "owner per filing; a sale reported identically by several insiders (a family holding company) is "
             "counted once, under the first filer; "
             "quarters of buybacks are derived from the company's 10-Q and 10-K cash flow statements. A sale in this "
             "list is a timing overlap, not evidence of wrongdoing; sales marked 10b5-1 were scheduled in advance under "
             "a trading plan.")
    k = {**kw, "org_label": "Company"}
    yc = [Column("buybacks", "Buybacks", "money"), Column("net_income", "Net income", "money?"),
          Column("pct_of_profit", "Share of profits", "pct?")]
    sc = [Column("sales", "Sales", "num"), Column("plan_sold", "Under 10b5-1 plans", "money?"),
          Column("company_buybacks", "Company buybacks that year", "money?")]
    return [
        Board("sec-buyback-spenders", "Biggest share buyback spenders", "Buying Themselves Back",
              "Public companies that spent the most buying back their own stock in a fiscal year, with what that was "
              "as a share of the year's profits.",
              f"Value = cash spent repurchasing common stock in the fiscal year. Share of profits = buybacks / net "
              f"income (blank in a loss year). Exchange-traded funds and trusts, whose share redemptions are tagged "
              f"as repurchases, are left out. {fsds}",
              _buyback_years("true", "b.buybacks"), Column("value", "Buybacks", "money"), yc[1:],
              ["Buybacks return cash to shareholders and raise earnings per share; they also support the stock price "
               "when executives are paid in stock."],
              year_label="Fiscal year", unit="company", **{**k, "org_label": "Organization"}),
        Board("sec-buybacks-over-profits", "Companies that spent more on buybacks than they earned", "Spending Past the Profits",
              "Public companies whose stock buybacks in a fiscal year were bigger than their net income for that year, "
              "including companies that lost money and bought back stock anyway.",
              f"Value = buybacks minus net income (all of the buybacks in a year with a loss), for years where "
              f"buybacks were larger and at least $10 million. Exchange-traded funds and trusts, whose share "
              f"redemptions are tagged as repurchases, are left out. {fsds}",
              _buyback_years("b.net_income IS NOT NULL AND b.buybacks > b.net_income AND b.buybacks >= 10000000",
                             "b.buybacks - greatest(b.net_income, 0)"),
              Column("value", "Buybacks beyond profits", "money"), yc,
              ["The difference is paid from cash on hand, borrowing or asset sales."],
              year_label="Fiscal year", unit="company", **{**k, "org_label": "Organization"}),
        Board("sec-buyback-insider-sellers", "Executives who sold the most while their company bought back stock",
              "Selling Into the Buyback",
              "Corporate officers and directors who sold the most of their own company's stock on the open market in quarters when "
              "the company was buying back its shares.",
              f"Value = insider's open-market sales in the year, counting only sales in calendar quarters when the "
              f"company reported buyback spending. {sales}",
              _buyback_sellers("x.quarter_buybacks > 0"), Column("value", "Sold during buybacks", "money"), sc,
              ["A company buying its own shares adds demand for the stock in the same quarters its insiders sold."],
              year_label="Year", unit="insider", **k),
        Board("sec-buyback-announcement-sellers", "Insiders who sold the most right after a buyback announcement",
              "Right After the Announcement",
              "Corporate officers and directors who sold the most stock within 30 days after their company announced a new or "
              "larger buyback in an 8-K.",
              f"Value = insider's open-market sales in the year made 0 to 30 days after an 8-K announcing a new or "
              f"larger repurchase authorization (found in EDGAR full-text search by phrase; some announcements use "
              f"other wording and are missed). {sales}",
              _buyback_sellers("x.ann_accession IS NOT NULL"), Column("value", "Sold after announcements", "money"), sc,
              ["Buyback announcements often lift a stock's price for a few days."],
              year_label="Year", unit="insider", **k),
    ]


def _ceo_pay() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'company'::text AS subject_kind, p.cik AS subject_key, p.entity_name AS subject_name,
               {norm_sql('p.entity_name')} AS subject_norm, '/corporate/company/' || p.cik AS subject_url,
               NULL::text AS match, NULL::text AS ein, NULL::text AS org_name, NULL::text AS state,
               'DEF 14A'::text AS form_type, extract(year FROM p.period_end)::int AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, p.peo_total AS value, p.neo_avg_total,
               CASE WHEN p.neo_avg_total > 0 THEN round(p.peo_total / p.neo_avg_total, 1) END AS ratio,
               'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=DEF+14A&CIK=' || p.cik AS source_url
        FROM sec_exec_pay p
        WHERE p.peo_total > 0 AND p.peo_total < 1e9
          AND NOT coalesce(p.peo_total > 50 * (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY p2.peo_total)
                                               FROM sec_exec_pay p2 WHERE p2.cik = p.cik
                                                 AND p2.period_end <> p.period_end AND p2.peo_total > 0), false)"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _two_hats() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'person'::text AS subject_kind, pc.id::text AS subject_key, pc.display_name AS subject_name,
               {norm_sql('pc.display_name')} AS subject_norm, '/person/' || pc.id || '#sec' AS subject_url,
               'FUZZY'::text AS match, NULL::text AS ein, pc.orgs[1] AS org_name, pc.states[1] AS state,
               'SEC'::text AS form_type, x.last_year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               x.companies AS value, pc.n_orgs, pc.latest_title, x.companies_list,
               '/person/' || pc.id || '#sec' AS source_url
        FROM (SELECT l.cluster_id, count(DISTINCT f.issuer_cik) AS companies,
                     extract(year FROM max(f.filing_date))::int AS last_year,
                     left(string_agg(DISTINCT f.issuer_name, '; '), 300) AS companies_list
              FROM sec_person_links l JOIN sec_insider_owners o ON o.owner_cik = l.key
              JOIN sec_insider_filings f ON f.accession = o.accession
              WHERE l.source = 'insider' GROUP BY 1) x
        JOIN person_clusters pc ON pc.id = x.cluster_id"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def corporate_boards() -> list:
    from app.boards import Board, Column
    from app.corporate import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="sec", source_label="SEC EDGAR structured data",
              search=True)
    return [
        Board("sec-insider-sales", "Biggest insider stock sales", "Cashing Out",
              "Corporate officers, directors and big shareholders who sold the most of their own company's stock "
              "on the open market in a year.",
              "Value = shares times price for open-market sales (transaction code S) the insider reported on Form 4 "
              "in the year, at one company. Filings that list more than one reporting owner are left out so no sale "
              "is counted twice, and so are single transactions over $5 billion or $100,000 a share (filer typos). "
              "From the SEC's Insider Transactions Data Sets (2006 onward).",
              _sales(), Column("value", "Sold", "money"),
              [Column("ticker", "Ticker"), Column("roles", "Role"), Column("filings", "Filings", "num")],
              ["Many large sales are made under prearranged trading plans (Rule 10b5-1)."],
              year_label="Year", org_label="Company", unit="insider", **kw),
        Board("sec-formd-raises", "Biggest private fundraisings", "Private Money",
              "Private funds and companies that reported raising the most on Form D, the notice filed for offerings "
              "exempt from registration.",
              "Value = total amount sold reported on the filing (new notices only, not amendments). Form D is "
              "filed within 15 days of the first sale; amounts are what the issuer reports and are not audited. "
              "From the SEC's Form D Data Sets (coverage starts in 2014).",
              _formd(), Column("value", "Amount sold", "money"),
              [Column("industry", "Industry"), Column("investors", "Investors", "num?")],
              ["Pooled investment funds (private equity, hedge and venture funds) report the capital raised to date."],
              year_label="Year filed", org_label="Fund type or industry", unit="offering", **kw),
        *_subscription_boards(kw),
        *_buyback_boards(kw),
        Board("sec-adv-shrinking", "Private funds whose reported value fell the most (distributions or write-downs)",
              "Distributions or Write-downs",
              "Private funds whose gross asset value on Form ADV fell the most, in percent, from its peak to a later year. The drop "
              "is money paid back to investors (distributions), a write-down of the fund's holdings, or both: the "
              "filing doesn't say which.",
              "Value = the percent drop from the fund's highest gross asset value in any year to the lowest value it "
              "reported in a later year, for peaks of at least $5 million; ties go to the bigger dollar drop. From SEC Form ADV data, Schedule D section 7.B.1 (private funds "
              "reported by registered and exempt reporting advisers, November 2011 through the latest SEC file), the "
              "adviser's latest filing in each year. Left out as entry errors: a peak more than 10 times the fund's "
              "next-highest year, a later value that matches the peak in thousands or millions, and any year over $250 billion (more than any private fund holds).",
              _adv_shrinking(), Column("value", "Drop from peak", "pct"),
              [Column("drop", "Dollar drop", "money"), Column("peak", "Peak value", "money"),
               Column("peak_year", "Peak year"), Column("low", "Later low", "money"),
               Column("peak_owners", "Investors at peak", "num?"), Column("low_owners", "Investors later", "num?")],
              ["Form ADV shows fund size, not distributions: a fund returning money to investors as it winds down "
               "shrinks just like one whose investments lost value."],
              year_label="Year of the low", org_label="Adviser", unit="fund", **kw),
        Board("sec-ceo-pay", "Highest-paid CEOs", "Corner Office",
              "Public companies whose principal executive officer had the highest total compensation, from the "
              "pay-versus-performance table in the proxy statement.",
              "Value = total compensation of the principal executive officer as reported in the Summary "
              "Compensation Table and repeated in the proxy's pay-versus-performance table, tagged in XBRL "
              "(ecd:PeoTotalCompAmt), for the fiscal year ending in the year shown. Ratio = CEO pay / average of the "
              "other named executives. Proxies filed from 2023 on. Values of $1 billion or more, or more than 50 "
              "times the company's other years, are tagging errors (thousands tagged as dollars) and are left out.",
              _ceo_pay(), Column("value", "CEO total pay", "money"),
              [Column("neo_avg_total", "Other executives, average", "money?"), Column("ratio", "Ratio", "multiple?")],
              ["A company that had two CEOs in a year reports each; the tagged total may be the sum."],
              year_label="Fiscal year", org_label="Organization", unit="company", **kw),
        Board("sec-990-insiders", "Nonprofit leaders who are corporate insiders", "Two Hats",
              "People listed on nonprofit tax returns who also file as officers, directors or 10% owners of public "
              "companies, ranked by how many companies.",
              "Value = companies the person filed insider reports (Forms 3, 4, 5) for. Linked by name only: the "
              "same first, middle and last name, held by exactly one person on this site, in one of that person's "
              "states. Every link is marked Fuzzy; check the person page.",
              _two_hats(), Column("value", "Companies", "num"),
              [Column("latest_title", "Nonprofit title"), Column("companies_list", "Companies")],
              ["Name matches can join two different people who share a full name in the same state."],
              year_label="Latest filing", org_label="Nonprofit", unit="person", **kw),
    ]


def _subscription_boards(kw: dict) -> list:
    from app.boards import Board, Column
    src = ("From the SEC's Form D Data Sets (coverage starts in 2014). An offering is the original Form D and its amendments; "
           "the latest filing's total amount sold is compared with the total offering amount on the first filing (issuers raise the "
           "target in amendments as they sell more). Amounts are what the "
           "issuer reports, not audited, and an open offering may still be selling. Deal-by-deal SPVs (\"SPV\" or "
           "\"a series of\" in the name) are left out of the over, under and on-target lists.")
    cols = [Column("initial_offering", "First target", "money"), Column("latest_offering", "Latest target", "money"),
            Column("latest_sold", "Sold", "money"), Column("ratio", "Sold / first target", "multiple"),
            Column("filings", "Filings", "num")]
    k = {**kw, "year_label": "Latest filing", "org_label": "Fund type or industry", "unit": "offering"}
    return [
        Board("sec-formd-oversubscribed", "Oversubscribed private offerings", "Overflowing",
              "Offerings that have sold more than the target on their first filing, by the latest amendment.",
              f"Value = amount sold (latest filing) minus the first filing's total offering amount, for first targets of at "
              f"least $100,000; offerings reporting more than 50 times their first target are left out (almost always "
              f"amounts entered in the wrong units). {src}",
              _subscription("NOT o.is_spv AND NOT o.initial_indefinite AND o.initial_offering >= 100000 AND o.latest_sold > o.initial_offering * 1.01 "
                            "AND o.latest_sold <= o.initial_offering * 50",
                            "o.latest_sold - o.initial_offering"),
              Column("value", "Over target", "money"), cols, [], **k),
        Board("sec-formd-undersubscribed", "Undersubscribed private offerings", "Short of the Mark",
              "Offerings that have sold less than the target on their first filing, by the latest amendment.",
              f"Value = the first filing's total offering amount minus amount sold (latest filing), for first targets of at "
              f"least $100,000. {src}",
              _subscription("NOT o.is_spv AND NOT o.initial_indefinite AND o.initial_offering >= 100000 AND o.latest_sold < o.initial_offering * 0.99",
                            "o.initial_offering - o.latest_sold"),
              Column("value", "Short of target", "money"), cols, [], **k),
        Board("sec-formd-on-target", "Private offerings right on target", "Bullseye",
              "Offerings whose amount sold (latest filing) matches the target on their first filing, within 1%.",
              f"Value = amount sold (latest filing), for offerings within 1% of a first target of at least $100,000. {src}",
              _subscription("NOT o.is_spv AND NOT o.initial_indefinite AND o.initial_offering >= 100000 "
                            "AND o.latest_sold BETWEEN o.initial_offering * 0.99 AND o.initial_offering * 1.01",
                            "o.latest_sold"),
              Column("value", "Sold", "money"), cols, [], **k),
        Board("sec-formd-filed-once", "Private offerings filed once, never updated", "Filed Once, Never Updated",
              "Private offerings whose only Form D is the first one: no amendment in more than a year, though an "
              "offering still selling must file one every year. Ranked by the amount they set out to raise.",
              f"Value = the total offering amount on the only filing, for offerings first filed more than 13 months "
              f"ago with a target of at least $100,000. Funds whose adviser reports their size on Form ADV are left "
              f"out (they are tracked, just not through Form D; their pages show the Form ADV value). An offering "
              f"that closed within a year owes no amendment, so this lists silence, not wrongdoing. {src}",
              _subscription("NOT o.is_spv AND o.filings = 1 AND NOT o.initial_indefinite "
                            "AND o.first_date < current_date - interval '13 months' "
                            "AND o.initial_offering >= 100000 AND o.initial_offering < 1e11 "
                            "AND NOT EXISTS (SELECT 1 FROM adv_fund_links l JOIN adv_funds f ON f.fund_id = l.fund_id "
                            "WHERE l.root_accession = o.root_accession AND f.gav > 0)",
                            "o.initial_offering"),
              Column("value", "Target", "money"),
              [Column("latest_sold", "Sold (reported)", "money"), Column("first_date", "Filed"),
               Column("investors", "Investors", "num?")], [], **k),
        Board("sec-formd-indefinite", "Private offerings with an indefinite target", "No Ceiling",
              "Offerings whose total offering amount is marked \"Indefinite\" on the first or latest filing (common for "
              "open-ended funds), ranked by "
              "the amount sold.",
              f"Value = amount sold (latest filing), for offerings whose total offering amount is Indefinite. {src}",
              _subscription("(o.indefinite OR o.initial_indefinite) AND o.latest_sold > 0", "o.latest_sold"),
              Column("value", "Sold", "money"),
              [Column("latest_sold", "Sold", "money"), Column("filings", "Filings", "num"),
               Column("investors", "Investors", "num?")], [], **k),
    ]


ALTERNATIVES = {
    "sec-insider-sales": ["Cashing Out", "Exit Strategy", "Selling the Farm"],
    "sec-formd-raises": ["Private Money", "Quiet Billions", "The Exempt List"],
    "sec-ceo-pay": ["Corner Office", "C-Suite Payday", "Top Dollar"],
    "sec-990-insiders": ["Two Hats", "Boardroom Crossover", "Double Duty"],
    "sec-buyback-spenders": ["Buying Themselves Back", "Shareholder Payday", "The Buyback Kings"],
    "sec-buybacks-over-profits": ["Spending Past the Profits", "Borrowing to Buy Back", "More Than They Made"],
    "sec-buyback-insider-sellers": ["Selling Into the Buyback", "The Other Side of the Trade", "Cashing In on the Bid"],
    "sec-buyback-announcement-sellers": ["Right After the Announcement", "Thirty-Day Window", "Good News, Sold"],
    "sec-formd-filed-once": ["Filed Once, Never Updated", "One and Done", "Radio Silence"],
    "sec-adv-shrinking": ["Distributions or Write-downs", "Shrinking Funds", "Paid Out or Marked Down"],
}
