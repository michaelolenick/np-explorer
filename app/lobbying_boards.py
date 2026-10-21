"""Leaderboards for federal lobbying (app/lobbying.py, loader/lda.py). Views read lda_client_years and
lda_filings. Year = the filing year of the quarterly reports. Shown only where LDA_PUBLIC=1."""

from __future__ import annotations

GROUP_NAME = "lobbying"
GROUP = {"title": "Federal lobbying", "subtitle": "K Street",
         "definition": "Who spends the most lobbying Congress and the executive branch, which firms earn the most, "
                       "and which nonprofits lobby hardest. From Lobbying Disclosure Act reports."}
SOURCE = ("From Lobbying Disclosure Act reports filed with the Senate and House (LD-2, quarterly since 2008, twice "
          "a year before). Spending = income a lobbying firm reported from the client plus expenses an organization "
          "reported for lobbying on its own behalf. Amounts under $5,000 a quarter (under $10,000 before 2008) may "
          "be reported as zero.")


def _clients(where: str) -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'client'::text AS subject_kind, c.client_id::text AS subject_key, c.client_name AS subject_name,
               {norm_sql('c.client_name')} AS subject_norm, '/lobbying/client/' || c.client_id AS subject_url,
               NULL::text AS match, c.client_ein AS ein, o.name AS org_name, c.state, 'LD-2'::text AS form_type,
               c.year::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, c.spent AS value,
               CASE WHEN c.client_ein IS NOT NULL THEN '/org/' || c.client_ein END AS org_url,
               c.firms, c.reports, c.doc AS source_url
        FROM lda_client_years c LEFT JOIN organizations o ON o.ein = c.client_ein
        WHERE c.spent > 0 AND {where}"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def _firms() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'firm'::text AS subject_kind, f.registrant_id::text AS subject_key, min(f.registrant_name) AS subject_name,
               {norm_sql('min(f.registrant_name)')} AS subject_norm, '/lobbying/firm/' || f.registrant_id AS subject_url,
               NULL::text AS match, NULL::text AS ein, NULL::text AS org_name, min(f.registrant_state) AS state,
               'LD-2'::text AS form_type, f.filing_year::int AS tax_year, NULL::bigint AS filing_id,
               NULL::bigint AS object_id, sum(f.income) AS value, count(DISTINCT f.client_id) AS clients,
               (array_agg(f.document_url ORDER BY f.dt_posted DESC))[1] AS source_url
        FROM lda_filings f WHERE NOT f.self_filer AND f.income > 0 GROUP BY f.registrant_id, f.filing_year"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def lobbying_boards() -> list:
    from app.boards import Board, Column
    from app.lobbying import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="lda", year_label="Year",
              source_label="Lobbying Disclosure Act reports", search=True)
    return [
        Board("lobby-spenders", "Biggest spenders on federal lobbying", "Hired Guns",
              "Companies, trade groups, unions and nonprofits that spent the most on federal lobbying in a year.",
              f"Value = the client's lobbying spending in the year, summed over every report naming it. {SOURCE}",
              _clients("true"), Column("value", "Spent", "money"),
              [Column("firms", "Firms", "num"), Column("reports", "Reports", "num")], [],
              org_label="Nonprofit page", unit="client", **kw),
        Board("lobby-nonprofits", "Nonprofits spending the most on lobbying", "Mission Lobbying",
              "Clients that match a nonprofit filing on this site, ranked by federal lobbying spending.",
              f"Value = the client's lobbying spending in the year. Matched to a Form 990 filer by normalized name "
              f"and state, one filer per name. {SOURCE}",
              _clients("c.client_ein IS NOT NULL"), Column("value", "Spent", "money"),
              [Column("firms", "Firms", "num"), Column("reports", "Reports", "num")],
              ["Trade associations (501(c)(6)) and social welfare groups (501(c)(4)) can lobby without limit; "
               "charities (501(c)(3)) only a little."], org_label="Nonprofit page", unit="client", **kw),
        Board("lobby-firms", "Lobbying firms earning the most", "K Street Cash Registers",
              "Outside lobbying firms ranked by the income they reported from clients in a year.",
              f"Value = income the firm reported across its clients in the year. Organizations lobbying for "
              f"themselves are left out. {SOURCE}",
              _firms(), Column("value", "Income", "money"), [Column("clients", "Clients", "num")], [],
              org_label="Organization", unit="firm", **kw),
    ]


ALTERNATIVES = {
    "lobby-spenders": ["Hired Guns", "Access Fees", "The Influence Bill"],
    "lobby-nonprofits": ["Mission Lobbying", "Charity on the Hill", "Do-Gooder Lobby"],
    "lobby-firms": ["K Street Cash Registers", "Revolving Riches", "Influence Inc."],
}
