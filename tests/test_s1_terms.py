"""IPO offering terms (loader/s1_terms.py, app/ipos.py underwriter pages, app/ipo_terms_boards.py; owner,
2026-11-13): the cover-page parser against saved excerpts, underwriter name normalisation, the menu entry, the
pages' layout and the boards' registration."""

from pathlib import Path

import pytest

from loader import s1_terms as t

FIX = Path(__file__).parent / "fixtures" / "s1"

EXPECTED = {
    "airbnb_424b4": {"is_ipo": True, "price": 68.0, "shares_offered": 51323531, "shares_company": 50000000, "shares_selling": 1323531,
                     "proceeds": 3490000108.0, "exchange": "Nasdaq", "ticker": "ABNB", "leads": ["Morgan Stanley", "Goldman Sachs"],
                     "first": ("Morgan Stanley", 17600478), "n_min": 30},
    "airbnb_s1a": {"is_ipo": True, "price": None, "price_low": 56.0, "price_high": 60.0, "shares_offered": 51551723, "shares_selling": 1551723,
                   "exchange": "Nasdaq", "ticker": "ABNB", "n_min": 30},
    "arm_424b4": {"is_ipo": True, "price": 51.0, "shares_offered": 95500000, "proceeds": 4870500000.0, "exchange": "Nasdaq", "ticker": "ARM",
                  "security": "ADS", "n_min": 20},
    "reddit_424b4": {"is_ipo": True, "price": 34.0, "shares_offered": 22000000, "shares_company": 15276527, "shares_selling": 6723473,
                     "proceeds": 748000000.0, "exchange": "NYSE", "ticker": "RDDT", "leads": ["Morgan Stanley", "Goldman Sachs", "J.P. Morgan"],
                     "first": ("Morgan Stanley", 7667000), "n_min": 15},
    "digital_island_424b1_1999": {"is_ipo": True, "price": 10.0, "shares_offered": 6000000, "proceeds": 60000000.0, "exchange": "Nasdaq",
                                  "ticker": "ISLD", "leads": ["Bear Stearns"], "n_min": 3},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_cover_pages_parse(name):
    r = t.parse_document((FIX / f"{name}.txt").read_text(), "424B4")
    want = EXPECTED[name]
    for k in ("is_ipo", "price", "price_low", "price_high", "shares_offered", "shares_company", "shares_selling", "proceeds",
              "exchange", "ticker", "security"):
        if k in want:
            assert r[k] == want[k], (name, k, r[k])
    if "leads" in want:
        assert r["leads"] == want["leads"], (name, r["leads"])
    names = [u["name"] for u in r["underwriters"]]
    assert len(names) >= want["n_min"] and len(names) == len(set(names)), (name, names)
    if "first" in want:
        assert (r["underwriters"][0]["name"], r["underwriters"][0]["shares"]) == want["first"]
    assert r["useful"] and r["note"]


def test_nothing_is_read_from_a_filing_without_a_cover():
    r = t.parse_document("As filed with the Securities and Exchange Commission.\nAmendment No. 3 to Form F-1\nEX-5.1 opinion only.", "F-1/A")
    assert not r["useful"] and r["price"] is None and r["underwriters"] == [] and r["note"] == "no terms found"


def test_price_is_not_taken_from_an_assumed_or_cornerstone_mention():
    text = ("Subject to Completion. It is currently estimated that the initial public offering price will be between $72.00 and "
            "$74.00 per share. Investors have indicated an interest in purchasing $5.0 billion of shares in this offering at the "
            "initial public offering price (including $200.0 million which Amazon has indicated). Based on an assumed initial "
            "public offering price of $73.00 per share, the midpoint of the price range.")
    r = t.parse_cover(text, "S-1/A")
    assert (r["price_low"], r["price_high"]) == (72.0, 74.0) and r["price"] is None


def test_range_without_a_trailing_per_share_and_a_us_dollar_price():
    r = t.parse_cover("Prospectus. The initial public offering price per ADS is estimated to be between $47.00 and $51.00. "
                      "Our ADSs will be listed on the Nasdaq Global Select Market under the symbol “ARM”.", "F-1/A")
    assert (r["price_low"], r["price_high"], r["exchange"], r["ticker"]) == (47.0, 51.0, "Nasdaq", "ARM")
    r = t.parse_cover("Prospectus. 320,106,100 American Depositary Shares. The initial public offering price of the ADSs is US$68.00 per ADS.", "424B4")
    assert r["price"] == 68.0 and r["shares_offered"] == 320106100 and r["proceeds"] == 68.0 * 320106100


def test_underwriter_names_are_normalised():
    assert t.name_key("Goldman Sachs & Co. LLC") == t.name_key("GOLDMAN, SACHS & CO.") == t.name_key("Goldman Sachs") == "goldman sachs"
    assert t.canonical("J.P. MORGAN SECURITIES LLC") == t.canonical("JPMorgan") == "J.P. Morgan"
    assert t.canonical("Merrill Lynch, Pierce, Fenner & Smith Incorporated") == "Merrill Lynch"
    assert t.canonical("BofA Securities, Inc.") == t.canonical("Banc of America Securities LLC") == "BofA Securities"
    assert t.name_key("Feltl and Company, Inc.") == t.name_key("FELTL & CO") and t.canonical("FELTL AND COMPANY, INC.") == "Feltl and Company, Inc"
    assert t.known_names_in("Morgan Stanley Goldman Sachs & Co. LLC") == ["Morgan Stanley", "Goldman Sachs"]
    assert t.known_names_in("Barclays | | Goldman Sachs & Co. LLC | | J.P. Morgan | | Mizuho") == ["Barclays", "Goldman Sachs", "J.P. Morgan", "Mizuho"]
    assert t.name_key("Lehman Brothers Inc.") == "lehman brothers" and t.canonical("LEHMAN BROTHERS") == "Lehman Brothers"


def test_underwriting_table_rows():
    text = ("Underwriting\nUnder the terms and subject to the conditions in an underwriting agreement, the underwriters named below, for whom "
            "Morgan Stanley & Co. LLC and Goldman Sachs & Co. LLC are acting as representatives, have severally agreed to purchase:\n"
            " Name | | Number of Shares | \n Morgan Stanley & Co. LLC | | 7,667,000 | \n Goldman Sachs & Co. LLC | | 4,136,000 | \n"
            " Deutsche Bank Securities Inc. \n | | 550,000 | \n Samuel A. Ramirez & Company, Inc. | | 44,000 | \n Total: | | 22,000,000 | \n")
    rows = t.underwriting_table(text)
    assert rows == [("Morgan Stanley", 7667000), ("Goldman Sachs", 4136000), ("Deutsche Bank", 550000), ("Ramirez & Co.", 44000)]
    assert t.representatives(text, rows) == ["Morgan Stanley", "Goldman Sachs"]
    plain = ("UNDERWRITING\n   The underwriters named below have severally agreed to purchase\n"
             "           Underwriters                                    Number of Shares\n"
             "   Bear, Stearns & Co. Inc. ...............................   2,400,000\n"
             "   Lehman Brothers Inc. ...................................   1,800,000\n"
             "                                                             ---------\n     Total ..........................   6,000,000\n")
    assert t.underwriting_table(plain) == [("Bear Stearns", 2400000), ("Lehman Brothers", 1800000)]


def test_paths_menu_and_boards():
    from app import ipos
    assert ipos.uw_path("goldman sachs") == "/ipos/underwriters/goldman-sachs" and ipos.uw_key("goldman-sachs") == "goldman sachs"
    assert ipos.uw_key("Nope!") is None
    base = open("templates/base.html").read()
    sec = base[base.index('nav-drop-head">Corporate and SEC'):base.index('nav-drop-head">Food safety')]
    assert 'class="nav-drop-sub" href="/ipos/underwriters"' in sec
    from app import boards, ipo_terms_boards
    slugs = {b.slug for b in ipo_terms_boards.ipo_terms_boards()}
    if not ipos.PUBLIC:
        assert slugs == set()
        return
    assert slugs == {"ipo-biggest", "ipo-priced-below-range", "ipo-priced-above-range", "ipo-busiest-underwriters"} == set(ipo_terms_boards.ALTERNATIVES)
    assert slugs <= {b.slug for b in boards.visible()} and "ipo-terms" in boards.GROUPS
    assert {b.slug for b in boards.group_members("ipo-terms")} == slugs
    for b in boards.group_members("ipo-terms"):
        assert b.per_org and not b.forms and b.search and b.formula.startswith("Value = ") and "subject_url" in b.sql and "org_pos" in b.sql
        assert b.subtitle == ipo_terms_boards.ALTERNATIVES[b.slug][0]


def test_pages():
    from app import ipos
    if not ipos.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    page = c.get("/ipos/underwriters")
    if page.status_code == 404:          # tables not loaded on this database
        return
    assert "<h1>IPO underwriters</h1>" in page.text and '<body class="wide contained">' in page.text
    about = c.get("/about").text
    nav = lambda h: h[h.index("site-nav"):h.index("</nav>")].count("<a ")  # noqa: E731
    assert nav(page.text) == nav(about)
    assert c.get("/ipos/underwriters/nope-xyz-123").status_code == 404
    assert c.get("/ipos/underwriters?year=1800").status_code == 200
    with db.conn() as conn:
        uw = conn.execute("SELECT name_key, name FROM ipo_underwriters WHERE deals > 0 ORDER BY deals DESC LIMIT 1").fetchone() \
            if conn.execute("SELECT to_regclass('ipo_underwriters') AS t").fetchone()["t"] else None
        co = conn.execute("SELECT cik, name FROM ipo_companies WHERE offer_price IS NOT NULL AND lead_underwriters IS NOT NULL ORDER BY offer_proceeds DESC NULLS LAST LIMIT 1").fetchone()
    if uw:
        p = c.get(ipos.uw_path(uw["name_key"]))
        assert p.status_code == 200 and uw["name"] in p.text and '<body class="wide contained">' in p.text and nav(p.text) == nav(about)
        assert "<h2>Deals" in p.text
        assert c.get(f"/ipos/underwriters?year={co and co['cik'] and 2020}").status_code == 200
    if co:
        p = c.get(ipos.path(co["cik"], co["name"]))
        assert p.status_code == 200 and "<h2>Offering terms</h2>" in p.text and "/ipos/underwriters/" in p.text
        assert "<h2>Filings" in p.text and "<h2>Prospectus pages read" in p.text
    hub = c.get("/ipos").text
    assert 'href="/ipos/underwriters"' in hub
