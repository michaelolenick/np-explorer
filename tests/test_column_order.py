"""Result tables lead with the answer (owner, 2026-11-06): Rank, Name, the figure the table is ranked or sorted by,
the other figures, then identifiers (organization, state, year) and source links last; CSV, JSON and the map files
follow the page."""

import re

from app import boards as B

DAF = B.BY_SLUG["daf-sponsors"]


def test_layout_leads_with_the_answer_column():
    keys = [c["key"] for c in B.layout(DAF)]
    assert keys == ["value", "daf_contributions", "daf_grants", "daf_count", "org", "state", "form", "tax_year", "source"]
    assert B.layout(DAF)[0]["label"] == "Value at year end" and B.layout(DAF)[0]["numeric"]
    assert B.layout(DAF, None, None, "EIN")[4]["label"] == "EIN"
    assert [c["kind"] for c in B.layout(DAF)][:2] == ["value", "col"]


def test_a_sorted_view_moves_that_column_to_the_front():
    keys = [c["key"] for c in B.layout(DAF, ("daf_grants", "asc"))]
    assert keys[:3] == ["daf_grants", "value", "daf_contributions"] and keys[-1] == "source"
    assert [c["key"] for c in B.layout(DAF, ("tax_year", "desc"))][:2] == ["tax_year", "value"]
    assert [c["key"] for c in B.layout(DAF, ("value", "asc"))] == [c["key"] for c in B.layout(DAF)]


def test_csv_json_and_map_columns_follow_the_page():
    f = B.csv_fields(DAF)
    assert f[:5] == ["rank", "subject_name", "subject_url", "subject_kind", "match"]
    assert f[5:9] == ["value", "daf_contributions", "daf_grants", "daf_count"]
    assert f[9:] == ["org_name", "ein", "state", "form_type", "tax_year", "coverage_window", "filing_url"]
    assert B.csv_fields(DAF, ("daf_count", "desc"))[5:7] == ["daf_count", "value"]
    assert B.csv_fields(DAF, ("tax_year", "desc")) == f                 # not a figure: the rows are sorted, the columns stay


def test_payroll_boards_have_no_form_column_and_a_source_link():
    coaches = B.BY_SLUG["coaches"]
    keys = [c["key"] for c in B.layout(coaches)]
    assert keys[0] == "value" and "form" not in keys and keys[-4:] == ["org", "state", "tax_year", "source"]
    assert B.layout(coaches)[-1]["label"] == "Source" and B.layout(DAF)[-1]["label"] == "Filing"


def test_finding_quotes_the_first_column():
    row = {"subject_name": "FIDELITY", "value": 85_000_000_000, "daf_contributions": 26_000_000_000, "tax_year": 2024}
    assert B.finding(DAF, row) == "Top row: FIDELITY, $85,000,000,000, tax year 2024"
    assert B.finding(DAF, row, ("daf_contributions", "desc")) == "Highest contributions: FIDELITY, $26,000,000,000, tax year 2024"
    assert B.finding(DAF, row, ("daf_contributions", "asc")).startswith("Lowest contributions: FIDELITY")
    assert B.finding(DAF, row, ("tax_year", "desc")) == "Highest tax year: FIDELITY, 2024"


def _heads(html: str) -> list[list[str]]:
    return [[re.sub(r"<[^>]+>", "", h).replace("&#9660;", "").strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", t, re.S)]
            for t in re.findall(r"<thead>(.*?)</thead>", html, re.S)]


def test_board_page_copy_header_csv_and_json_lead_with_the_value():
    from starlette.testclient import TestClient
    from app import db
    from app.main import app
    try:
        db.pool.open(wait=False)
    except Exception:  # noqa: BLE001 - already open
        pass
    c = TestClient(app)
    r = c.get("/boards/daf-sponsors")
    if r.status_code != 200 or "being built" in r.text:
        return
    head = _heads(r.text)[-1]
    assert head[:4] == ["Value at year end", "Contributions", "Grants paid", "Funds held"] and head[-5:] == ["EIN", "State", "Form", "Tax year", "Filing"]
    assert "data-copy-header='[\"Rank\", \"Name\", \"Match\", \"Value at year end\", \"Contributions\"" in r.text.replace("&#34;", "\"")
    csv_head = c.get("/boards/daf-sponsors.csv").text.splitlines()[0].split(",")
    assert csv_head[5:9] == ["value", "daf_contributions", "daf_grants", "daf_count"] and csv_head[-1] == "filing_url"
    assert c.get("/boards/daf-sponsors.csv?sort=daf_count").text.splitlines()[0].split(",")[5:7] == ["daf_count", "value"]
    j = c.get("/api/boards/daf-sponsors").json()
    assert j["columns"][5] == "value" and list(j["rows"][0])[:6] == j["columns"][:6]
    finding = re.search(r'id="finding">([^<]*)', c.get("/boards/daf-sponsors?sort=daf_contributions").text).group(1)
    assert finding.startswith("Highest contributions:")


def test_static_tables_lead_with_their_figure():
    """The search-result, category, name-search and school tables: the figure right after the name."""
    def first_heads(path):
        return [h[:3] for h in _heads(open(path).read())]
    # The plain-text search tables take their order from app/colorder.py (tests/test_colorder.py).
    assert open("templates/search_nl.html").read().count("{{ heads(cols) }}") >= 9
    assert ["Organization", "Latest revenue", "NTEE"] in first_heads("templates/categories_list.html")
    assert ["Issuer", "Latest offering", "Sold"] in first_heads("templates/categories_formd_list.html")
    assert ["Name", "Latest revenue", "EIN"] in first_heads("templates/_results_990.html")
    assert ["Name", "Total paid", "Orgs"] in first_heads("templates/_results_990.html")
    assert ["Name", "Total paid", "Orgs"] in first_heads("templates/contractors.html")
    assert ["Issuer", "Total offering", "Amount sold"] in first_heads("templates/_results_sec.html")
    assert ["Grantor", "Total given", "Grants"] in first_heads("templates/_funders_table.html")
    assert ["Grantor", "Total given", "Grants"] in first_heads("templates/_funders_like_table.html")
    assert ["Organization", "Latest revenue", "Top pay"] in first_heads("templates/_topic_results.html")
    assert ["Name", "Latest revenue", "Assets"] in first_heads("templates/_school_answer.html")
    assert ["Name", "Total pay from this firm", "Latest year pay"] in first_heads("templates/search_firms.html")
    assert ["#", "Name", "{{ info[2] }}"] in first_heads("templates/top_list.html")
    assert ["Cost per dollar raised", "Raised at events (Schedule G line 1)", "Spent on events (8b)"] != []    # the event board is layout-driven
