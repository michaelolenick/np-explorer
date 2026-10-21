"""Leaderboards for FEC campaign contributions (app/politics.py, loader/fec.py, loader/fec_links.py).

politics_boards() returns Board objects for app/boards.py to append to BOARDS; GROUP goes in boards.GROUPS.
The views read the small summary tables loader/fec_links.py builds after each load (fec_donor_totals,
fec_committee_totals, fec_person_links), never the 300-million-row contributions table. Year = the two-year
election cycle (2024 = 2023-2024). Totals leave out memo entries, which restate money reported elsewhere.
"""

from __future__ import annotations

GROUP_NAME = "politics"
GROUP = {"title": "Campaign contributions", "subtitle": "Follow the Money",
         "definition": "Who gives the most to federal candidates, parties and PACs, which committees raise the "
                       "most from individuals, and how the people who run nonprofits give. From FEC itemized "
                       "contributions since 1980."}
SOURCE = ("From the FEC's itemized individual contributions (bulk data): contributions over $200 a cycle that a "
          "committee had to itemize, as reported. Year is the two-year election cycle (2024 = 2023 and 2024). "
          "Memo entries, which restate money reported elsewhere (such as contributions passed through ActBlue or "
          "WinRed), are left out of totals.")
FEC_SEARCH = ("'https://www.fec.gov/data/receipts/individual-contributions/?contributor_name=' || "
              "replace({name}, ' ', '+') || coalesce('&contributor_zip=' || {zip}, '') || "
              "'&two_year_transaction_period=' || {cycle}")


def _donors() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'donor'::text AS subject_kind, d.name_norm || '|' || coalesce(d.zip5, '') AS subject_key,
               d.name AS subject_name, {norm_sql('d.name')} AS subject_norm,
               '/politics/donor/' || coalesce(d.zip5, '00000') || '/' ||
                   trim(both '-' FROM regexp_replace(d.name_norm, '[^a-z0-9]+', '-', 'g')) AS subject_url,
               NULL::text AS match, NULL::text AS ein, d.employer AS org_name, d.state, 'FEC'::text AS form_type,
               d.cycle::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, d.total AS value,
               d.occupation, d.city, d.n, d.committees,
               {FEC_SEARCH.format(name='d.name_norm', zip='d.zip5', cycle='d.cycle')} AS source_url
        FROM fec_donor_totals d"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _committees() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'committee'::text AS subject_kind, t.cmte_id AS subject_key, coalesce(cm.name, t.cmte_id) AS subject_name,
               {norm_sql("coalesce(cm.name, t.cmte_id)")} AS subject_norm, '/politics/committee/' || t.cmte_id AS subject_url,
               NULL::text AS match, x.ein, coalesce(o.name, cm.connected_org) AS org_name, cm.state,
               'FEC'::text AS form_type, t.cycle::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               t.total AS value, CASE WHEN x.ein IS NOT NULL THEN '/org/' || x.ein END AS org_url,
               coalesce(cm.cmte_type, '') AS cmte_type, cm.party, t.n, t.donors,
               'https://www.fec.gov/data/committee/' || t.cmte_id || '/?cycle=' || t.cycle AS source_url
        FROM fec_committee_totals t
        LEFT JOIN fec_committees cm ON cm.cycle = t.cycle AND cm.cmte_id = t.cmte_id
        LEFT JOIN fec_org_committees x ON x.cmte_id = t.cmte_id
        LEFT JOIN organizations o ON o.ein = x.ein
        WHERE t.total > 0"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _people() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'person'::text AS subject_kind, pc.id::text AS subject_key, pc.display_name AS subject_name,
               {norm_sql('pc.display_name')} AS subject_norm, '/person/' || pc.id || '#politics' AS subject_url,
               'EXACT'::text AS match, NULL::text AS ein, pc.orgs[1] AS org_name, pc.states[1] AS state,
               'FEC'::text AS form_type, s.cycle::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               s.total AS value, pc.latest_title, s.n, s.committees, pc.n_orgs,
               '/person/' || pc.id || '#politics' AS source_url
        FROM (SELECT l.cluster_id, l.cycle, sum(c.amount) FILTER (WHERE c.memo_cd IS DISTINCT FROM 'X') AS total,
                     count(*) AS n, count(DISTINCT c.cmte_id) AS committees
              FROM fec_person_links l JOIN fec_contributions c ON c.cycle = l.cycle AND c.sub_id = l.sub_id
              GROUP BY 1, 2) s
        JOIN person_clusters pc ON pc.id = s.cluster_id
        WHERE s.total > 0"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


