"""Leaderboards from the Wikipedia and Wikidata matches (app/wikipedia.py, loader/wikipedia.py; owner, 2026-11-14):
nonprofit leaders who have a Wikipedia article, organizations with the most such people in their filings, and nonprofits
with a Wikipedia article by revenue. Only links of methods whose sampled precision is high enough are used (wiki.link.show).
The views read wiki.board_people and wiki.board_orgs, which `python -m loader.wikipedia publish` rebuilds."""

from __future__ import annotations

import os

GROUP_NAME = "wikipedia"
GROUP = {"title": "Nonprofits and Wikipedia", "subtitle": "Well Known",
         "definition": "The people and organizations in FURP's records that also have a Wikipedia article: nonprofit "
                       "leaders with their own page, the organizations whose boards hold the most of them, and the "
                       "biggest nonprofits Wikipedia describes. Matched to Wikipedia and Wikidata by identifiers or by "
                       "name plus a corroborating signal (loader/wikipedia.py)."}
SOURCE = ("Wikipedia and Wikidata, from the official dumps, used under their open licences (the short description is the article's own; attribution on /data#wikipedia); "
          "matched to FURP by an exact identifier (EIN, SEC CIK) or by the full name plus a signal from Wikidata (an employer or "
          "board seat that is an organization the person is on in the filings), each method judged on random samples of at least "
          "50 and shown only when its precision is high. A shared name is not proof of the same person: use the "
          "\"Report a wrong match\" link on the page.")
PUBLIC = os.environ.get("WIKIPEDIA_PUBLIC", "1") == "1"


def _people() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'person'::text AS subject_kind, b.cluster_id::text AS subject_key, b.name AS subject_name,
               {norm_sql('b.name')} AS subject_norm, '/person/' || b.cluster_id AS subject_url, 'FUZZY'::text AS match,
               b.ein, b.org_name, b.state, b.form_type, b.tax_year, b.filing_id, NULL::bigint AS object_id,
               b.total::numeric AS value, '/org/' || b.ein AS org_url, b.wiki_url AS source_url,
               b.title, b.wiki_desc, b.wiki_title, b.method
        FROM wiki.board_people b"""
    return _ranked_by_org(inner, "value DESC, subject_key")


def _notable_boards() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'org'::text AS subject_kind, o.ein AS subject_key, o.name AS subject_name, {norm_sql('o.name')} AS subject_norm,
               '/org/' || o.ein AS subject_url, NULL::text AS match, o.ein, o.name AS org_name, o.state, '990'::text AS form_type,
               o.latest_filing_year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id, b.n_people::numeric AS value,
               '/org/' || o.ein AS org_url, NULL::text AS source_url, b.names, o.latest_total_revenue AS revenue, o.city
        FROM wiki.board_orgs b JOIN organizations o ON o.ein = b.ein WHERE b.n_people >= 2"""
    return _ranked_by_org(inner, "value DESC, revenue DESC NULLS LAST, subject_key")


def _big_nonprofits() -> str:
    from app.boards import _ranked_by_org, norm_sql
    inner = f"""
        SELECT 'org'::text AS subject_kind, o.ein AS subject_key, o.name AS subject_name, {norm_sql('o.name')} AS subject_norm,
               '/org/' || o.ein AS subject_url, NULL::text AS match, o.ein, o.name AS org_name, o.state, '990'::text AS form_type,
               o.latest_filing_year AS tax_year, NULL::bigint AS filing_id, NULL::bigint AS object_id,
               o.latest_total_revenue::numeric AS value, '/org/' || o.ein AS org_url, b.wiki_url AS source_url,
               b.wiki_title, b.wiki_desc, b.founded, o.latest_total_assets AS assets, o.city
        FROM wiki.board_orgs_wp b JOIN organizations o ON o.ein = b.ein WHERE o.latest_total_revenue > 0"""
    return _ranked_by_org(inner, "value DESC, subject_key")


def wikipedia_boards() -> list:
    from app.boards import Board, Column
    if not PUBLIC:
        return []
    kw = dict(per_org=True, forms=(), group=GROUP_NAME, kind="census", year_label="Year", source_label="Wikipedia, Wikidata and FURP's records", search=True,
              table_notes=[ATTRIBUTION])
    return [
        Board("wikipedia-nonprofit-leaders", "Nonprofit leaders with a Wikipedia article, by pay", "Famous Names",
              "People on nonprofit tax returns who have a Wikipedia article, ranked by their highest reported pay.",
              "Value = the person's highest annual pay on a Form 990 return (salary, related-organization pay and other compensation). "
              "A person is shown only when the match to a Wikipedia article is by an exact SEC CIK or by the same name plus a Wikidata "
              "employer or board seat that is an organization the person is on in the filings (precision judged on random samples, "
              "on /data#wikipedia). " + SOURCE,
              _people(), Column("value", "Highest pay", "money"),
              [Column("title", "Title"), Column("wiki_desc", "On Wikipedia"), Column("tax_year", "Year", "year")],
              ["The same name is not proof of the same person; each person page carries a \"Report a wrong match\" link."],
              unit="person", org_label="Organization", **{k: v for k, v in kw.items() if k != "org_label"}),
        Board("wikipedia-notable-boards", "Organizations with the most people who have a Wikipedia article", "Star Boards",
              "Nonprofits whose returns list two or more people who have a Wikipedia article, ranked by how many.",
              "Value = the number of distinct people on the organization's returns (any year) who are matched to a Wikipedia article. " + SOURCE,
              _notable_boards(), Column("value", "People with a Wikipedia article", "num"),
              [Column("names", "Who"), Column("revenue", "Latest revenue", "money"), Column("city", "City")],
              ["Large foundations and universities list many officers over the years, so older organizations rank higher."],
              unit="organization", org_label="Organization", **{k: v for k, v in kw.items() if k != "org_label"}),
        Board("wikipedia-big-nonprofits", "Nonprofits with a Wikipedia article, by revenue", "Written Up",
              "Nonprofits that have an English Wikipedia article, ranked by latest reported revenue.",
              "Value = total revenue on the organization's latest Form 990 return. An organization is shown when its IRS EIN is the "
              "one Wikidata records for the article, or by an exact website or name and headquarters city match (precision judged on "
              "random samples, on /data#wikipedia). " + SOURCE,
              _big_nonprofits(), Column("value", "Revenue", "money"),
              [Column("wiki_title", "Wikipedia article"), Column("wiki_desc", "Description"), Column("founded", "Founded", "year"),
               Column("assets", "Assets", "money"), Column("city", "City")],
              ["Wikipedia covers the best-known organizations; most nonprofits have no article."],
              unit="organization", org_label="Organization", **{k: v for k, v in kw.items() if k != "org_label"}),
    ]


ALTERNATIVES: dict = {}
ATTRIBUTION = ("Descriptions from Wikipedia, licensed CC BY-SA 4.0, linked to each article (its history lists the authors); "
               "facts from Wikidata, CC0.")
