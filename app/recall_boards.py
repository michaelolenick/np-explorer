"""Leaderboards for food recalls (app/recalls.py, loader/recalls.py). One row per recalling firm (all years); Year
= the year of its latest recall. Shown only where RECALLS_PUBLIC=1."""

from __future__ import annotations

GROUP_NAME = "recalls"
GROUP = {"title": "Food recalls", "subtitle": "Kitchen Nightmares",
         "definition": "The firms with the most food recalls, the most dangerous ones, and repeat recallers that "
                       "also sell to the government or lobby it. From FDA food enforcement reports."}
SOURCE = ("From FDA food enforcement reports (openFDA), every report since June 2012; one report per recalled "
          "product, so one recall event can cover several. Firms are grouped by name and state. USDA FSIS meat, "
          "poultry and egg recalls are not included yet.")


def _firms(where: str, value: str) -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'recallfirm'::text AS subject_kind, f.firm_id AS subject_key, f.name AS subject_name,
               {norm_sql('f.name')} AS subject_norm, '/recalls/firm/' || f.firm_id AS subject_url, NULL::text AS match,
               (SELECT l.key FROM food_recall_links l WHERE l.firm_id = f.firm_id AND l.kind = 'org' LIMIT 1) AS ein,
               (SELECT l.name FROM food_recall_links l WHERE l.firm_id = f.firm_id AND l.kind = 'org' LIMIT 1) AS org_name,
               f.state, 'FDA'::text AS form_type, extract(year FROM f.last_recall)::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value, NULL::text AS org_url,
               'https://api.fda.gov/food/enforcement.json?search=recalling_firm:"' || replace(f.name, '"', '') || '"&limit=100'
                   AS source_url,
               f.recalls, f.class1, f.events, f.fed_food_contracts, f.fed_contracts, f.lobby_spent,
               CASE WHEN f.has_pac THEN 'Yes' ELSE '' END AS pac
        FROM food_recall_firms f WHERE {where}"""
    return _ranked_by_org(inner, "value DESC, recalls DESC, subject_key")


def recall_boards() -> list:
    from app.boards import Board, Column
    from app.recalls import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="recalls", year_label="Latest recall",
              source_label="FDA food enforcement reports", search=True, org_label="Nonprofit page", unit="firm")
    return [
        Board("recalls-most", "Firms with the most food recalls", "Frequent Recallers",
              "Food companies with the most recalled products in FDA enforcement reports since 2012.",
              f"Value = the firm's recall reports, all years. {SOURCE}",
              _firms("f.recalls > 0", "f.recalls"), Column("value", "Recalls", "num"),
              [Column("class1", "Class I", "num"), Column("events", "Recall events", "num")], [], **kw),
        Board("recalls-class1", "Most Class I food recalls", "Danger Zone",
              "Class I is the FDA's most serious kind: a reasonable chance the food could cause serious illness or "
              "death. These firms have the most.",
              f"Value = the firm's Class I recall reports, all years. {SOURCE}",
              _firms("f.class1 > 0", "f.class1"), Column("value", "Class I recalls", "num"),
              [Column("recalls", "All recalls", "num"), Column("events", "Recall events", "num")], [], **kw),
        Board("recalls-connected", "Repeat recallers with federal food contracts or lobbyists", "Recalled but Connected",
              "Firms with at least three recalls that also sell food to the federal government, lobby it, or "
              "sponsor a political committee.",
              f"Value = the firm's recall reports. Federal food contracts = contract obligations from the Department "
              f"of Agriculture and the Defense Logistics Agency (USAspending; contract years loaded so far); "
              f"lobbying = spending on Lobbying Disclosure Act reports naming the firm as a client; PAC = it "
              f"sponsors a federal political committee (FEC). Matched by normalized name and state. {SOURCE}",
              _firms("f.recalls >= 3 AND (coalesce(f.fed_food_contracts, 0) > 0 OR coalesce(f.lobby_spent, 0) > 0 "
                     "OR f.has_pac)", "f.recalls"),
              Column("value", "Recalls", "num"),
              [Column("class1", "Class I", "num"), Column("fed_food_contracts", "Federal food contracts", "money"),
               Column("lobby_spent", "Lobbying", "money"), Column("pac", "PAC", "text")], [], **kw),
    ]


ALTERNATIVES = {
    "recalls-most": ["Frequent Recallers", "Back to the Shelf", "Return to Sender"],
    "recalls-class1": ["Danger Zone", "Do Not Eat", "Code Red Kitchen"],
    "recalls-connected": ["Recalled but Connected", "Bad Batch, Good Friends", "Recall and Lobby"],
}
