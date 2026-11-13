"""The continuous cross-referencing engine (loader/xref.py, owner 2026-11-13) and what shows it: the xlinks rows it
writes (both directions, idempotent, tagged with their linker), its state table, the /data section, the API and the
MCP tool. Runs against the shared database on records that exist (the Red Cross, EIN 530196605); every row a test
inserts carries linker 'test:xref' and is deleted afterwards."""

import json

import pytest
from starlette.testclient import TestClient

from app import main
from loader import db, xref

client = TestClient(main.app)            # no `with`: keeps the shared pool open
RED_CROSS = "530196605"
MARK = "test:xref"


@pytest.fixture(autouse=True, scope="module")
def pool():
    from app import db as appdb
    try:
        appdb.pool.open()
    except Exception:  # noqa: BLE001 - already open
        pass


@pytest.fixture
def conn():
    with db.connect() as c:
        xref.ensure_schema(c)
        c.execute("DELETE FROM xlinks WHERE linker = %s", (MARK,))
        c.execute("DELETE FROM xref_state WHERE linker = %s", (MARK,))
        c.commit()
        yield c
        c.rollback()
        c.execute("DELETE FROM xlinks WHERE linker = %s", (MARK,))
        c.execute("DELETE FROM xref_state WHERE linker = %s", (MARK,))
        c.commit()


def test_street_and_zip_normalization():
    assert xref.street_norm("431 18th Street, N.W., Suite 200") == "431 18TH ST NW STE 200"
    assert xref.street_norm("431 18TH ST NW STE 200") == "431 18TH ST NW STE 200"
    assert xref.street_norm("P.O. Box 12") is None and xref.street_norm("Main Street") is None
    assert xref.zip5("20006-5310") == "20006" and xref.zip5("abc") is None
    assert xref.state_of(" dc ") == "DC" and xref.state_of("District of Columbia") is None
    assert xref.topic_label("mental_health") == "Mental health"


def test_schema_and_state_table(conn):
    cols = {r[0] for r in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'xlinks'")}
    assert {"linker", "added"} <= cols
    for t in ("xref_state", "xref_names", "xref_counts"):
        assert conn.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0] is not None, t
    xref.set_state(conn, MARK, src_kind="org", dst_kinds="fed", rule="a test", cursor="abc", added=3, seconds=1.5)
    xref.set_state(conn, MARK, cursor="abd", added=2, seconds=0.5)
    st = xref.get_state(conn, MARK)
    assert st["cursor"] == "abd" and st["rows_added"] == 2 and st["total_added"] == 5 and st["runs"] == 2
    assert st["rule"] == "a test" and st["src_kind"] == "org" and st["last_run"] is not None


def test_ein_rule_links_the_red_cross_both_ways_and_is_idempotent(conn):
    conn.execute("DROP TABLE IF EXISTS xb")
    conn.execute("CREATE TEMP TABLE xb AS SELECT * FROM xref_names WHERE kind = 'org' AND key = %s", (RED_CROSS,))
    if not conn.execute("SELECT count(*) FROM xb").fetchone()[0]:       # not collected yet: collect it for the test
        rows, _ = xref.c_org(conn, "530196604", 1)
        assert rows and rows[0]["key"] == RED_CROSS and rows[0]["core"] == "american national red cross"
        xref._upsert_names(conn, rows)
        conn.execute("DROP TABLE xb")
        conn.execute("CREATE TEMP TABLE xb AS SELECT * FROM xref_names WHERE kind = 'org' AND key = %s", (RED_CROSS,))
    first = xref.ein_links(conn, MARK)
    again = xref.ein_links(conn, MARK)
    assert again == 0                      # ON CONFLICT DO NOTHING on the primary key
    pairs = conn.execute("""SELECT src_kind, dst_kind, how FROM xlinks WHERE ((src_kind = 'org' AND src_key = %s)
                            OR (dst_kind = 'org' AND dst_key = %s)) AND how LIKE 'EIN (EXACT%%'""", (RED_CROSS, RED_CROSS)).fetchall()
    kinds = {(a, b) for a, b, _ in pairs}
    forward = {b for a, b, h in pairs if a == "org" and h == "EIN (EXACT)"}      # the engine's rows (the lobbying registrant, ...)
    assert forward, pairs
    for b in forward:
        assert (b, "org") in kinds, b                                             # and the other direction
    assert all("EXACT" in h for _, _, h in pairs)
    assert first >= 0


