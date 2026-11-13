"""Leaderboards for food recalls (app/recalls.py, loader/recalls.py). One row per recalling firm (all years); Year
= the year of its latest recall. Shown only where RECALLS_PUBLIC=1."""

from __future__ import annotations

GROUP_NAME = "recalls"
GROUP = {"title": "Food recalls", "subtitle": "Kitchen Nightmares",
         "definition": "The firms with the most food recalls, the most dangerous ones, repeat recallers over the most "
                       "years, and recalling firms that also sell food to the government or lobby it. From FDA food "
                       "enforcement reports and USDA FSIS recalls."}
SOURCE = ("From FDA food enforcement reports (openFDA), every report since June 2012, and USDA FSIS meat, poultry "
          "and egg recalls since 2014; one FDA report per recalled product, so one recall event can cover several. "
          "Firms are grouped by name and state.")
CONNECTED = ("Federal food contracts = contract obligations from the Department of Agriculture and the Defense "
             "Logistics Agency (USAspending; contract years loaded so far); lobbying = spending on Lobbying Disclosure "
             "Act reports naming the firm as a client; PAC = it sponsors a federal political committee (FEC). Matched "
             "by normalized name and state.")


def _firms(where: str, value: str, order: str = "value DESC, recalls DESC, subject_key") -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'recallfirm'::text AS subject_kind, f.firm_id AS subject_key, f.name AS subject_name,
               {norm_sql('f.name')} AS subject_norm, '/recalls/firm/' || f.firm_id AS subject_url, NULL::text AS match,
               (SELECT l.key FROM food_recall_links l WHERE l.firm_id = f.firm_id AND l.kind = 'org' LIMIT 1) AS ein,
               (SELECT l.name FROM food_recall_links l WHERE l.firm_id = f.firm_id AND l.kind = 'org' LIMIT 1) AS org_name,
               f.state, (SELECT string_agg(DISTINCT upper(r.source), ', ') FROM food_recalls r WHERE r.firm_id = f.firm_id) AS form_type,
               extract(year FROM f.last_recall)::int AS tax_year,
               NULL::bigint AS filing_id, NULL::bigint AS object_id, ({value})::numeric AS value, NULL::text AS org_url,
               CASE WHEN EXISTS (SELECT 1 FROM food_recalls r WHERE r.firm_id = f.firm_id AND r.source = 'fda')
                    THEN 'https://api.fda.gov/food/enforcement.json?search=recalling_firm:"' || replace(f.name, '"', '') || '"&limit=100'
                    ELSE (SELECT r.source_url FROM food_recalls r WHERE r.firm_id = f.firm_id AND r.source = 'fsis'
                          ORDER BY r.recall_initiation_date DESC NULLS LAST LIMIT 1) END AS source_url,
               f.recalls, f.class1, f.events, f.fed_food_contracts, f.fed_contracts, f.lobby_spent,
               CASE WHEN f.has_pac THEN 'Yes' ELSE '' END AS pac, f.first_recall, f.last_recall
        FROM food_recall_firms f WHERE f.firm_id <> 'fsis-pha' AND ({where})"""   # alerts naming no firm stay off the boards
    return _ranked_by_org(inner, order)


def recall_boards() -> list:
    from app.boards import Board, Column
    from app.recalls import PUBLIC
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="recalls", year_label="Latest recall",
              source_label="FDA food enforcement reports and USDA FSIS recalls", search=True, org_label="Nonprofit page", unit="firm")
    return [
        Board("recalls-most", "Firms with the most food recalls", "Frequent Recallers",
              "Food companies with the most recalled products in FDA enforcement reports since 2012 and USDA FSIS recalls since 2014.",
              f"Value = the firm's recall reports, all years. {SOURCE}",
              _firms("f.recalls > 0", "f.recalls"), Column("value", "Recalls", "num"),
              [Column("class1", "Class I", "num"), Column("events", "Recall events", "num")], [], **kw),
        Board("recalls-class1", "Most Class I food recalls", "Danger Zone",
              "Class I is the most serious kind at the FDA and at USDA FSIS: a reasonable chance the food could cause "
              "serious illness or death. These firms have the most.",
              f"Value = the firm's Class I recall reports, all years. {SOURCE}",
              _firms("f.class1 > 0", "f.class1"), Column("value", "Class I recalls", "num"),
              [Column("recalls", "All recalls", "num"), Column("events", "Recall events", "num")], [], **kw),
        Board("recalls-connected", "Repeat recallers with federal food contracts or lobbyists", "Recalled but Connected",
              "Firms with at least three recalls that also sell food to the federal government, lobby it, or "
              "sponsor a political committee.",
              f"Value = the firm's recall reports. {CONNECTED} {SOURCE}",
              _firms("f.recalls >= 3 AND (coalesce(f.fed_food_contracts, 0) > 0 OR coalesce(f.lobby_spent, 0) > 0 "
                     "OR f.has_pac)", "f.recalls"),
              Column("value", "Recalls", "num"),
              [Column("class1", "Class I", "num"), Column("fed_food_contracts", "Federal food contracts", "money"),
               Column("lobby_spent", "Lobbying", "money"), Column("pac", "PAC", "text")], [], **kw),
        Board("recalls-repeat-years", "Firms recalling food in the most separate years", "Habitual Recallers",
              "Food companies with recalls spread over the most calendar years: not one bad batch but a pattern, "
              "year after year.",
              f"Value = the number of distinct years in which the firm started a recall, for firms with at least "
              f"three recalls; ties go to the firm with more recalls. {SOURCE}",
              _firms("f.recalls >= 3", "(SELECT count(DISTINCT extract(year FROM r.recall_initiation_date)) FROM food_recalls r "
                     "WHERE r.firm_id = f.firm_id AND r.recall_initiation_date IS NOT NULL)"),
              Column("value", "Years with a recall", "num"),
              [Column("recalls", "Recalls", "num"), Column("class1", "Class I", "num"), Column("first_recall", "First recall"),
               Column("last_recall", "Latest recall")],
              ["Big manufacturers and distributors handle thousands of products; a recall most years can be scale, "
               "not carelessness."], **kw),
        Board("recalls-federal-food", "Recalling firms with the biggest federal food contracts", "Feeding the Government",
              "Food companies with at least one recall that also sell food to the federal government, ranked by the "
              "value of those contracts.",
              f"Value = the firm's federal food contracts. {CONNECTED} {SOURCE}",
              _firms("f.recalls > 0 AND coalesce(f.fed_food_contracts, 0) > 0", "f.fed_food_contracts"),
              Column("value", "Federal food contracts", "money"),
              [Column("recalls", "Recalls", "num"), Column("class1", "Class I", "num"),
               Column("fed_contracts", "All federal contracts", "money"), Column("last_recall", "Latest recall")],
              ["School lunch, military rations and commodity purchases make USDA and the Defense Logistics Agency "
               "the biggest food buyers in the country."], **kw),
        Board("recalls-lobbying", "Recalling firms that spend the most on lobbying", "Recall and Lobby",
              "Food companies with at least one recall that are also clients on federal Lobbying Disclosure Act "
              "reports, ranked by lobbying spending.",
              f"Value = the firm's lobbying spending, all years loaded. {CONNECTED} {SOURCE}",
              _firms("f.recalls > 0 AND coalesce(f.lobby_spent, 0) > 0", "f.lobby_spent"),
              Column("value", "Lobbying", "money"),
              [Column("recalls", "Recalls", "num"), Column("class1", "Class I", "num"),
               Column("fed_food_contracts", "Federal food contracts", "money"), Column("pac", "PAC", "text")],
              ["Food safety rules, farm bills and trade are lobbied by the same companies that recall products."], **kw),
    ]


ALTERNATIVES = {
    "recalls-most": ["Frequent Recallers", "Back to the Shelf", "Return to Sender"],
    "recalls-class1": ["Danger Zone", "Do Not Eat", "Code Red Kitchen"],
    "recalls-connected": ["Recalled but Connected", "Bad Batch, Good Friends", "Recall and Lobby"],
    "recalls-repeat-years": ["Habitual Recallers", "Every Year Again", "Same Firm, New Batch"],
    "recalls-federal-food": ["Feeding the Government", "Mess Hall Suppliers", "Recalled and Still Serving"],
    "recalls-lobbying": ["Recall and Lobby", "Spoiled and Spending", "K Street Kitchen"],
}
