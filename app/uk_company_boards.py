"""Leaderboards of UK companies (app/uk_companies.py, loader/uk_companies.py; owner, 2026-11-14).

Three boards from schema uk_companies (Companies House free company data and PSC snapshot): industries by new incorporations,
the largest PSC networks, and company status by region. Rebuilt from scripts/nightly.sh after the monthly snapshot reloads.
The free product holds LIVE companies only, so "dissolved" is not counted: the status board ranks regions by the share of live
companies that are not plainly active (strike-off proposals, liquidation, administration, receivership).
"""

from __future__ import annotations

GROUP_NAME = "uk-companies"
GROUP = {"title": "UK companies", "subtitle": "Limited, Not Lost",
         "definition": "Companies on the UK register at Companies House: the industries incorporating the most new companies, "
                       "the people and companies with significant control over the most companies, and how many companies in "
                       "each region are in trouble."}
SOURCE = ("Companies House, Free Company Data Product and People with Significant Control snapshot (Open Government Licence v3.0): "
          "live companies only. Contains public sector information licensed under the Open Government Licence v3.0. "
          "Source: Companies House.")
CH = "'https://find-and-update.company-information.service.gov.uk/company/' || {n}"
DL = "https://download.companieshouse.gov.uk/en_output.html"


def _newest_by_sic() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'uk_sic'::text AS subject_kind, s.code AS subject_key, s.code || ' ' || s.descr AS subject_name,
               {norm_sql("s.code || ' ' || s.descr")} AS subject_norm,
               '/uk/companies/search?q=' || s.code AS subject_url, NULL::text AS match, NULL::text AS ein, NULL::text AS org_name,
               NULL::text AS state, 'UK'::text AS form_type, extract(year FROM current_date)::int AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, s.new_year::numeric AS value, NULL::text AS org_url, '{DL}' AS source_url,
               s.new_quarter, s.companies, round(100.0 * s.new_year / nullif(s.companies, 0), 1) AS share_new, s.latest, s.latest_name
        FROM (SELECT x.code, (array_agg(x.descr))[1] AS descr, count(*) FILTER (WHERE x.incorporated >= current_date - 365) AS new_year,
                     count(*) FILTER (WHERE x.incorporated >= current_date - 91) AS new_quarter, count(*) AS companies,
                     max(x.incorporated) AS latest, (array_agg(x.name ORDER BY x.incorporated DESC NULLS LAST))[1] AS latest_name
              FROM (SELECT u.code, u.descr, c.incorporated, c.name FROM uk_companies.company c,
                           LATERAL unnest(c.sic, c.sic_text) AS u(code, descr)) x
              GROUP BY x.code) s
        WHERE s.new_year > 0"""
    return _ranked_by_org(inner, "value DESC, subject_key")


def _psc_networks() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'uk_psc'::text AS subject_kind, p.name_norm || '|' || p.birth_year || '-' || p.birth_month AS subject_key, p.name AS subject_name,
               {norm_sql('p.name')} AS subject_norm, '/uk/company/' || p.example_company AS subject_url, NULL::text AS match, NULL::text AS ein,
               NULL::text AS org_name, NULL::text AS state, 'UK'::text AS form_type, extract(year FROM p.first_notified)::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, p.companies::numeric AS value, NULL::text AS org_url,
               {CH.format(n='p.example_company')} AS source_url,
               p.birth_year, p.nationality, p.country_of_residence, p.example_company, ec.name AS example_name, p.first_notified
        FROM uk_companies.psc_person p LEFT JOIN uk_companies.company ec ON ec.company_number = p.example_company
        WHERE p.companies >= 5"""
    return _ranked_by_org(inner, "value DESC, subject_key")


