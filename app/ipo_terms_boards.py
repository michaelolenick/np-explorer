"""Leaderboards for the IPO offering terms (loader/s1_terms.py, app/ipos.py; owner, 2026-11-13): the biggest
offerings by gross proceeds, the IPOs priced furthest below and above their proposed range, and the busiest
underwriters. One row per registrant (or per underwriting firm); Year = the year the deal priced. Shown unless
IPOS_PUBLIC=0. The registration-history boards are app/ipo_boards.py (group "ipos")."""

from __future__ import annotations

GROUP_NAME = "ipo-terms"
GROUP = {"title": "IPO pricing and underwriters", "subtitle": "Ringing the Bell",
         "definition": "What the IPOs raised and who sold them, from the cover pages of the final prospectuses: the "
                       "biggest offerings by gross proceeds, the deals priced furthest below and above the range the "
                       "company first proposed, and the investment banks on the most deals. From SEC EDGAR."}
SOURCE = ("From the cover pages of the final prospectuses (Forms 424B4 and 424B1) and the last registration statement "
          "before pricing (S-1/A, F-1/A) in SEC EDGAR, read by loader/s1_terms.py: price range, final price, shares, "
          "gross proceeds (price times shares, or the cover's total) and the underwriters named. Each registrant "
          "appears once with its earliest priced offering in the window; follow-on and resale prospectuses are left "
          "out of the IPO boards by the cover's own wording.")
EDGAR = "'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=' || c.cik || '&type=424B4'"
RANGE = "CASE WHEN c.price_low IS NOT NULL THEN '$' || trim(to_char(c.price_low, '999990.99')) || '-$' || trim(to_char(c.price_high, '999990.99')) END"


def _companies(value: str, where: str, order: str = "value DESC, offer_proceeds DESC NULLS LAST, subject_key") -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'ipo_company'::text AS subject_kind, c.cik AS subject_key, c.name AS subject_name,
               {norm_sql('c.name')} AS subject_norm, '/ipos/' || ltrim(c.cik, '0') AS subject_url, NULL::text AS match,
               c.ein, c.sic_desc AS org_name, c.state, c.kind AS form_type, extract(year FROM c.offer_date)::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value, NULL::text AS org_url,
               {EDGAR} AS source_url, c.offer_date, c.offer_price, {RANGE} AS price_range,
               round((c.price_low + c.price_high) / 2, 2) AS midpoint, c.offer_shares, c.offer_proceeds,
               c.offer_exchange || coalesce(' ' || c.offer_ticker, '') AS listing, c.lead_underwriters, c.n_underwriters
        FROM ipo_companies c
        WHERE c.name IS NOT NULL AND c.offer_price IS NOT NULL AND c.offer_date IS NOT NULL AND ({where})"""
    return _ranked_by_org(inner, order)


def _underwriters() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'ipo_underwriter'::text AS subject_kind, u.name_key AS subject_key, u.name AS subject_name,
               {norm_sql('u.name')} AS subject_norm, '/ipos/underwriters/' || replace(u.name_key, ' ', '-') AS subject_url,
               NULL::text AS match, NULL::text AS ein, u.bd_name AS org_name, NULL::text AS state, '424B4'::text AS form_type,
               extract(year FROM u.last)::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               u.deals::numeric AS value, NULL::text AS org_url,
               CASE WHEN u.bd_cik IS NOT NULL THEN 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=' || u.bd_cik END AS source_url,
               u.lead_deals, u.ipos, u.proceeds, u.lead_proceeds, extract(year FROM u.first)::int AS first_year,
               extract(year FROM u.last)::int AS last_year
        FROM ipo_underwriters u WHERE u.deals > 0"""
    return _ranked_by_org(inner, "value DESC, proceeds DESC NULLS LAST, subject_key")


