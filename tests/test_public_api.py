"""FURP for AI assistants (owner, 2026-10-27): llms.txt, JSON-LD, one URL per entity, the /api/v1 JSON API and the
MCP server at /mcp. Runs against the shared database, like the other page tests."""

import json
import re

import pytest
from starlette.testclient import TestClient

from app import main, mcp, public_api, seo, slugs

client = TestClient(main.app)            # no `with`: keeps the shared pool open
RED_CROSS = "530196605"


@pytest.fixture(autouse=True, scope="module")
def pool():
    from app import db
    try:
        db.pool.open()
    except Exception:  # noqa: BLE001 - already open
        pass


def _ld(html: str) -> list[dict]:
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def test_llms_txt_lists_every_dataset_and_how_to_link():
    r = client.get("/llms.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    t = r.text
    assert t.startswith("# FURP\n\n> ") and "context window" in t          # what FURP does for language models
    for d in public_api.datasets():
        assert d["name"] in t
    assert "/org/{name-slug}-{ein}" in t and "/mcp" in t and "/api/v1" in t
    assert "/ask?q=" not in t                     # never send assistants to the pages that call a language model
    full = client.get("/llms-full.txt").text
    assert len(full) > len(t) and "Notes for assistants" in full


def test_home_page_has_website_with_a_name_search_action():
    graph = _ld(client.get("/").text)[0]["@graph"]
    site = next(x for x in graph if x["@type"] == "WebSite")
    assert site["potentialAction"]["target"]["urlTemplate"].endswith("/search?type=name&q={search_term_string}")
    assert any(x["@type"] == "Organization" for x in graph)


def test_org_page_json_ld_has_identifiers():
    r = client.get(f"/org/{RED_CROSS}", follow_redirects=True)
    ld = _ld(r.text)[0]
    assert ld["@type"] == "NGO" and ld["taxID"] == "53-0196605" and ld["@id"] == ld["url"]
    assert {"@type": "PropertyValue", "propertyID": "EIN", "value": "53-0196605"} in ld["identifier"]
    assert any("propublica.org" in x for x in ld["sameAs"])
    assert all(v is not None for v in (ld.get("address") or {}).values())


def test_entity_ld_identifiers_and_same_as():
    d = seo.ld("Corporation", "JPMORGAN CHASE & CO", "/corporate/company/jpmorgan-chase-and-co-19617", cik="0000019617")
    assert d["identifier"] == [{"@type": "PropertyValue", "propertyID": "SEC CIK", "value": "19617"}]
    assert d["sameAs"] == ["https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000019617"]
    d = seo.ld("Organization", "Acme", "/business/VA/1", registry=("VA", "S1"), address={"addressLocality": None})
    assert d["identifier"][0]["propertyID"] == "VA business entity ID" and "address" not in d


def test_one_url_per_org():
    assert slugs.parse("org", "53-0196605") == RED_CROSS                  # the EIN as the IRS writes it
    r = client.get("/org/53-0196605", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].endswith(f"-{RED_CROSS}")
    r = client.get(f"/org/{RED_CROSS}/", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == f"/org/{RED_CROSS}"     # permanent, not 307


def test_api_index_datasets_and_search():
    idx = client.get("/api/v1").json()
    assert idx["mcp_server"].endswith("/mcp") and "context window" in idx["for_ai_assistants"]
    ids = {d["id"] for d in client.get("/api/v1/datasets").json()["datasets"]}
    assert {"nonprofits", "people", "patents", "business-registries"} <= ids
    r = client.get("/api/v1/search?q=american+national+red+cross&type=organizations").json()
    org = next(o for o in r["organizations"] if o["ein"] == RED_CROSS)
    assert org["url"] == f"{public_api.SITE_URL}/org/american-national-red-cross-{RED_CROSS}"
    assert client.get("/api/v1/search?q=a").status_code == 400
    assert client.get("/api/v1/datasets/federal-spending?q=acme").status_code == 400     # profiles only
    assert client.get("/api/v1/datasets/nope?q=acme").status_code == 404


def test_api_org_and_person_profiles_carry_canonical_urls():
    o = client.get("/api/v1/organizations/53-0196605").json()
    assert o["ein"] == "53-0196605" and o["url"].endswith(f"-{RED_CROSS}") and o["filings"]
    people = o["people_latest_year"]["people"]
    assert people and all(p["person_url"].startswith(public_api.SITE_URL + "/person/") for p in people if p.get("cluster_id"))
    assert client.get(o["url"].replace(public_api.SITE_URL, "/api/v1/organizations")).json()["ein"] == "53-0196605"
    pid = people[0]["cluster_id"]
    p = client.get(f"/api/v1/people/{pid}").json()
    assert p["url"] == public_api.SITE_URL + slugs.canonical("person", pid, p["name"])
    assert any(r["ein"] == RED_CROSS for r in p["nonprofit_roles"]) and "license" in p
    assert client.get("/api/v1/people/999999999999").status_code == 404


def _rpc(method, params=None, i=1):
    body = {"jsonrpc": "2.0", "method": method, **({"id": i} if i is not None else {}), **({"params": params} if params else {})}
    return client.post("/mcp", json=body, headers={"Accept": "application/json, text/event-stream"})


def test_mcp_handshake_and_tools():
    r = _rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    res = r.json()["result"]
    assert res["protocolVersion"] == "2025-06-18" and res["serverInfo"]["name"] == "furp" and "context window" in res["instructions"]
    assert _rpc("initialize", {"protocolVersion": "1999-01-01"}).json()["result"]["protocolVersion"] == mcp.VERSIONS[0]
    assert _rpc("notifications/initialized", i=None).status_code == 202
    tools = {t["name"]: t for t in _rpc("tools/list").json()["result"]["tools"]}
    assert {"search", "get_person", "get_organization", "list_datasets", "search_dataset"} <= set(tools)
    assert all(t["annotations"]["readOnlyHint"] for t in tools.values())
    res = _rpc("tools/call", {"name": "get_organization", "arguments": {"organization": "53-0196605"}}).json()["result"]
    assert not res["isError"] and res["structuredContent"]["url"].endswith(f"-{RED_CROSS}")
    assert json.loads(res["content"][0]["text"])["ein"] == "53-0196605"
    bad = _rpc("tools/call", {"name": "get_person", "arguments": {"person": "nobody"}}).json()["result"]
    assert bad["isError"]
    assert _rpc("nope").json()["error"]["code"] == -32601
    assert client.get("/mcp").status_code == 405


def test_developers_page_uses_the_site_layout():
    r = client.get("/developers")
    assert r.status_code == 200 and "/mcp" in r.text and 'class="wide contained"' in r.text
    assert '<link rel="canonical" href="https://furp.org/developers">' in r.text or "/developers\">" in r.text