def _status_by_region() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'uk_region'::text AS subject_kind, r.region AS subject_key, r.region AS subject_name, {norm_sql('r.region')} AS subject_norm,
               '/uk/companies/search?q=limited&region=' || replace(r.region, ' ', '%20') AS subject_url, NULL::text AS match, NULL::text AS ein,
               NULL::text AS org_name, NULL::text AS state, 'UK'::text AS form_type, extract(year FROM current_date)::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, round(100.0 * r.other / r.companies, 2) AS value, NULL::text AS org_url,
               '{DL}' AS source_url, r.companies, r.active, r.strike_off, r.liquidation, r.administration, r.other
        FROM (SELECT c.region, count(*) AS companies, count(*) FILTER (WHERE c.status = 'Active') AS active,
                     count(*) FILTER (WHERE c.status ILIKE '%%strike off%%') AS strike_off,
                     count(*) FILTER (WHERE c.status ILIKE '%%liquidation%%') AS liquidation,
                     count(*) FILTER (WHERE c.status ILIKE '%%administration%%') AS administration,
                     count(*) FILTER (WHERE c.status <> 'Active') AS other
              FROM uk_companies.company c WHERE c.region IS NOT NULL GROUP BY c.region) r
        WHERE r.companies >= 1000"""
    return _ranked_by_org(inner, "value DESC, subject_key")


_OFFICER_SOURCE = ("Companies House REST API (officers), fetched company by company in priority order, so counts cover the companies fetched so far "
                   "and grow over time. Birth month and year only; no day of birth or home address is kept. " + SOURCE)


def _officer_inner(where: str, extra: str = "") -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'uk_officer'::text AS subject_kind, s.officer_id AS subject_key, s.name AS subject_name, {norm_sql('s.name')} AS subject_norm,
               '/uk/officer/' || s.officer_id AS subject_url, NULL::text AS match, NULL::text AS ein, NULL::text AS org_name,
               NULL::text AS state, 'UK'::text AS form_type, extract(year FROM s.first_appointed)::int AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, s.current_appointments::numeric AS value, NULL::text AS org_url,
               {CH.format(n='s.example_company')} AS source_url,
               s.appointments, s.companies, s.birth_year, s.nationality, s.first_appointed, ec.name AS example_name{extra}
        FROM uk_companies.officer_stats s LEFT JOIN uk_companies.company ec ON ec.company_number = s.example_company
        WHERE {where}"""
    return _ranked_by_org(inner, "value DESC, subject_key")


def _officers_most() -> str:
    return _officer_inner("s.current_appointments >= 5")


def _officers_trustees() -> str:
    return _officer_inner("""EXISTS (SELECT 1 FROM uk_companies.officer_match m WHERE m.officer_id = s.officer_id
                                     AND m.method IN ('trustee_linked_charity', 'trustee_linked_charity_fl'))""")


def _officers_us() -> str:
    return _officer_inner("""EXISTS (SELECT 1 FROM uk_companies.officer_match m WHERE m.officer_id = s.officer_id
                                     AND m.method IN ('us_insider_same_company', 'formd_party_same_issuer'))""")