def ipo_terms_boards() -> list:
    from app.boards import Board, Column
    from app.ipos import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="ipo", year_label="Priced", org_label="Industry",
              source_label="SEC EDGAR prospectuses", search=True, unit="registrant")
    deal = [Column("offer_date", "Priced"), Column("offer_price", "Price", "money"), Column("price_range", "Proposed range"),
            Column("offer_shares", "Shares", "num"), Column("offer_proceeds", "Gross proceeds", "money"), Column("listing", "Listing"),
            Column("lead_underwriters", "Lead underwriters"), Column("n_underwriters", "Syndicate", "num")]
    return [
        Board("ipo-biggest", "Biggest IPOs by gross proceeds", "Ringing the Bell",
              "Initial public offerings ranked by what they raised: the final price times the shares sold, as the "
              "cover of the final prospectus states it.",
              f"Value = gross proceeds of the offering (the cover's total, else final price x shares sold, before "
              f"underwriting discounts and any over-allotment option), for registrants whose prospectus calls the deal "
              f"an initial public offering. {SOURCE}",
              _companies("c.offer_proceeds", "c.offer_is_ipo AND c.offer_proceeds > 0"), Column("value", "Gross proceeds", "money"),
              [deal[0], deal[1], deal[2], deal[3], deal[5], deal[6], deal[7]],
              ["Proceeds include shares sold by existing holders; the company keeps only its own share, less fees.",
               "A few very large '424B4' prospectuses belong to spin-offs or carve-outs rather than classic IPOs; the "
               "registrant's page shows the document."], **kw),
        Board("ipo-priced-below-range", "IPOs priced furthest below their proposed range", "Marked Down",
              "Companies whose final IPO price came in below the price range they had proposed in their last "
              "registration statement, ranked by the discount to the range's midpoint.",
              f"Value = (midpoint of the proposed range - final price) / midpoint, in percent, for IPOs whose final "
              f"price was below the low end of the range. {SOURCE}",
              _companies("round((c.price_low + c.price_high) / 2 - c.offer_price, 4) / ((c.price_low + c.price_high) / 2) * 100",
                         "c.offer_is_ipo AND c.price_low IS NOT NULL AND c.offer_price < c.price_low"),
              Column("value", "Cut from midpoint", "pct"),
              [deal[0], deal[2], Column("midpoint", "Midpoint", "money"), deal[1], deal[4], deal[5], deal[6]],
              ["A company that cut its price often also cut the share count; the proceeds column shows the result."], **kw),
        Board("ipo-priced-above-range", "IPOs priced furthest above their proposed range", "Hot Deals",
              "Companies whose final IPO price came in above the top of the range they had proposed, ranked by the "
              "premium to the range's midpoint.",
              f"Value = (final price - midpoint of the proposed range) / midpoint, in percent, for IPOs whose final "
              f"price was above the high end of the range. {SOURCE}",
              _companies("round(c.offer_price - (c.price_low + c.price_high) / 2, 4) / ((c.price_low + c.price_high) / 2) * 100",
                         "c.offer_is_ipo AND c.price_high IS NOT NULL AND c.offer_price > c.price_high"),
              Column("value", "Premium to midpoint", "pct"),
              [deal[0], deal[2], Column("midpoint", "Midpoint", "money"), deal[1], deal[4], deal[5], deal[6]], [], **kw),
        Board("ipo-busiest-underwriters", "Underwriters on the most priced offerings", "Syndicate Regulars",
              "Investment banks ranked by the number of priced registered stock offerings they were named in as an "
              "underwriter, lead or syndicate member.",
              f"Value = final prospectuses (424B4, 424B1) naming the firm among the underwriters, all years, with "
              f"the firm's names normalised (Goldman, Sachs & Co. and Goldman Sachs & Co. LLC are one firm). {SOURCE}",
              _underwriters(), Column("value", "Deals", "num"),
              [Column("lead_deals", "As lead", "num"), Column("ipos", "IPOs", "num"), Column("proceeds", "Proceeds of deals", "money"),
               Column("lead_proceeds", "Proceeds as lead", "money"), Column("first_year", "First", "year"), Column("last_year", "Latest", "year")],
              ["Firms that were renamed are merged by the rule in loader/s1_terms.py; firms that were bought keep their own name."],
              **{**kw, "unit": "underwriter", "org_label": "Registered as", "year_label": "Latest deal"}),
    ]


ALTERNATIVES = {
    "ipo-biggest": ["Ringing the Bell", "Biggest Debuts", "Opening Day Haul"],
    "ipo-priced-below-range": ["Marked Down", "Cold Reception", "Below the Range"],
    "ipo-priced-above-range": ["Hot Deals", "Oversubscribed", "Above the Range"],
    "ipo-busiest-underwriters": ["Syndicate Regulars", "The Bookrunners", "Wall Street's Dealmakers"],
}
