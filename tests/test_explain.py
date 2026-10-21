"""Explain what I am seeing (app/explain.py): the button only on data pages; the data sent is compact; URLs checked."""

from starlette.testclient import TestClient

from app import explain, main

client = TestClient(main.app)


def test_button_only_on_data_pages():
    assert "explain-btn" not in client.get("/about").text and "explain-btn" not in client.get("/").text


def test_bad_urls_are_refused():
    assert client.get("/explain?u=https://evil.example/").status_code == 400
    assert client.get("/explain?u=/about").status_code == 400


def test_compact_shortens_lists_and_drops_internal_fields():
    c = explain.compact({"rows": [{"name": f"Org {i}", "name_norm": "x", "value": i} for i in range(100)]})
    assert len(c["rows"]) == explain.MAX_LIST + 1 and c["rows"][-1].startswith("... and")
    assert "name_norm" not in c["rows"][0]
