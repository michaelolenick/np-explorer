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
               o.latest_sold, CASE WHEN o.latest_offering > 0 THEN round(o.latest_sold / o.latest_offering, 2) END AS ratio,
               o.filings, o.investors, o.first_date,
               {EDGAR.format(cik='o.cik', acc='o.latest_accession')} AS source_url
        FROM sec_formd_offerings o
        WHERE o.latest_sold IS NOT NULL AND o.latest_sold < 1e11 AND {where}"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


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
           "the latest filing's total amount sold is compared with its total offering amount. Amounts are what the "
           "issuer reports, not audited, and an open offering may still be selling. Deal-by-deal SPVs (\"SPV\" or "
           "\"a series of\" in the name) are left out of the over, under and on-target lists.")
    cols = [Column("initial_offering", "First target", "money"), Column("latest_offering", "Latest target", "money"),
            Column("latest_sold", "Sold", "money"), Column("ratio", "Sold / target", "multiple"),
            Column("filings", "Filings", "num")]
    k = {**kw, "year_label": "Latest filing", "org_label": "Fund type or industry", "unit": "offering"}
    return [
        Board("sec-formd-oversubscribed", "Oversubscribed private offerings", "Overflowing",
              "Offerings that sold more than their stated total offering amount, by the latest filing.",
              f"Value = amount sold minus total offering amount (latest filing), for offerings with a target of at "
              f"least $100,000. {src}",
              _subscription("NOT o.is_spv AND NOT o.indefinite AND o.latest_offering >= 100000 AND o.latest_sold > o.latest_offering * 1.01",
                            "o.latest_sold - o.latest_offering"),
              Column("value", "Over target", "money"), cols, [], **k),
        Board("sec-formd-undersubscribed", "Undersubscribed private offerings", "Short of the Mark",
              "Offerings that have sold less than their stated total offering amount, by the latest filing.",
              f"Value = total offering amount minus amount sold (latest filing), for offerings with a target of at "
              f"least $100,000. {src}",
              _subscription("NOT o.is_spv AND NOT o.indefinite AND o.latest_offering >= 100000 AND o.latest_sold < o.latest_offering * 0.99",
                            "o.latest_offering - o.latest_sold"),
              Column("value", "Short of target", "money"), cols, [], **k),
        Board("sec-formd-on-target", "Private offerings right on target", "Bullseye",
              "Offerings whose amount sold matches their total offering amount (within 1%), by the latest filing.",
              f"Value = amount sold (latest filing), for offerings within 1% of a target of at least $100,000. {src}",
              _subscription("NOT o.is_spv AND NOT o.indefinite AND o.latest_offering >= 100000 "
                            "AND o.latest_sold BETWEEN o.latest_offering * 0.99 AND o.latest_offering * 1.01",
                            "o.latest_sold"),
              Column("value", "Sold", "money"), cols, [], **k),
        Board("sec-formd-indefinite", "Private offerings with an indefinite target", "No Ceiling",
              "Offerings whose total offering amount is marked \"Indefinite\" (common for open-ended funds), ranked by "
              "the amount sold.",
              f"Value = amount sold (latest filing), for offerings whose total offering amount is Indefinite. {src}",
              _subscription("o.indefinite AND o.latest_sold > 0", "o.latest_sold"),
              Column("value", "Sold", "money"),
              [Column("latest_sold", "Sold", "money"), Column("filings", "Filings", "num"),
               Column("investors", "Investors", "num?")], [], **k),
    ]


ALTERNATIVES = {
    "sec-insider-sales": ["Cashing Out", "Exit Strategy", "Selling the Farm"],
    "sec-formd-raises": ["Private Money", "Quiet Billions", "The Exempt List"],
    "sec-ceo-pay": ["Corner Office", "C-Suite Payday", "Top Dollar"],
    "sec-990-insiders": ["Two Hats", "Boardroom Crossover", "Double Duty"],
}
