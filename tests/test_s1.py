"""IPO registrations (loader/s1.py, app/ipos.py; owner, 2026-11-12): the index parsing, which filings count, the
company facts, the menu submenu, the pages, the API dataset and the MCP tool."""

import datetime as dt

from loader import s1

S1_LINE = "1019849|PENSKE AUTOMOTIVE GROUP, INC.|S-1|2010-01-21|edgar/data/1019849/0000950123-10-004077.txt\n"


def test_parse_line_keeps_only_the_forms_we_want():
    assert s1.parse_line(S1_LINE) == ("1019849", "PENSKE AUTOMOTIVE GROUP, INC.", "S-1", dt.date(2010, 1, 21), "0000950123-10-004077")
    assert s1.parse_line("CIK|Company Name|Form Type|Date Filed|Filename\n") is None
    assert s1.parse_line("860585|RBS PARTNERS L P /CT|13FCONP|1993-02-11|edgar/data/860585/9999999997-04-035713.txt\n") is None
    assert s1.parse_line("1019849|PENSKE|10-K|2010-01-21|edgar/data/1019849/0000950123-10-004078.txt\n") is None
    assert s1.parse_line("garbage\n") is None
    assert s1.parse_line("0000320193|APPLE|S-1/A|2010-01-21|edgar/data/320193/0000950123-10-004079.txt")[0] == "320193"   # CIK unpadded


def test_select_filings_windows_the_extra_forms_on_the_registration():
    d = dt.date
    rows = [("1", "Acme", "S-1", d(2020, 1, 10), "a1"), ("1", "Acme", "S-1/A", d(2020, 2, 1), "a2"),
            ("1", "Acme Inc", "S-1/A", d(2020, 3, 1), "a3"), ("1", "Acme", "EFFECT", d(2020, 3, 5), "a4"),
            ("1", "Acme", "424B4", d(2020, 3, 6), "a5"), ("1", "Acme", "424B4", d(2023, 6, 1), "a6"),   # a shelf, 3 years on
            ("1", "Acme", "424B1", d(2019, 1, 1), "a0"),                                                # before the S-1
            ("2", "Beta", "424B4", d(2020, 3, 6), "b1"),                                                # no S-1 at all
            ("3", "Gamma", "F-1", d(2021, 5, 5), "c1"), ("3", "Gamma", "RW", d(2021, 9, 9), "c2")]
    filings, summary = s1.select_filings(rows)
    assert [f[4] for f in filings] == ["a1", "a2", "a3", "a4", "a5", "c1", "c2"]
    acme = summary["1"]
    assert acme["kind"] == "S-1" and acme["index_name"] == "Acme Inc" and acme["n_reg"] == 1 and acme["n_amend"] == 2
    assert acme["first_filed"] == d(2020, 1, 10) and acme["last_filed"] == d(2020, 3, 1)
    assert acme["priced"] == d(2020, 3, 6) and acme["effect"] == d(2020, 3, 5) and acme["withdrawn"] is None
    assert acme["n_filings"] == 5
    assert "2" not in summary
    assert summary["3"]["kind"] == "F-1" and summary["3"]["withdrawn"] == d(2021, 9, 9) and summary["3"]["priced"] is None


def test_company_facts_from_a_submissions_json():
    sub = {"cik": "1018724", "name": "AMAZON COM INC", "sic": "5961", "sicDescription": "Retail-Catalog & Mail-Order Houses",
           "ein": "911646860", "stateOfIncorporation": "DE", "entityType": "operating", "tickers": ["AMZN"], "exchanges": ["Nasdaq"],
           "formerNames": [{"name": "AMAZON COM INC", "from": "1997-05-15T00:00:00.000Z", "to": "1998-01-01T00:00:00.000Z"}],
           "addresses": {"business": {"street1": "410 TERRY AVENUE NORTH", "street2": None, "city": "SEATTLE",
                                      "stateOrCountry": "WA", "zipCode": "98109"}}}
    f = s1.company_facts(sub)
    assert f["name"] == "AMAZON COM INC" and f["sic"] == "5961" and f["ein"] == "911646860" and f["state_inc"] == "DE"
    assert f["street"] == "410 TERRY AVENUE NORTH" and f["city"] == "SEATTLE" and f["state"] == "WA" and f["zip"] == "98109"
    assert f["tickers"] == "AMZN" and f["exchanges"] == "Nasdaq"
    assert f["former_names"] == [{"name": "AMAZON COM INC", "from": "1997-05-15", "to": "1998-01-01"}]
    assert s1.company_facts({"ein": "000000000", "addresses": {}})["ein"] is None


