"""Leaderboards for IPO registrations (app/ipos.py, loader/s1.py): the most-amended S-1 and F-1 registrations, the
longest roads to a withdrawal, serial registrants, and the registrants that also take federal awards, lobby, sponsor
benefit plans or share their insiders with nonprofit returns (ipo_links). One row per registrant (CIK); Year = the
year of its latest filing. Shown unless IPOS_PUBLIC=0 (owner, 2026-11-13)."""

from __future__ import annotations

GROUP_NAME = "ipos"
GROUP = {"title": "IPO registrations", "subtitle": "Going Public",
         "definition": "Companies that filed to go public on Form S-1 or F-1: the most-amended registrations, the "
                       "longest waits before a withdrawal, serial registrants, and the registrants that also take "
                       "federal awards, lobby Washington, sponsor benefit plans or share their insiders with "
                       "nonprofit tax returns. From SEC EDGAR."}
SOURCE = ("From SEC EDGAR's quarterly form indexes (S-1 and F-1 registration statements, their amendments, "
          "effectiveness notices, pricing prospectuses and withdrawal requests, 1994 on) and the EDGAR company "
          "submissions file, one row per registrant. Status is the registrant's latest event: priced, effective, "
          "withdrawn or still pending. Ties to other records come from the registrant's EIN or its name and state "
          "(loader/s1.py), as each board says.")
STATUS = """CASE WHEN c.priced IS NULL AND c.effect IS NULL AND c.withdrawn IS NULL THEN 'Pending'
                 WHEN c.withdrawn IS NOT NULL AND c.withdrawn >= coalesce(c.priced, c.withdrawn)
                      AND c.withdrawn >= coalesce(c.effect, c.withdrawn) THEN 'Withdrawn'
                 WHEN c.priced IS NOT NULL THEN 'Priced' ELSE 'Effective' END"""