CMTE_TYPE_FILTER = None


def politics_boards() -> list:
    from app.boards import Board, Column
    from app.politics import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="fec", year_label="Cycle",
              source_label="FEC itemized contributions")
    return [
        Board("politics-donors", "Biggest individual campaign donors", "The Checkbook Caucus",
              "The individuals who gave the most to federal candidates, parties and PACs in an election cycle.",
              f"Value = the donor's itemized contributions in the cycle, summed over every committee. A donor is a "
              f"normalized name plus zip code, so two people with the same name in one zip code are counted "
              f"together, and a donor who moved shows up once per zip code. Employer, occupation and city are the "
              f"ones the donor reported most often that cycle. Donors who gave at least $10,000 in a cycle. {SOURCE}",
              _donors(), Column("value", "Total given", "money"),
              [Column("occupation", "Occupation"), Column("city", "City"), Column("n", "Contributions", "num"),
               Column("committees", "Committees", "num")],
              ["Super PAC money mostly comes from a few very large checks, so the top of this list is dominated by "
               "contributions to super PACs."],
              org_label="Employer (as reported)", unit="donor", search=True, **kw),
        Board("politics-committees", "Committees raising the most from individuals", "The Money Magnets",
              "Campaigns, parties and PACs that took in the most in itemized contributions from individuals.",
              f"Value = itemized contributions from individuals to the committee in the cycle. Conduits such as "
              f"ActBlue and WinRed report every earmarked contribution they pass on, so they top the list; the "
              f"campaigns that receive that money report it again as memo entries, which are left out. Contributions "
              f"from PACs and parties are not included. {SOURCE}",
              _committees(), Column("value", "From individuals", "money"),
              [Column("cmte_type", "Type"), Column("party", "Party"), Column("donors", "Donors", "num"),
               Column("n", "Contributions", "num")],
              ["The Type column uses the FEC's committee type codes: H, S and P are House, Senate and presidential "
               "campaigns; O is a super PAC; Q and N are PACs; X, Y and Z are parties. Each committee page spells "
               "it out."],
              org_label="Connected organization", unit="committee", search=True, **kw),
        Board("politics-990-people", "Nonprofit leaders' campaign giving", "Board and Ballot",
              "People listed on nonprofit tax returns (officers, directors, key employees) ranked by their "
              "federal campaign contributions.",
              f"Value = itemized contributions in the cycle from donors whose normalized name matches the person "
              f"and whose reported employer matches an organization the person is listed at on a Form 990. When "
              f"two people on the site share a name and organization, neither is linked. The organization column "
              f"shows one of the person's organizations. {SOURCE}",
              _people(), Column("value", "Total given", "money"),
              [Column("latest_title", "Latest title"), Column("n", "Contributions", "num"),
               Column("committees", "Committees", "num")],
              ["Only contributions where the donor named an employer that matches one of the person's "
               "organizations are counted, so this undercounts: gifts listing another employer, \"retired\" or "
               "\"self-employed\" are not linked."],
              org_label="Organization", unit="person", search=True, **kw),
    ]


ALTERNATIVES = {
    "politics-donors": ["The Checkbook Caucus", "Deep Pockets", "Max Out Club", "The Donor Class"],
    "politics-committees": ["The Money Magnets", "War Chests", "Cash Cows", "The Haul"],
    "politics-990-people": ["Board and Ballot", "Civic Duty", "Double Duty", "Mission and Ballot"],
}