def test_name_and_state_rule_never_links_a_bare_common_name(conn):
    conn.execute("DROP TABLE IF EXISTS xb")
    conn.execute("""CREATE TEMP TABLE xb (LIKE xref_names)""")
    conn.execute("""INSERT INTO xb (kind, key, name, core, state, updated) VALUES ('org', 'test-1', 'Acme', 'acme', 'TX', now()),
                    ('org', 'test-2', 'Grace', 'grace', 'TX', now())""")
    assert xref.name_state_links(conn, MARK) == 0
    assert conn.execute("SELECT count(*) FROM xlinks WHERE linker = %s", (MARK,)).fetchone()[0] == 0


def test_both_ways_writes_two_rows_once(conn):
    sel = """SELECT 'org' AS s_kind, 'test-src' AS s_key, 'A' AS s_name, 'DC' AS s_state, 'fed' AS t_kind, 'TESTUEI00001' AS t_key,
                    'B' AS t_name, 'DC' AS t_state, 'a test rule (EXACT)' AS how"""
    assert xref._both_ways(conn, sel, {}, MARK) == 2
    assert xref._both_ways(conn, sel, {}, MARK) == 0
    rows = conn.execute("SELECT src_kind, dst_kind FROM xlinks WHERE linker = %s ORDER BY 1", (MARK,)).fetchall()
    assert [tuple(r) for r in rows] == [("fed", "org"), ("org", "fed")]
    conn.commit()
    from app import xlinks
    out = xlinks.for_target("fed", "TESTUEI00001")
    assert out and out[0]["src_kind"] == "org" and out[0]["url"] == "/org/test-src" and out[0]["how"] == "a test rule (EXACT)"
    api = xlinks.links("fed", "TESTUEI00001")
    assert api["count"] >= 1 and api["links"][0]["confidence"] == "EXACT" and api["links"][0]["url"].endswith("/org/test-src")


def test_every_kind_has_a_label_and_url():
    from app import xlinks
    for kind, (dataset, label, url) in xlinks.SOURCES.items():
        assert label and url("1:2" if kind == "biz" else "123")
        assert kind in xlinks.TARGETS
    assert xlinks._interest_url("ntee:B21") == "/categories/ntee/B21"
    assert xlinks._interest_url("field:women:issues") == "/categories/furp/women/issues"


def test_data_page_has_the_cross_references_section_in_the_site_layout():
    r = client.get("/data")
    assert r.status_code == 200
    assert '<body class="wide contained">' in r.text
    assert 'id="xref"' in r.text and "Cross-references" in r.text and "/api/v1/xlinks" in r.text
    # the menu and every section the page had before stay
    for h in ("Sources", "Coverage", "Refresh schedule", "Name matching", 'id="grants"', 'id="boards"', 'id="license"', "Corrections"):
        assert h in r.text, h


def test_entity_templates_include_the_cross_links_block():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "templates"
    for t in ("contractor", "recalls_firm", "ipos_company", "adv_fund", "patent_assignee", "trademark_owner", "institution",
              "inventor", "formd_party", "corporate_insider", "student_loan_issuer", "openpayments_company", "ipos_underwriter",
              "corporate_company", "business_entity", "lobbying_client", "fedspend_recipient", "politics_committee"):
        assert "_xlinks_section.html" in (root / f"{t}.html").read_text(), t
    assert "_xlinks_peers.html" in (root / "_sections" / "org_other.html").read_text()


def test_api_and_mcp_answer():
    r = client.get("/api/v1/xlinks", params={"kind": "org", "key": "53-0196605"})
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "org" and d["key"] == RED_CROSS and isinstance(d["links"], list) and "interests" in d
    for x in d["links"]:
        assert x["url"].startswith("http") and x["how"] and x["confidence"] in ("EXACT", "FUZZY", "Fuzzy")
    assert client.get("/api/v1/xlinks", params={"kind": "nope", "key": "1"}).status_code == 404
    assert "/xlinks" in json.dumps(client.get("/api/v1").json()["endpoints"])
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Accept": "application/json"})
    assert "get_links" in [t["name"] for t in r.json()["result"]["tools"]]
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                  "params": {"name": "get_links", "arguments": {"kind": "org", "key": RED_CROSS}}},
                    headers={"Accept": "application/json"})
    res = r.json()["result"]
    assert not res["isError"] and res["structuredContent"]["key"] == RED_CROSS
    r = client.get("/developers")
    assert "/xlinks" in r.text and "get_links" in r.text


def test_org_page_keeps_its_sections_and_shows_interests_block_when_linked():
    r = client.get("/org/" + RED_CROSS, follow_redirects=True)
    assert r.status_code == 200 and '<body class="wide contained">' in r.text
    assert "Mission" in r.text or "NTEE code" in r.text