def test_quarters_and_paths():
    qs = s1.quarters(today=dt.date(1994, 5, 1))
    assert qs[0] == (1993, 1) and qs[-1] == (1994, 2) and len(qs) == 6
    assert s1.index_path(2024, 3).name == "2024QTR3.master.gz"


def test_cik_keys_and_paths():
    from app import ipos
    assert ipos.cik_of("1018724") == "1018724" and ipos.cik_of("amazon-com-inc-1018724") == "1018724"
    assert ipos.cik_of("0001018724") == "1018724" and ipos.cik_of("abc") is None and ipos.cik_of("") is None
    assert ipos.path("1018724", "Amazon com Inc") == "/ipos/amazon-com-inc-1018724" and ipos.path("0001018724", None) == "/ipos/1018724"


def test_menu_submenu_more_page_and_registry():
    base = open("templates/base.html").read()
    sec = base[base.index('nav-drop-head">Corporate and SEC'):base.index('nav-drop-head">Food safety')]
    assert '<a href="/ipos">IPO registrations (S-1, F-1)</a>' in sec
    for sub in ("/ipos/filings", "/ipos/by/year", "/ipos/by/state", "/ipos/by/industry"):
        assert f'class="nav-drop-sub" href="{sub}"' in sec
    from app import ipos, mcp, public_api
    if ipos.PUBLIC:
        assert "ipos" in {d["id"] for d in public_api.datasets()}
        assert "ipos" in mcp._DATASET_IDS
    assert ipos.FORMS["424B4"].startswith("424B4") and set(ipos.BY) == {"year", "state", "industry", "incorporation"}


def test_pages_and_api():
    from app import ipos
    if not ipos.PUBLIC:
        return
    from starlette.testclient import TestClient
    from app import db, main
    db.pool.open(wait=False)
    c = TestClient(main.app)
    hub = c.get("/ipos")
    if hub.status_code == 404:          # tables not loaded on this database
        return
    assert "<h1>IPO registrations (S-1, F-1)</h1>" in hub.text and 'href="/ipos/filings"' in hub.text
    assert '<body class="wide contained">' in hub.text and "Data: SEC EDGAR" in hub.text
    about = c.get("/about").text
    assert hub.text[hub.text.index("site-nav"):hub.text.index("</nav>")].count("<a ") == about[about.index("site-nav"):about.index("</nav>")].count("<a ")
    assert "<h1>IPO filings in 2021</h1>" in c.get("/ipos/filings?year=2021&form=S-1").text
    assert "<h1>IPO registrants" in c.get("/ipos/companies?q=holdings&state=DE").text
    for by in ipos.BY:
        assert f"<h1>IPO registrants {ipos.BY[by].lower()}</h1>" in c.get(f"/ipos/by/{by}").text
    assert c.get("/ipos/by/nope").status_code == 404
    assert c.get("/ipos/abc").status_code == 404
    assert c.get("/ipos/99999999999").status_code == 404
    with db.conn() as conn:
        row = conn.execute("SELECT cik, name FROM ipo_companies WHERE priced IS NOT NULL ORDER BY first_filed DESC LIMIT 1").fetchone()
    if row:
        page = c.get(ipos.path(row["cik"], row["name"]))
        assert page.status_code == 200 and row["name"] in page.text and "<h2>Filings" in page.text
        assert c.get(f"/ipos/{row['cik']}").status_code == 200
        more = c.get("/more").text
        assert '<a href="/ipos">' in more
        r = c.get("/api/v1/datasets/ipos?q=" + row["name"].split()[0])
        assert r.status_code == 200 and r.json()["dataset"] == "ipos"