def uk_company_boards() -> list:
    from app.boards import Board, Column
    from app.uk_companies import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="census", year_label="Year", source_label="Companies House",
              search=True, org_label="Organization")
    return [
        Board("uk-companies-new-by-sic", "UK industries with the most new companies", "Fresh Registrations",
              "SIC industry codes ranked by how many live companies with that code were incorporated in the past 12 months.",
              "Value = live companies listing the SIC code (any of up to four) with an incorporation date in the last 365 days. A company "
              "with several codes counts under each. The free data holds live companies only, so earlier years are undercounted (struck off "
              "companies are gone) and no year-on-year growth is shown. " + SOURCE,
              _newest_by_sic(), Column("value", "New companies, past 12 months", "num"),
              [Column("new_quarter", "Past 3 months", "num"), Column("companies", "All live companies", "num"),
               Column("share_new", "Share new", "pct"), Column("latest", "Latest incorporation"), Column("latest_name", "Latest company")],
              ["Code 99999 (dormant) and 82990 (other business support) are catch-alls many new companies choose."],
              unit="industry", **{**kw, "org_label": "Industry"}),
        Board("uk-psc-networks", "The largest PSC networks in the UK", "Controlling Interests",
              "People who are listed as a current person with significant control of the most live UK companies.",
              "Value = distinct live companies where the same full name and birth month and year appear as a current individual PSC "
              "(five or more companies). The register carries no identifier across companies, so two people can share a name and birth "
              "month: this is a count of matching records, not proof of one person. Corporate PSCs are not counted. " + SOURCE,
              _psc_networks(), Column("value", "Companies controlled", "num"),
              [Column("birth_year", "Born"), Column("nationality", "Nationality"), Column("country_of_residence", "Lives in"),
               Column("example_name", "Example company"), Column("first_notified", "First notified")],
              ["Nominee and professional service providers appear here: many shell companies are formed by one person."],
              unit="person", **kw),
        Board("uk-company-status-by-region", "UK regions by share of companies not active", "Strike-Off Country",
              "Regions ranked by the share of their live registered companies whose status is something other than plain Active.",
              "Value = companies in the region with a status other than Active (proposal to strike off, liquidation, administration, "
              "receivership, voluntary arrangement) divided by all live companies in the region, as a percentage. The region is taken "
              "from the registered office's postcode area. Dissolved companies are not in the free data. Regions with fewer than "
              "1,000 companies are left out. " + SOURCE,
              _status_by_region(), Column("value", "Share not active", "pct"),
              [Column("companies", "Companies", "num"), Column("active", "Active", "num"), Column("strike_off", "Proposed strike off", "num"),
               Column("liquidation", "In liquidation", "num"), Column("administration", "In administration", "num")],
              ["A proposal to strike off is often a company its owners no longer want, not a failure."],
              unit="region", **{**kw, "org_label": "Region"}),
        Board("uk-officers-most-appointments", "UK company officers with the most current appointments", "Serial Directors",
              "People holding the most current directorships and other officer posts across UK companies.",
              "Value = current (not resigned) appointments of one Companies House officer id in the companies fetched so far (five or more). "
              "Companies House links one person's appointments under an officer id but sometimes splits a person across ids. Corporate officers "
              "are not counted. Company formation agents and nominee directors rank high. " + _OFFICER_SOURCE,
              _officers_most(), Column("value", "Current appointments", "num"),
              [Column("appointments", "All appointments", "num"), Column("birth_year", "Born"), Column("nationality", "Nationality"),
               Column("first_appointed", "First appointed"), Column("example_name", "Example company")],
              ["Coverage grows daily as officers are fetched; priority goes to charities and companies linked to US filings."],
              unit="officer", **{**kw, "org_label": "Officer"}),
        Board("uk-officers-also-trustees", "UK company officers who are also charity trustees", "Directors Doing Good",
              "Officers of a company that is the registered company of a UK charity whose trustee list names the same person.",
              "A person is listed when an officer of a company shares their name with a trustee of the charity registered to that same company "
              "(Charity Commission register, England and Wales). The shared charity is the corroboration; a name alone is never enough. " + _OFFICER_SOURCE,
              _officers_trustees(), Column("value", "Current appointments", "num"),
              [Column("appointments", "All appointments", "num"), Column("birth_year", "Born"), Column("nationality", "Nationality"),
               Column("example_name", "Example company")],
              ["Most charitable companies are run by their trustees, so this board is large; rank is by how many companies the person directs."],
              unit="officer", **{**kw, "org_label": "Officer"}),
        Board("uk-officers-also-us", "UK company officers also in US filings", "Across the Pond",
              "Officers of UK companies who are also named insiders or Form D people of the same company's US counterpart.",
              "An officer of a UK company that is matched to an SEC filer or Form D issuer who has the same full name as an SEC insider (Forms 3, 4, 5) "
              "or a person on a Form D filing of that issuer. The shared company is the corroboration. " + _OFFICER_SOURCE,
              _officers_us(), Column("value", "Current appointments", "num"),
              [Column("appointments", "All appointments", "num"), Column("birth_year", "Born"), Column("nationality", "Nationality"),
               Column("example_name", "Example company")],
              [], unit="officer", **{**kw, "org_label": "Officer"}),
    ]


ALTERNATIVES = {
    "uk-companies-new-by-sic": ["Fresh Registrations", "New Limited Companies", "Startup Codes"],
    "uk-psc-networks": ["Controlling Interests", "One Person, Many Companies", "PSC Empires"],
    "uk-company-status-by-region": ["Strike-Off Country", "Active or Not", "Regional Reality Check"],
    "uk-officers-most-appointments": ["Serial Directors", "Many Hats", "Board Collectors"],
    "uk-officers-also-trustees": ["Directors Doing Good", "Company and Cause", "Trustee Directors"],
    "uk-officers-also-us": ["Across the Pond", "Transatlantic Directors", "UK and US Boards"],
}