def _companies(value: str, where: str, extra: str = "", joins: str = "", order: str = "value DESC, n_filings DESC, subject_key") -> str:
    """One row per registrant with the standard columns, the status and its filing counts, plus extra columns."""
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'ipo_company'::text AS subject_kind, c.cik AS subject_key, c.name AS subject_name,
               {norm_sql('c.name')} AS subject_norm, '/ipos/' || ltrim(c.cik, '0') AS subject_url, NULL::text AS match,
               c.ein, c.sic_desc AS org_name, c.state, c.kind AS form_type, extract(year FROM c.last_filed)::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value, NULL::text AS org_url,
               'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=' || c.cik || '&type=' || left(c.kind, 3) AS source_url,
               {STATUS} AS status, c.n_filings, c.n_reg, c.n_amend, c.first_filed, c.last_filed, c.tickers{extra}
        FROM ipo_companies c {joins}
        WHERE c.name IS NOT NULL AND ({where})"""
    return _ranked_by_org(inner, order)


FED = """JOIN (SELECT l.cik, sum(f.total) AS fed_total, sum(f.n) AS fed_awards, count(*) AS fed_recipients
              FROM ipo_links l JOIN fed_recipient_names f ON f.uei = l.dst_key WHERE l.dst_kind = 'fed' GROUP BY 1) fd ON fd.cik = c.cik"""
LDA = """JOIN (SELECT l.cik, sum(y.spent) AS lobby_spent, count(DISTINCT y.year) AS lobby_years,
                     min(y.year) AS lobby_first, max(y.year) AS lobby_last
              FROM ipo_links l JOIN lda_client_years y ON y.client_id::text = l.dst_key
              WHERE l.dst_kind = 'lda_client' GROUP BY 1) lb ON lb.cik = c.cik"""
PEOPLE = """JOIN (SELECT l.cik, count(DISTINCT l.dst_key) AS people,
                        left(string_agg(DISTINCT l.dst_name, '; ' ORDER BY l.dst_name), 300) AS people_list
                 FROM ipo_links l JOIN person_clusters pc ON pc.id::text = l.dst_key
                 WHERE l.dst_kind = 'person' AND pc.n_filings > 0 GROUP BY 1) pp ON pp.cik = c.cik"""
PLANS = """JOIN (SELECT DISTINCT ON (l.cik) l.cik, s.ein AS plan_ein, s.plans, s.filings AS plan_filings,
                        s.first_year AS plan_first, s.last_year AS plan_last
                 FROM ipo_links l JOIN form5500_sponsors s ON s.ein = l.dst_key
                 WHERE l.dst_kind = 'f5500' ORDER BY l.cik, s.plans DESC) pl ON pl.cik = c.cik"""


def ipo_boards() -> list:
    from app.boards import Board, BoardFilter, Column
    from app.ipos import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="ipo", year_label="Latest filing", org_label="Industry",
              source_label="SEC EDGAR registration filings", search=True, unit="registrant",
              filters=[BoardFilter("status", "Status", "status", all_label="All statuses")])
    base = [Column("status", "Status"), Column("n_reg", "Registration statements", "num"),
            Column("n_amend", "Amendments", "num"), Column("n_filings", "Filings", "num"),
            Column("first_filed", "First filed"), Column("last_filed", "Latest filing"), Column("tickers", "Ticker")]
    return [
        Board("ipo-most-amended", "IPO registrations amended the most times", "Still Rewriting",
              "Companies that filed the most amendments to their S-1 or F-1 registration statements before pricing, "
              "going effective, withdrawing, or while still waiting.",
              f"Value = amendments (S-1/A and F-1/A) the registrant filed, all years. {SOURCE}",
              _companies("c.n_amend", "c.n_amend > 0"), Column("value", "Amendments", "num"),
              [base[0]] + base[1:2] + base[3:],
              ["Every SEC comment letter can mean another amendment; a registrant that goes back to market several "
               "times amends every time."], **kw),
        Board("ipo-longest-withdrawn", "IPO registrations withdrawn after the longest wait", "Cold Feet",
              "Companies whose latest move was to withdraw their registration statement (a Form RW), ranked by the "
              "time from their first filing to the withdrawal.",
              f"Value = days from the registrant's first S-1 or F-1 filing to its withdrawal request, for registrants "
              f"whose withdrawal is their latest event. {SOURCE}",
              _companies("c.withdrawn - c.first_filed", f"c.withdrawn IS NOT NULL AND c.withdrawn > c.first_filed AND ({STATUS}) = 'Withdrawn'",
                         ", c.withdrawn"),
              Column("value", "Days in registration", "num"),
              [Column("withdrawn", "Withdrawn"), base[1], base[2], base[3], base[4]],
              ["A registration can sit for years through market downturns; withdrawing it is routine housekeeping "
               "when a company is bought instead, or raises money privately."],
              **{**kw, "filters": []}),
        Board("ipo-serial-registrants", "Companies that filed the most registration statements", "Serial Registrants",
              "Registrants that filed new S-1 or F-1 registration statements again and again, not counting amendments.",
              f"Value = original registration statements (S-1 and F-1, not amendments) filed by the registrant, all "
              f"years, for registrants with at least two. {SOURCE}",
              _companies("c.n_reg", "c.n_reg >= 2"), Column("value", "Registration statements", "num"),
              [base[0], base[2], base[3], base[4], base[5], base[6]],
              ["Commodity trusts, insurance companies and small public companies raising money repeatedly file a "
               "new S-1 for every offering; the count is activity, not trouble."], **kw),
        Board("ipo-federal-awards", "IPO registrants that take the most federal money", "Backed by Washington",
              "Companies that filed to go public and are also federal award recipients (contracts, grants and other "
              "assistance in USAspending), ranked by the federal money obligated to them.",
              f"Value = federal obligations (all award types and fiscal years loaded) to the recipient identifiers "
              f"(UEIs) linked to the registrant by EIN or by name and state. {SOURCE}",
              _companies("fd.fed_total", "fd.fed_total > 0", ", fd.fed_awards, fd.fed_recipients", FED),
              Column("value", "Federal awards", "money"),
              [base[0], Column("fed_awards", "Award records", "num"), Column("fed_recipients", "Recipient identifiers", "num"),
               base[4], base[5], base[6]],
              ["Name-and-state matches can join a registrant to a different company with the same name; the "
               "registrant's page lists every link."], **kw),
        Board("ipo-lobbying", "IPO registrants that spend the most on lobbying", "Prospectus and K Street",
              "Companies that filed to go public and are also clients on federal Lobbying Disclosure Act reports, "
              "ranked by lobbying spending.",
              f"Value = lobbying spending (income lobbying firms reported from the client plus the client's own reported "
              f"expenses, all years loaded) for the lobbying clients linked to the registrant by EIN or by name and "
              f"state. {SOURCE}",
              _companies("lb.lobby_spent", "lb.lobby_spent > 0", ", lb.lobby_years, lb.lobby_first, lb.lobby_last", LDA),
              Column("value", "Lobbying", "money"),
              [base[0], Column("lobby_years", "Years lobbying", "num"), Column("lobby_first", "First year", "year"),
               Column("lobby_last", "Latest year", "year"), base[4], base[5], base[6]], [], **kw),
        Board("ipo-nonprofit-insiders", "IPO registrants whose insiders appear on nonprofit tax returns", "Insiders with Two Hats",
              "Companies that filed to go public, ranked by how many of their officers, directors and 10% owners "
              "(from their Forms 3, 4 and 5) are also people on nonprofit Form 990 returns.",
              f"Value = people linked to the registrant as an insider who have at least one Form 990 record on this site. "
              f"Linked by name only (the same full name, one person on this site, in one of that person's states), so "
              f"check the person page. {SOURCE}",
              _companies("pp.people", "pp.people > 0", ", pp.people_list", PEOPLE), Column("value", "Insiders on nonprofit returns", "num"),
              [base[0], Column("people_list", "People"), base[4], base[5], base[6]],
              ["Name matches can join two different people who share a full name in the same state."], **kw),
        Board("ipo-benefit-plans", "IPO registrants sponsoring the most benefit plans", "Plans Before the Bell",
              "Companies that filed to go public and sponsor pension, 401(k) or welfare plans on Form 5500, ranked by "
              "the number of plans.",
              f"Value = distinct plans the registrant (matched to a Form 5500 sponsor by EIN) has filed annual returns "
              f"for, plan years 2009 on. {SOURCE}",
              _companies("pl.plans", "pl.plans > 0", ", pl.plan_filings, pl.plan_first, pl.plan_last, '/form5500/sponsor/' || pl.plan_ein AS plans_url", PLANS),
              Column("value", "Benefit plans", "num"),
              [base[0], Column("plan_filings", "Form 5500 filings", "num"), Column("plan_first", "First plan year", "year"),
               Column("plan_last", "Latest plan year", "year"), base[4], base[5], base[6]], [], **kw),
    ]


ALTERNATIVES = {
    "ipo-most-amended": ["Still Rewriting", "Draft Twelve", "Comment Letter Season"],
    "ipo-longest-withdrawn": ["Cold Feet", "Never Rang the Bell", "The Long Goodbye"],
    "ipo-serial-registrants": ["Serial Registrants", "Back to the Well", "Filing Again"],
    "ipo-federal-awards": ["Backed by Washington", "Public Money, Public Offering", "Uncle Sam's Portfolio"],
    "ipo-lobbying": ["Prospectus and K Street", "Lobbying Before Listing", "Roadshow to Capitol Hill"],
    "ipo-nonprofit-insiders": ["Insiders with Two Hats", "Boardroom Crossover", "Charity and Cap Table"],
    "ipo-benefit-plans": ["Plans Before the Bell", "Pensions Going Public", "The 401(k) Roadshow"],
}
