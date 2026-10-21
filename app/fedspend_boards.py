"""Leaderboards for federal awards from USAspending (app/fedspend.py, loader/usaspending.py).

fedspend_boards() returns Board objects for app/boards.py to append to BOARDS; GROUP goes in boards.GROUPS. The
views read usa_recipient_totals (one row per fiscal year, kind and recipient), built after each load. Year is the
federal fiscal year (October to September). Shown only where FEDSPEND_PUBLIC=1.
"""

from __future__ import annotations

GROUP_NAME = "fedspend"
GROUP = {"title": "Federal grants and contracts", "subtitle": "Uncle Sam's Checkbook",
         "definition": "Which nonprofits take in the most federal grants and contracts, and who gets the most "
                       "federal money overall. From USAspending award data since fiscal 2007."}
SOURCE = ("From USAspending.gov award data: obligations (money the government committed) summed over each award's "
          "transactions in the fiscal year (October to September; 2024 = October 2023 to September 2024). "
          "Negative obligations (de-obligations) are included, so a year's total can be lower than new awards. "
          "Awards to individuals and county-level aggregates are left out. A recipient is a name plus zip code as "
          "the award reports it; organizations link to their nonprofit page when the name and zip match one filer.")


def _recipients(where: str, kind_sql: str = "true") -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'recipient'::text AS subject_kind, r.recipient_name || '|' || coalesce(r.zip5, '') AS subject_key,
               r.recipient_name AS subject_name, {norm_sql('r.recipient_name')} AS subject_norm,
               CASE WHEN r.recipient_ein IS NOT NULL THEN '/org/' || r.recipient_ein || '#federal' END AS subject_url,
               NULL::text AS match, r.recipient_ein AS ein, r.top_agency AS org_name, r.state, 'USA'::text AS form_type,
               r.fiscal_year::int AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, sum(r.total) AS value,
               min(r.city) AS city, sum(r.n_awards) AS n_awards, (array_agg(r.top_award_url))[1] AS source_url
        FROM usa_recipient_totals r
        WHERE {where} AND {kind_sql}
        GROUP BY r.recipient_name, r.zip5, r.recipient_ein, r.top_agency, r.state, r.fiscal_year
        HAVING sum(r.total) > 0"""
    return _ranked_by_org(inner, "value DESC, tax_year DESC, subject_key")


def fedspend_boards() -> list:
    from app.boards import Board, Column
    from app.fedspend import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="usa", year_label="Fiscal year",
              source_label="USAspending.gov award data", org_label="Main awarding agency", search=True)
    cols = [Column("city", "City"), Column("n_awards", "Awards", "num")]
    return [
        Board("fed-nonprofit-grants", "Nonprofits getting the most federal grants", "Uncle Sam's Favorites",
              "Nonprofits that took in the most federal grants, cooperative agreements and other assistance in a "
              "fiscal year.",
              f"Value = assistance obligations to the recipient in the fiscal year. Nonprofit = the award marks the "
              f"recipient as a nonprofit or private college. {SOURCE}",
              _recipients("r.nonprofit", "r.kind = 'assistance'"), Column("value", "Federal assistance", "money"),
              cols, ["Pass-through money counts where it lands first: a university that passes a grant to partners "
                     "shows the whole grant."], unit="recipient", **kw),
        Board("fed-nonprofit-contracts", "Nonprofits with the biggest federal contracts", "Mission Contractors",
              "Nonprofits paid the most under federal contracts in a fiscal year: research labs, hospitals, "
              "think tanks, universities.",
              f"Value = contract obligations to the recipient in the fiscal year. Nonprofit = the contract marks "
              f"the vendor as a nonprofit or other not-for-profit. {SOURCE}",
              _recipients("r.nonprofit", "r.kind = 'contract'"), Column("value", "Federal contracts", "money"),
              cols, ["Federally funded research and development centers run by nonprofits (MITRE, RAND, Battelle "
                     "labs) top this list."], unit="recipient", **kw),
        Board("fed-top-recipients", "Biggest recipients of federal money", "The Federal Faucet",
              "Every organization, nonprofit or not, ranked by federal grants and contracts together in a fiscal "
              "year.",
              f"Value = grants, other assistance and contract obligations to the recipient in the fiscal year. "
              f"{SOURCE}",
              _recipients("true"), Column("value", "Federal awards", "money"), cols,
              ["States and state agencies receive formula grants (Medicaid, highways) that dwarf everything else."],
              unit="recipient", **kw),
    ]


ALTERNATIVES = {
    "fed-nonprofit-grants": ["Uncle Sam's Favorites", "The Grant Machine", "Federal Darlings"],
    "fed-nonprofit-contracts": ["Mission Contractors", "Beltway Charities", "Nonprofit Inc."],
    "fed-top-recipients": ["The Federal Faucet", "Uncle Sam's Checkbook", "Top of the Trough"],
}
