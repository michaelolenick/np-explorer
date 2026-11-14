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
    ]


ALTERNATIVES = {
    "uk-companies-new-by-sic": ["Fresh Registrations", "New Limited Companies", "Startup Codes"],
    "uk-psc-networks": ["Controlling Interests", "One Person, Many Companies", "PSC Empires"],
    "uk-company-status-by-region": ["Strike-Off Country", "Active or Not", "Regional Reality Check"],
}
